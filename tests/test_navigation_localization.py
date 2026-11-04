"""GPS/EKF curriculum: exact grading, aligned measurements, isolation and saved code."""
import copy
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import numpy as np
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot import Inputs,JointState,ModuleContext,PositionFix2D,Sample
from tankbot_host.application import ApplicationState,LEGACY_LAYERS
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure,catalog
from tankbot_host.level_plugins import LevelValidationError
from tankbot_host.navigation_templates import EKF_ADAPTER
from tankbot_host.workspace import starter
from tankbot_host.workspace_api import WorkspaceAPI
from navigation_support import solution


class NavigationLocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=load_config(ROOT/'config/game.yaml')

    def setUp(self):self.config=configure(self.base,'navigation.c2')

    def authority(self,files=None):
        a=Authority(self.config,controlled=True,startup_sources=files);self.addCleanup(a.close);return a

    def finish(self,a):
        for _ in range(a.campaign.limit_ticks+10*a.period):
            a.advance()
            if a.campaign.status!='active':return a.campaign.result
        self.fail('GPS localization did not terminate')

    def test_reference_passes_with_drift_and_scoring_does_not_follow_display_source(self):
        a=self.authority(solution(self.config))
        for _ in range(150):a.advance()
        self.assertEqual(a.selector.source_id,'ekf')
        self.assertEqual(a.view['schema'],'view_snapshot@5')
        self.assertEqual({m['channel'] for m in a.view['payload']['pose_estimates']},
                         {'/robot/estimates/ekf/pose','/robot/estimates/odometry/pose'})
        a.select_pose_source('odometry')
        result=self.finish(a)
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['scored_samples'],239)
        self.assertEqual(result['reference_samples'],239)
        self.assertLess(result['rmse_m'],.15);self.assertLess(result['yaw_rmse_rad'],.15)
        self.assertGreater(result['reference_rmse_m'],.3)
        self.assertGreater(result['origin_distance_m'],.3)  # Deliberately no endpoint pass gate.
        self.assertEqual(a.tick-a.campaign.started_tick,1440)
        self.assertEqual(a.view['payload']['selected_pose']['source_id'],'odometry')
        before=copy.deepcopy(a._private)
        for _ in range(30):a.advance()
        self.assertEqual(a._private,before)
        self.assertEqual(a.view['payload']['objects'],[])
        self.assertLessEqual(len(a._self_pose_history),self.config['runtime']['estimate_history_ticks']+1)

    def test_pure_prediction_without_gps_cannot_pass_default_seed(self):
        files=solution(self.config)
        source=files['localization/ekf.py'];source=source[:source.index('    def correct(')]+'''    def correct(self, position_m, measurement_covariance) -> None:
        pass
'''
        files['localization/ekf.py']=source
        result=self.finish(self.authority(files))
        self.assertFalse(result['passed']);self.assertEqual(result['reason'],'estimation_failed')
        self.assertAlmostEqual(result['rmse_m'],result['reference_rmse_m'])

    def test_same_seed_retries_repeat_and_other_confirmed_seeds_also_pass(self):
        traces=[]
        for seed in (1,1,2):
            self.config['runtime']['seed']=seed
            a=self.authority(solution(self.config));result=self.finish(a)
            self.assertTrue(result['passed'],result)
            traces.append((a._private,a._sensors,result))
        # Run IDs differ but physical state, measurements and diagnostics must not.
        self.assertEqual(traces[0][0],traces[1][0]);self.assertEqual(traces[0][2],traces[1][2])
        self.assertEqual(traces[0][1]['/robot/sensors/gps/fix']['payload'],traces[1][1]['/robot/sensors/gps/fix']['payload'])
        self.assertNotEqual(traces[0][0],traces[2][0])

    def test_bad_state_or_covariance_produces_python_traceback_or_router_rejection(self):
        for code,expected in (('self.state = np.zeros(2,dtype=np.float64)','shape=(3,)'),
                              ('self.covariance = np.full((3,3),np.nan,dtype=np.float64)','NaN/Inf'),
                              ('self.covariance = -np.eye(3,dtype=np.float64)','INVALID_COVARIANCE')):
            with self.subTest(code=code):
                files=solution(self.config)
                files['localization/ekf.py']=files['localization/ekf.py'].replace('        r: float = self.model.wheel_radius_m','        '+code+'\n        return\n        r: float = self.model.wheel_radius_m')
                a=self.authority(files);result=self.finish(a)
                self.assertFalse(result['passed']);self.assertLess(a.tick,60)
                log=json.dumps(a.logs.public(),ensure_ascii=False)
                self.assertIn(expected,log)
                if expected!='INVALID_COVARIANCE':self.assertIn('Traceback (most recent call last)',log)

    def test_runtime_and_views_only_receive_public_measurements_and_player_estimates(self):
        a=self.authority(solution(self.config))
        for _ in range(90):a.advance()
        self.assertEqual(set(a.runtime_inputs()),{'/robot/cmd_vel','/robot/sensors/joint_states','/robot/sensors/gps/fix'})
        self.assertNotIn('truth',json.dumps(a.worker_init));self.assertNotIn('gains',json.dumps(a.worker_init))
        self.assertNotIn('truth',json.dumps(a.view));self.assertIsNone(a._private['turret_state'])
        inputs=a.graph.graph['modules']
        for mid in ('wheel_control','odometry','ekf'):
            self.assertEqual(inputs[mid]['input_channels']['wheels'],'/robot/sensors/joint_states')
        fix=a._sensors['/robot/sensors/gps/fix']
        self.assertEqual(set(fix['payload']),{'position_m','covariance'})
        self.assertEqual(fix['frame_id'],'map')
        self.assertNotIn('/robot/localization/pose',a.runtime_inputs())

    def test_pose_comparison_allowlist_staleness_and_metric_permissions(self):
        a=self.authority(solution(self.config))
        for _ in range(90):a.advance()
        gateway=a.gateway;policy=gateway.policy
        policy['pose_estimate_channels']=['/robot/estimates/ekf/pose']
        def project(tick):return gateway.build(tick,0,a.selector,a._sensors,campaign=True,pose_candidates=a._candidates)
        self.assertEqual(len(project(a.tick)['pose_estimates']),1)
        self.assertEqual(project(a.tick+policy['pose_hide_after_ticks']+1)['pose_estimates'],[])
        policy['allowed_pose_frames']=[];self.assertEqual(project(a.tick)['pose_estimates'],[])
        allowed=a.campaign.definition['permissions']['visualization']['allowed_metrics']
        allowed.remove('reference_rmse_m');allowed.remove('reference_yaw_rmse_rad')
        self.assertNotIn('reference_rmse_m',a.campaign.public()['live_metrics'])
        a.config['campaign']['levels']['navigation.c2']['permissions']['visualization']['allowed_metrics']=allowed
        item=next(v for v in catalog(a.config) if v['level_id']=='navigation.c2')
        self.assertNotIn('reference_metric',item['live_feedback'][0])
        a.campaign.finish(a.tick,reason='aborted')
        self.assertNotIn('reference_rmse_m',a.campaign.public()['result'])
        self.assertNotIn('reference_samples',a.campaign.public()['result'])

    def test_scaffold_upgrade_preserves_all_algorithms_and_historical_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            c1=configure(self.base,'navigation.c1');api=WorkspaceAPI(c1,directory=directory)
            old=api.store.read();authored=solution(c1)
            api.store.edit(old['revision'],{path:authored[path] for path in ('control/wheel_controller.py','localization/odometry.py')})
            before=api.store.read();state=api.unlock(self.config)
            self.assertTrue(state['learning']['upgrade_required'])
            for path in ('control/wheel_controller.py','localization/odometry.py'):
                self.assertEqual(state['snapshot']['files'][path],before['files'][path])
            ekf='# my EKF\n'+solution(self.config)['localization/ekf.py']
            current=api.store.edit(state['snapshot']['revision'],{'localization/ekf.py':ekf})
            plan=api.post('upgrade',{'revision':current['revision']})
            for path in ('control/wheel_controller.py','localization/odometry.py','localization/ekf.py'):
                self.assertNotIn(path,[entry['path'] for entry in plan['entries']])
            api.post('apply',{'plan_id':plan['plan_id'],'revision':current['revision'],'resolutions':{entry['path']:'incoming' for entry in plan['entries']}})
            self.assertFalse(api.get()['learning']['upgrade_required'])
            self.assertEqual(api.store.read(before['revision'])['files'],before['files'])
            api.unlock(c1)
            self.assertTrue(api.get()['learning']['upgrade_required'])
            self.assertEqual(api.store.read()['files']['localization/ekf.py'],ekf)

    def test_existing_settings_and_completed_progress_are_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);state=ApplicationState(self.base,path/'settings.yaml',path/'progress.json')
            value=state.settings;value['layers']={k:value['layers'][k] for k in LEGACY_LAYERS}
            state.write_settings(value)
            for lid in state.levels[:-1]:state.complete(state.register_attempt(lid),lid)
            raw=(path/'settings.yaml').read_bytes();save=(path/'progress.json').read_bytes()
            reopened=ApplicationState(self.base,path/'settings.yaml',path/'progress.json')
            self.assertIn('navigation.c2',reopened.progress()['unlocked_levels'])
            self.assertFalse(reopened.settings['layers']['gps'])
            self.assertEqual(raw,(path/'settings.yaml').read_bytes());self.assertEqual(save,(path/'progress.json').read_bytes())

    def test_invalid_scored_source_alignment_and_initial_covariance_fail_at_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);shutil.copytree(ROOT/'levels',path/'levels')
            base=yaml.safe_load((ROOT/'config/game.yaml').read_text());base['level_plugins']['directory']=str(path/'levels')
            (path/'game.yaml').write_text(yaml.safe_dump(base))
            original=yaml.safe_load((ROOT/'levels/navigation.C2.yaml').read_text())
            for field in ('source','alignment','covariance','reference','candidate'):
                value=copy.deepcopy(original)
                if field=='source':value['evaluation']['module_id']='unknown'
                elif field=='alignment':value['robots'][0]['sensors'][1]['period_ticks']=20
                elif field=='covariance':value['communication']['runtime']['manifest']['modules'][2]['config']['initial_covariance']=[[-1,0,0],[0,1,0],[0,0,1]]
                elif field=='reference':value['evaluation']['reference_module_id']='ekf'
                else:value['permissions']['visualization']['view_policy']['pose_estimate_channels'].append('/robot/estimates/unknown/pose')
                (path/'levels/navigation.C2.yaml').write_text(yaml.safe_dump(value,allow_unicode=True))
                with self.subTest(field=field),self.assertRaises(LevelValidationError):load_config(path/'game.yaml')

    def test_ekf_adapter_deduplicates_gps_matches_time_and_resets(self):
        class Probe:
            def __init__(self,*args):self.state=np.zeros(3);self.covariance=np.zeros((3,3));self.predictions=[];self.corrections=[]
            def predict(self,rates,dt):self.predictions.append((rates,dt))
            def correct(self,position,covariance):self.corrections.append((position,covariance))
        namespace={'EkfLocalization':Probe}
        exec(EKF_ADAPTER.replace('from localization.ekf import EkfLocalization',''),namespace)
        a=self.authority();config=copy.deepcopy(a.worker_init['config'])
        config['module']={'initial_covariance':np.zeros((3,3)).tolist()}
        adapter=namespace['EkfLocalizationModule']();adapter.setup(ModuleContext(0,0.,0,config))
        def step(tick,gps_tick):
            wheels=Sample(JointState(('left','right'),(0.,0.),(1.,2.),()),tick,'base_link',tick)
            gps=Sample(PositionFix2D([1.,2.],np.eye(2)),gps_tick,'map',gps_tick)
            context=ModuleContext(tick,.1,tick+6,config)
            adapter.update(Inputs({'wheels':wheels,'gps':gps}),context)
            return context
        step(6,0);step(12,0);step(30,30);step(36,30)
        self.assertEqual(len(adapter.filter.corrections),1)
        self.assertEqual([round(p[1],5) for p in adapter.filter.predictions],[.1,.1,.3,.1])
        self.assertFalse(adapter.filter.predictions[0][0].flags.writeable)
        output=io.StringIO()
        with contextlib.redirect_stdout(output):step(42,40);step(48,40)
        self.assertIn('跳过未对齐',output.getvalue());self.assertEqual(len(adapter.filter.corrections),1)
        adapter.reset(ModuleContext(100,0.,100,config),'deploy')
        step(102,90);self.assertEqual(adapter.filter.corrections,[])
        self.assertAlmostEqual(adapter.filter.predictions[0][1],2/60)


if __name__=='__main__':unittest.main()
