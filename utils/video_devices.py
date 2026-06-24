"""Helpers for discovering usable V4L2 camera devices on Linux."""
from __future__ import annotations

import ctypes
import fcntl
import glob
import os
import time
from typing import List, Optional, Tuple


VIDIOC_QUERYCAP = 0x80685600
V4L2_CAP_VIDEO_CAPTURE = 0x00000001
V4L2_CAP_VIDEO_CAPTURE_MPLANE = 0x00001000
V4L2_CAP_META_CAPTURE = 0x00800000


class _V4L2Capability(ctypes.Structure):
    _fields_ = [
        ("driver", ctypes.c_ubyte * 16),
        ("card", ctypes.c_ubyte * 32),
        ("bus_info", ctypes.c_ubyte * 32),
        ("version", ctypes.c_uint32),
        ("capabilities", ctypes.c_uint32),
        ("device_caps", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32 * 3),
    ]


def _device_index_from_path(device_path: str) -> Optional[int]:
    base_name = os.path.basename(device_path)
    if not base_name.startswith("video"):
        return None
    try:
        return int(base_name[5:])
    except ValueError:
        return None


def _decode_c_string(raw_field) -> str:
    return bytes(raw_field).split(b"\0", 1)[0].decode("utf-8", errors="ignore")


def _query_capabilities(device_path: str) -> Optional[Tuple[str, int, int]]:
    # 캡처 노드(video0, video2, ...)가 일시적으로 점유된 경우 즉시 None을 반환하면
    # discover가 보조 노드(video1, video3, ...)를 대신 선택할 수 있다.
    # 재시도로 일시적 접근 실패를 극복한다.
    for attempt in range(3):
        try:
            fd = os.open(device_path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        except OSError:
            if attempt < 2:
                time.sleep(0.05)
                continue
            return None

        try:
            buffer = ctypes.create_string_buffer(ctypes.sizeof(_V4L2Capability))
            fcntl.ioctl(fd, VIDIOC_QUERYCAP, buffer, True)
            capability = _V4L2Capability.from_buffer_copy(buffer.raw)
            card_name = _decode_c_string(capability.card)
            return card_name, int(capability.capabilities), int(capability.device_caps)
        except OSError:
            if attempt < 2:
                time.sleep(0.05)
            continue
        finally:
            os.close(fd)

    return None


def _is_video_capture_device(card_name: str, capabilities: int, device_caps: int) -> bool:
    caps = device_caps or capabilities
    if caps & V4L2_CAP_META_CAPTURE:
        return False
    if not (caps & (V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_VIDEO_CAPTURE_MPLANE)):
        return False

    lowered_name = card_name.lower()
    if any(token in lowered_name for token in ("metadata", "embedded", "stats")):
        return False

    return True


def discover_video_capture_indices() -> List[int]:
    """Return /dev/video* indices that look like actual capture devices."""
    device_paths = sorted(
        glob.glob("/dev/video*"),
        key=lambda path: (_device_index_from_path(path) if _device_index_from_path(path) is not None else 10_000),
    )

    camera_indices: List[int] = []
    for device_path in device_paths:
        device_index = _device_index_from_path(device_path)
        if device_index is None:
            continue

        cap_info = _query_capabilities(device_path)
        if cap_info is None:
            continue

        card_name, capabilities, device_caps = cap_info
        if not _is_video_capture_device(card_name, capabilities, device_caps):
            continue

        camera_indices.append(device_index)

    return camera_indices
