"""C6 prior/private boundaries, lifecycle and real native reference closed loops."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]
from tankbot_host.authority import Authority,load_config,core_configuration
from tankbot_host.campaign import configure
from tankbot_host.deployment import DeploymentManager
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_protocol.validation import Rejected
from test_navigation_global_planning import drive_job
from local_navigation_support import solution


class NavigationLocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=load_config(ROOT/'config/game.yaml')
        cls.config=configure(cls.base,'navigation.c6')

    def create(self,config=None):
        a=Authority(config or self.config,controlled=True);self.addCleanup(a.close)
        a.deployment=DeploymentManager(a);return a

    def snapshot(self,a,directory,method):
        api=WorkspaceAPI(a.config,directory=directory);s=api.store.read()
        return api.store.edit(s['revision'],{p:v for p,v in solution(a.config,method).items() if s['files'].get(p)!=v})

    def test_prior_physics_program_view_and_developer_boundaries(self):
        a=self.create();private=a.config['private_obstacles']['walls'][0]
        self.assertNotIn(private,a.public_profile()['walls']);self.assertNotIn('private_obstacles',json.dumps(a.public_profile()))
        self.assertIn(private,core_configuration(a.config)['scene']['walls'])
        self.assertEqual(len(a.scene.world.walls),len(a.config['scene']['walls'])+1)
        self.assertNotIn('private_obstacles',json.dumps(a.worker_init));self.assertNotIn('reference_length_m',json.dumps(a.worker_init))
        self.assertEqual(a.worker_init['config']['local_navigation_parameters']['command_delay_s'],.2)
        with self.assertRaises(Rejected):a.developer_snapshot()
        before=copy.deepcopy(a.runtime_inputs());a.developer_mode=True
        self.assertEqual(a.developer_snapshot()['private_obstacles'],[private]);self.assertEqual(a.runtime_inputs(),before)
        self.assertNotIn('truth',json.dumps(a.view));self.assertEqual(a.view['payload']['objects'],[])
        with tempfile.TemporaryDirectory() as tmp:
            snap=self.snapshot(a,tmp,'nominal');position=copy.deepcopy(a._private['truth_pose'])
            a.deployment.start('test',snapshot=snap);result=drive_job(a)
            # A prior-safe plan crossing the unmarked square must still pass.
            self.assertEqual(result['status'],'Ready',result)
            self.assertEqual(a._private['truth_pose'],position);self.assertIsNone(a.campaign.started_tick)
            self.assertIsNone(a.campaign.navigation.reference)

    def test_two_reference_methods_three_seeds_and_terminal_freeze(self):
        evidence=[]
        for method in ('geometric','dwa'):
            for seed in (0,1,2):
                with self.subTest(method=method,seed=seed),tempfile.TemporaryDirectory() as tmp:
                    c=copy.deepcopy(self.config);c['runtime']['seed']=seed;a=self.create(c)
                    snap=self.snapshot(a,tmp,method)
                    for op in ('test','deploy'):
                        a.deployment.start(op,snapshot=snap);last=drive_job(a)
                        self.assertIn(last['status'],('Ready','Active'),last)
                    for _ in range(a.campaign.limit_ticks+30):
                        a.advance()
                        if a.campaign.status!='active':break
                    evidence.append({'method':method,'seed':seed,'result':copy.deepcopy(a.campaign.result),
                                     'runtime':a.worker.timing.public(),'started_tick':a.campaign.started_tick,
                                     'last_local':copy.deepcopy(a.control_feedback.local),
                                     'scan_costs_ms':list(a.sensor_scheduler.backend('distance_scan').costs_ms)})
                    self.assertTrue(a.campaign.result['passed'],a.campaign.result)
                    self.assertEqual(a.campaign.result['settled_ticks'],30)
                    self.assertEqual(a.worker.timing.public()['timeouts'],0)
                    self.assertEqual(a.graph.graph['modules']['path_tracking']['input_channels'],
                                     {'pose':'/robot/estimates/ekf/pose','scan':'/robot/sensors/scan','wheels':'/robot/sensors/joint_states'})
                    self.assertEqual(a.control_feedback.local['payload']['protection'],'ok')
                    result=copy.deepcopy(a.campaign.result);physical=copy.deepcopy(a._private)
                    for _ in range(8):a.advance()
                    self.assertEqual(a.campaign.result,result);self.assertEqual(a._private,physical)
                    a.close();self._cleanups.pop()
        p=ROOT/'.m1-cache/navigation-c6-qa/native-regression.json';p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')

    def test_nominal_hits_unknown_obstacle_while_stop_only_times_out(self):
        for method,reason in (('nominal','collision'),('stop','timeout')):
            with self.subTest(method=method),tempfile.TemporaryDirectory() as tmp:
                a=self.create();snap=self.snapshot(a,tmp,method)
                for op in ('test','deploy'):
                    a.deployment.start(op,snapshot=snap);self.assertIn(drive_job(a)['status'],('Ready','Active'))
                for _ in range(a.campaign.limit_ticks+30):
                    a.advance()
                    if a.campaign.status!='active':break
                self.assertEqual(a.campaign.result['reason'],reason)
                self.assertNotIn('contact',json.dumps(a.campaign_status()))
                a.close();self._cleanups.pop()

    def test_a_prior_only_alternative_plan_can_pass_without_avoidance_actions(self):
        # A different public-map search cost prefers the upper half-plane.
        # No hidden obstacle input, fixed waypoint or judge route is supplied.
        a=self.create()
        with tempfile.TemporaryDirectory() as directory:
            files=solution(a.config,'nominal')
            key='navigation/planning_geometry.py'
            files[key]=files[key].replace('simplified = [nodes[0]]','simplified = nodes').replace('current = 0','current = len(nodes)-1')
            key='navigation/global_planner.py'
            files[key]=files[key].replace('candidate = distance+step','candidate = distance+step*(5. if geo.data.grid_to_world(*neighbour)[1]<start_xy[1] else 1.)')
            api=WorkspaceAPI(a.config,directory=directory);head=api.store.read()
            snapshot=api.store.edit(head['revision'],{p:v for p,v in files.items() if head['files'].get(p)!=v})
            for op in ('test','deploy'):
                a.deployment.start(op,snapshot=snapshot);self.assertIn(drive_job(a)['status'],('Ready','Active'))
            for _ in range(a.campaign.limit_ticks+30):
                a.advance()
                if a.campaign.status!='active':break
            self.assertTrue(a.campaign.result['passed'],a.campaign.result)
            self.assertEqual(a.control_feedback.local['payload']['nominal_vx_mps'],a.control_feedback.local['payload']['final_vx_mps'])

    def test_local_runtime_infinite_loop_is_terminated_without_driving_test_world(self):
        a=self.create()
        with tempfile.TemporaryDirectory() as directory:
            api=WorkspaceAPI(a.config,directory=directory);head=api.store.read();files=solution(a.config)
            files['navigation/local_controller.py']='class LocalController:\n def __init__(self,*args):pass\n def update(self,observation,dt):\n  while True:pass\n'
            snapshot=api.store.edit(head['revision'],{p:v for p,v in files.items() if head['files'].get(p)!=v})
            before=copy.deepcopy(a._private['truth_pose'])
            a.deployment.start('test',snapshot=snapshot);worker=a.deployment.job['worker'];result=drive_job(a)
            self.assertEqual(result['status'],'Failed');self.assertIsNotNone(worker.proc.poll())
            self.assertIsNone(a.campaign.started_tick);self.assertEqual(a._private['truth_pose'],before)
            self.assertIsNone(a.campaign.navigation.reference)

    def test_upgrade_roundtrip_keeps_five_algorithms_custom_source_and_revision(self):
        previous=configure(self.base,'navigation.c5');files=solution(self.config)
        names=('control/wheel_controller.py','localization/odometry.py','localization/ekf.py','navigation/path_follower.py','navigation/global_planner.py')
        with tempfile.TemporaryDirectory() as directory:
            api=WorkspaceAPI(previous,directory=directory);old=api.store.read()
            saved=api.store.edit(old['revision'],{**{p:files[p] for p in names},'my_notes.py':'# C6 preservation\n'})
            api.unlock(self.config);head=api.store.read();plan=api.post('upgrade',{'revision':head['revision']})
            self.assertFalse(set(names)&{e['path'] for e in plan['entries']})
            api.post('apply',{'plan_id':plan['plan_id'],'revision':head['revision'],'resolutions':{e['path']:'incoming' for e in plan['entries']}})
            for config in (previous,self.config,previous):api.unlock(config)
            restored=api.store.read()
            for p in names:self.assertEqual(restored['files'][p],saved['files'][p])
            self.assertEqual(restored['files']['my_notes.py'],'# C6 preservation\n')
            self.assertEqual(api.store.read(saved['revision']),saved)
