"""
카메라 초기화 및 캡처 기능
"""
from __future__ import annotations

import cv2
import time
import threading
import platform
import re
import shutil
import subprocess
from typing import List, Optional, Tuple
from config.settings import (
    CAMERA_INDICES, CAMERA_MAX_RETRIES, CAMERA_RETRY_DELAY,
    CAMERA_CAPTURE_CONFIGS,
    CAMERA_DEFAULT_WIDTH, CAMERA_DEFAULT_HEIGHT,
    CAMERA_DEFAULT_FPS, CAMERA_DEFAULT_FOURCC,
    CAMERA_OUTPUT_WIDTH, CAMERA_OUTPUT_HEIGHT,
    CAMERA_RECONNECT_COOLDOWN_SEC, CAMERA_RECONNECT_MAX_RETRIES,
    CAMERA_RESET_CONTROLS_TO_DEFAULT, CAMERA_DISABLE_AUTOFOCUS,
    CAMERA_AUTOFOCUS_CONTROL_NAMES,
)
from errors.enums import CameraError
from utils.logger import get_logger, EventType

logger = get_logger("hardware.camera")

# OS 감지
IS_WINDOWS = platform.system() == "Windows"
IS_JETSON = platform.system() == "Linux" and platform.machine() in ["aarch64", "arm64"]


def diagnose_camera_error(camera_index: int) -> CameraError:
    """
    카메라 연결 실패 시 에러 타입을 진단합니다.
    """
    # 1. 기본 테스트 - 요청한 카메라가 열리는지 확인
    test_cap = cv2.VideoCapture(camera_index)
    if test_cap.isOpened():
        test_cap.release()
        return CameraError.OK
    test_cap.release()
    
    # 2. 다른 백엔드로 시도
    if IS_WINDOWS:
        # Windows용: CAP_DSHOW 대신 CAP_MSMF 등
        backends = [cv2.CAP_MSMF, cv2.CAP_ANY]
    else:
        # Jetson용 (Linux): CAP_V4L2, CAP_GSTREAMER 등
        backends = [cv2.CAP_V4L2, cv2.CAP_GSTREAMER, cv2.CAP_ANY]
    
    for backend in backends:
        test_cap = cv2.VideoCapture(camera_index, backend)
        if test_cap.isOpened():
            test_cap.release()
            return CameraError.BACKEND_ERROR
        test_cap.release()
    
    # 3. 시스템에 카메라가 전혀 없는지 확인 (여러 인덱스 시도)
    any_camera_found = False
    candidate_indices = CAMERA_INDICES if CAMERA_INDICES else list(range(8))
    for idx in candidate_indices:
        test_cap = cv2.VideoCapture(idx)
        if test_cap.isOpened():
            any_camera_found = True
            test_cap.release()
            break
        test_cap.release()
    
    # 다른 카메라는 있지만 요청한 인덱스의 카메라가 없는 경우
    if any_camera_found:
        if camera_index in candidate_indices:
            return CameraError.DEVICE_BUSY
        return CameraError.DEVICE_NOT_FOUND
    
    # 시스템에 카메라가 전혀 없는 경우
    if not any_camera_found:
        return CameraError.DEVICE_NOT_FOUND
    
    # 4. 그 외의 경우 (장치 사용 중 또는 권한 문제)
    return CameraError.DEVICE_BUSY


def _open_cap(
    camera_index: int,
    setup_format: bool = True,
    width: int = CAMERA_DEFAULT_WIDTH,
    height: int = CAMERA_DEFAULT_HEIGHT,
    fps: float = CAMERA_DEFAULT_FPS,
    fourcc: str = CAMERA_DEFAULT_FOURCC,
) -> cv2.VideoCapture:
    """OS에 맞는 백엔드로 VideoCapture를 생성한다."""
    if setup_format and not IS_WINDOWS:
        _apply_v4l2_camera_controls(camera_index)

    if IS_WINDOWS:
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)

    _disable_opencv_autofocus(cap)

    if setup_format:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

    warmup_tries = 50 if setup_format else 20
    if cap.isOpened():
        for _ in range(warmup_tries):
            if cap.read()[0]:
                break
            time.sleep(0.05)

    return cap


