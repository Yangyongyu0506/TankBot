"""Navigation C3: ordered goals, stable stopping, voltage-only control and saved algorithms."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import numpy as np
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]
from tankbot import Inputs,ModuleContext,Pose2D,Sample,Twist,Vector3,WaypointGoal
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import CampaignSession,configure,catalog
from tankbot_host.deployment import DeploymentManager
from tankbot_host.level_plugins import LevelValidationError
from tankbot_host.navigation_task import WaypointRoute
from tankbot_host.navigation_templates import WAYPOINT_ADAPTER
from tankbot_host.workspace_api import WorkspaceAPI
from navigation_support import solution


class NavigationWaypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=load_config(ROOT/'config/game.yaml')
        cls.config=configure(cls.base,'navigation.c3')
        cls.spec=cls.config['campaign']['levels']['navigation.c3']['rules']['waypoint_route']

    def authority(self,files=None):
        a=Authority(self.config,controlled=True,startup_sources=files)
        self.addCleanup(a.close)
        return a

    def final_goal(self,route):
        for tick,point in enumerate(self.spec['points_m'][:-1],1):
            route.observe([*point,0.],[0.,0.,0.],tick)
        self.assertEqual(route.goal_index,len(self.spec['points_m'])-1)

    def private(self,pose=None,velocity=None):
        return {'truth_pose':pose or [0.,0.,2.2],'truth_velocity':velocity or [0.,0.,0.],
                'targets':[],'target_hits':{},'player_hp':None,'motion_metrics':{'path_length_m':0.}}

    def test_order_radius_and_public_feedback_never_disclose_true_distance_or_velocity(self):
        route=WaypointRoute(self.spec)
        route.observe([0.,0.,0.],[0.,0.,0.],1)
        self.assertEqual(route.reached_count,0)  # The final origin is not the first goal.
        for tick,point in enumerate(self.spec['points_m'][:-1],2):
            previous=route.goal_index
            route.observe([*point,0.],[0.,0.,0.],tick)
            self.assertEqual(route.goal_index,previous+1)
            route.observe([0.,0.,0.],[0.,0.,0.],tick)
            self.assertEqual(route.goal_index,previous+1)  # Polling/repeated ticks do not advance.
        outside=float(np.nextafter(self.spec['position_tolerance_m'],np.inf))
        route.observe([outside,0.,0.],[0.,0.,0.],10)
        self.assertEqual(route.reached_count,3)
        route.observe([self.spec['position_tolerance_m'],0.,0.],[0.,0.,0.],11)
        self.assertEqual(route.reached_count,4)
        self.assertEqual(set(route.goal()),{'goal_index','position_m'})
        self.assertEqual(set(route.public()),{'goal_index','reached_count','total','settled_ticks','required_settle_ticks','complete'})

    def test_settle_uses_elapsed_continuous_ticks_and_all_velocity_axes(self):
        route=WaypointRoute(self.spec);self.final_goal(route)
        velocity=[self.spec['stop_linear_speed_mps'],0.,self.spec['stop_yaw_rate_radps']]
        for tick in range(10,10+self.spec['stop_duration_ticks']):
            route.observe([0.,0.,2.2],velocity,tick)
        self.assertFalse(route.complete)
        route.observe([0.,0.,2.2],velocity,10+self.spec['stop_duration_ticks'])
        self.assertTrue(route.complete)  # No terminal yaw target.
        for bad_velocity in ([0.,self.spec['stop_linear_speed_mps']*2,0.],
                             [0.,0.,self.spec['stop_yaw_rate_radps']*2]):
            route=WaypointRoute(self.spec);self.final_goal(route)
            for tick in range(10,20):route.observe([0.,0.,0.],[0.,0.,0.],tick)
            route.observe([0.,0.,0.],bad_velocity,20)
            self.assertEqual(route.settled_ticks,0)
            route.observe([0.,0.,0.],[0.,0.,0.],30)
            self.assertEqual(route.settled_ticks,0)  # A time gap cannot count as observed stability.

    def test_success_on_last_tick_timeout_before_settling_and_fault_priority(self):
        for kind in ('success','timeout','fault'):
            session=CampaignSession(self.config);session.start(0,self.private())
            self.final_goal(session.navigation)
            first=session.limit_ticks-self.spec['stop_duration_ticks']+(kind=='timeout')
            reason=None
            for tick in range(first,session.limit_ticks+1):
                session.controller_faulted=kind=='fault' and tick==session.limit_ticks
                reason=session.outcome(self.private(),tick)
            self.assertEqual(reason,{'success':'objective_completed','timeout':'timeout','fault':'controller_error'}[kind])

    def test_reference_closed_loop_passes_with_estimated_pose_and_freezes_terminal_world(self):
        a=self.authority(solution(self.config))
        a.select_pose_source('odometry')  # Rendering cannot redirect the navigation input.
        requests=[];submit=a.worker.submit
        def capture(request):requests.append(copy.deepcopy(request));return submit(request)
        a.worker.submit=capture
        for _ in range(a.campaign.limit_ticks+120):
            a.advance()
            if a.campaign.status!='active':break
        self.assertTrue(a.campaign.result['passed'],a.campaign.result)
        self.assertEqual(a.campaign.result['waypoints_reached'],4)
        self.assertEqual(a.campaign.result['settled_ticks'],self.spec['stop_duration_ticks'])
        self.assertLess(a.tick-a.campaign.started_tick,a.campaign.limit_ticks)
        self.assertEqual(a.selector.source_id,'odometry')
        nav=a.graph.graph['modules']['waypoint_navigation']
        self.assertEqual(nav['input_channels']['pose'],'/robot/estimates/ekf/pose')
        self.assertTrue(any(any(m['schema']=='pose2d@1' for m in r['payload']['inputs']) for r in requests))
        self.assertTrue(all(item['target'] is None for item in a.replay))
        self.assertTrue(any('wheel_voltage_target' in item['actuators'] for item in a.replay))
        self.assertNotIn('truth',json.dumps(a.worker_init))
        before=copy.deepcopy(a._private)
        for _ in range(30):a.advance()
        self.assertEqual(a._private,before)
        self.assertNotIn('origin_distance_m',a.campaign.result)
        self.assertNotIn('path_length_m',a.campaign.result)
        evidence={'result':a.campaign.result,'started_tick':a.campaign.started_tick,'finished_tick':a.tick,
                  'private_terminal_pose':a._private['truth_pose'],'private_terminal_velocity':a._private['truth_velocity']}
        path=ROOT/'.m1-cache/navigation-c3-qa/native-controlled.json';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')

    def test_blank_scaffold_tests_do_not_move_or_arm_the_formal_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            api=WorkspaceAPI(self.config,directory=directory)
            a=self.authority();a.deployment=DeploymentManager(a)
            before=copy.deepcopy(a._private['truth_pose'])
            a.deployment.start('test',snapshot=api.store.read())
            for _ in range(600):
                a.advance()
                if a.deployment.job is None:break
            self.assertEqual(a.deployment.last['status'],'Ready',a.deployment.last)
            self.assertEqual(set(a.deployment.last['modules_executed']),{'wheel_control','odometry','ekf','waypoint_navigation'})
            self.assertIsNone(a.campaign.started_tick)
            self.assertEqual(a.campaign.navigation.reached_count,0)
            self.assertEqual(a._private['truth_pose'],before)

    def test_server_bounds_references_even_if_a_custom_adapter_skips_its_limit(self):
        files=solution(self.config)
        files['navigation/waypoint_module.py']=files['navigation/waypoint_module.py'].replace('ctx.publish("command", bounded,','ctx.publish("command", command,')
        files['navigation/waypoint_controller.py']=files['navigation/waypoint_controller.py'].replace('        delta: NDArray[np.float64] = target_xy-estimated_pose[:2]',
            '        return Twist(linear=Vector3(x=99.),angular=Vector3(z=-99.))\n        delta: NDArray[np.float64] = target_xy-estimated_pose[:2]')
        a=self.authority(files)
        for _ in range(50):a.advance()
        cached=a.graph.cache['/robot/cmd_vel'];routed=a._sensors['/robot/cmd_vel']
        self.assertEqual(cached,routed)
        self.assertEqual(cached['payload']['linear']['x'],self.spec['control_limits']['max_vx_mps'])
        self.assertEqual(cached['payload']['angular']['z'],-self.spec['control_limits']['max_wz_radps'])
        self.assertTrue(all(item['target'] is None for item in a.replay))

    def test_bad_controller_fails_promptly_with_python_feedback(self):
        files=solution(self.config)
        files['navigation/waypoint_controller.py']=files['navigation/waypoint_controller.py'].replace('        delta: NDArray[np.float64] = target_xy-estimated_pose[:2]',
            '        return Twist(linear=Vector3(x=float("nan")))\n        delta: NDArray[np.float64] = target_xy-estimated_pose[:2]')
        a=self.authority(files)
        for _ in range(120):
            a.advance()
            if a.campaign.status!='active':break
        self.assertEqual(a.campaign.result['reason'],'controller_error')
        logs=json.dumps(a.logs.public(),ensure_ascii=False)
        self.assertIn('Traceback (most recent call last)',logs)
        self.assertIn('WaypointController.update',logs)

    def test_redeploy_keeps_mission_object_checkpoints_and_start_time(self):
        import time
        files=solution(self.config);a=self.authority(files)
        for _ in range(600):
            a.advance()
            if a.campaign.navigation.reached_count:break
        self.assertGreater(a.campaign.navigation.reached_count,0)
        route=a.campaign.navigation;started=a.campaign.started_tick;reached=route.reached_count
        with tempfile.TemporaryDirectory() as directory:
            api=WorkspaceAPI(self.config,directory=directory);before=api.store.read()
            snapshot=api.store.edit(before['revision'],{p:files[p] for p in ('control/wheel_controller.py','localization/odometry.py','localization/ekf.py','navigation/waypoint_controller.py')})
            a.deployment=DeploymentManager(a)
            for kind in ('test','deploy'):
                a.deployment.start(kind,snapshot=snapshot)
                deadline=time.monotonic()+10
                while a.deployment.job is not None and time.monotonic()<deadline:
                    a.advance()
                    if a.deployment.job and not a.deployment.job['worker'].ready:time.sleep(.002)
                self.assertIsNone(a.deployment.job)
                self.assertEqual(a.deployment.last['status'],'Ready' if kind=='test' else 'Active',a.deployment.last)
            self.assertIs(a.campaign.navigation,route)
            self.assertEqual(a.campaign.started_tick,started)
            self.assertGreaterEqual(route.reached_count,reached)
            self.assertGreater(a.campaign.elapsed_ticks,0)

    def test_only_the_task_layer_controls_route_projection_not_runtime_goal_access(self):
        a=self.authority()
        item=next(level for level in catalog(a.config) if level['level_id']=='navigation.c3')
        self.assertEqual(item['navigation']['points_m'],self.spec['points_m'])
        self.assertIn('navigation',a.campaign.public())
        a.campaign.definition['permissions']['visualization']['allowed_layers'].remove('waypoints')
        a.config['campaign']['levels']['navigation.c3']['permissions']['visualization']['allowed_layers']=list(a.campaign.definition['permissions']['visualization']['allowed_layers'])
        item=next(level for level in catalog(a.config) if level['level_id']=='navigation.c3')
        self.assertNotIn('navigation',item)
        self.assertNotIn('navigation',a.campaign.public())
        self.assertIn('/robot/navigation/goal',a.runtime_inputs())

    def test_c2_upgrade_preserves_source_revision_and_adds_only_new_algorithm(self):
        with tempfile.TemporaryDirectory() as directory:
            c2=configure(self.base,'navigation.c2');api=WorkspaceAPI(c2,directory=directory)
            initial=api.store.read();files=solution(c2)
            authored={path:files[path] for path in ('control/wheel_controller.py','localization/odometry.py','localization/ekf.py')}
            api.store.edit(initial['revision'],authored);before=api.store.read()
            state=api.unlock(self.config)
            self.assertTrue(state['learning']['upgrade_required'])
            for path,source in authored.items():self.assertEqual(state['snapshot']['files'][path],source)
            self.assertIn('return Twist()',state['snapshot']['files']['navigation/waypoint_controller.py'])
            plan=api.post('upgrade',{'revision':state['snapshot']['revision']})
            self.assertFalse(set(authored)&{entry['path'] for entry in plan['entries']})
            api.post('apply',{'plan_id':plan['plan_id'],'revision':state['snapshot']['revision'],'resolutions':{entry['path']:'incoming' for entry in plan['entries']}})
            self.assertFalse(api.get()['learning']['upgrade_required'])
            self.assertEqual(api.store.read(before['revision']),before)

    def test_loader_rejects_conflicts_truth_input_and_unusable_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);shutil.copytree(ROOT/'levels',path/'levels')
            base=yaml.safe_load((ROOT/'config/game.yaml').read_text());base['level_plugins']['directory']=str(path/'levels')
            (path/'game.yaml').write_text(yaml.safe_dump(base))
            original=yaml.safe_load((ROOT/'levels/navigation.C3.yaml').read_text())
            for case in ('overlap','limits','duration','truth','required_pose','missing_pose_binding','missing_reference'):
                value=copy.deepcopy(original)
                if case=='overlap':value['permissions']['data_access']['actuators']['/robot/cmd_vel']='twist@1'
                elif case=='limits':value['objectives']['waypoint_route']['control_limits']['max_vx_mps']=100.
                elif case=='duration':value['objectives']['waypoint_route']['stop_duration_ticks']=100000
                elif case=='truth':
                    connection=next(c for c in value['communication']['runtime']['manifest']['connections'] if c['to']=='waypoint_navigation.pose');connection['from']='/world/truth'
                elif case=='required_pose':value['communication']['runtime']['contracts']['waypoint_navigation']['inputs']['pose']['required']=True
                elif case=='missing_pose_binding':
                    value['communication']['runtime']['manifest']['connections']=[c for c in value['communication']['runtime']['manifest']['connections'] if c['to']!='waypoint_navigation.pose']
                else:value['permissions']['data_access'].pop('references')
                (path/'levels/navigation.C3.yaml').write_text(yaml.safe_dump(value,allow_unicode=True))
                with self.subTest(case=case),self.assertRaises(LevelValidationError):load_config(path/'game.yaml')

    def test_adapter_missing_stale_or_wrong_frame_pose_brakes_and_checks_output(self):
        class Controller:
            result=Twist(linear=Vector3(x=9.),angular=Vector3(z=-9.))
            def __init__(self,**kwargs):self.calls=[]
            def update(self,pose,target,dt):self.calls.append((pose,target,dt));return self.result
        namespace={'WaypointController':Controller}
        exec(WAYPOINT_ADAPTER.replace('from navigation.waypoint_controller import WaypointController',''),namespace)
        a=self.authority();config=a.worker_init['config']
        adapter=namespace['WaypointNavigationModule']();adapter.setup(ModuleContext(0,0.,0,config))
        goal=Sample(WaypointGoal(0,[2.,0.]),6,'map',0)
        def update(pose):
            ctx=ModuleContext(18,.1,24,config);samples={'goal':goal}
            if pose is not None:samples['pose']=pose
            adapter.update(Inputs(samples),ctx)
            return ctx._outputs[0][2]
        for pose in (None,Sample(Pose2D(0.,0.,0.),0,'map',0),Sample(Pose2D(0.,0.,0.),12,'odom',0)):
            value=update(pose);self.assertEqual(value['linear']['x'],0.);self.assertEqual(value['angular']['z'],0.)
        pose=Sample(Pose2D(0.,0.,0.),12,'map',0);value=update(pose)
        self.assertEqual(value['linear']['x'],self.spec['control_limits']['max_vx_mps'])
        self.assertEqual(value['angular']['z'],-self.spec['control_limits']['max_wz_radps'])
        self.assertFalse(adapter.controller.calls[-1][0].flags.writeable)
        for bad in (np.zeros(2),Twist(linear=Vector3(y=1.)),Twist(angular=Vector3(z=float('nan')))):
            adapter.controller.result=bad
            with self.subTest(bad=str(bad)),self.assertRaises((TypeError,ValueError)):update(pose)
