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
from tankbot import AimInput, AimOutput, GpsFixData, PolarTargetEstimate, ModuleContext, Inputs, Sample, Pose2D, JointState, WeaponState, RadarData, RadarDetection
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure,RadarSimulator,blocked
from tankbot_host.weapon_sensors import GpsInterceptSimulator
from tankbot_host.workspace import starter
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_host.robot_graph import inspect_graph
from tankbot_protocol.validation import Validator,Rejected,envelope


class WeaponsCurriculumTests(unittest.TestCase):
    def config(self,level='c4'):
        return configure(load_config(ROOT/'config/game.yaml'),level)

    def test_polar_adapter_passes_typed_current_frame_tuple_without_filtering(self):
        from dataclasses import FrozenInstanceError
        from tankbot_host.weapon_curriculum import RAW_ADAPTERS
        namespace={};exec(RAW_ADAPTERS,namespace)
        module=namespace['PolarTrackingModule']();module.last_tick=None
        class Tracker:
            def __init__(self):self.calls=[]
            def update(self,measurements,own_pose,dt):
                self.calls.append((measurements,own_pose,dt))
                return measurements[0] if measurements else None
        module.tracker=Tracker()
        def step(tick,detections,pose_tick=None):
            ctx=ModuleContext(tick,.1,tick+6,{'lesson':{'tick_duration_s':1/60}})
            pose=Sample(Pose2D(2.,3.,.4),tick if pose_tick is None else pose_tick,'map',tick)
            radar=Sample(RadarData(detections),tick,'radar_link',tick)
            module.update(Inputs({'self_pose':pose,'radar':radar}),ctx)
            return ctx
        detection=RadarDetection('anonymous-frame',4.2,-.3)
        ctx=step(0,(detection,));measurements,own,dt=module.tracker.calls[-1]
        self.assertIsInstance(measurements,tuple)
        self.assertIsInstance(measurements[0],PolarTargetEstimate)
        self.assertEqual((measurements[0].range_m,measurements[0].bearing_rad),(4.2,-.3))
        self.assertIsNone(measurements[0].covariance)
        with self.assertRaises(FrozenInstanceError):measurements[0].range_m=99.
        np.testing.assert_allclose(own,[2.,3.,.4]);self.assertAlmostEqual(dt,.1)
        self.assertEqual(ctx._outputs[0][3:],('base_link',0))
        step(0,(detection,));self.assertEqual(len(module.tracker.calls),1)
        step(6,(detection,),pose_tick=0);self.assertEqual(len(module.tracker.calls),1)
        ctx=step(12,());self.assertEqual(module.tracker.calls[-1][0],())
        self.assertAlmostEqual(module.tracker.calls[-1][2],.2)
        self.assertEqual(ctx._outputs,[])
        self.assertEqual(len(measurements),1,'later empty frames must not mutate or accumulate earlier inputs')

    def test_tuple_api_upgrade_preserves_algorithms_and_checks_adapter_not_protocol(self):
        from tankbot_host.campaign_templates import framework_upgrade
        from tankbot_host.learning import learning_bundle
        for level in ('c3','c4'):
            with self.subTest(level=level),tempfile.TemporaryDirectory() as directory:
                c=self.config(level);files=starter(c)
                old=files['robot_modules/observations.py'].replace('    scaffold_api: str = "polar_tuple@1"\n','')
                files['robot_modules/observations.py']=old
                files['perception/polar_tracker.py']='# player legacy matrix algorithm\n'
                api=WorkspaceAPI(c,directory=directory);before=api.store.read()
                saved=api.store.edit(before['revision'],files)
                view=api.get();self.assertTrue(view['learning']['upgrade_required'])
                plan=api.post('upgrade',{'revision':view['snapshot']['revision']})
                self.assertNotIn('perception/polar_tracker.py',[e['path'] for e in plan['entries']])
                api.post('apply',{'revision':plan['base_revision'],'plan_id':plan['plan_id'],
                    'resolutions':{e['path']:'incoming' for e in plan['entries']}})
                self.assertFalse(api.get()['learning']['upgrade_required'])
                self.assertEqual(api.store.read()['files']['perception/polar_tracker.py'],files['perception/polar_tracker.py'])
                self.assertEqual(api.store.read(saved['revision'])['files'],saved['files'])
                current=starter(c)
                current['robot_modules/observations.py']='# formatting comment\n'+current['robot_modules/observations.py']
                self.assertFalse(framework_upgrade(c,current)['required'])
                current['robot_modules/observations.py']='def broken(:\n'
                self.assertFalse(framework_upgrade(c,current)['required'],'ordinary syntax errors must reach Python diagnostics')
                guide=learning_bundle(c)['lesson']
                signature=next(f['signature'] for f in guide['functions'] if f['path']=='perception/polar_tracker.py')
                self.assertIn('measurements: tuple[PolarTargetEstimate, ...]',signature)
                self.assertIn('输入 covariance 为 None',next(x['description'] for x in guide['functions'] if x['path']=='perception/polar_tracker.py'))

    def test_declared_controls_sensor_grants_and_multi_file_tasks(self):
        for level in ('c3','c4','c5'):
            c=self.config(level);d=c['campaign']['levels'][level]
            self.assertEqual(c['control_sources']['chassis'],'disabled')
            self.assertEqual(c['control_sources']['turret'],'keyboard' if level=='c3' else 'robot')
            self.assertEqual(c['control_sources']['weapon'],'keyboard' if level=='c3' else 'robot')
            self.assertNotIn('/robot/sensors/intercepted_gps',d['runtime']['grants']['inputs'])
            self.assertEqual(d['armor_mode'],level=='c5')
            self.assertEqual(d['time_limit_s'],180 if level=='c5' else 120)
            if level=='c3':self.assertEqual(d['runtime']['grants']['outputs'],['target_polar_estimate@1'])
            if level=='c5':
                self.assertEqual(d['target']['motion']['chassis'],'omnidirectional')
                self.assertEqual(d['target']['motion']['spin_rate_radps'],3.)
                self.assertEqual(d['tutorial']['lesson']['edit_files'],['perception/armor_tracker.py','weapons/target_prediction.py','weapons/auto_aim.py'])

    def test_c4_reuses_c3_world_enemy_observations_outcomes_and_noise(self):
        first,second=self.config('c3'),self.config('c4')
        d3,d4=first['campaign']['levels']['c3'],second['campaign']['levels']['c4']
        for field in ('target','sensors','scene','rules','time_limit_s','timer_start','evaluation'):
            self.assertEqual(d3[field],d4[field],field)
        self.assertEqual(first['weapons']['targets'],second['weapons']['targets'])
        target=first['weapons']['targets'][0]['target_id']
        private={'truth_pose':[0.,0.,0.],'targets':[{'target_id':target,'alive':True,'pose':[-3.,-2.,0.]}]}
        radar1,radar2=RadarSimulator(first),RadarSimulator(second)
        for tick in range(0,600,6):self.assertEqual(radar1.sample(private,tick),radar2.sample(private,tick))
        a=Authority(second,controlled=True);self.addCleanup(a.close)
        self.assertIsNone(a.intercepted_gps.sensor)
        self.assertIsNone(a.armor_detector.sensor)
        self.assertNotIn('/robot/sensors/intercepted_gps',a.runtime_inputs())
        self.assertNotIn('/robot/sensors/armor_detections',a.runtime_inputs())
        self.assertEqual(a.worker_init['config']['actuators']['armor_mounts'],[])
        for method,value in ((a.turret_keyboard,{'velocity_radps':1.}),(a.fire_keyboard,{'request_id':'manual'})):
            with self.assertRaises(ValueError):method(value)

    def test_polar_aiming_uses_sampling_pose_and_bounded_authorized_history(self):
        from tankbot_host.weapon_curriculum import PREDICTIVE_ADAPTER
        namespace={};exec(PREDICTIVE_ADAPTER,namespace)
        module=namespace['PredictiveAimingModule']();module.public_poses={}
        class Predictor:
            def update(self,observation,dt):
                self.observation=observation
                return observation.target_rt
        class Controller:
            def update(self,observation,dt):return AimOutput(0.,True)
        module.predictor=Predictor();module.controller=Controller()
        c=self.config();horizon=c['runtime']['estimate_history_ticks']
        def step(tick,pose,target=None):
            ctx=ModuleContext(tick,.1,tick+6,{'lesson':{'tick_duration_s':1/60,'estimate_history_ticks':horizon}})
            samples={'self_pose':Sample(Pose2D(*pose),tick,'map',tick),'turret':Sample(JointState(['turret'],[0.],[0.]),tick,'base_link',tick),'weapon':Sample(WeaponState(True,0,0,0,None),tick,'base_link',tick)}
            if target is not None:samples['target']=target
            module.update(Inputs(samples),ctx)
            return ctx
        step(0,[0.,0.,0.])
        target=Sample(PolarTargetEstimate(2.,0.),0,'base_link',0)
        step(6,[9.,9.,math.pi],target)
        observed=module.predictor.observation
        np.testing.assert_allclose(observed.target_xy,[2.,0.])
        np.testing.assert_allclose(observed.own_pose,[9.,9.,math.pi])
        self.assertIsNone(observed.target_yaw_rad)
        self.assertAlmostEqual(observed.target_age_s,12/60)
        for tick in range(12,horizon+12,6):step(tick,[9.,9.,0.])
        ctx=step(horizon+12,[9.,9.,0.],target)
        self.assertIsNone(module.predictor.observation.target_xy)
        self.assertEqual(ctx._commands,[],'an unprojectable target must never trigger fire')
        self.assertLessEqual(len(module.public_poses),horizon//6+1)

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
            original=api.store.read();kept={'perception/tracker.py':'# saved KF\n',
                'perception/polar_tracker.py':'# saved C3 EKF\n',
                'perception/fusion_tracker.py':'# retained legacy fusion\n',
                'weapons/target_prediction.py':'# saved center predictor\n',
                'weapons/auto_aim.py':'# saved legacy controller\n'}
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
