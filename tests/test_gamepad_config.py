"""Input configuration stays optional for old profiles and never grants actuator rights."""
import copy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/name) for name in ('host','protocol','sdk/python')]
from tankbot_host.authority import Authority, load_config
from tankbot_protocol.validation import Validator, Rejected


class GamepadConfigTests(unittest.TestCase):
    def test_legacy_profile_and_strict_complete_gamepad_settings(self):
        config=load_config(ROOT/'config/m1.json')
        validator=Validator(config,'configuration')
        legacy=copy.deepcopy(config);legacy['view'].pop('gamepad')
        validator.structure(legacy,'simulation-profile.schema.json')
        for mutation in ('missing_axis','bad_deadzone','zero_threshold','too_fast'):
            value=copy.deepcopy(config);joy=value['view']['gamepad']
            if mutation=='missing_axis':del joy['axes']['forward']
            elif mutation=='bad_deadzone':joy['deadzone']=1
            elif mutation=='zero_threshold':joy['button_threshold']=0
            else:joy['refresh_ms']=1
            with self.assertRaises(Rejected,msg=mutation):validator.structure(value,'simulation-profile.schema.json')

    def test_input_settings_are_public_but_robot_lease_still_rejects_manual_controls(self):
        config=load_config(ROOT/'config/m1.json')
        config['control_sources']={key:'robot' for key in config['control_sources']}
        authority=Authority(config,controlled=True)
        self.addCleanup(authority.close)
        public=authority.public_profile()
        self.assertEqual(public['view']['gamepad'],config['view']['gamepad'])
        for send,value in ((authority.keyboard,{'linear':{'x':1,'y':0,'z':0},'angular':{'x':0,'y':0,'z':0}}),
                           (authority.turret_keyboard,{'velocity_radps':1}),
                           (authority.fire_keyboard,{'request_id':'gamepad-test'})):
            with self.assertRaisesRegex(Rejected,'UNAUTHORIZED'):send(value)


if __name__=='__main__':unittest.main()
