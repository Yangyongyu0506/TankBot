import unittest
import numpy as np
from tankbot import AimInput, AimOutput
from weapons.target_prediction import TargetPredictor
from weapons.auto_aim import AutoAim


class PredictiveContractTest(unittest.TestCase):
    def test_no_target_predictor_and_controller(self) -> None:
        observation: AimInput = AimInput(None,0.0,np.zeros(3,dtype=np.float64),0.0,0.0,True)
        predictor: TargetPredictor = TargetPredictor(1.0,np.array([[1.0,0.0,0.0]],dtype=np.float64))
        self.assertIsNone(predictor.update(observation,dt=1.0))
        controller: AutoAim = AutoAim(1.0,1.0)
        result: AimOutput = controller.update(observation,dt=1.0)
        self.assertIsInstance(result,AimOutput)
        self.assertFalse(result.fire)
        self.assertTrue(np.isfinite(result.acceleration_radps2))
