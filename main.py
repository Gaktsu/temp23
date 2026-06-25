"""
메인 실행 파일 - 전체 흐름 제어
"""
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from system.heartbeat import HeartbeatWriter, bootstrap_heartbeat

bootstrap_heartbeat(
    status="booting",
    extra={
        "pid": os.getpid(),
        "script": __file__,
    },
)

import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication
from ai.detector import WarningLevel, load_roi_polygon
from ai.model import load_model
from config import roi_setup as _roi_setup_mod
from config.roi_manager import roi_config_path
from config.settings import (
    CAMERA_HEALTH_CHECK_INTERVAL_SEC,
    CAMERA_INDICES,
    CAMERA_RECONNECT_MAX_RETRIES,
    CAMERA_STALE_THRESHOLD_SEC,
    CAMERA_DEFAULT_WIDTH, CAMERA_DEFAULT_HEIGHT,
    CAMERA_OUTPUT_WIDTH, CAMERA_OUTPUT_HEIGHT,
    DISPLAY_MODE,
    EVENT_RECORD_POST_SEC,
    PROJECT_ROOT,
    RECORDING_MODE,
    WATCHDOG_SCRIPT_PATH,
    WATCHDOG_TEST_DELAY,
    WATCHDOG_TEST_MODE,
    WINDOW_NAME,
)
from hardware.buzzer import Buzzer
from hardware.camera import CameraCapture, init_cameras
from hardware.imu import IMU
from pipeline.capture import start_capture_threads
from pipeline.inference import start_inference_thread
from pipeline.recorder import start_save_thread
from pipeline.shared_state import SharedState
from pipeline.sensors import start_sensor_threads
from pipeline.uploader import get_upload_status_snapshot, start_event_upload_worker
from ui.renderer import draw_detections
from ui_app import MainApp
from utils.logger import EventType, get_logger
from utils.sensor_sync import SensorBuffer
from utils.time_utils import FPSCounter
# 중앙 Orchestrator 로거
logger = get_logger("main_orchestrator")
MAIN_SUPERVISED_ENV = "JETSON_MAIN_SUPERVISED"


# ──────────────────────────────────────────────
# 초기화 헬퍼
# ──────────────────────────────────────────────

def _start_watchdog_timer() -> None:
    """Watchdog 테스트 모드: 설정된 시간 후 강제 오류 발생"""
    def _crash():
        time.sleep(WATCHDOG_TEST_DELAY)
        logger.event_error(EventType.ERROR_OCCURRED, "⚠️ Watchdog 테스트: 강제 오류 발생")
        raise RuntimeError("Watchdog 테스트를 위해 일부러 발생시킨 오류입니다!")
    threading.Thread(target=_crash, daemon=False, name="watchdog_test").start()




def _build_sensor_getter(imu_buffer: SensorBuffer):
    """IMU 최신 데이터를 시각 기준으로 묶어 반환하는 getter 클로저 생성"""
    def get_sensor_snapshot(timestamp: float) -> dict:
        imu_sample = imu_buffer.get_latest()
        return {
            "timestamp": timestamp,
            "imu": {"ts": imu_sample[0], "data": imu_sample[1]} if imu_sample else None,
        }
    return get_sensor_snapshot


