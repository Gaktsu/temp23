"""
Sensor thread helpers for IMU polling.
"""
from __future__ import annotations

import threading
import time
from typing import List

from hardware.imu import IMU
from utils.logger import get_logger
from utils.sensor_sync import SensorBuffer

logger = get_logger("pipeline.sensors")


def start_sensor_threads(
    imu: IMU,
    stop_event: threading.Event,
    imu_buffer: SensorBuffer,
) -> List[threading.Thread]:
    """IMU 폴링 스레드 시작. 하드웨어 없으면 스레드 생략."""
    threads = []

    def _make_sensor_loop(sensor, buffer):
        def loop():
            while not stop_event.is_set():
                data = sensor.read_data()
                if data is not None:
                    buffer.add(time.time(), data)
                time.sleep(1.0)
        return loop

    if imu.start():
        t = threading.Thread(target=_make_sensor_loop(imu, imu_buffer), daemon=True, name="imu_worker")
        t.start()
        threads.append(t)
        logger.debug("IMU 스레드 시작")
    return threads