def _run_v4l2_ctl(camera_index: int, args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["v4l2-ctl", "-d", f"/dev/video{camera_index}"] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _parse_v4l2_default_controls(output: str) -> dict:
    controls = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        name = line.split()[0]
        ctrl_type_match = re.search(r"\(([^)]+)\)", line)
        if ctrl_type_match and ctrl_type_match.group(1) in {"button", "ctrl-class"}:
            continue
        flags_match = re.search(r"flags=([^\s]+)", line)
        flags = flags_match.group(1).split(",") if flags_match else []
        if "read-only" in flags or "inactive" in flags:
            continue
        default_match = re.search(r"default=(-?\d+)", line)
        if default_match is None:
            continue
        controls[name] = int(default_match.group(1))
    return controls


def _set_v4l2_control(camera_index: int, name: str, value: int) -> bool:
    result = _run_v4l2_ctl(camera_index, ["--set-ctrl", f"{name}={value}"])
    if result.returncode != 0:
        logger.event_warning(
            EventType.CAMERA_ERROR,
            "카메라 V4L2 컨트롤 적용 실패",
            {
                "camera_index": camera_index,
                "control": name,
                "value": value,
                "stderr": result.stderr.strip(),
            },
        )
        return False
    return True


def _reset_v4l2_controls_to_default(camera_index: int) -> None:
    if shutil.which("v4l2-ctl") is None:
        logger.event_warning(
            EventType.CAMERA_ERROR,
            "v4l2-ctl 없음 - 카메라 컨트롤 기본값 초기화 건너뜀",
            {"camera_index": camera_index},
        )
        return

    result = _run_v4l2_ctl(camera_index, ["--list-ctrls"])
    if result.returncode != 0:
        logger.event_warning(
            EventType.CAMERA_ERROR,
            "카메라 V4L2 컨트롤 조회 실패",
            {"camera_index": camera_index, "stderr": result.stderr.strip()},
        )
        return

    controls = _parse_v4l2_default_controls(result.stdout)
    applied = 0
    for name, default_value in controls.items():
        if _set_v4l2_control(camera_index, name, default_value):
            applied += 1

    logger.event_info(
        EventType.MODULE_INIT,
        "카메라 V4L2 컨트롤 기본값 초기화 완료",
        {
            "camera_index": camera_index,
            "controls_found": len(controls),
            "controls_applied": applied,
        },
    )


def _disable_autofocus_controls(camera_index: int) -> None:
    if shutil.which("v4l2-ctl") is None:
        return

    disabled = []
    for name in CAMERA_AUTOFOCUS_CONTROL_NAMES:
        result = _run_v4l2_ctl(camera_index, ["--set-ctrl", f"{name}=0"])
        if result.returncode == 0:
            disabled.append(name)

    if disabled:
        logger.event_info(
            EventType.MODULE_INIT,
            "카메라 자동초점 비활성화",
            {"camera_index": camera_index, "controls": disabled},
        )
    else:
        logger.event_info(
            EventType.MODULE_INIT,
            "자동초점 컨트롤 없음 - 비활성화 적용 안 함",
            {"camera_index": camera_index},
        )


def _disable_opencv_autofocus(cap: cv2.VideoCapture) -> None:
    if not cap.isOpened():
        return

    if CAMERA_DISABLE_AUTOFOCUS and hasattr(cv2, "CAP_PROP_AUTOFOCUS"):
        try:
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        except Exception:
            pass


def _apply_v4l2_camera_controls(camera_index: int) -> None:
    # 장치를 열 때마다 기본값 복원 및 자동초점 비활성화를 다시 적용한다.
    if CAMERA_RESET_CONTROLS_TO_DEFAULT:
        _reset_v4l2_controls_to_default(camera_index)
    if CAMERA_DISABLE_AUTOFOCUS:
        _disable_autofocus_controls(camera_index)


def open_camera_with_retry(
    camera_index: int,
    max_retries: int = 10,
    retry_delay: float = 5.0,
    width: int = CAMERA_DEFAULT_WIDTH,
    height: int = CAMERA_DEFAULT_HEIGHT,
    fps: float = CAMERA_DEFAULT_FPS,
    fourcc: str = CAMERA_DEFAULT_FOURCC,
) -> Optional[cv2.VideoCapture]:
    """
    카메라를 열고, 실패 시 재시도합니다.

    Args:
        camera_index: 카메라 인덱스
        max_retries: 최대 재시도 횟수
        retry_delay: 재시도 간 대기 시간 (초)

    Returns:
        성공 시 VideoCapture 객체, 실패 시 None
    """
    error_messages = {
        CameraError.DEVICE_NOT_FOUND: "카메라 장치를 찾을 수 없습니다.",
        CameraError.DEVICE_BUSY: "카메라가 다른 프로그램에서 사용 중입니다.",
        CameraError.PERMISSION_DENIED: "카메라 접근 권한이 거부되었습니다.",
        CameraError.BACKEND_ERROR: "카메라 백엔드 오류가 발생했습니다.",
        CameraError.UNKNOWN: "알 수 없는 카메라 오류가 발생했습니다.",
    }

    cap = _open_cap(camera_index, width=width, height=height, fps=fps, fourcc=fourcc)

    retry_count = 0
    while not cap.isOpened() and retry_count < max_retries:
        error_type = diagnose_camera_error(camera_index)
        error_msg = error_messages.get(error_type, "알 수 없는 오류")

        retry_count += 1

        print(f"[에러 유형: {error_type.name}] {error_msg}")
        print(f"카메라 연결 재시도 중... ({retry_count}/{max_retries})")

        time.sleep(retry_delay)
        cap.release()
        cap = _open_cap(camera_index, width=width, height=height, fps=fps, fourcc=fourcc)

    if not cap.isOpened():
        print(f"\n카메라를 열 수 없습니다. {max_retries}번 시도 후 실패했습니다.")
        cap.release()
        return None
    print("카메라 연결 성공!")
    return cap


class CameraCapture:
    """카메라 캡처를 담당하는 클래스"""
    
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        self.cap_lock = threading.Lock()
        self._reconnect_lock = threading.Lock()
        self._reconnect_cooldown_until: float = 0.0
        self.reconnect_attempts: int = 0
        self.last_reconnect_result: str = "not_attempted"
        self.last_reconnect_ts: float = 0.0
        cfg = CAMERA_CAPTURE_CONFIGS.get(camera_index, {})
        self._cap_width  = cfg.get("width",  CAMERA_DEFAULT_WIDTH)
        self._cap_height = cfg.get("height", CAMERA_DEFAULT_HEIGHT)
        self._cap_fps    = cfg.get("fps",    CAMERA_DEFAULT_FPS)
        self._cap_fourcc = cfg.get("fourcc", CAMERA_DEFAULT_FOURCC)
        self._out_width  = cfg.get("output_width",  CAMERA_OUTPUT_WIDTH)
        self._out_height = cfg.get("output_height", CAMERA_OUTPUT_HEIGHT)
        
    def start(self, max_retries: int = 10, retry_delay: float = 5.0) -> bool:
        """카메라 시작"""
        logger.event_info(
            EventType.MODULE_START,
            "CameraCapture 시작",
            {"camera_index": self.camera_index}
        )
        self.cap = open_camera_with_retry(
            self.camera_index, max_retries, retry_delay,
            width=self._cap_width, height=self._cap_height,
            fps=self._cap_fps, fourcc=self._cap_fourcc,
        )
        if self.cap is None:
            return False
        self.running = True
        return True

    def ensure_cap_open(self, max_retries: int = 3, retry_delay: float = 2.0) -> bool:
        """현재 캡이 열려있지 않으면 재연결을 시도합니다."""
        if not self.running:
            return False

        with self.cap_lock:
            current_cap = self.cap
            if current_cap is not None and getattr(current_cap, "isOpened", lambda: False)():
                return True

        return self.reconnect(max_retries=max_retries, retry_delay=retry_delay)

    def reconnect(self, max_retries: int = CAMERA_RECONNECT_MAX_RETRIES, retry_delay: float = 2.0) -> bool:
        """카메라를 강제로 다시 엽니다."""
        if not self.running:
            return False

        # 동시 reconnect 방지 (health monitor + read_frame 동시 호출 차단)
        if not self._reconnect_lock.acquire(blocking=False):
            return False

        try:
            if time.time() < self._reconnect_cooldown_until:
                self.last_reconnect_result = "cooldown"
                return False

            with self.cap_lock:
                if self.cap is not None:
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                    self.cap = None

            for attempt in range(1, max_retries + 1):
                self.reconnect_attempts += 1
                self.last_reconnect_ts = time.time()
                logger.event_warning(
                    EventType.CAMERA_ERROR,
                    "카메라 재연결 시도",
                    {
                        "camera_index": self.camera_index,
                        "attempt": attempt,
                        "max_retries": max_retries,
                        "total_attempts": self.reconnect_attempts,
                    },
                )
                cap = _open_cap(
                    self.camera_index,
                    setup_format=True,
                    width=self._cap_width,
                    height=self._cap_height,
                    fps=self._cap_fps,
                    fourcc=self._cap_fourcc,
                )
                if cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        with self.cap_lock:
                            self.cap = cap
                            self.running = True
                        self._reconnect_cooldown_until = 0.0
                        self.last_reconnect_result = "success"
                        logger.event_info(
                            EventType.CAMERA_OPEN,
                            "카메라 재연결 성공",
                            {
                                "camera_index": self.camera_index,
                                "attempt": attempt,
                                "width": self._cap_width,
                                "height": self._cap_height,
                                "fps": self._cap_fps,
                                "fourcc": self._cap_fourcc,
                            },
                        )
                        return True

                cap.release()
                if attempt < max_retries:
                    time.sleep(retry_delay)

            logger.event_error(
                EventType.CAMERA_ERROR,
                "카메라 재연결 실패",
                {
                    "camera_index": self.camera_index,
                    "max_retries": max_retries,
                    "cooldown_sec": CAMERA_RECONNECT_COOLDOWN_SEC,
                },
            )
            self.last_reconnect_result = "failed"
            self._reconnect_cooldown_until = time.time() + CAMERA_RECONNECT_COOLDOWN_SEC
            return False

        finally:
            self._reconnect_lock.release()
    
    def read_frame(self) -> tuple[bool, Optional[cv2.Mat]]:
        """프레임 읽기"""
        if not self.running:
            return False, None

        # 캡이 없거나 열려있지 않으면 재연결 시도 (쿨다운 중이면 스킵)
        with self.cap_lock:
            cap = self.cap
        if cap is None or not getattr(cap, 'isOpened', lambda: False)():
            if time.time() < self._reconnect_cooldown_until:
                return False, None
            logger.event_warning(EventType.CAMERA_ERROR, f"캡이 닫혀있음. 재연결 시도: camera_index={self.camera_index}")
            if not self.ensure_cap_open(max_retries=3, retry_delay=2.0):
                return False, None

        with self.cap_lock:
            cap = self.cap
            if cap is None:
                return False, None
            ret, frame = cap.read()
        # 읽기에 실패하면 즉시 reconnect(STREAMOFF/STREAMON)하지 않고
        # 먼저 짧게 재시도한다. 일시적 USB 패킷 손실은 이 구간에서 복구된다.
        # 재시도가 전부 실패할 때만 reconnect를 호출해 스트림을 재시작한다.
        if not ret:
            for _ in range(5):
                time.sleep(0.05)
                with self.cap_lock:
                    cap = self.cap
                    if cap is None:
                        break
                    ret, frame = cap.read()
                if ret:
                    return ret, frame

            if time.time() < self._reconnect_cooldown_until:
                return False, None
            logger.event_warning(EventType.CAMERA_ERROR, f"프레임 읽기 실패. 재연결 시도: camera_index={self.camera_index}")
            if self.reconnect(max_retries=3, retry_delay=5.0):
                with self.cap_lock:
                    cap = self.cap
                if cap is not None:
                    return cap.read()
            return False, None

        return ret, frame

    # def ensure_cap_open(self, max_retries: int = 3, retry_delay: float = 2.0) -> bool:
    #     """현재 `self.cap`이 열려있지 않다면 재연결을 시도한다."""
    #     # 기존 cap 정리
    #     try:
    #         if self.cap is not None:
    #             try:
    #                 self.cap.release()
    #             except Exception:
    #                 pass
    #         self.cap = None
    #     except Exception:
    #         pass

    #     retry = 0
    #     while retry < max_retries:
    #         retry += 1
    #         logger.event_info(EventType.CAMERA_INIT, f"재연결 시도 {retry}/{max_retries}: camera_index={self.camera_index}")
    #         cap = open_camera_with_retry(self.camera_index, max_retries=1, retry_delay=retry_delay)
    #         if cap is not None and getattr(cap, 'isOpened', lambda: False)():
    #             self.cap = cap
    #             logger.event_info(EventType.CAMERA_OPEN, f"카메라 재연결 성공: camera_index={self.camera_index}")
    #             return True
    #         time.sleep(retry_delay)

    #     logger.event_error(EventType.CAMERA_ERROR, f"카메라 재연결 실패: camera_index={self.camera_index}")
    #     return False
    
    def release(self):
        """카메라 리소스 해제"""
        logger.event_info(
            EventType.MODULE_STOP,
            "CameraCapture 종료",
            {"camera_index": self.camera_index}
        )
        self.running = False
        with self.cap_lock:
            if self.cap is not None:
                self.cap.release()
                self.cap = None


def init_cameras() -> Optional[List[CameraCapture]]:
    """설정된 카메라 인덱스로 카메라를 초기화. 하나라도 실패 시 None 반환."""
    logger.event_info(
        EventType.MODULE_INIT,
        "카메라 자동 탐색 결과",
        {"camera_indices": CAMERA_INDICES},
    )
    cameras: List[CameraCapture] = []
    for idx in CAMERA_INDICES:
        logger.event_info(EventType.MODULE_INIT, f"카메라 {idx} 초기화 중")
        camera = CameraCapture(idx)
        if not camera.start(CAMERA_MAX_RETRIES, CAMERA_RETRY_DELAY):
            logger.event_error(EventType.CAMERA_ERROR, f"카메라 {idx} 초기화 실패")
            for cam in cameras:
                cam.release()
            return None
        cameras.append(camera)
        logger.event_info(EventType.CAMERA_OPEN, f"카메라 {idx} 초기화 완료")
        if idx != CAMERA_INDICES[-1]:
            time.sleep(1.5)  # 앞 카메라 USB 협상 완료 후 다음 카메라 열기
    logger.debug(f"{len(cameras)}개 카메라 초기화 완료")
    return cameras
