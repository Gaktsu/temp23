import time
import unittest

from ai.detector import Detection, WarningLevel
from pipeline.inference import _count_persons_in_roi
from pipeline.shared_state import SharedState


class SafetyPipelineTests(unittest.TestCase):
    def _person(self, bbox):
        return Detection(
            bbox=bbox,
            confidence=0.9,
            class_id=0,
            class_name="person",
        )

    def test_roi_outside_detection_is_not_intrusion(self):
        state = SharedState()
        detections = [self._person((10, 10, 30, 40))]
        roi = [[100, 100], [200, 100], [200, 200], [100, 200]]
        roi_count = _count_persons_in_roi(detections, roi)

        state.update_detection_result(
            detections,
            WarningLevel.SAFE,
            roi_count > 0,
            time.time(),
            sensor_data=None,
        )

        self.assertEqual(state.last_detections, detections)
        self.assertFalse(state.is_intruding())
        self.assertEqual(state.snapshot().warning_level, WarningLevel.SAFE)

    def test_roi_inside_foot_point_is_intrusion(self):
        state = SharedState()
        detections = [self._person((120, 80, 160, 150))]
        roi = [[100, 100], [200, 100], [200, 200], [100, 200]]
        roi_count = _count_persons_in_roi(detections, roi)

        state.update_detection_result(
            detections,
            WarningLevel.BLIND_SPOT,
            roi_count > 0,
            time.time(),
            sensor_data=None,
        )

        self.assertEqual(roi_count, 1)
        self.assertTrue(state.is_intruding())
        self.assertEqual(state.snapshot().warning_level, WarningLevel.BLIND_SPOT)

    def test_missing_roi_forces_safe(self):
        state = SharedState()
        detections = [self._person((120, 80, 160, 150))]
        roi_count = _count_persons_in_roi(detections, None)

        state.update_detection_result(
            detections,
            WarningLevel.SAFE,
            roi_count > 0,
            time.time(),
            sensor_data=None,
        )

        self.assertEqual(roi_count, 0)
        self.assertFalse(state.is_intruding())
        self.assertEqual(state.snapshot().warning_level, WarningLevel.SAFE)

    def test_stale_intrusion_expires(self):
        state = SharedState()
        stale_ts = time.time() - 60.0
        state.update_detection_result(
            [self._person((120, 80, 160, 150))],
            WarningLevel.BLIND_SPOT,
            True,
            stale_ts,
            sensor_data=None,
        )

        self.assertFalse(state.is_intruding())
        self.assertEqual(state.snapshot().warning_level, WarningLevel.SAFE)


if __name__ == "__main__":
    unittest.main()
