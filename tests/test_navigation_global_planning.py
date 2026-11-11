"""One-shot preparation, formal lifecycle, privacy and old-project retention."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]
from tankbot_host.authority import load_config,Authority
from tankbot_host.campaign import configure,CampaignSession,catalog
from tankbot_host.deployment import DeploymentManager
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_host.planning_navigation import PlanningNavigation
from planning_support import solution


def drive_job(a,timeout=15):
    deadline=time.monotonic()+timeout
    while a.deployment.job and time.monotonic()<deadline:
        a.advance()
        if a.deployment.job and (not a.deployment.job['worker'].ready or a.deployment.job['phase'] in ('Planning','Initializing')):
            time.sleep(.001)
    if a.deployment.job:raise AssertionError('Deployment did not finish within isolated test deadline')
    return a.deployment.last


class NavigationPlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=load_config(ROOT/'config/game.yaml')
        cls.config=configure(cls.base,'navigation.c5')

    def authority(self,config=None):
        a=Authority(config or self.config,controlled=True)
        self.addCleanup(a.close)
        a.deployment=DeploymentManager(a)
        return a

    def snapshot(self,a,directory,files=None):
        api=WorkspaceAPI(a.config,directory=directory);current=api.store.read()
        return api.store.edit(current['revision'],{p:v for p,v in (files or {}).items() if current['files'].get(p)!=v}) if files else current

    def test_astar_dijkstra_multiseed_real_closed_loop_and_frozen_terminal(self):
        evidence=[]
        for algorithm in ('astar','dijkstra'):
            for seed in (0,1,2):
                c=copy.deepcopy(self.config);c['runtime']['seed']=seed
                with self.subTest(algorithm=algorithm,seed=seed),tempfile.TemporaryDirectory() as directory:
                    a=self.authority(c);snapshot=self.snapshot(a,directory,solution(c,algorithm))
                    before=copy.deepcopy(a._private['truth_pose'])
                    a.deployment.start('test',snapshot=snapshot);tested=drive_job(a)
                    self.assertEqual(tested['status'],'Ready',tested)
                    self.assertIsNone(a.campaign.started_tick);self.assertIsNone(a.campaign.navigation.reference)
                    self.assertEqual(a._private['truth_pose'],before)
                    tested_id=tested['id']
                    a.deployment.start('deploy',snapshot=snapshot);deployed=drive_job(a)
                    self.assertEqual(deployed['status'],'Active',deployed)
                    self.assertNotEqual(deployed['id'],tested_id)
                    self.assertIsNotNone(deployed['preparation']['planning_elapsed_ms'])
                    self.assertLess(deployed['preparation']['planning_elapsed_ms'],5000)
                    for _ in range(a.campaign.limit_ticks+30):
                        a.advance()
                        if a.campaign.status!='active':break
                    result=a.campaign.result
                    self.assertTrue(result and result['passed'],result)
                    self.assertEqual(result['settled_ticks'],30)
                    self.assertEqual(result['tracking_samples'],a.tick-a.campaign.started_tick)
                    self.assertEqual(a.worker.timing.public()['timeouts'],0)
                    self.assertEqual(a.graph.graph['modules']['path_tracking']['input_channels'],{'pose':'/robot/estimates/ekf/pose'})
                    self.assertNotIn('reference_length_m',json.dumps(a.worker_init))
                    self.assertNotIn('wall_contact',json.dumps(a.worker_init))
                    self.assertNotIn('truth',json.dumps(a.runtime_inputs()))
                    frozen=copy.deepcopy(a._private)
                    for _ in range(5):a.advance()
                    self.assertEqual(a._private,frozen)
                    evidence.append({'algorithm':algorithm,'seed':seed,'result':result,'test':tested,
                                     'deployment':deployed,'runtime':a.worker.timing.public(),
                                     'goal_xy':a.campaign.navigation.task['goal_xy'],
                                     'reference_length_m':a.campaign.navigation.task['reference_length_m']})
                    a.close();self._cleanups.pop()
        destination=ROOT/'.m1-cache/navigation-c5-qa/native-multiseed.json'
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')

    def test_blank_test_none_and_python_exception_do_not_start_official_attempt(self):
        for change,code in ((None,'PLANNING_NO_PATH'),
                            ('class GlobalPlanner:\n def __init__(self,*args):\n  raise RuntimeError("planner constructor evidence")\n','PLANNING_ERROR')):
            a=self.authority()
            with tempfile.TemporaryDirectory() as directory:
                snapshot=self.snapshot(a,directory,{'navigation/global_planner.py':change} if change else None)
                a.deployment.start('test',snapshot=snapshot);result=drive_job(a)
                self.assertEqual(result['status'],'Failed');self.assertIn(code,result['error'])
                self.assertIsNone(a.campaign.started_tick);self.assertEqual(a.campaign.status,'active')
                self.assertIsNone(a.campaign.navigation.reference)
                if change:
                    self.assertEqual(result['diagnostic']['path'],'navigation/global_planner.py')
            a.close();self._cleanups.pop()

    def test_planning_timeout_in_constructor_kills_worker_without_blocking_physics(self):
        a=self.authority()
        source='class GlobalPlanner:\n def __init__(self,*args):\n  while True: pass\n'
        with tempfile.TemporaryDirectory() as directory:
            snapshot=self.snapshot(a,directory,{'navigation/global_planner.py':source})
            a.deployment.start('test',snapshot=snapshot);worker=a.deployment.job['worker']
            started=time.monotonic();tick=a.tick
            result=drive_job(a,10)
            self.assertEqual(result['status'],'Failed');self.assertIn('RESOURCE_LIMIT',result['error'])
            self.assertGreaterEqual(time.monotonic()-started,5.)
            self.assertLess(time.monotonic()-started,9.)
            self.assertGreater(a.tick,tick+6);self.assertIsNotNone(worker.proc.poll())
            self.assertIsNone(a.campaign.started_tick)

    def test_freeze_rejects_replanning_and_ui_permissions_do_not_grant_program_data(self):
        a=self.authority();before_inputs=copy.deepcopy(a.runtime_inputs())
        with tempfile.TemporaryDirectory() as directory:
            snapshot=self.snapshot(a,directory,solution(self.config))
            for kind in ('test','deploy'):
                a.deployment.start(kind,snapshot=snapshot);self.assertIn(drive_job(a)['status'],('Ready','Active'))
            for _ in range(60):a.advance()
            started=a.campaign.started_tick;identity=a.campaign.navigation.reference['path_id']
            with self.assertRaisesRegex(ValueError,'PATH_FROZEN'):a.deployment.start('deploy',snapshot=snapshot)
            self.assertEqual(a.campaign.started_tick,started);self.assertEqual(a.campaign.navigation.reference['path_id'],identity)
        self.assertEqual(a.runtime_inputs(),before_inputs)
        public=a.campaign.public()['global_planning']
        self.assertNotIn('tracking_rmse_m',public);self.assertNotIn('path_length_m',public)
        entry=next(e for e in catalog(a.config) if e['level_id']=='navigation.c5')
        self.assertIn('grid',entry['global_planning']['map']);self.assertIn('inflated_grid',entry['global_planning'])
        self.assertNotIn('reference_length_m',json.dumps(entry))
        permission=a.campaign.definition['permissions']['visualization']
        permission['allowed_layers'].remove('path');permission['task_feedback']['live']=[]
        self.assertNotIn('route',a.campaign.public()['global_planning'])
        self.assertNotIn('goal_distance_m',a.campaign.public()['global_planning'])

    def test_formal_no_path_response_fails_brakes_and_preserves_source_revision(self):
        from unittest.mock import patch
        a=self.authority()
        with tempfile.TemporaryDirectory() as directory:
            snapshot=self.snapshot(a,directory,solution(self.config))
            a.deployment.start('test',snapshot=snapshot);self.assertEqual(drive_job(a)['status'],'Ready')
            a.deployment.start('deploy',snapshot=snapshot);worker=a.deployment.job['worker'];poll=worker.poll_preparation
            def no_path():
                response=poll()
                if response and response['operation']=='plan':response['payload']['result']=None
                return response
            with patch.object(worker,'poll_preparation',side_effect=no_path):result=drive_job(a)
            self.assertIn('PLANNING_NO_PATH',result['error'])
            self.assertEqual(a.campaign.result['reason'],'planning_failed');self.assertFalse(a.campaign.result['passed'])
            self.assertIsNone(a.campaign.started_tick);self.assertIsNone(a._wheel_voltage_target)
            self.assertIsNone(a.campaign.navigation.reference)
            frozen=copy.deepcopy(a._private)
            for _ in range(10):a.advance()
            self.assertEqual(a._private,frozen)
            self.assertEqual(WorkspaceAPI(a.config,directory=directory).store.read()['revision'],snapshot['revision'])

    def test_continuous_stop_last_tick_contact_fault_priority_and_diagnostics_not_gates(self):
        for condition in ('success','collision','fault','timeout'):
            s=CampaignSession(copy.deepcopy(self.config));task=copy.deepcopy(s.navigation.task);task['goal_xy']=[1.,0.]
            s.navigation=PlanningNavigation(s.navigation.spec,task,60)
            s.navigation.accept_path({'path_id':'unit','points_m':[[0.,0.],[1.,0.]],'length_m':1.},1.)
            s.start(0);s.navigation.weighted_squared_error=10000.;s.navigation.scored_duration_s=1.
            first=s.limit_ticks-30+(condition=='timeout')
            result=None
            for tick in range(first,s.limit_ticks+1):
                s.controller_faulted=condition=='fault' and tick==s.limit_ticks
                private={'truth_pose':[1.,0.,2.],'truth_velocity':[0.,0.,0.],'targets':[],'target_hits':{},
                         'motion_metrics':{'path_length_m':0.},'wall_contact':condition=='collision' and tick==s.limit_ticks}
                result=s.outcome(private,tick)
            self.assertEqual(result,{'success':'objective_completed','collision':'collision','fault':'controller_error','timeout':'timeout'}[condition])
            s.finish(s.limit_ticks,passed=condition=='success',reason=result)
            report=copy.deepcopy(s.result);s.outcome(private,s.limit_ticks+1);self.assertEqual(s.result,report)

    def test_upgrade_preview_and_roundtrip_retain_four_algorithms_custom_files_and_history(self):
        c4=configure(self.base,'navigation.c4');files=solution(self.config)
        protected=('control/wheel_controller.py','localization/odometry.py','localization/ekf.py','navigation/path_follower.py')
        with tempfile.TemporaryDirectory() as directory:
            api=WorkspaceAPI(c4,directory=directory);initial=api.store.read()
            saved=api.store.edit(initial['revision'],{**{p:files[p] for p in protected},'my_notes.py':'# player-owned\n'})
            api.unlock(self.config);current=api.store.read();plan=api.post('upgrade',{'revision':current['revision']})
            self.assertFalse(set(protected)&{e['path'] for e in plan['entries']})
            self.assertIn('return None',current['files']['navigation/global_planner.py'])
            api.post('apply',{'plan_id':plan['plan_id'],'revision':current['revision'],
                              'resolutions':{e['path']:'incoming' for e in plan['entries']}})
            api.unlock(c4);api.unlock(self.config);restored=api.store.read()
            for p in protected:self.assertEqual(restored['files'][p],saved['files'][p])
            self.assertEqual(restored['files']['my_notes.py'],'# player-owned\n')
            self.assertEqual(api.store.read(saved['revision']),saved)