def _start_camera_health_monitor(
    cameras: List[CameraCapture],
    states: List[SharedState],
    stop_event: threading.Event,
) -> threading.Thread:
    """프레임이 장시간 멈춘 카메라를 재연결하는 보조 감시 스레드."""
    last_reconnect_attempt: Dict[int, float] = {cam_id: 0.0 for cam_id in CAMERA_INDICES}
    monitor_start = time.time()

    def _monitor() -> None:
        while not stop_event.is_set():
            now = time.time()
            for idx, (camera, state) in enumerate(zip(cameras, states)):
                cam_id = CAMERA_INDICES[idx]
                with state.frame_lock:
                    last_frame_ts = state.latest_frame_ts

                if last_frame_ts <= 0.0:
                    frame_age_sec = now - monitor_start
                    if frame_age_sec < CAMERA_STALE_THRESHOLD_SEC:
                        continue
                else:
                    frame_age_sec = now - last_frame_ts
                    if frame_age_sec < CAMERA_STALE_THRESHOLD_SEC:
                        continue

                if now - last_reconnect_attempt.get(cam_id, 0.0) < CAMERA_HEALTH_CHECK_INTERVAL_SEC:
                    continue

                last_reconnect_attempt[cam_id] = now
                logger.event_warning(
                    EventType.CAMERA_ERROR,
                    "카메라 프레임 정지 감지 - 재연결 시도",
                    {
                        "camera_index": cam_id,
                        "frame_age_sec": round(frame_age_sec, 2),
                        "threshold_sec": CAMERA_STALE_THRESHOLD_SEC,
                        "last_frame_seen": last_frame_ts > 0.0,
                        "reconnect_attempts": getattr(camera, "reconnect_attempts", 0),
                        "last_reconnect_result": getattr(camera, "last_reconnect_result", "unknown"),
                    },
                )

                if camera.reconnect(max_retries=CAMERA_RECONNECT_MAX_RETRIES, retry_delay=2.0):
                    logger.event_info(
                        EventType.CAMERA_OPEN,
                        "카메라 프레임 복구 성공",
                        {"camera_index": cam_id},
                    )
                else:
                    logger.event_error(
                        EventType.CAMERA_ERROR,
                        "카메라 프레임 복구 실패",
                        {"camera_index": cam_id},
                    )

            stop_event.wait(CAMERA_HEALTH_CHECK_INTERVAL_SEC)

    thread = threading.Thread(target=_monitor, daemon=True, name="camera_health_monitor")
    thread.start()
    logger.debug("카메라 건강 감시 스레드 시작")
    return thread




# ──────────────────────────────────────────────
# 메인 루프 헬퍼
# ──────────────────────────────────────────────

def _get_current_frame(states: List[SharedState], cam_idx: int):
    """현재 표시 카메라의 최신 프레임과 탐지 결과를 SharedState에서 읽어 반환"""
    state = states[cam_idx]
    with state.frame_lock:
        seq = state.latest_frame_seq
        frame = state.latest_frame.copy() if state.latest_frame is not None else None
    with state.detection_lock:
        detections = list(state.last_detections)
        last_intrusion_ts = state.last_intrusion_ts
    intrusion = state.is_intruding()
    return frame, seq, detections, intrusion, last_intrusion_ts


def _determine_saving(intrusion: bool, last_intrusion_ts: float) -> bool:
    """현재 saving 상태 결정 (full 모드는 항상 True, event 모드는 침입 + post 구간)"""
    if RECORDING_MODE == "full":
        return True
    if last_intrusion_ts > 0:
        return intrusion or (time.time() - last_intrusion_ts <= EVENT_RECORD_POST_SEC)
    return intrusion


def _determine_saving_global(states: List[SharedState]) -> bool:
    """모든 카메라 중 하나라도 저장 중이면 True (침입 + post 구간 포함)"""
    if RECORDING_MODE == "full":
        return True
    now = time.time()
    for state in states:
        with state.detection_lock:
            last_ts   = state.last_intrusion_ts
        intrusion = state.is_intruding()
        if intrusion:
            return True
        if last_ts > 0 and (now - last_ts) <= EVENT_RECORD_POST_SEC:
            return True
    return False


