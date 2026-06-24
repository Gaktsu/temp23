"""
Runtime heartbeat writer for the main control process.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Iterable, Optional

from config.settings import (
    CAMERA_INDICES,
    CAMERA_STALE_THRESHOLD_SEC,
    HEARTBEAT_INTERVAL_SEC,
    HEARTBEAT_PATH,
)
from utils.logger import EventType, get_logger

logger = get_logger("system.heartbeat")


def _iso_from_epoch(epoch_value: float) -> Optional[str]:
    if not epoch_value:
        return None
    return datetime.fromtimestamp(epoch_value).isoformat(timespec="seconds")


def bootstrap_heartbeat(status: str = "starting", extra: Optional[Dict] = None) -> None:
    """메인 초기화 초기에 쓸 수 있는 최소 heartbeat를 기록합니다."""
    payload = {
        "last_update": _iso_from_epoch(time.time()),
        "last_update_epoch": time.time(),
        "status": status,
        "camera": {},
        "ai": {"last_update": None, "last_update_epoch": 0.0, "per_camera": {}},
        "upload_queue": {
            "video_queue_size": 0,
            "event_queue_sizes": {},
            "event_queue_total": 0,
            "active_uploads": 0,
            "completed_uploads": 0,
            "failed_uploads": 0,
            "last_failure_count": 0,
            "last_failure_reason": None,
            "last_failure_file": None,
            "last_failure_ts": None,
        },
    }
    if extra:
        payload["startup"] = extra

    os.makedirs(os.path.dirname(HEARTBEAT_PATH), exist_ok=True)
    tmp_path = f"{HEARTBEAT_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, HEARTBEAT_PATH)


class HeartbeatWriter:
    """Periodically writes a JSON heartbeat snapshot for watchdog monitoring."""

    def __init__(
        self,
        cameras,
        states,
        save_queue,
        upload_status_getter: Optional[Callable[[], Dict]] = None,
        heartbeat_path: str = HEARTBEAT_PATH,
        interval_sec: float = HEARTBEAT_INTERVAL_SEC,
    ) -> None:
        self.cameras = cameras
        self.states = states
        self.save_queue = save_queue
        self.upload_status_getter = upload_status_getter
        self.heartbeat_path = heartbeat_path
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> threading.Thread:
        """Start the background writer thread."""
        if self._thread is not None and self._thread.is_alive():
            return self._thread

        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="heartbeat_writer",
        )
        self._thread.start()
        logger.event_info(
            EventType.MODULE_START,
            "Heartbeat writer started",
            {"heartbeat_path": self.heartbeat_path, "interval_sec": self.interval_sec},
        )
        return self._thread

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the background writer thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        logger.event_info(EventType.MODULE_STOP, "Heartbeat writer stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.write_once()
            except Exception as exc:
                logger.event_error(
                    EventType.ERROR_OCCURRED,
                    "Heartbeat write failed",
                    {"error": str(exc)},
                    exc_info=True,
                )
            self._stop_event.wait(self.interval_sec)

    def _collect_camera_snapshot(self, cam_id: int, camera, state) -> Dict:
        now_epoch = time.time()
        with state.frame_lock:
            last_frame_ts = state.latest_frame_ts
            frame_seq = state.latest_frame_seq
        with state.detection_lock:
            last_detection_ts = state.last_detection_ts
            last_inference_ts = state.last_inference_ts
            last_intrusion_ts = state.last_intrusion_ts
            last_warning_level = getattr(state.last_warning_level, "value", str(state.last_warning_level))
            intrusion = state.last_intrusion
            forklift_speed = state.forklift_speed

        frame_age_sec = round(now_epoch - last_frame_ts, 3) if last_frame_ts else None
        inference_age_sec = round(now_epoch - last_inference_ts, 3) if last_inference_ts else None
        detection_age_sec = round(now_epoch - last_detection_ts, 3) if last_detection_ts else None
        camera_open = bool(getattr(camera, "cap", None) is not None and getattr(camera.cap, "isOpened", lambda: False)())
        camera_status = "starting"
        if frame_age_sec is not None:
            camera_status = "ok" if frame_age_sec <= CAMERA_STALE_THRESHOLD_SEC else "stale"
        if not camera_open:
            camera_status = "reconnecting" if camera.running else "stopped"

        return {
            "camera_index": cam_id,
            "running": bool(getattr(camera, "running", False)),
            "open": camera_open,
            "status": camera_status,
            "frame_seq": frame_seq,
            "last_frame_ts": _iso_from_epoch(last_frame_ts),
            "frame_age_sec": frame_age_sec,
            "last_detection_ts": _iso_from_epoch(last_detection_ts),
            "detection_age_sec": detection_age_sec,
            "last_inference_ts": _iso_from_epoch(last_inference_ts),
            "inference_age_sec": inference_age_sec,
            "last_intrusion_ts": _iso_from_epoch(last_intrusion_ts),
            "intrusion": intrusion,
            "last_warning_level": last_warning_level,
            "forklift_speed": forklift_speed,
        }

    def _collect_upload_snapshot(self) -> Dict:
        save_queue_size = self.save_queue.qsize() if self.save_queue is not None else 0
        event_queue_sizes = {
            str(CAMERA_INDICES[idx]): state.event_queue.qsize()
            for idx, state in enumerate(self.states)
        }
        event_queue_total = sum(event_queue_sizes.values())
        upload_status = self.upload_status_getter() if self.upload_status_getter else {}
        upload_status = dict(upload_status)
        upload_status.setdefault("active_uploads", 0)
        upload_status.setdefault("completed_uploads", 0)
        upload_status.setdefault("failed_uploads", 0)
        return {
            "video_queue_size": save_queue_size,
            "event_queue_sizes": event_queue_sizes,
            "event_queue_total": event_queue_total,
            "active_uploads": upload_status.get("active_uploads", 0),
            "completed_uploads": upload_status.get("completed_uploads", 0),
            "failed_uploads": upload_status.get("failed_uploads", 0),
            "last_failure_count": upload_status.get("last_failure_count", 0),
            "last_failure_reason": upload_status.get("last_failure_reason"),
            "last_failure_file": upload_status.get("last_failure_file"),
            "last_failure_ts": upload_status.get("last_failure_ts"),
        }

    def _build_snapshot(self) -> Dict:
        now_epoch = time.time()
        camera_snapshot = {
            str(CAMERA_INDICES[idx]): self._collect_camera_snapshot(CAMERA_INDICES[idx], camera, state)
            for idx, (camera, state) in enumerate(zip(self.cameras, self.states))
        }
        freshest_inference_epoch = 0.0
        for state in self.states:
            with state.detection_lock:
                freshest_inference_epoch = max(freshest_inference_epoch, state.last_inference_ts)

        camera_statuses = [entry["status"] for entry in camera_snapshot.values()]
        overall_status = "running"
        if not camera_snapshot:
            overall_status = "starting"
        elif any(status in {"stale", "reconnecting", "stopped"} for status in camera_statuses):
            overall_status = "degraded"
        elif any(entry["last_frame_ts"] is None for entry in camera_snapshot.values()):
            overall_status = "starting"

        return {
            "last_update": _iso_from_epoch(now_epoch),
            "last_update_epoch": now_epoch,
            "status": overall_status,
            "camera": camera_snapshot,
            "ai": {
                "last_update": _iso_from_epoch(freshest_inference_epoch),
                "last_update_epoch": freshest_inference_epoch,
                "per_camera": {
                    str(CAMERA_INDICES[idx]): {
                        "last_inference_ts": _iso_from_epoch(state.last_inference_ts),
                        "last_detection_ts": _iso_from_epoch(state.last_detection_ts),
                        "inference_age_sec": round(now_epoch - state.last_inference_ts, 3) if state.last_inference_ts else None,
                    }
                    for idx, state in enumerate(self.states)
                },
            },
            "upload_queue": self._collect_upload_snapshot(),
        }

    def _atomic_write(self, payload: Dict) -> None:
        os.makedirs(os.path.dirname(self.heartbeat_path), exist_ok=True)
        tmp_path = f"{self.heartbeat_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.heartbeat_path)

    def write_once(self) -> Dict:
        """Write a single heartbeat snapshot and return it."""
        payload = self._build_snapshot()
        self._atomic_write(payload)
        logger.debug(
            "Heartbeat updated",
            {
                "heartbeat_path": self.heartbeat_path,
                "status": payload.get("status"),
                "camera_count": len(payload.get("camera", {})),
            },
        )
        return payload
