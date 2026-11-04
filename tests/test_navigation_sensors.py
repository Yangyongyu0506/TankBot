"""Confirmed self-GPS and shared noisy encoders, deterministic sampling and isolation."""
import copy
import json
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure
from tankbot_host.sensor_instances import definitions,SensorScheduler
from tankbot_host.level_plugins import LevelValidationError


def sensor_configuration(base):
    config=configure(base,'navigation.c1')
    sensors=config['campaign']['levels']['navigation.c1']['sensors']
    sensors[0].update(parameters={'velocity_stddev_radps':.2,'gain_error_min':-.03,'gain_error_max':.03,'position_model':'integrated_rate_noise'},
                      random_stream={'id':'test-encoder','seed_mode':'named'})
    sensors.append({'id':'gps','robot_id':'player','type':'gps','period_ticks':30,'mount':{'parent_frame':'base_link','translation_m':[0.,0.],'yaw_rad':0.},
                    'random_stream':{'id':'test-gps','seed_mode':'named'},'topic':'/robot/sensors/gps/fix','schema':'position_fix2d@1','frame_id':'map',
                    'parameters':{'noise':{'position_stddev_m':.2,'bias_m':[0.,0.],'drop_probability':0.},'latency_ticks':0,'wall_occlusion':False}})
    return config


class NavigationSensorTests(unittest.TestCase):
    def setUp(self):
        self.base=load_config(ROOT/'config/game.yaml')
        self.config=sensor_configuration(self.base)

    def scheduler(self,config=None):
        c=config or self.config
        s=SensorScheduler(definitions(c),c);self.addCleanup(s.close);return s

    def private(self,tick):
        return {'truth_pose':[1.+tick/60,-2.,.3],
                'sensors':{'joint_states':{'name':['left','right'],'position':[tick/60,2*tick/60],'velocity':[1.,2.],'effort':[]}}}

    def test_duplicate_guard_reset_seed_and_stream_independence(self):
        first=self.scheduler();without_gps=copy.deepcopy(self.config)
        without_gps['campaign']['levels']['navigation.c1']['sensors'].pop()
        second=self.scheduler(without_gps)
        trace=[]
        for tick in range(0,91,2):
            state=self.private(tick);untouched=copy.deepcopy(state)
            batch={s.type:p for s,p in first.sample(state,tick)}
            trace.append(batch);self.assertEqual(first.sample(state,tick),())
            self.assertEqual(batch['wheel_encoder'],dict((s.type,p) for s,p in second.sample(state,tick))['wheel_encoder'])
            self.assertEqual(state,untouched)
            self.assertEqual('gps' in batch,tick%30==0)
        first.reset()
        replay=[{s.type:p for s,p in first.sample(self.private(tick),tick)} for tick in range(0,91,2)]
        self.assertEqual(trace,replay)
        different=copy.deepcopy(self.config);different['runtime']['seed']+=1
        self.assertNotEqual(trace[0],{s.type:p for s,p in self.scheduler(different).sample(self.private(0),0)})

    def test_gps_reports_only_noisy_position_and_measurement_covariance(self):
        scheduler=self.scheduler()
        samples=[]
        for tick in range(0,15000,30):
            private=self.private(tick)
            fix=dict((s.type,p) for s,p in scheduler.sample(private,tick))['gps']
            self.assertEqual(set(fix),{'position_m','covariance'})
            self.assertEqual(fix['covariance'],[.2**2,0.,0.,.2**2])
            samples.append(np.asarray(fix['position_m'])-private['truth_pose'][:2])
        values=np.asarray(samples)
        self.assertTrue(np.all(np.abs(np.mean(values,axis=0))<.04))
        self.assertTrue(np.all(np.abs(np.std(values,axis=0)-.2)<.03))

    def test_encoder_angle_and_rate_share_gain_and_noise_and_do_not_expose_ideal_fields(self):
        scheduler=self.scheduler();backend=scheduler.backend('wheel_encoder')
        self.assertTrue(all(.97<=gain<=1.03 for gain in backend.gains))
        zero=dict((s.type,p) for s,p in scheduler.sample(self.private(0),0))['wheel_encoder']
        next_state=self.private(2);sample=dict((s.type,p) for s,p in scheduler.sample(next_state,2))['wheel_encoder']
        for i in range(2):
            noise=sample['velocity'][i]-backend.gains[i]*next_state['sensors']['joint_states']['velocity'][i]
            expected=backend.gains[i]*next_state['sensors']['joint_states']['position'][i]+noise/30
            self.assertAlmostEqual(sample['position'][i],expected)
        self.assertEqual(set(zero),{'name','position','velocity','effort'})
        self.assertNotEqual(sample['velocity'],next_state['sensors']['joint_states']['velocity'])

    def test_invalid_navigation_streams_and_models_fail_during_resolution(self):
        for mutate in (
            lambda sensors:sensors[0]['random_stream'].update(seed_mode='legacy_seed'),
            lambda sensors:sensors[1]['parameters'].update(latency_ticks=1),
            lambda sensors:sensors[1]['parameters']['noise'].update(bias_m=[1.,0.]),
            lambda sensors:sensors[1]['parameters']['noise'].update(drop_probability=.1),
            lambda sensors:sensors[1].update(random_stream={}),
        ):
            c=copy.deepcopy(self.config);mutate(c['campaign']['levels']['navigation.c1']['sensors'])
            with self.assertRaises(LevelValidationError):definitions(c)
        standalone=copy.deepcopy(self.config);standalone['campaign']['active_level']=None
        unknown=copy.deepcopy(self.config['campaign']['levels']['navigation.c1']['sensors'][1])
        unknown.update(type='unknown_sensor',random_stream=None)
        standalone['sensor_instances']=[unknown]
        with self.assertRaises(LevelValidationError):definitions(standalone)

    def test_original_ideal_encoder_is_still_native_and_unchanged(self):
        c=configure(self.base,'navigation.c1');s=self.scheduler(c)
        self.assertEqual(s.instances[0].backend,'rust')
        state=self.private(0)
        self.assertEqual(s.sample(state,0)[0][1],state['sensors']['joint_states'])
        from tankbot_host.navigation import localization_parameters
        self.assertEqual(localization_parameters(c),{'wheel_rate_covariance':[[0.,0.],[0.,0.]],'gain_error_bounds':[0.,0.]})
