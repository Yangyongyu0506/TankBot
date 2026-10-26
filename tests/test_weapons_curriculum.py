"""C3-C5 observation/control boundaries, frame semantics, reproducibility and player preservation."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot import AimInput, GpsFixData, PolarTargetEstimate, ModuleContext
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure,RadarSimulator,blocked
from tankbot_host.weapon_sensors import GpsInterceptSimulator
from tankbot_host.workspace import starter
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_host.robot_graph import inspect_graph
from tankbot_protocol.validation import Validator,Rejected,envelope
from weapons_curriculum_support import FUSION


class WeaponsCurriculumTests(unittest.TestCase):
    def config(self,level='c4'):
        return configure(load_config(ROOT/'config/game.yaml'),level)

    def test_declared_controls_sensor_grants_and_multi_file_tasks(self):
        for level in ('c3','c4','c5'):
            c=self.config(level);d=c['campaign']['levels'][level]
            self.assertEqual(c['control_sources']['chassis'],'disabled')
            self.assertEqual(c['control_sources']['turret'],'robot' if level=='c5' else 'keyboard')
            self.assertEqual(c['control_sources']['weapon'],'robot' if level=='c5' else 'keyboard')
            self.assertEqual('/robot/sensors/intercepted_gps' in d['runtime']['grants']['inputs'],level!='c3')
            self.assertEqual(d['armor_mode'],level!='c3')
            self.assertEqual(d['time_limit_s'],120 if level=='c3' else 180)
            if level=='c3':self.assertEqual(d['runtime']['grants']['outputs'],['target_polar_estimate@1'])
            if level=='c5':
                self.assertEqual(d['target']['motion']['chassis'],'omnidirectional')
                self.assertEqual(d['target']['motion']['spin_rate_radps'],3.)
                self.assertEqual(d['tutorial']['lesson']['edit_files'],['weapons/target_prediction.py','weapons/auto_aim.py'])

    def test_front_gps_geometry_occlusion_range_and_empty_frames(self):
        c=self.config();sensor=next(s for s in c['campaign']['levels']['c4']['sensors'] if s['type']=='intercepted_gps')
        sensor['parameters']['noise'].update(position_stddev_m=0.,drop_probability=0.)
        target=c['weapons']['targets'][0]['target_id']
        private={'truth_pose':[0.,0.,0.],'targets':[{'target_id':target,'alive':True,'pose':[2.,0.,math.pi/2]}]}
        c['scene']['walls']=[{'center':[1.,0.],'size':[.2,4.]}]
        self.assertTrue(blocked((0,0),(2,0),c['scene']['walls']))
        sampler=GpsInterceptSimulator(c)
        value=sampler.sample(private,0)
        np.testing.assert_allclose(value['positions_m'],[[2.,c['body']['length_m']/2]])
        self.assertIsNone(sampler.sample(private,0));self.assertIsNone(sampler.sample(private,1))
        private['targets'][0]['pose'][0]=sensor['parameters']['range_m']+1
        self.assertEqual(sampler.sample(private,6),{'positions_m':[]})
        private['targets'][0]['alive']=False
        self.assertEqual(sampler.sample(private,12),{'positions_m':[]})

    def test_seeded_gps_stream_does_not_change_existing_radar_noise(self):
        c=self.config();target=c['weapons']['targets'][0]['target_id']
        private={'truth_pose':[0.,0.,0.],'targets':[{'target_id':target,'alive':True,'pose':[-3.,-2.,0.]}]}
        first,second=GpsInterceptSimulator(c),GpsInterceptSimulator(c)
        radar1,radar2=RadarSimulator(c),RadarSimulator(c)
        fixes=[]
        for tick in range(0,6000,6):
            before=radar1.sample(private,tick)
            value=first.sample(private,tick)
            self.assertEqual(value,second.sample(private,tick))
            self.assertEqual(before,radar2.sample(private,tick))
            fixes.extend(value['positions_m'])
        self.assertGreater(len(fixes),850);self.assertLess(len(fixes),950)
        errors=np.asarray(fixes)-np.array([-3+c['body']['length_m']/2,-2])
        self.assertTrue(np.all(np.abs(errors.std(axis=0)-.15)<.02))

    def test_c3_polar_output_is_projected_with_published_pose_and_never_moves_truth(self):
        a=Authority(self.config('c3'),controlled=True);self.addCleanup(a.close)
        original=copy.deepcopy(a._private['truth_pose'])
        a._public_pose_history[0]={'x_m':2.,'y_m':3.,'yaw_rad':math.pi/2}
        message=envelope('target_polar_estimate@1','/robot/estimates/tracking/target_polar',
            {'range_m':2.,'bearing_rad':0.,'covariance':[.04,0.,0.,.09]},tick=0,hz=a.hz,run_id=a.run_id,publisher_id='module:tracking',sequence=0,frame_id='base_link')
        a.accept_graph_output('tracking',message,activation_tick=0)
        projected=a._target_estimate
        self.assertEqual(projected['schema'],'target_estimate@1');self.assertEqual(projected['frame_id'],'map')
        np.testing.assert_allclose([projected['payload']['x_m'],projected['payload']['y_m']],[2.,5.])
        np.testing.assert_allclose(projected['payload']['covariance'],[.36,0.,0.,.04],atol=1e-12)
        self.assertEqual(a._private['truth_pose'],original)
        estimates=a.campaign.estimates
        a.config['view_policy']['system_pose_allowed']=False
        a.gateway.policy['system_pose_allowed']=False
        a._build_view()
        self.assertIsNone(a.view['payload']['selected_pose'])
        self.assertEqual(a.view['payload']['target_estimates'],[])
        self.assertEqual(a.campaign.estimates,estimates)  # display permissions never undo evaluation

    def test_c3_cannot_subscribe_to_gps_and_new_payloads_remain_strict(self):
        c=self.config('c3');a=Authority(c,controlled=True);self.addCleanup(a.close)
        files=starter(c);manifest=json.loads(files['tankbot.json']);contract=json.loads(files['contracts/tracking.json'])
        contract['inputs']['gps']={'schema':'gps_fix@1','required':False,'max_age_ticks':24}
        files['contracts/tracking.json']=json.dumps(contract)
        manifest['connections'].append({'from':'/robot/sensors/intercepted_gps','to':'tracking.gps'})
        with self.assertRaisesRegex(ValueError,'UNAUTHORIZED_GRAPH_INPUT'):inspect_graph(files,manifest,a)
        msg=envelope('gps_fix@1','/robot/sensors/intercepted_gps',{'positions_m':[[1.,2.]]},tick=0,hz=60,run_id='test',publisher_id='sensor:gps',sequence=0,frame_id='map')
        Validator(c,'test').structure(msg)
        for payload in ({'positions_m':[[1.,2.,3.]]},{'positions_m':[[1.,2.]],'yaw_rad':0.}):
            bad=copy.deepcopy(msg);bad['payload']=payload
            with self.assertRaises(Rejected):Validator(c,'test').structure(bad)
        ctx=ModuleContext(0,0.,0,{})
        ctx.publish('target',PolarTargetEstimate(1.,.2,np.eye(2)),frame_id='base_link')
        self.assertEqual(ctx._outputs[0][1],'target_polar_estimate@1')
        self.assertEqual(ctx._outputs[0][2]['covariance'],[1.,0.,0.,1.])
        with self.assertRaises(ValueError):GpsFixData(np.zeros((1,3)))

    def test_stationary_center_rotation_is_observable_with_front_gps(self):
        c=self.config();namespace={};exec(FUSION.replace('__PARAMS__',repr(c['validation']['reference_aim'])),namespace)
        radius=c['body']['length_m']/2
        tracker=namespace['FusionTracker'](np.array([radius,0.]),np.diag([.45**2,.08**2]),np.eye(2)*.15**2)
        for index in range(200):
            yaw=3.*index/10
            radar=np.array([[4.,0.]])
            gps=np.array([[4+radius*math.cos(yaw),radius*math.sin(yaw)]])
            result=tracker.update(radar,gps,np.zeros(3),.1)
        error=(result.yaw_rad-yaw+math.pi)%math.tau-math.pi
        self.assertLess(abs(error),.05)
        self.assertLess(math.hypot(result.x_m-4,result.y_m),.05)

    def test_spinning_omni_translates_while_body_heading_rotates(self):
        a=Authority(self.config('c5'),controlled=True);self.addCleanup(a.close)
        poses=[]
        for _ in range(180):
            a.advance();poses.append(a._private['targets'][0]['pose'])
        yaw=np.unwrap(np.array(poses)[:,2])
        self.assertGreater(yaw[-1]-yaw[0],math.pi)
        self.assertGreater(poses[-1][0]-poses[0][0],.5)

    def test_revised_scaffolds_preserve_existing_algorithms_and_legacy_control(self):
        with tempfile.TemporaryDirectory() as directory:
            api=WorkspaceAPI(self.config('c2'),directory=directory)
            original=api.store.read();kept={'perception/tracker.py':'# saved KF\n','weapons/auto_aim.py':'# saved legacy controller\n'}
            api.store.edit(original['revision'],kept)
            for level in ('c3','c4','c5','c2'):
                value=api.unlock(self.config(level))
                for path,source in kept.items():self.assertEqual(value['snapshot']['files'][path],source)

    def test_polar_prediction_input_preserves_existing_aiminput_api(self):
        observation=AimInput(np.array([2.,5.]),.2,np.array([2.,3.,math.pi/2]),0.,0.,True)
        np.testing.assert_allclose(observation.target_rt,[2.,0.],atol=1e-12)
        self.assertFalse(observation.target_rt.flags.writeable)
        result=observation.with_target_polar(np.array([3.,math.pi/2]))
        np.testing.assert_allclose(result.target_xy,[-1.,3.],atol=1e-12)
        np.testing.assert_allclose(observation.target_xy,[2.,5.])
