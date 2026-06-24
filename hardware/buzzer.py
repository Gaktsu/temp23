"""
경고음 제어 (sounds 파일 재생)
"""

import os
import shutil
import subprocess

# 기존 GPIO 부저 로직은 사용하지 않음.
# try:
#     import RPi.GPIO as GPIO
# except Exception:
#     GPIO = None


class Buzzer:
    """경고음 제어 클래스 (기존 Buzzer 인터페이스 유지)"""

    def __init__(self, pin: int = 32, use_board: bool = True, sound_path: str = None):
        self.pin = pin
        self.use_board = use_board
        self.sound_path = sound_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "sounds",
            "audley_fergine-warning-alarm-loop-2-314878.mp3",
        )
        self.is_active = False
        self._initialized = False
        self._process = None
        self._player_cmd = None

    def start(self) -> bool:
        """경고음 재생 준비"""
        if not os.path.exists(self.sound_path):
            print(f"경고음 파일을 찾을 수 없습니다: {self.sound_path}")
            self._initialized = False
            return False

        if shutil.which("gst-launch-1.0") is not None:
            self._player_cmd = [
                "gst-launch-1.0",
                "-q",
                "filesrc",
                f"location={self.sound_path}",
                "!",
                "decodebin",
                "!",
                "audioconvert",
                "!",
                "audioresample",
                "!",
                "autoaudiosink",
            ]
        elif shutil.which("ffplay") is not None:
            self._player_cmd = [
                "ffplay",
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "error",
                "-stream_loop",
                "-1",
                self.sound_path,
            ]
        else:
            print("사용 가능한 경고음 플레이어(gst-launch-1.0/ffplay)가 없습니다.")
            self._initialized = False
            return False

        # 기존 GPIO 부저 초기화 로직은 사용하지 않음.
        # GPIO.setwarnings(False)
        # GPIO.setmode(GPIO.BOARD if self.use_board else GPIO.BCM)
        # GPIO.setup(self.pin, GPIO.OUT, initial=GPIO.LOW)
        self.is_active = False
        self._initialized = True
        return True

    def activate(self):
        """경고음 재생 시작"""
        if not self._initialized:
            if not self.is_active:
                print("경고음 활성화")
            self.is_active = True
            return

        if self._process is not None and self._process.poll() is None:
            self.is_active = True
            return

        self._process = subprocess.Popen(
            self._player_cmd,
            stdout=subprocess.DEVNULL,
        )
        self.is_active = True

    def deactivate(self):
        """경고음 재생 중지"""
        if not self._initialized:
            if self.is_active:
                print("경고음 비활성화")
            self.is_active = False
            return

        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1)
        self._process = None
        self.is_active = False

    def stop(self):
        """경고음 정리"""
        self.deactivate()
        # 기존 GPIO 정리 로직은 사용하지 않음.
        # if GPIO is not None and self._initialized:
        #     GPIO.cleanup(self.pin)
        self._initialized = False
