import unittest
import numpy as np
from tankbot import AimInput, AimOutput
from weapons.auto_aim import AutoAim


class AutoAimContractTest(unittest.TestCase):
    def test_no_target_output_contract(self) -> None:
        controller: AutoAim = AutoAim(projectile_speed_mps=1.0,max_acceleration_radps2=1.0)
        observation: AimInput = AimInput(None,0.0,np.zeros(3,dtype=np.float64),0.0,0.0,True)
        result: AimOutput = controller.update(observation,dt=1.0)
        self.assertIsInstance(result,AimOutput)
        self.assertIsInstance(result.fire,bool)
        self.assertTrue(np.isfinite(result.acceleration_radps2))
