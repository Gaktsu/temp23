"""
Watchdog process that supervises the main control program.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import (
    HEARTBEAT_PATH,
    MAIN_SCRIPT_PATH,
    WATCHDOG_LOG_PATH,
    WATCHDOG_POLL_INTERVAL_SEC,
    WATCHDOG_RESTART_DELAY_SEC,
    WATCHDOG_STALE_THRESHOLD_SEC,
    WATCHDOG_STARTUP_GRACE_SEC,
)


@dataclass
class HeartbeatSnapshot:
    last_update_epoch: float = 0.0
    status: str = "unknown"
    camera_status: str = "unknown"
    raw: Optional[dict] = None


class Watchdog:
    """Monitor main.py heartbeat and restart the process when it stalls."""

    def __init__(
        self,
        main_script_path: str = MAIN_SCRIPT_PATH,
        heartbeat_path: str = HEARTBEAT_PATH,
        poll_interval_sec: float = WATCHDOG_POLL_INTERVAL_SEC,
        stale_threshold_sec: float = WATCHDOG_STALE_THRESHOLD_SEC,
        startup_grace_sec: float = WATCHDOG_STARTUP_GRACE_SEC,
        restart_delay_sec: float = WATCHDOG_RESTART_DELAY_SEC,
    ) -> None:
        self.main_script_path = main_script_path
        self.heartbeat_path = heartbeat_path
        self.poll_interval_sec = poll_interval_sec
        self.stale_threshold_sec = stale_threshold_sec
        self.startup_grace_sec = startup_grace_sec
        self.restart_delay_sec = restart_delay_sec
        self._logger = self._configure_logger()
        self._stop_requested = False
        self._launch_count = 0

    def _configure_logger(self) -> logging.Logger:
        os.makedirs(os.path.dirname(WATCHDOG_LOG_PATH), exist_ok=True)
        logger = logging.getLogger("jetson.watchdog")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        file_handler = logging.FileHandler(WATCHDOG_LOG_PATH, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        logger.propagate = False
        return logger

    def _log(self, level: int, message: str, extra: Optional[dict] = None) -> None:
        if extra:
            message = f"{message} | {json.dumps(extra, ensure_ascii=False)}"
        self._logger.log(level, message)

    def _load_heartbeat(self) -> HeartbeatSnapshot:
        if not os.path.exists(self.heartbeat_path):
            return HeartbeatSnapshot()

        try:
            with open(self.heartbeat_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            self._log(logging.WARNING, "heartbeat.json 읽기 실패", {"error": str(exc)})
            return HeartbeatSnapshot()

        camera_status = "unknown"
        camera_section = payload.get("camera", {}) if isinstance(payload, dict) else {}
        if isinstance(camera_section, dict):
            statuses = [str(item.get("status", "unknown")) for item in camera_section.values() if isinstance(item, dict)]
            if any(status in {"stale", "reconnecting", "stopped"} for status in statuses):
                camera_status = "degraded"
            elif statuses:
                camera_status = "ok"

        return HeartbeatSnapshot(
            last_update_epoch=float(payload.get("last_update_epoch", 0.0) or 0.0),
            status=str(payload.get("status", "unknown")),
            camera_status=camera_status,
            raw=payload,
        )

    def _launch_main(self) -> subprocess.Popen:
        self._launch_count += 1
        self._log(
            logging.INFO,
            "메인 프로세스 실행",
            {"launch_count": self._launch_count, "script": self.main_script_path},
        )
        try:
            if os.path.exists(self.heartbeat_path):
                os.remove(self.heartbeat_path)
        except Exception as exc:
            self._log(logging.WARNING, "기존 heartbeat 삭제 실패", {"error": str(exc)})
        kwargs = {"stdout": None, "stderr": None, "stdin": None}
        env = os.environ.copy()
        env["JETSON_MAIN_SUPERVISED"] = "1"
        kwargs["env"] = env
        if os.name == "posix":
            kwargs["start_new_session"] = True
        return subprocess.Popen([sys.executable, self.main_script_path], **kwargs)

    def _terminate_process(self, process: subprocess.Popen, reason: str) -> None:
        self._log(logging.WARNING, "메인 프로세스 종료 시도", {"reason": reason, "pid": process.pid})
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except Exception as exc:
            self._log(logging.WARNING, "SIGTERM 전송 실패", {"error": str(exc)})
            try:
                process.terminate()
            except Exception:
                pass

        deadline = time.time() + 5.0
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.2)

        if process.poll() is None:
            self._log(logging.WARNING, "메인 프로세스 강제 종료", {"reason": reason, "pid": process.pid})
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except Exception as exc:
                self._log(logging.ERROR, "강제 종료 실패", {"error": str(exc)})

    def _should_restart_for_stale_heartbeat(
        self,
        heartbeat: HeartbeatSnapshot,
        process: subprocess.Popen,
        runtime_start: float,
    ) -> bool:
        if process.poll() is not None:
            return False

        now = time.time()
        if heartbeat.last_update_epoch <= 0.0:
            if now - runtime_start < self.startup_grace_sec:
                return False
            self._log(
                logging.ERROR,
                "heartbeat.json이 아직 생성되지 않았습니다",
                {"elapsed_sec": round(now - runtime_start, 2), "grace_sec": self.startup_grace_sec},
            )
            return True

        if heartbeat.last_update_epoch < runtime_start:
            if now - runtime_start < self.startup_grace_sec:
                return False

            self._log(
                logging.ERROR,
                "현재 실행에서 heartbeat가 아직 갱신되지 않았습니다",
                {
                    "elapsed_sec": round(now - runtime_start, 2),
                    "launch_epoch": round(runtime_start, 3),
                    "heartbeat_epoch": round(heartbeat.last_update_epoch, 3),
                    "grace_sec": self.startup_grace_sec,
                },
            )
            return True

        age_sec = now - heartbeat.last_update_epoch
        if age_sec <= self.stale_threshold_sec:
            return False

        if heartbeat.camera_status == "degraded" and age_sec <= self.stale_threshold_sec + self.poll_interval_sec:
            self._log(
                logging.WARNING,
                "카메라 이상으로 보이는 heartbeat 지연 감지 - 재연결 유예",
                {
                    "age_sec": round(age_sec, 2),
                    "threshold_sec": self.stale_threshold_sec,
                    "poll_interval_sec": self.poll_interval_sec,
                    "status": heartbeat.status,
                    "camera_status": heartbeat.camera_status,
                },
            )
            return False

        self._log(
            logging.ERROR,
            "heartbeat 갱신 중단 감지",
            {
                "age_sec": round(age_sec, 2),
                "threshold_sec": self.stale_threshold_sec,
                "status": heartbeat.status,
                "camera_status": heartbeat.camera_status,
            },
        )
        return True

    def _monitor_process(self, process: subprocess.Popen, runtime_start: float) -> str:
        while not self._stop_requested:
            heartbeat = self._load_heartbeat()
            if self._should_restart_for_stale_heartbeat(heartbeat, process, runtime_start):
                return "restart"

            returncode = process.poll()
            if returncode is not None:
                if returncode == 0:
                    self._log(logging.INFO, "메인 프로세스 정상 종료", {"returncode": returncode})
                    return "exit"
                self._log(logging.WARNING, "메인 프로세스 비정상 종료", {"returncode": returncode})
                return "restart"

            time.sleep(self.poll_interval_sec)

        return "stop"

    def run(self) -> None:
        self._log(
            logging.INFO,
            "Watchdog 시작",
            {
                "main_script": self.main_script_path,
                "heartbeat_path": self.heartbeat_path,
                "poll_interval_sec": self.poll_interval_sec,
                "stale_threshold_sec": self.stale_threshold_sec,
            },
        )

        while not self._stop_requested:
            process = self._launch_main()
            runtime_start = time.time()
            outcome = self._monitor_process(process, runtime_start)

            if outcome == "exit":
                break
            if outcome == "stop":
                self._terminate_process(process, "watchdog stop requested")
                break

            self._terminate_process(process, "heartbeat stale or abnormal exit")
            self._log(
                logging.INFO,
                "메인 프로세스 재시작 대기",
                {"restart_delay_sec": self.restart_delay_sec},
            )
            time.sleep(self.restart_delay_sec)

        self._log(logging.INFO, "Watchdog 종료")

    def stop(self) -> None:
        self._stop_requested = True


if __name__ == "__main__":
    Watchdog().run()
