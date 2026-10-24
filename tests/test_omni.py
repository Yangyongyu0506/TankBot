"""Radial omni observations and public calibration, checked independently of renderer math."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'host'),str(ROOT/'protocol'),str(ROOT/'sdk/python'),str(ROOT/'examples/robot')]
from tankbot_host.authority import CoreAdapter,load_config
from localization.kinematics import body_increment


class OmniTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config(ROOT/'config/game.yaml')

    def core(self,config=None):
        c=CoreAdapter(config or self.config,'omnidirectional');self.addCleanup(c.close);return c

    def test_basis_and_mixed_motion_use_tangential_projection(self):
        r=self.config['wheels']['radius_m'];R=self.config['wheels']['omnidirectional']['center_radius_m']
        s=math.sqrt(.5)
        # Rows are independently stated for FL=45, FR=315, RL=135, RR=225 degrees.
        matrix=[[-s,s,R],[s,s,R],[-s,-s,R],[s,-s,R]]
        for velocity in ([1,0,0],[0,1,0],[0,0,1],[.7,-.3,.8],[-.2,.6,-1.2]):
            c=copy.deepcopy(self.config);c['scene']['initial_velocity']=velocity
            core=self.core(c);sample=core.snapshot['sensors']['joint_states']
            expected=[sum(a*b for a,b in zip(row,velocity))/r for row in matrix]
            self.assertEqual(sample['name'],['front_left','front_right','rear_left','rear_right'])
            for actual,want in zip(sample['velocity'],expected):self.assertAlmostEqual(actual,want,delta=1e-10)
            recovered=body_increment(sample['name'],sample['velocity'],c['wheels'])
            for actual,want in zip(recovered,velocity):self.assertAlmostEqual(actual,want,delta=1e-10)

    def test_all_wheels_rotate_same_sign_for_positive_yaw(self):
        c=copy.deepcopy(self.config);c['scene']['initial_velocity']=[0,0,1]
        rates=self.core(c).snapshot['sensors']['joint_states']['velocity']
        expected=c['wheels']['omnidirectional']['center_radius_m']/c['wheels']['radius_m']
        self.assertTrue(all(abs(rate-expected)<1e-10 for rate in rates))

    def test_sensor_and_calibration_reordering_preserves_named_inverse(self):
        c=copy.deepcopy(self.config);c['scene']['initial_velocity']=[.4,-.2,.5]
        c['wheels']['omnidirectional']['wheels'].reverse()
        sample=self.core(c).snapshot['sensors']['joint_states']
        result=body_increment(sample['name'][::-1],sample['velocity'][::-1],c['wheels'])
        for actual,want in zip(result,c['scene']['initial_velocity']):self.assertAlmostEqual(actual,want,delta=1e-10)

    def test_geometry_parameters_affect_observation_without_changing_body_dynamics(self):
        c=copy.deepcopy(self.config);c['wheels']['omnidirectional']['center_radius_m']*=.8
        c['wheels']['omnidirectional']['wheels']=[{**w,'azimuth_deg':(w['azimuth_deg']+15)%360} for w in c['wheels']['omnidirectional']['wheels']]
        original=self.core();changed=self.core(c)
        for tick in range(30):
            request={'op':'step','target':{'vx':.5,'vy':.25,'wz':.4,'source_tick':tick}}
            a=original.call(request);b=changed.call(request)
            self.assertEqual(a['truth_pose'],b['truth_pose']);self.assertEqual(a['truth_velocity'],b['truth_velocity'])
            if b['sensors']:
                sample=b['sensors']['joint_states']
                recovered=body_increment(sample['name'],sample['velocity'],c['wheels'])
                for actual,want in zip(recovered,b['truth_velocity']):self.assertAlmostEqual(actual,want,delta=1e-10)
        self.assertNotEqual(a['sensors']['joint_states']['velocity'],b['sensors']['joint_states']['velocity'])

    def test_non_symmetric_or_incomplete_calibration_fails_closed(self):
        variants=[]
        bad=copy.deepcopy(self.config);bad['wheels']['omnidirectional']['wheels'][0]['azimuth_deg']+=1;variants.append(bad)
        bad=copy.deepcopy(self.config);bad['wheels']['omnidirectional']['wheels'][0]['name']='front_right';variants.append(bad)
        bad=copy.deepcopy(self.config);bad['wheels']['omnidirectional']['center_radius_m']=0;variants.append(bad)
        bad=copy.deepcopy(self.config);bad['wheels']['omnidirectional']['geometry_version']='mecanum@1';variants.append(bad)
        bad=copy.deepcopy(self.config);del bad['wheels']['omnidirectional']['center_radius_m'];variants.append(bad)
        for c in variants:
            with self.subTest(wheels=c['wheels']):
                with self.assertRaises(ValueError):self.core(c)
                with tempfile.NamedTemporaryFile(mode='w',suffix='.json') as file:
                    json.dump(c,file);file.flush()
                    with self.assertRaises(ValueError):load_config(file.name)

    def test_reference_inverse_rejects_wrong_sample_names(self):
        for names in (['front_left']*4,['front_left','front_right','rear_left','unknown']):
            with self.assertRaises(ValueError):body_increment(names,[0]*4,self.config['wheels'])
