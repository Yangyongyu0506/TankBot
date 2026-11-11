"""Instantaneous scan model, immutable SDK values, independent lifecycle and streams."""
import copy
import json
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot import Scan2D,LocalControlInput,Twist
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure
from tankbot_host.scene_definition import resolve_scene
from tankbot_host.sensor_instances import SensorScheduler
from tankbot_host.distance_scan import DistanceScanSimulator


class ScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=resolve_scene(configure(load_config(ROOT/'config/game.yaml'),'navigation.c6')).to_config()
        from tankbot_host.sensor_instances import definitions
        cls.instances=definitions(cls.config)
        cls.instance=next(i for i in cls.instances if i.type=='distance_scan')

    def sensor(self,walls,noise=0):
        from dataclasses import replace
        p=json.loads(self.instance.parameters_json);p['noise_stddev_m']=noise
        sensor=DistanceScanSimulator(replace(self.instance,parameters_json=json.dumps(p)),walls,32)
        sensor.reset('isolated-scan');return sensor

    def test_angles_nearest_occlusion_min_max_and_no_return(self):
        sensor=self.sensor([{'center':[6.1,0],'size':[.2,.2]}, {'center':[3.1,0],'size':[.2,.2]},
                            {'center':[0,2.1],'size':[.2,.2]},{'center':[-.03,0],'size':[.02,.02]}])
        data=sensor.measure({'truth_pose':[0.,0.,0.]},6)
        scan=Scan2D(**data)
        self.assertEqual(len(scan.ranges_m),180);self.assertAlmostEqual(scan.angles_rad[45],np.pi/2)
        self.assertEqual(scan.ranges_m[0],3.);self.assertTrue(scan.hit_mask[0])
        self.assertEqual(scan.ranges_m[45],2.);self.assertTrue(scan.hit_mask[45])
        self.assertEqual(scan.ranges_m[90],.05);self.assertTrue(scan.hit_mask[90])
        self.assertEqual(scan.ranges_m[135],6.);self.assertFalse(scan.hit_mask[135])
        exact=self.sensor([{'center':[6.1,0],'size':[.2,.2]}]).measure({'truth_pose':[0.,0.,0.]},6)
        self.assertTrue(exact['hit_mask'][0]);self.assertEqual(exact['ranges_m'][0],6.)
        outside=self.sensor([{'center':[6.2,0],'size':[.2,.2]}]).measure({'truth_pose':[0.,0.,0.]},6)
        self.assertFalse(outside['hit_mask'][0])
        rotated=sensor.measure({'truth_pose':[0.,0.,np.pi/2]},12)
        self.assertAlmostEqual(rotated['ranges_m'][0],2.)

    def test_noise_repeat_reset_close_and_immutable_inputs(self):
        walls=[{'center':[2.1,0.],'size':[.2,10.]}]
        sensor=self.sensor(walls,.02);data=sensor.measure({'truth_pose':[0.,0.,0.]},6)
        self.assertEqual(data,sensor.measure({'truth_pose':[100.,0.,0.]},6))
        samples=[sensor.measure({'truth_pose':[0.,0.,0.]},tick)['ranges_m'][0]-2 for tick in range(12,6012,6)]
        self.assertLess(abs(float(np.mean(samples))),.003);self.assertAlmostEqual(float(np.std(samples)),.02,delta=.002)
        sensor.reset('isolated-scan');self.assertEqual(data,sensor.measure({'truth_pose':[0.,0.,0.]},6))
        scan=Scan2D(**data)
        observation=LocalControlInput(np.zeros(3),np.array([[0.,0.],[1.,0.]]),scan,Twist(),.1,.0,np.zeros(2),0.)
        for array in (scan.ranges_m,scan.hit_mask,scan.angles_rad,observation.estimated_pose,observation.reference_path,observation.wheel_rates_radps):
            with self.assertRaises(ValueError):array.setflags(write=True)
        sensor.close()
        with self.assertRaisesRegex(ValueError,'CLOSED'):sensor.measure({'truth_pose':[0.,0.,0.]},12)

    def test_js_roundtrip_integer_range_does_not_quantize_noisy_returns(self):
        from dataclasses import replace
        p=json.loads(self.instance.parameters_json);p['range_max_m']=6
        sensor=DistanceScanSimulator(replace(self.instance,parameters_json=json.dumps(p)),
                                     [{'center':[.6,0.],'size':[.2,2.]}],32)
        sensor.reset('js-roundtrip')
        scan=Scan2D(**sensor.measure({'truth_pose':[0.,0.,0.]},6))
        self.assertTrue(.4 < scan.ranges_m[0] < .6)
        self.assertNotEqual(scan.ranges_m[0],int(scan.ranges_m[0]))

    def test_scheduler_does_not_consume_encoder_or_gps_random_stream(self):
        a=SensorScheduler(self.instances,self.config)
        b=SensorScheduler([i for i in self.instances if i.type!='distance_scan'],self.config)
        private={'truth_pose':[0.,0.,0.], 'sensors':{'joint_states':{'name':['left','right'],'position':[0.,0.],'velocity':[0.,0.],'effort':[]}}}
        for tick in range(0,181,2):
            first=[(i.type,p) for i,p in a.sample(private,tick) if i.type!='distance_scan']
            self.assertEqual(first,[(i.type,p) for i,p in b.sample(private,tick)])
            self.assertEqual(a.sample(private,tick),())
        a.reset();b.reset()
        self.assertEqual([(i.type,p) for i,p in a.sample(private,0) if i.type!='distance_scan'],[(i.type,p) for i,p in b.sample(private,0)])
        a.close()
        with self.assertRaisesRegex(ValueError,'CLOSED'):a.sample(private,2)

    def test_fast_and_standard_schema_checks_are_equivalent_for_scan_arrays(self):
        from tankbot_protocol.validation import Validator
        from tankbot_protocol.message import envelope
        v=Validator(self.config,'array-check');payload=self.sensor([{'center':[6.1,0.],'size':[.2,.2]}]).measure({'truth_pose':[0.,0.,0.]},6)
        base=envelope('scan2d@1','/robot/sensors/scan',payload,tick=6,hz=60,run_id='array-check',publisher_id='sensor:distance_scan',sequence=1,frame_id='base_link')
        cases=[base]
        for key in ('ranges_m','hit_mask'):
            for invalid in (None,[],[0.]*181,[True]*180,['0']*180,[None]*180,{},[False,1]):
                msg=copy.deepcopy(base);msg['payload'][key]=invalid;cases.append(msg)
        for case in cases:
            self.assertEqual(v.schemas['envelope.schema.json'].is_valid(case),v._envelope_validator.is_valid(case))

    def test_hidden_generation_failure_is_bounded_not_a_weakened_task(self):
        from tankbot_host.global_planning import PlanningError
        c=configure(load_config(ROOT/'config/game.yaml'),'navigation.c6')
        obstacle=c['campaign']['levels']['navigation.c6']['rules']['local_navigation']['obstacle']
        obstacle.update(size_m=100.,max_attempts=1)
        with self.assertRaisesRegex(PlanningError,'LOCAL_SCENE_GENERATION_FAILED'):resolve_scene(c)

    def test_self_and_other_robot_state_are_not_scan_targets(self):
        sensor=self.sensor([{'center':[20.,0.],'size':[1.,1.]}])
        sample=sensor.measure({'truth_pose':[0.,0.,0.], 'targets':[{'pose':[.1,0.,0.]}], 'body':{'size':[.8,.6]}},6)
        self.assertFalse(any(sample['hit_mask']))
        self.assertEqual(sample['ranges_m'],[6.]*180)

    def test_hidden_scene_constraints_reproducibility_and_prior_path_validation(self):
        from tankbot_host.local_scene import rectangle_distance,physical_walls
        from tankbot_host.global_planning import map_grid,SafeGrid,reference_distances
        for seed in (0,1,2):
            c=copy.deepcopy(self.config);c.pop('private_obstacles');c.pop('navigation_planning');c['runtime']['seed']=seed
            first=resolve_scene(c);second=resolve_scene(c)
            self.assertEqual(first.definition_id,second.definition_id)
            d=first.to_config();task=d['navigation_planning'];wall=d['private_obstacles']['walls'][0]
            self.assertEqual(wall['size'],[.6,.6])
            for point in (task['start_xy'],task['goal_xy']):self.assertGreaterEqual(rectangle_distance(point,wall['center'],.6),1.5)
            raw,_=map_grid(physical_walls(d),.2,20000);safe=SafeGrid(raw,.5,.15)
            self.assertIn(raw.world_to_grid(task['goal_xy']),reference_distances(safe,task['start_xy'],20000))
            self.assertEqual(d['scene']['walls'],self.config['scene']['walls'])
