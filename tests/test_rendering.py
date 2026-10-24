"""Authority-side checks for independent presentation settings."""
import copy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'protocol'),str(ROOT/'sdk/python')]
from tankbot_host.authority import Authority,CoreAdapter,load_config


class RenderingTests(unittest.TestCase):
    def test_visual_settings_do_not_change_physics(self):
        config=load_config(ROOT/'config/game.yaml')
        other=copy.deepcopy(config)
        other['view']['snapshot_hz']=10
        other['rendering']['viewport_width_m']=5
        other['rendering']['chassis_models']['differential']['hull']['length_m']=.5
        cores=[CoreAdapter(c,'differential') for c in (config,other)]
        try:
            for tick in range(30):
                request={'op':'step','target':{'vx':1,'vy':0,'wz':.2,'source_tick':tick}}
                self.assertEqual(cores[0].call(request),cores[1].call(request))
        finally:
            for core in cores:core.close()

    def test_profile_selects_independent_visuals_without_exposing_internal_model(self):
        config=load_config(ROOT/'config/game.yaml')
        profiles=[]
        for chassis in config['chassis']:
            c=copy.deepcopy(config);c['scene']['default_chassis']=chassis
            authority=Authority(c,controlled=True)
            try:
                profile=authority.public_profile();profiles.append(profile)
                self.assertNotIn('chassis_models',profile['rendering'])
                self.assertNotIn('mass_kg',profile['body'])
                self.assertEqual(profile['chassis_visual'],c['rendering']['chassis_models'][chassis])
                if chassis=='omnidirectional':
                    self.assertEqual(profile['wheel_calibration'],{'radius_m':c['wheels']['radius_m'],**c['wheels']['omnidirectional']})
                    self.assertNotIn('wheels',profile['chassis_visual'])
                else:self.assertIsNone(profile['wheel_calibration'])
                self.assertEqual(profile['view']['snapshot_hz'],30)
            finally:authority.close()
        self.assertNotEqual(profiles[0]['chassis_visual']['model_id'],profiles[1]['chassis_visual']['model_id'])
        self.assertNotEqual(profiles[0]['chassis_visual']['hull'],profiles[1]['chassis_visual']['hull'])
