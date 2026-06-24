"""
Video upload helper using curl multipart form.
"""
from __future__ import annotations

import os
import subprocess
import time
import threading
from datetime import datetime
from typing import Optional

from config.settings import (
    CAMERA_INDICES,
    EVENT_LOG_COOLDOWN_SEC,
    EVENT_LOG_ENABLED,
    EVENT_LOG_TIMEOUT_SEC,
    EVENT_LOG_URL,
    ROI_WARNING_COOLDOWN_SEC,
    UPLOAD_COMBINED,
    UPLOAD_DEVICE_ID,
    UPLOAD_DEVICE_KEY,
    UPLOAD_MAX_RETRIES,
    UPLOAD_REL_DIR,
    UPLOAD_RETRY_DELAY_SEC,
    UPLOAD_TIMEOUT_SEC,
    UPLOAD_URL,
)
from ai.detector import WarningLevel
from utils.logger import EventType, get_logger

_SEVERITY_MAP = {
    WarningLevel.BLIND_SPOT: 1,
    WarningLevel.APPROACH:   2,
    WarningLevel.URGENT:     3,
}

_last_roi_warning_ts: dict[int, float] = {}

logger = get_logger("pipeline.uploader")


def _post_event_json(event_type: str, severity) -> None:
    """이벤트 메타데이터를 EVENT_LOG_URL에 JSON POST로 전송합니다."""
    import json
    import urllib.request

    payload = json.dumps({
        "device_id": UPLOAD_DEVICE_ID,
        "device_key": UPLOAD_DEVICE_KEY,
        "event_type": event_type,
        "severity": severity,
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            EVENT_LOG_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=EVENT_LOG_TIMEOUT_SEC):
            pass
        logger.event_info(
            EventType.MODULE_STOP,
            "이벤트 JSON 전송 성공",
            {"event_type": event_type, "severity": severity},
        )
    except Exception as e:
        logger.event_error(
            EventType.ERROR_OCCURRED,
            "이벤트 JSON 전송 실패",
            {"event_type": event_type, "severity": severity, "error": str(e)},
        )

# 카메라별 마지막 전송 시각 (쿨다운 관리)
_last_event_log_ts: dict[int, float] = {}
_upload_status_lock = threading.Lock()
_upload_status = {
    "active_uploads": 0,
    "completed_uploads": 0,
    "failed_uploads": 0,
    "last_failure_count": 0,
    "last_failure_reason": None,
    "last_failure_file": None,
    "last_failure_ts": None,
}


def get_upload_status_snapshot() -> dict:
    """Heartbeat에 기록할 업로드 상태를 스레드 안전하게 반환합니다."""
    with _upload_status_lock:
        return dict(_upload_status)


def _extract_date(file_path: str) -> str:
    """Extract YYYY-MM-DD from event folder if possible; fallback to current date."""
    # Example folder: event_20260326_110530_gps_unknown
    base = os.path.normpath(file_path)
    parts = base.split(os.sep)
    for part in parts:
        if not part.startswith("event_"):
            continue
        tokens = part.split("_")
        if len(tokens) < 2:
            continue
        date_token = tokens[1]
        if len(date_token) == 8 and date_token.isdigit():
            return f"{date_token[0:4]}-{date_token[4:6]}-{date_token[6:8]}"
    return datetime.now().strftime("%Y-%m-%d")


def upload_video_file(file_path: str, date_str: Optional[str] = None) -> bool:
    """
    Upload video file to server with multipart/form-data.

    Form fields:
      - file
      - device_id
            - device_key
      - rel_dir
      - date
    """
    if not os.path.exists(file_path):
        logger.event_error(
            EventType.ERROR_OCCURRED,
            "업로드 실패: 파일이 존재하지 않음",
            {"file": file_path},
        )
        return False

    if not date_str:
        date_str = _extract_date(file_path)

    with _upload_status_lock:
        _upload_status["active_uploads"] += 1

    last_error = ""
    try:
        for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
            cmd = [
                "curl",
                "--silent",
                "--show-error",
                "--fail",
                "--max-time",
                str(int(UPLOAD_TIMEOUT_SEC)),
                "-F",
                f"file=@{file_path}",
                "-F",
                f"device_id={UPLOAD_DEVICE_ID}",
                "-F",
                f"device_key={UPLOAD_DEVICE_KEY}",
                "-F",
                f"rel_dir={UPLOAD_REL_DIR}",
                "-F",
                f"date={date_str}",
                UPLOAD_URL,
            ]

            logger.event_info(
                EventType.MODULE_START,
                "영상 업로드 시도",
                {
                    "file": file_path,
                    "attempt": attempt,
                    "max_retries": UPLOAD_MAX_RETRIES,
                    "url": UPLOAD_URL,
                },
            )

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=int(UPLOAD_TIMEOUT_SEC) + 5,
                )
            except FileNotFoundError:
                last_error = "curl 명령을 찾을 수 없음"
                logger.event_error(
                    EventType.ERROR_OCCURRED,
                    "업로드 실패: curl 명령을 찾을 수 없음",
                    {"file": file_path},
                )
                break
            except subprocess.TimeoutExpired:
                result = None

            if result is not None and result.returncode == 0:
                logger.event_info(
                    EventType.MODULE_STOP,
                    "영상 업로드 성공",
                    {"file": file_path, "attempt": attempt},
                )
                with _upload_status_lock:
                    _upload_status["completed_uploads"] += 1
                return True

            last_error = "timeout" if result is None else (result.stderr or "")[-500:]
            logger.event_warning(
                EventType.RETRY_ATTEMPT,
                "영상 업로드 실패, 재시도 예정",
                {
                    "file": file_path,
                    "attempt": attempt,
                    "stderr": last_error,
                },
            )
            if attempt < UPLOAD_MAX_RETRIES:
                sleep_sec = UPLOAD_RETRY_DELAY_SEC * attempt
                time.sleep(sleep_sec)

        logger.event_error(
            EventType.ERROR_OCCURRED,
            "영상 업로드 최종 실패",
            {
                "file": file_path,
                "retries": UPLOAD_MAX_RETRIES,
                "last_failure_reason": last_error,
            },
        )
        with _upload_status_lock:
            _upload_status["failed_uploads"] += 1
            _upload_status["last_failure_count"] = UPLOAD_MAX_RETRIES
            _upload_status["last_failure_reason"] = last_error
            _upload_status["last_failure_file"] = file_path
            _upload_status["last_failure_ts"] = datetime.now().isoformat()
        return False
    finally:
        with _upload_status_lock:
            _upload_status["active_uploads"] = max(0, _upload_status["active_uploads"] - 1)