def _open_roi_setup(states: List[SharedState]) -> None:
    """ROI 캘리브레이션 도구를 메인 스레드에서 실행.
    백그라운드 스레드(캡처/추론/저장/센서)는 계속 실행된다.
    카메라 충돌 방지를 위해 SharedState의 최신 프레임을 frame_getter로 전달한다.
    """
    logger.event_info(EventType.USER_INPUT, "ROI 캘리브레이션 도구 열기", {"key": "w"})

    # 창을 닫기 전에 현재 창 모드와 크기를 읽어 roi_setup에 그대로 전달
    is_fullscreen = (
        cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN) == cv2.WINDOW_FULLSCREEN
    )
    rect = cv2.getWindowImageRect(WINDOW_NAME)  # (x, y, w, h)
    window_config = {
        "fullscreen": is_fullscreen,
        "width": rect[2] if rect[2] > 0 else 1280,
        "height": rect[3] if rect[3] > 0 else 720,
    }

    cv2.destroyWindow(WINDOW_NAME)
    cv2.waitKey(1)

    def _make_getter(state):
        def getter():
            with state.frame_lock:
                if state.latest_frame is not None:
                    return state.latest_frame.copy()
            return None
        return getter

    frame_getters = {
        CAMERA_INDICES[i]: _make_getter(states[i])
        for i in range(len(states))
    }

    _roi_setup_mod.main(frame_getters=frame_getters, window_config=window_config)
    # 캘리브레이션 종료 후 메인 전체화면 창 복원
    cv2.namedWindow(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    logger.event_info(EventType.STATE_CHANGE, "ROI 캘리브레이션 완료, 메인 창 복원")


def _handle_keypress(key: int, cam_idx: int, num_cameras: int) -> Tuple[int, bool]:
    """키 입력 처리. (새 카메라 인덱스, 종료 여부) 반환"""
    if key == ord('c'):
        new_idx = (cam_idx + 1) % num_cameras
        logger.event_info(EventType.USER_INPUT, "카메라 전환",
                          {"key": "c", "camera_index": CAMERA_INDICES[new_idx]})
        print(f"카메라 {CAMERA_INDICES[new_idx]}번으로 전환")
        return new_idx, False
    if key == ord('q'):
        logger.event_info(EventType.USER_INPUT, "종료 신호 감지", {"key": "q"})
        return cam_idx, True
    return cam_idx, False


# ──────────────────────────────────────────────
# 분할 화면 헬퍼 (DISPLAY_MODE="split" 전용)
# ──────────────────────────────────────────────

def _stack_panels(panels: List[cv2.Mat]) -> cv2.Mat:
    """N개 패널을 2열 그리드로 합성"""
    if not panels:
        return np.zeros((480, 640, 3), dtype=np.uint8)
    if len(panels) == 1:
        return panels[0]
    h, w = panels[0].shape[:2]
    resized = [cv2.resize(p, (w, h)) if p.shape[:2] != (h, w) else p for p in panels]
    if len(resized) == 2:
        return np.hstack(resized)
    # 3개 이상: 2열 그리드
    cols = 2
    rows = (len(resized) + cols - 1) // cols
    blank = np.zeros((h, w, 3), dtype=np.uint8)
    while len(resized) < rows * cols:
        resized.append(blank)
    row_imgs = [np.hstack(resized[r * cols:(r + 1) * cols]) for r in range(rows)]
    return np.vstack(row_imgs)


def _load_roi_polygons() -> Dict[int, Any]:
    """카메라별 ROI 폴리곤 파일을 읽어 dict 반환. 파일 없으면 None."""
    scale_x = CAMERA_DEFAULT_WIDTH / CAMERA_OUTPUT_WIDTH
    scale_y = CAMERA_DEFAULT_HEIGHT / CAMERA_OUTPUT_HEIGHT
    return {
        cam_id: load_roi_polygon(roi_config_path(cam_id), scale_x=scale_x, scale_y=scale_y)
        for cam_id in CAMERA_INDICES
    }


def _read_camera_state_snapshot(state: SharedState):
    """한 카메라의 최신 프레임·탐지·경고 레벨을 스레드 안전하게 읽어 반환합니다."""
    with state.frame_lock:
        frame = state.latest_frame.copy() if state.latest_frame is not None else None
    with state.detection_lock:
        detections = list(state.last_detections)
        warning_level = state.last_warning_level
    intrusion = state.is_intruding()
    if not intrusion:
        warning_level = WarningLevel.SAFE
    return frame, detections, intrusion, warning_level


def _render_camera_panel(
    frame,
    detections,
    fps: float,
    saving: bool,
    cam_id: int,
    state: SharedState,
    draw_ms: float,
    roi_polygons: Optional[Dict[int, Any]],
) -> Tuple[cv2.Mat, float]:
    """한 카메라 프레임에 탐지 오버레이를 그리고 (panel, draw_ms) 를 반환합니다."""
    t0 = time.perf_counter()
    panel = draw_detections(
        frame,
        detections,
        fps,
        saving,
        cam_id,
        intrusion=state.is_intruding(),
        capture_ms=state.capture_ms,
        inference_ms=state.inference_ms,
        postprocess_ms=state.postprocess_ms,
        draw_ms=draw_ms,
        roi_polygon=roi_polygons.get(cam_id) if roi_polygons else None,
        forklift_speed=state.forklift_speed,
        warning_level=state.last_warning_level if state.is_intruding() else WarningLevel.SAFE,
    )
    return panel, (time.perf_counter() - t0) * 1000


def _build_split_frame(
    states: List[SharedState],
    fps_counters: Dict[int, "FPSCounter"],
    draw_ms_list: List[float],
    roi_polygons: Optional[Dict[int, Any]] = None,
) -> Tuple[cv2.Mat, bool, List[float]]:
    """모든 카메라 프레임을 분할 합성. (combined_frame, any_intrusion, new_draw_ms_list) 반환"""
    panels = []
    any_intrusion = False
    new_draw_ms: List[float] = []
    global_saving = _determine_saving_global(states)

    for i, state in enumerate(states):
        cam_id = CAMERA_INDICES[i]
        frame, detections, intrusion, warning_level = _read_camera_state_snapshot(state)

        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

        any_intrusion = any_intrusion or intrusion
        fps = fps_counters[cam_id].update()

        panel, elapsed_ms = _render_camera_panel(
            frame, detections, fps, global_saving, cam_id,
            state, draw_ms_list[i], roi_polygons,
        )
        new_draw_ms.append(elapsed_ms)
        panels.append(panel)

    return _stack_panels(panels), any_intrusion, new_draw_ms


# ──────────────────────────────────────────────
# 정리
# ──────────────────────────────────────────────

def _cleanup(
    cameras: List[CameraCapture],
    states: List[SharedState],
    threads: List[threading.Thread],
    save_stop_event: threading.Event,
    inference_stop_event: threading.Event,
    sensor_stop_event: threading.Event,
    imu: IMU,
    buzzer: Buzzer,
    heartbeat_writer=None,
) -> None:
    """모든 스레드 종료 및 리소스 해제"""
    logger.event_info(EventType.MODULE_STOP, "시스템 종료 프로세스 시작")

    # 1단계: 종료 요청 즉시 카메라 캡처를 멈춰 장치 점유를 먼저 해제한다.
    #   save_worker는 큐에 남은 프레임만 정리하고 종료한다.
    inference_stop_event.set()
    save_stop_event.set()
    sensor_stop_event.set()
    for state in states:
        state.stop_event.set()
    cv2.destroyAllWindows()
    logger.debug("OpenCV 윈도우 종료")
    buzzer.stop()

    logger.debug("캡처/추론/센서 스레드 종료 신호 전송")
    for t in threads:
        if t.name != "save_worker":
            t.join(timeout=1.0)

    for i, camera in enumerate(cameras):
        camera.release()
        logger.event_info(EventType.CAMERA_CLOSE, f"카메라 {CAMERA_INDICES[i]} 리소스 해제")

    # 2단계: save_worker가 남은 큐 처리 + 변환 + 업로드 완료할 때까지 대기
    logger.debug("save_worker 종료 대기 중 (남은 프레임 변환 + 업로드)")
    for t in threads:
        if t.name == "save_worker":
            t.join(timeout=EVENT_RECORD_POST_SEC + 60.0)
            if t.is_alive():
                logger.event_warning(
                    EventType.MODULE_STOP,
                    "save_worker 종료 대기 시간 초과",
                    {"timeout_sec": EVENT_RECORD_POST_SEC + 60.0},
                )
            break

    # 업로드 완료 후 heartbeat 중단 — 먼저 멈추면 watchdog이 업로드 중 프로세스를 강제 종료함
    if heartbeat_writer is not None:
        try:
            heartbeat_writer.stop(timeout=1.0)
        except Exception:
            pass

    imu.stop()
    logger.event_info(EventType.SYSTEM_STOP, "Person Detection System 종료 완료")
    try:
        import subprocess as _sp
        _sp.run(["stty", "sane"], check=False)
    except Exception:
        pass


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

def main():
    """메인 함수 - 전체 시스템 흐름 제어

    흐름:
        1. 모델 로드
        2. 카메라 초기화
        3. 공유 자원 준비
        4. 스레드 시작 (캡처 / 추론 / IMU / 저장)
        5. 부저 초기화
        6. 메인 표시 루프 (프레임 획득 → 시각화 → 키 입력)
        7. 정리 (스레드 종료, 리소스 해제)
    """
    logger.event_info(EventType.SYSTEM_START, "Person Detection System 시작")
    bootstrap_heartbeat(
        status="starting",
        extra={
            "pid": os.getpid(),
            "script": __file__,
        },
    )
    heartbeat_writer: Optional[HeartbeatWriter] = None
    camera_health_thread: Optional[threading.Thread] = None
    runtime_stop_event = threading.Event()

    # Watchdog 테스트 모드 확인
    if WATCHDOG_TEST_MODE:
        logger.event_warning(EventType.MODULE_INIT,
                             f"⚠️ WATCHDOG 테스트 모드 활성화: {WATCHDOG_TEST_DELAY}초 후 강제 종료됩니다",
                             {"test_delay": WATCHDOG_TEST_DELAY})
        _start_watchdog_timer()

    # 1. 카메라 초기화
    cameras = init_cameras()
    if cameras is None:
        return
    states: List[SharedState] = [SharedState() for _ in cameras]

    # 2. 카메라별 독립 모델 로드 (ByteTrack 상태 공유 방지)
    _loaded = [load_model() for _ in cameras]
    if any(m is None for m in _loaded):
        return
    models: List[Any] = [m for m in _loaded if m is not None]

    # 3. 공유 자원 준비
    save_queue       = queue.Queue(maxsize=512)
    save_stop_event  = threading.Event()
    inference_stop_event = threading.Event()
    sensor_stop_event = threading.Event()
    fps_map: Dict[int, float] = {}
    state_map    = {cam_id: state for cam_id, state in zip(CAMERA_INDICES, states)}
    fps_counters = {cam_id: FPSCounter() for cam_id in CAMERA_INDICES}

    imu_buffer = SensorBuffer(maxlen=1)
    get_sensor_snapshot = _build_sensor_getter(imu_buffer)

    # 4. 스레드 시작
    imu = IMU()
    threads: List[threading.Thread] = (
        start_capture_threads(cameras, states, fps_map, save_queue)
        + start_inference_thread(models, states, get_sensor_snapshot, inference_stop_event)
        + start_sensor_threads(imu, sensor_stop_event, imu_buffer)
        + [start_save_thread(save_queue, save_stop_event, fps_map, get_sensor_snapshot, state_map)]
        + [start_event_upload_worker([s.event_queue for s in states], inference_stop_event)]
    )
    logger.event_info(EventType.MODULE_START, f"{len(cameras)}개 카메라 스레드 시작 완료")

    # 5. 부저 초기화
    buzzer = Buzzer(pin=32, use_board=True)
    buzzer.start()

    heartbeat_writer = HeartbeatWriter(
        cameras=cameras,
        states=states,
        save_queue=save_queue,
        upload_status_getter=get_upload_status_snapshot,
    )
    heartbeat_writer.start()
    camera_health_thread = _start_camera_health_monitor(cameras, states, runtime_stop_event)

    # 6. PyQt5 UI 실행 (SharedState 리스트를 LiveScreen에 주입)
    try:
        app = QApplication(sys.argv)
        window = MainApp(shared_states=states, buzzer=buzzer)
        def _request_shutdown(signum, _frame) -> None:
            logger.event_warning(EventType.USER_INPUT, "종료 신호 감지", {"signal": signum})
            runtime_stop_event.set()
            app.quit()

        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(signum, _request_shutdown)
            except Exception:
                pass
        window.show()
        app.exec_()
    except KeyboardInterrupt:
        logger.event_warning(EventType.USER_INPUT, "키보드 인터럽트로 종료")
    except Exception as e:
        logger.event_error(EventType.ERROR_OCCURRED, "메인 루프 오류 발생",
                           {"error": str(e)}, exc_info=True)
    finally:
        runtime_stop_event.set()
        # Qt 소멸자 순서 보장: window → app 순으로 명시적 삭제
        # (GC가 역순으로 삭제하면 "terminate called without an active exception" 발생)
        try:
            window.close()
            del window
        except Exception:
            pass
        try:
            del app
        except Exception:
            pass
        # UI가 종료된 뒤 _cleanup을 비복시(non-daemon) 스레드로 실행
        try:
            if camera_health_thread is not None:
                camera_health_thread.join(timeout=1.0)
        except Exception:
            logger.event_warning(EventType.MODULE_STOP, "CameraHealthMonitor 정지 실패")
        # 메인 스레드가 UI 메시지 폼프 없이 즉시 리턴하므로 OS 응답 없음 다이얼로그 미표시
        cleanup_thread = threading.Thread(
            target=_cleanup,
            args=(cameras, states, threads, save_stop_event,
                  inference_stop_event, sensor_stop_event, imu, buzzer,
                  heartbeat_writer),
            daemon=False,
            name="cleanup_main",
        )
        cleanup_thread.start()
        # 메인 스레드 종료 → Python이 non-daemon 스레드(cleanup)가 끝날 때까지 프로세스 유지


def _launch_watchdog_and_wait() -> int:
    """main.py를 직접 실행했을 때 watchdog를 먼저 띄우고 종료를 기다립니다."""
    env = os.environ.copy()
    env[MAIN_SUPERVISED_ENV] = "1"

    popen_kwargs = {
        "env": env,
        "cwd": PROJECT_ROOT,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True

    watchdog_process = subprocess.Popen(
        [sys.executable, WATCHDOG_SCRIPT_PATH],
        **popen_kwargs,
    )

    logger.event_info(
        EventType.SYSTEM_START,
        "Watchdog 런처 시작",
        {"watchdog_script": WATCHDOG_SCRIPT_PATH, "watchdog_pid": watchdog_process.pid},
    )

    try:
        return watchdog_process.wait()
    except KeyboardInterrupt:
        logger.event_warning(EventType.USER_INPUT, "런처 종료 신호 감지")
        _terminate_process_group(watchdog_process, "launcher keyboard interrupt")
        return 130
    finally:
        if watchdog_process.poll() is None:
            _terminate_process_group(watchdog_process, "launcher shutdown")


def _terminate_process_group(process: subprocess.Popen, reason: str, timeout: float = 5.0) -> None:
    """Terminate a subprocess and its child process group/session."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except Exception as exc:
        logger.event_warning(
            EventType.MODULE_STOP,
            "프로세스 그룹 SIGTERM 전송 실패",
            {"reason": reason, "pid": process.pid, "error": str(exc)},
        )
        try:
            process.terminate()
        except Exception:
            pass

    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except Exception as exc:
            logger.event_error(
                EventType.ERROR_OCCURRED,
                "프로세스 그룹 SIGKILL 전송 실패",
                {"reason": reason, "pid": process.pid, "error": str(exc)},
            )


if __name__ == "__main__":
    if os.environ.get(MAIN_SUPERVISED_ENV) == "1":
        main()
    else:
        raise SystemExit(_launch_watchdog_and_wait())
