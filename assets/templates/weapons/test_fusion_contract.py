import unittest
import numpy as np
from tankbot import TargetPoseEstimate
from perception.fusion_tracker import FusionTracker


class FusionContractTest(unittest.TestCase):
    def test_empty_observations_contract(self) -> None:
        tracker: FusionTracker = FusionTracker(np.array([1.0,0.0],dtype=np.float64),np.eye(2,dtype=np.float64),np.eye(2,dtype=np.float64))
        result: TargetPoseEstimate | None = tracker.update(np.empty((0,2),dtype=np.float64),np.empty((0,2),dtype=np.float64),np.zeros(3,dtype=np.float64),dt=1.0)
        if result is not None:
            self.assertIsInstance(result,TargetPoseEstimate)
            self.assertTrue(np.isfinite(np.array([result.x_m,result.y_m,result.yaw_rad])).all())
