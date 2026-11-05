"""C4 full module chain, timing/privacy, authority limits and non-destructive upgrades."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]
from tankbot import Inputs,ModuleContext,Pose2D,Sample,Twist,Vector3
from tankbot_host.authority import load_config,Authority,CoreAdapter
from tankbot_host.campaign import configure,catalog
from tankbot_host.deployment import DeploymentManager
from tankbot_host.scene_definition import resolve_scene,SceneResolver
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_host.navigation_templates import PATH_ADAPTER
from tankbot_protocol.validation import Rejected
from path_tracking_support import solution


class NavigationPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=load_config(ROOT/'config/game.yaml')
        cls.config=configure(cls.base,'navigation.c4')

    def authority(self,files=None,config=None):
        a=Authority(config or self.config,controlled=True,startup_sources=files)
        self.addCleanup(a.close)
        return a

    def test_multi_seed_complete_closed_loop_uses_ekf_and_wheel_voltage_and_freezes(self):
        evidence=[]
        for seed in (0,1,2,7):
            c=copy.deepcopy(self.config);c['runtime']['seed']=seed
            c['campaign']['levels']['navigation.c4']['randomization']['seed']=seed
            a=self.authority(solution(c),c)
            for _ in range(a.campaign.limit_ticks+120):
                a.advance()
                if a.campaign.status!='active':break
            r=a.campaign.result
            self.assertTrue(r and r['passed'],(seed,r))
            self.assertLessEqual(r['tracking_rmse_m'],a.campaign.navigation.spec['tracking_rmse_limit_m'])
            self.assertLessEqual(r['max_deviation_m'],a.campaign.navigation.spec['max_deviation_m'])
            self.assertEqual(r['checkpoints_reached'],r['checkpoint_count'])
            self.assertEqual(r['tracking_samples'],a.tick-a.campaign.started_tick)
            self.assertAlmostEqual(r['scored_duration_s'],r['tracking_samples']/a.hz)
            self.assertEqual(a.graph.graph['modules']['path_tracking']['input_channels'],{'pose':'/robot/estimates/ekf/pose'})
            self.assertNotIn('truth',json.dumps(a.worker_init))
            self.assertTrue(all(row['target'] is None for row in a.replay))
            self.assertTrue(any('wheel_voltage_target' in row['actuators'] for row in a.replay))
            before=copy.deepcopy(a._private)
            for _ in range(10):a.advance()
            self.assertEqual(a._private,before)
            evidence.append({'seed':seed,'result':r,'reference':a.config['navigation_path'],
                             'runtime':a.worker.timing.public(),'terminal_pose':a._private['truth_pose']})
            a.close()
            self._cleanups.pop()  # Already closed, avoid retaining four worker resources.
        path=ROOT/'.m1-cache/navigation-c4-qa/native-multiseed.json';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')

    def test_blank_short_test_does_not_arm_move_score_or_regenerate_the_real_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            a=self.authority();api=WorkspaceAPI(a.config,directory=directory)
            a.deployment=DeploymentManager(a)
            before=copy.deepcopy(a._private);identity=a.config['navigation_path']['path_id']
            a.deployment.start('test',snapshot=api.store.read())
            deadline=time.monotonic()+10
            while a.deployment.job and time.monotonic()<deadline:
                a.advance()
                if a.deployment.job and not a.deployment.job['worker'].ready:time.sleep(.002)
            self.assertEqual(a.deployment.last['status'],'Ready',a.deployment.last)
            self.assertIsNone(a.campaign.started_tick)
            self.assertEqual(a.campaign.navigation.tracking_samples,0)
            self.assertEqual(a.campaign.navigation.reached_count,0)
            self.assertEqual(a._private['truth_pose'],before['truth_pose'])
            self.assertEqual(a.config['navigation_path']['path_id'],identity)

    def test_authority_rejects_reverse_and_bounds_custom_reference_without_physics_bypass(self):
        a=self.authority();spec=a.campaign.navigation.spec
        message={'channel':'/robot/cmd_vel','schema':'twist@1','frame_id':'base_link',
                 'payload':{'linear':{'x':99.,'y':0.,'z':0.},'angular':{'x':0.,'y':0.,'z':-99.}}}
        bounded=a.reference_output(message)
        self.assertEqual(bounded['payload']['linear']['x'],spec['control_limits']['max_vx_mps'])
        self.assertEqual(bounded['payload']['angular']['z'],-spec['control_limits']['max_wz_radps'])
        message['payload']['linear']['x']=-1.e-12
        with self.assertRaisesRegex(Rejected,'UNSUPPORTED_MOTION'):a.reference_output(message)
        message['payload']['linear']['x']=0.
        self.assertEqual(a.reference_output(message)['payload']['linear']['x'],0.)

    def test_missing_or_stale_player_pose_brakes_and_static_array_is_immutable(self):
        class Follower:
            result=Twist()
            def __init__(self,**kw):self.calls=[]
            def update(self,pose,path,dt):self.calls.append((pose,path,dt));return self.result
        a=self.authority()
        module=types.ModuleType('navigation.path_follower');module.PathFollower=Follower
        scope={}
        with patch.dict(sys.modules,{'navigation.path_follower':module}):exec(PATH_ADAPTER,scope)
        adapter=scope['PathTrackingModule']();ctx=ModuleContext(6,.1,12,a.worker_init['config']);adapter.setup(ctx)
        for sample in (None,Sample(Pose2D(0.,0.,0.),-100,'map',0),Sample(Pose2D(0.,0.,0.),6,'base_link',0)):
            update=ModuleContext(6,.1,12,a.worker_init['config'])
            adapter.update(Inputs({} if sample is None else {'pose':sample}),update)
            self.assertEqual(update._outputs[0][2]['linear']['x'],0.)
        self.assertFalse(adapter.controller.calls)
        update=ModuleContext(6,.1,12,a.worker_init['config']);adapter.update(Inputs({'pose':Sample(Pose2D(0.,0.,0.),6,'map',0)}),update)
        pose,path,dt=adapter.controller.calls[0]
        with self.assertRaises(ValueError):path.setflags(write=True)
        with self.assertRaises(ValueError):pose[0]=999.
        adapter.controller.result=Twist(linear=Vector3(x=-.1))
        with self.assertRaisesRegex(ValueError,'倒车'):adapter.update(Inputs({'pose':Sample(Pose2D(0.,0.,0.),6,'map',0)}),update)

    def test_contact_monitor_comes_from_existing_solver_and_is_not_a_player_sensor(self):
        scene=resolve_scene(self.config);core=CoreAdapter(scene.to_config(),'differential')
        self.addCleanup(core.close);contact=False
        for tick in range(900):
            snapshot=core.call({'op':'step','wheel_voltage_target':{'left_voltage_v':12.,'right_voltage_v':12.,'source_tick':tick}})
            if snapshot['wall_contact']:contact=True;break
        self.assertTrue(contact)
        a=self.authority()
        self.assertNotIn('wall_contact',json.dumps(a.runtime_inputs()))
        self.assertNotIn('wall_contact',json.dumps(a.worker_init))
        self.assertNotIn('wall_contact',json.dumps(a.view))

    def test_static_view_and_task_feedback_grants_do_not_change_player_inputs(self):
        a=self.authority();inputs=a.runtime_inputs();config=a.config
        item=next(x for x in catalog(config) if x['level_id']=='navigation.c4')
        self.assertIn('points_m',item['path_tracking']);self.assertIn('checkpoints_m',item['path_tracking'])
        value=a.campaign.public()['path_tracking']
        self.assertIn('goal_distance_m',value);self.assertNotIn('tracking_rmse_m',value)
        permission=a.campaign.definition['permissions']['visualization']
        permission['allowed_layers'].remove('path')
        config['campaign']['levels']['navigation.c4']['permissions']['visualization']['allowed_layers'].remove('path')
        item=next(x for x in catalog(config) if x['level_id']=='navigation.c4')
        self.assertNotIn('points_m',item['path_tracking']);self.assertIn('checkpoints_m',item['path_tracking'])
        permission['task_feedback']['live']=[]
        self.assertNotIn('path_tracking',a.campaign.public())
        a.campaign.finish(a.tick,reason='aborted')
        permission['task_feedback']['terminal']=['tracking_samples']
        report=a.campaign.public()['result']
        self.assertIn('tracking_samples',report)
        for key in ('tracking_rmse_m','max_deviation_m','scored_duration_s','checkpoints_reached','checkpoint_count','settled_ticks'):
            self.assertNotIn(key,report)
        self.assertEqual(inputs,a.runtime_inputs())

    def test_upgrade_and_roundtrip_preserve_all_four_old_algorithms_and_revision_history(self):
        from navigation_support import solution as waypoint_solution
        c3=configure(self.base,'navigation.c3')
        with tempfile.TemporaryDirectory() as directory:
            api=WorkspaceAPI(c3,directory=directory);initial=api.store.read();files=waypoint_solution(c3)
            paths=('control/wheel_controller.py','localization/odometry.py','localization/ekf.py','navigation/waypoint_controller.py')
            saved=api.store.edit(initial['revision'],{p:files[p] for p in paths})
            api.unlock(self.config);current=api.store.read()
            self.assertIn('return Twist()',current['files']['navigation/path_follower.py'])
            for p in paths:self.assertEqual(current['files'][p],saved['files'][p])
            plan=api.post('upgrade',{'revision':current['revision']})
            self.assertFalse(set(paths)&{entry['path'] for entry in plan['entries']})
            api.post('apply',{'plan_id':plan['plan_id'],'revision':current['revision'],'resolutions':{e['path']:'incoming' for e in plan['entries']}})
            self.assertFalse(api.get()['learning']['upgrade_required'])
            api.unlock(c3)
            for p in paths:self.assertEqual(api.store.read()['files'][p],saved['files'][p])
            self.assertEqual(api.store.read(saved['revision']),saved)

    def test_redeploy_preserves_reference_start_checkpoints_and_error_accumulator(self):
        files=solution(self.config);a=self.authority(files)
        for _ in range(180):a.advance()
        tracking=a.campaign.navigation;identity=tracking.reference['path_id'];started=a.campaign.started_tick
        samples=tracking.tracking_samples;reached=tracking.reached_count
        with tempfile.TemporaryDirectory() as directory:
            api=WorkspaceAPI(a.config,directory=directory);old=api.store.read()
            snapshot=api.store.edit(old['revision'],{p:v for p,v in files.items() if old['files'].get(p)!=v})
            a.deployment=DeploymentManager(a)
            for kind in ('test','deploy'):
                a.deployment.start(kind,snapshot=snapshot);deadline=time.monotonic()+10
                while a.deployment.job and time.monotonic()<deadline:
                    a.advance()
                    if a.deployment.job and not a.deployment.job['worker'].ready:time.sleep(.002)
                self.assertIsNone(a.deployment.job)
                self.assertEqual(a.deployment.last['status'],'Ready' if kind=='test' else 'Active',a.deployment.last)
            self.assertIs(a.campaign.navigation,tracking);self.assertEqual(tracking.reference['path_id'],identity)
            self.assertEqual(a.campaign.started_tick,started);self.assertGreater(tracking.tracking_samples,samples)
            self.assertGreaterEqual(tracking.reached_count,reached)