def upload_video_with_event(
    file_path: str,
    event_type: str,
    cam_id: int,
    speed_level: int,
    severity_override: Optional[int] = None,
    date_str: Optional[str] = None,
) -> bool:
    """영상 파일과 이벤트 메타데이터를 단일 multipart POST로 전송합니다.

    UPLOAD_COMBINED = True 일 때 upload_video_file + _send_event_log 를 대체합니다.
    기존 함수는 그대로 유지됩니다.
    """
    if not os.path.exists(file_path):
        logger.event_error(
            EventType.ERROR_OCCURRED,
            "통합 업로드 실패: 파일이 존재하지 않음",
            {"file": file_path},
        )
        return False

    if not date_str:
        date_str = _extract_date(file_path)

    if severity_override is not None:
        severity = severity_override
    else:
        try:
            severity = _SEVERITY_MAP[WarningLevel[event_type]]
        except KeyError:
            severity = None

    with _upload_status_lock:
        _upload_status["active_uploads"] += 1

    last_error = ""
    try:
        for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
            cmd = [
                "curl",
                "--silent", "--show-error", "--fail",
                "--max-time", str(int(UPLOAD_TIMEOUT_SEC)),
                "-F", f"file=@{file_path}",
                "-F", f"device_id={UPLOAD_DEVICE_ID}",
                "-F", f"device_key={UPLOAD_DEVICE_KEY}",
                "-F", f"rel_dir={UPLOAD_REL_DIR}",
                "-F", f"date={date_str}",
                "-F", f"event_type=ROI_WARNING_CAM{cam_id}",
                "-F", f"severity={severity}",
                "-F", f"cam_id={cam_id}",
                "-F", f"speed_level={speed_level}",
                UPLOAD_URL,
            ]

            logger.event_info(
                EventType.MODULE_START,
                "영상+이벤트 통합 업로드 시도",
                {
                    "file": file_path,
                    "attempt": attempt,
                    "max_retries": UPLOAD_MAX_RETRIES,
                    "url": UPLOAD_URL,
                    "event_type": f"ROI_WARNING_CAM{cam_id}",
                    "severity": severity,
                    "cam_id": cam_id,
                    "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            )

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=int(UPLOAD_TIMEOUT_SEC) + 5,
                )
            except FileNotFoundError:
                last_error = "curl 명령을 찾을 수 없음"
                logger.event_error(EventType.ERROR_OCCURRED, "통합 업로드 실패: curl 없음", {"file": file_path})
                break
            except subprocess.TimeoutExpired:
                result = None

            if result is not None and result.returncode == 0:
                logger.event_info(
                    EventType.MODULE_STOP,
                    "영상+이벤트 통합 업로드 성공",
                    {
                        "file": file_path,
                        "attempt": attempt,
                        "event_type": f"ROI_WARNING_CAM{cam_id}",
                        "severity": severity,
                        "cam_id": cam_id,
                        "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )
                _post_event_json(f"ROI_WARNING_CAM{cam_id}", severity)
                with _upload_status_lock:
                    _upload_status["completed_uploads"] += 1
                return True

            last_error = "timeout" if result is None else (result.stderr or "")[-500:]
            logger.event_warning(
                EventType.RETRY_ATTEMPT,
                "통합 업로드 실패, 재시도 예정",
                {"file": file_path, "attempt": attempt, "stderr": last_error},
            )
            if attempt < UPLOAD_MAX_RETRIES:
                time.sleep(UPLOAD_RETRY_DELAY_SEC * attempt)

        logger.event_error(
            EventType.ERROR_OCCURRED,
            "영상+이벤트 통합 업로드 최종 실패",
            {
                "file": file_path,
                "retries": UPLOAD_MAX_RETRIES,
                "event_type": f"ROI_WARNING_CAM{cam_id}",
                "severity": severity,
                "cam_id": cam_id,
                "last_failure_reason": last_error,
            },
        )
        with _upload_status_lock:
            _upload_status["failed_uploads"] += 1
            _upload_status["last_failure_count"] = UPLOAD_MAX_RETRIES
            _upload_status["last_failure_reason"] = last_error
            _upload_status["last_failure_file"] = file_path
            _upload_status["last_failure_ts"] = datetime.now().isoformat()
        return False
    finally:
        with _upload_status_lock:
            _upload_status["active_uploads"] = max(0, _upload_status["active_uploads"] - 1)


def post_fixed_roi_warning_event(warning_level: WarningLevel, cam_id: int) -> bool:
    """고정 ROI 경고 이벤트를 서버에 전송합니다.

    Args:
        warning_level: BLIND_SPOT / APPROACH / URGENT
        cam_id:        카메라 인덱스
    """
    severity = _SEVERITY_MAP.get(warning_level)
    if severity is None:
        return False

    event_type = f"ROI_WARNING_CAM{cam_id}"
    import json as _json
    payload = _json.dumps({
        "device_id": UPLOAD_DEVICE_ID,
        "device_key": UPLOAD_DEVICE_KEY,
        "event_type": event_type,
        "severity": severity,
    })

    cmd = [
        "curl", "-X", "POST", EVENT_LOG_URL,
        "-H", "Content-Type: application/json",
        "-d", payload,
    ]

    try:
        logger.event_info(
            EventType.MODULE_START,
            "고정 ROI 경고 이벤트 전송 시도",
            {"url": EVENT_LOG_URL, "event_type": event_type, "severity": severity, "cam_id": cam_id},
        )
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            logger.event_info(
                EventType.MODULE_STOP,
                "고정 ROI 경고 이벤트 전송 성공",
                {"event_type": event_type, "severity": severity},
            )
            return True

        logger.event_error(
            EventType.ERROR_OCCURRED,
            "고정 ROI 경고 이벤트 전송 실패",
            {"stderr": (result.stderr or "")[-500:]},
        )
        return False
    except FileNotFoundError:
        logger.event_error(EventType.ERROR_OCCURRED, "고정 ROI 경고 이벤트 전송 실패: curl 없음", {})
        return False
    except subprocess.TimeoutExpired:
        logger.event_error(EventType.ERROR_OCCURRED, "고정 ROI 경고 이벤트 전송 실패: 타임아웃", {})
        return False
    except Exception as e:
        logger.event_error(EventType.ERROR_OCCURRED, "고정 ROI 경고 이벤트 전송 중 예외 발생", {"error": str(e)})
        return False


def notify_roi_warning(warning_level: WarningLevel, cam_id: int) -> None:
    """SAFE → non-SAFE 전환 시 호출. 쿨다운 확인 후 백그라운드 전송.

    Args:
        warning_level: BLIND_SPOT / APPROACH / URGENT
        cam_id:        카메라 인덱스
    """
    if UPLOAD_COMBINED:
        return
    if warning_level == WarningLevel.SAFE:
        return
    now = time.time()
    if now - _last_roi_warning_ts.get(cam_id, 0.0) < ROI_WARNING_COOLDOWN_SEC:
        return
    _last_roi_warning_ts[cam_id] = now
    threading.Thread(
        target=post_fixed_roi_warning_event,
        args=(warning_level, cam_id),
        daemon=True,
        name=f"roi_warning_{cam_id}",
    ).start()


# ──────────────────────────────────────────────
# JSON 이벤트 로그 전송 (yolo_test-main send_to_ec2_server 이식)
# ──────────────────────────────────────────────

def _is_within_cooldown(cam_id: int) -> bool:
    """카메라별 쿨다운 내에 이미 전송했으면 True를 반환합니다."""
    return time.time() - _last_event_log_ts.get(cam_id, 0.0) < EVENT_LOG_COOLDOWN_SEC


def _record_event_log_timestamp(cam_id: int) -> None:
    """이벤트 로그 전송 시각을 카메라 쿨다운 기록에 저장합니다."""
    _last_event_log_ts[cam_id] = time.time()


def _dispatch_event_log(event_type: str, cam_id: int, speed_level: int, blocking: bool) -> None:
    """blocking 여부에 따라 이벤트 로그를 동기 또는 백그라운드 스레드로 전송합니다."""
    if blocking:
        _send_event_log(event_type, cam_id, speed_level)
    else:
        threading.Thread(
            target=_send_event_log,
            args=(event_type, cam_id, speed_level),
            daemon=True,
            name=f"event_log_{cam_id}",
        ).start()


def upload_event_log(
    event_type: str,
    cam_id: int,
    speed_level: int,
    *,
    blocking: bool = False,
) -> None:
    """
    경고 이벤트 발생 시 JSON 메타데이터를 서버에 전송.

    yolo_test-main/main_system.py의 send_to_ec2_server()를 이식:
    - 영상 파일 없이 경고 레벨·시각·속도를 JSON으로 즉시 전송
    - 기본적으로 백그라운드 스레드로 실행되어 추론 루프를 차단하지 않음
    - 카메라별 쿨다운(EVENT_LOG_COOLDOWN_SEC) 으로 중복 전송 방지

    Args:
        event_type:  "BLIND_SPOT" | "APPROACH" | "URGENT"
        cam_id:      카메라 인덱스
        speed_level: 지게차 속도 레벨 (0~5)
        blocking:    True 이면 호출 스레드에서 직접 실행 (테스트용)
    """
    if not EVENT_LOG_ENABLED:
        return
    if UPLOAD_COMBINED:
        return
    if _is_within_cooldown(cam_id):
        return
    _record_event_log_timestamp(cam_id)
    _dispatch_event_log(event_type, cam_id, speed_level, blocking)


def _send_event_log(event_type: str, cam_id: int, speed_level: int) -> None:
    """실제 HTTP POST 전송 (백그라운드 스레드에서 호출)."""
    import json
    import urllib.request
    import urllib.error

    try:
        severity = _SEVERITY_MAP[WarningLevel[event_type]]
    except KeyError:
        severity = None

    payload = {
        "device_id": UPLOAD_DEVICE_ID,
        "device_key": UPLOAD_DEVICE_KEY,
        "event_type": f"ROI_WARNING_CAM{CAMERA_INDICES.index(cam_id) + 1 if cam_id in CAMERA_INDICES else cam_id}",
        "severity": severity,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            EVENT_LOG_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=EVENT_LOG_TIMEOUT_SEC):
            pass
        logger.event_info(
            EventType.MODULE_STOP,
            "이벤트 로그 전송 성공",
            {"event_type": event_type, "cam_id": cam_id, "payload": payload},
        )
    except Exception as e:
        logger.event_error(
            EventType.ERROR_OCCURRED,
            "이벤트 로그 전송 실패 (서버 미연결 시 정상)",
            {"event_type": event_type, "cam_id": cam_id, "error": str(e)},
        )


# ──────────────────────────────────────────────
# 이벤트 큐 워커
# ──────────────────────────────────────────────

def _process_event_queue_item(event_type: str, cam_id: int, speed_level: int) -> None:
    """큐에서 꺼낸 이벤트 한 건을 파싱하여 upload_event_log를 호출합니다."""
    upload_event_log(event_type=event_type, cam_id=cam_id, speed_level=speed_level)


def start_event_upload_worker(
    event_queues: list,
    stop_event: threading.Event,
) -> threading.Thread:
    """
    SharedState.event_queue 들을 구독해 upload_event_log 를 호출하는 워커 스레드.

    inference.py 는 큐에 (event_type, cam_id, speed_level) 튜플만 넣고,
    실제 업로드 책임은 이 워커가 전담한다.

    Args:
        event_queues:  SharedState 리스트의 event_queue 목록
        stop_event:    종료 신호 Event
    """
    def _worker():
        import queue as _queue
        while not stop_event.is_set():
            for eq in event_queues:
                try:
                    event_type, cam_id, speed_level = eq.get_nowait()
                    _process_event_queue_item(event_type, cam_id, speed_level)
                except _queue.Empty:
                    pass
                except Exception as e:
                    logger.event_error(
                        EventType.ERROR_OCCURRED,
                        "이벤트 큐 워커 오류",
                        {"error": str(e)},
                    )
            time.sleep(0.1)

    t = threading.Thread(target=_worker, daemon=True, name="event_upload_worker")
    t.start()
    logger.debug("이벤트 업로드 워커 스레드 시작")
    return t
