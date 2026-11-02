"""Frozen pre-refactor traces, model isolation and reusable scene/sensor lifecycles."""
import copy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_host.authority import Authority,CoreAdapter,load_config
from tankbot_host.campaign import configure,RadarSimulator
from tankbot_host.weapon_sensors import ArmorDetectionSimulator
from tankbot_host.chassis_profiles import apply_profiles,load_profiles,wheel_calibration_for
from tankbot_host.scene_definition import resolve_scene,SceneResolver
from tankbot_host.sensor_instances import SensorScheduler
from tankbot_host.level_plugins import LevelValidationError


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class ResolvedSceneTests(unittest.TestCase):
    def setUp(self):self.base=load_config(ROOT/'config/game.yaml')

    def test_twelve_pre_refactor_traces_and_unified_sensor_frames_match(self):
        baseline=json.loads((ROOT/'tests/fixtures/simulator-before.json').read_text())
        for key,expected in baseline.items():
            lid,chassis=key.split(':')
            with self.subTest(level=lid,chassis=chassis):
                c=configure(self.base,lid);c['scene']['default_chassis']=chassis;apply_profiles(c,dynamics=True)
                scene=resolve_scene(c);scheduler=SensorScheduler(scene.sensors,c)
                core=CoreAdapter(c,chassis);radar=RadarSimulator(c);armor=ArmorDetectionSimulator(c)
                states=[];frames=[]
                try:
                    for tick in range(180):
                        state=core.snapshot;states.append(state)
                        frame=[radar.sample(state,tick),armor.sample(state,tick)];frames.append(frame)
                        batch={s.type:p for s,p in scheduler.sample(state,tick)}
                        self.assertEqual([batch.get('radar'),batch.get('armor_detector')],frame)
                        self.assertEqual(scheduler.sample(state,tick),())
                        if state['sensors'] is not None:self.assertIn('imu',batch)
                        core.call({'op':'step','target':{'vx':.3,'vy':0.,'wz':.15,'source_tick':tick}})
                    self.assertEqual({'physics':digest(states),'sensors':digest(frames)},expected)
                    scheduler.reset()
                    first={s.type:p for s,p in scheduler.sample(states[0],0)}
                    self.assertEqual([first.get('radar'),first.get('armor_detector')],frames[0])
                    scheduler.sample(states[2],2)
                    with self.assertRaisesRegex(ValueError,'TIME_REVERSED'):scheduler.sample(states[0],0)
                finally:core.close();scheduler.close()
                with self.assertRaisesRegex(ValueError,'CLOSED'):scheduler.sample(states[0],0)

    def test_full_model_parameters_and_enemy_model_are_independent(self):
        c=copy.deepcopy(self.base)
        diff=c['chassis_profiles']['differential'];omni=c['chassis_profiles']['omnidirectional']
        diff['body']['mass_kg']=31.;diff['servo']['max_force_x_n']=3.;diff['wheels']['radius_m']=.12
        omni['body']['mass_kg']=11.;omni['body']['yaw_inertia_kg_m2']=.7
        omni['servo']['max_force_x_n']=47.;omni['wheels']['radius_m']=.08
        load_profiles(c);c=configure(c,'c5')
        self.assertEqual(c['body']['mass_kg'],31.)
        self.assertEqual(c['wheels']['radius_m'],.12)
        target=c['weapons']['targets'][0]
        self.assertEqual(target['body']['mass_kg'],11.)
        self.assertEqual(target['servo']['max_force_x_n'],47.)
        self.assertEqual(wheel_calibration_for(c,'omnidirectional')['radius_m'],.08)
        scene=resolve_scene(c);self.assertEqual(scene.robots[1].chassis.to_dict()['body']['mass_kg'],11.)
        def velocity(config):
            core=CoreAdapter(config,'differential')
            try:
                state=core.call({'op':'step'})
                return abs(state['targets'][0]['velocity'][0])
            finally:core.close()
        strong=velocity(c);weak=copy.deepcopy(c);weak['weapons']['targets'][0]['servo']['max_force_x_n']=.1
        self.assertGreater(strong,velocity(weak))
        c['scene']['default_chassis']='omnidirectional';apply_profiles(c,dynamics=True)
        self.assertEqual(c['body']['mass_kg'],11.);self.assertEqual(c['wheels']['radius_m'],.08)

    def test_cached_definition_is_immutable_and_retries_get_fresh_state(self):
        scene=resolve_scene(configure(self.base,'c2'));resolver=SceneResolver(scene)
        self.assertIs(resolver.get('c2'),scene)
        with patch('tankbot_host.campaign.configure',wraps=configure) as compile_level:
            second=resolver.get('c5');self.assertIs(resolver.get('c5'),second)
            self.assertEqual(compile_level.call_count,1)
        with self.assertRaises(FrozenInstanceError):scene.world.physics_hz=99
        dto=scene.to_config();dto['scene']['walls'].clear()
        self.assertTrue(scene.world.walls);self.assertTrue(scene.to_config()['scene']['walls'])
        with patch('tankbot_host.level_plugins.read_definition',side_effect=AssertionError('must not read assets on retry')):
            a=Authority(scene,controlled=True);b=Authority(scene,controlled=True)
            try:
                self.assertIs(a.scene,b.scene);self.assertNotEqual(a.run_id,b.run_id)
                before=copy.deepcopy(b._private)
                for _ in range(12):a.advance()
                self.assertEqual(b._private,before)
                self.assertEqual(b.tick,0);self.assertEqual(a.tick,12)
                self.assertIsNot(a.sensor_scheduler,b.sensor_scheduler)
                a.config['scene']['walls'].clear();self.assertTrue(b.config['scene']['walls'])
            finally:a.close();b.close()

    def test_bad_instances_fail_before_core_creation(self):
        for field,value in [('robot_id','missing'),('period_ticks',0),('mount',{'parent_frame':'base_link','translation_m':[1,0],'yaw_rad':0})]:
            c=configure(self.base,'c2');c['campaign']['levels']['c2']['sensors'][0][field]=value
            with self.subTest(field=field),patch('tankbot_host.authority.CoreAdapter') as core:
                with self.assertRaises((ValueError,LevelValidationError)):Authority(c)
                core.assert_not_called()
        c=configure(self.base,'c2');s=c['campaign']['levels']['c2']['sensors'];s[1]['id']=s[0]['id']
        with self.assertRaises(LevelValidationError):resolve_scene(c)
        c=configure(self.base,'c2');s=c['campaign']['levels']['c2']['sensors'];s[0]['period_ticks']=6;s[0]['update_hz']=10
        with self.assertRaisesRegex(ValueError,'sample period'):resolve_scene(c)


if __name__=='__main__':unittest.main()
