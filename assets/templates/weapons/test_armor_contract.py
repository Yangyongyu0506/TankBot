import unittest
import numpy as np
from tankbot import TargetPoseEstimate
from perception.armor_tracker import ArmorTracker


class ArmorContractTest(unittest.TestCase):
    def test_empty_observations_contract(self) -> None:
        mounts: np.ndarray = np.array([[1.,0.,0.],[-1.,0.,-np.pi],[0.,1.,np.pi/2],[0.,-1.,-np.pi/2]],dtype=np.float64)
        tracker: ArmorTracker = ArmorTracker(mounts,np.eye(2,dtype=np.float64))
        result: TargetPoseEstimate | None = tracker.update(np.empty((0,2),dtype=np.float64),np.zeros(3,dtype=np.float64),dt=1.0)
        if result is not None:
            self.assertIsInstance(result,TargetPoseEstimate)
            self.assertTrue(np.isfinite(np.array([result.x_m,result.y_m,result.yaw_rad])).all())
