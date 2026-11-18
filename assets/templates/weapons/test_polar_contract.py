import unittest
import numpy as np
from tankbot import PolarTargetEstimate
from perception.polar_tracker import PolarTracker


class PolarContractTest(unittest.TestCase):
    def test_empty_measurements_contract(self) -> None:
        tracker: PolarTracker = PolarTracker(np.eye(2,dtype=np.float64))
        result: PolarTargetEstimate | None = tracker.update((),np.zeros(3,dtype=np.float64),dt=1.0)
        if result is not None:
            self.assertIsInstance(result,PolarTargetEstimate)
            self.assertGreaterEqual(result.range_m,0.0)
            self.assertTrue(np.isfinite(result.bearing_rad))
