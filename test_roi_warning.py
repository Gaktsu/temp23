"""
post_fixed_roi_warning_event 테스트 스크립트
랜덤으로 cam_id와 WarningLevel을 선택해 전송합니다.
"""
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.detector import WarningLevel
from pipeline.uploader import post_fixed_roi_warning_event
from config.settings import CAMERA_INDICES

LEVELS = [WarningLevel.BLIND_SPOT, WarningLevel.APPROACH, WarningLevel.URGENT]

cam_id = random.choice(CAMERA_INDICES)
warning_level = random.choice(LEVELS)

print(f"cam_id      : {cam_id}")
print(f"warning_level: {warning_level.name}")
print(f"전송 중...")

result = post_fixed_roi_warning_event(warning_level, cam_id)
print(f"결과: {'성공' if result else '실패'}")
