"""Migration baseline, strict plugin validation, permissions and zero-code discovery."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ("host","protocol","sdk/python")]
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure,CampaignSession
from tankbot_host.configuration import load_yaml
from tankbot_host.level_plugins import LevelValidationError
from tankbot_host.workspace import starter
from tankbot_host.application import ApplicationState
from level_baseline_support import projection
from campaign_support import TRANSFORMS,solutions
from tankbot_host.level_rules import evaluate


class Dumper(yaml.SafeDumper):
    def ignore_aliases(self,value):return True


class LevelPluginTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.levels=self.directory/'levels';shutil.copytree(ROOT/'levels',self.levels)
        self.base=load_yaml(ROOT/'config/game.yaml')
        self.base['level_plugins']['directory']=str(self.levels)
        self.path=self.directory/'game.yaml'
        self.write_base()

    def write_base(self):self.path.write_text(yaml.dump(self.base,Dumper=Dumper,allow_unicode=True,sort_keys=False))

    def definition(self,lid='c0'):return load_yaml(self.levels/(lid+'.yaml'))

    def write(self,value,lid='c0'):
        (self.levels/(lid+'.yaml')).write_text(yaml.dump(value,Dumper=Dumper,allow_unicode=True,sort_keys=False))

    def assert_subset(self,expected,actual,path=''):
        if isinstance(expected,dict):
            self.assertIsInstance(actual,dict,path)
            for key,value in expected.items():
                self.assertIn(key,actual,path+'.'+key)
                self.assert_subset(value,actual[key],path+'.'+key)
        else:self.assertEqual(expected,actual,path)

    def test_all_five_match_frozen_pre_refactoring_runtime_baselines(self):
        baseline=json.loads((ROOT/'tests/fixtures/level-behavior-before.json').read_text())
        config=load_config(self.path)
        self.assertEqual(list(config['campaign']['levels']),[*baseline['levels'],'c5'])
        for lid,expected in baseline['levels'].items():
            # User explicitly redesigned C3/C4 and added C5. Freeze the unchanged C0-C2 here;
            # new sensor/control/goal semantics have dedicated curriculum acceptance tests.
            if lid not in ('c0','c1','c2'):continue
            expected=copy.deepcopy(expected)
            # Subsequent user requirement: Weapons projectiles are now visible.
            # Keep the original fixture; only this explicit policy change is exempt.
            if lid in ('c1','c2','c3','c4'):
                expected=copy.deepcopy(expected)
                self.assertIs(expected['physics']['view_policy']['world_effects'],False)
                expected['physics']['view_policy']['world_effects']=True
            if lid=='c2':
                expected['guide']['steps']=[text.replace('击杀后通关；真值误差仅在尝试结束后给出。','击杀后通关；运行中查看累计位置 RMSE 和趋势，越低表示整体误差越小。') for text in expected['guide']['steps']]
                expected['guide']['completion']=expected['guide']['completion'].replace('把敌车 HP 减到 0 即通关；误差评分在尝试结束后显示，不作为额外门槛。','把敌车 HP 减到 0 即通关；运行中显示累计位置 RMSE，结束后保留最终诊断，不作为额外门槛。')
            with self.subTest(level=lid):
                actual=projection(config,lid)
                # SDK reference is additive across every lesson. Existing constructors, field
                # types and method signatures remain compatible; explanatory text can describe
                # the new sensors without pretending the old center-only C4 still exists.
                old_types=expected.pop('types');new_types={item['name']:item for item in actual['types']}
                for item in old_types:
                    value=new_types[item['name']]
                    self.assertEqual(item['constructor'],value['constructor'])
                    self.assertEqual([(f['name'],f['type']) for f in item['fields']],[(f['name'],f['type']) for f in value['fields']])
                    signatures={m['signature'] for m in value['methods']}
                    self.assertTrue({m['signature'] for m in item['methods']}<=signatures)
                self.assert_subset(expected,actual,lid)

    def test_invalid_definitions_report_file_and_precise_field(self):
        cases=[
            ('version','schema_version',lambda d:d.update(schema_version='99')),
            ('robot_type','robots[0].type',lambda d:d['robots'][0].update(type='unregistered_robot')),
            ('rate','robots[0].sensors[0].update_hz',lambda d:d['robots'][0]['sensors'][0].update(update_hz=0)),
            ('robot_id','robots',lambda d:d['robots'][1].update(id='player')),
            ('target_ref','objectives.target',lambda d:d['objectives'].update(target='missing')),
            ('rule','objectives.success',lambda d:d['objectives']['success'].update(type='unregistered_rule')),
            ('metric','evaluation.metrics[0].type',lambda d:d['evaluation']['metrics'][0].update(type='unknown_metric')),
            ('data_access','permissions.data_access.inputs',lambda d:d['permissions']['data_access']['inputs'].update({'/world/truth':'pose2d@1'})),
            ('display','visualization.initial_enabled',lambda d:d['visualization']['initial_enabled'].append('truth_robot')),
            ('source','visualization.sources.robot',lambda d:d['visualization']['sources'].update(robot='authorized_truth')),
            ('topic_collision','communication.runtime.manifest.connections',lambda d:d['communication']['runtime']['manifest']['connections'].append(copy.deepcopy(d['communication']['runtime']['manifest']['connections'][-1]))),
            ('code','communication.runtime.contracts.perception.entry_point',lambda d:d['communication']['runtime']['contracts']['perception'].update(entry_point='os:system')),
            ('overwrite','communication.runtime.managed_files',lambda d:d['communication']['runtime']['managed_files'].append('perception/transforms.py')),
            ('asset','world.map.path',lambda d:d['world'].update(map={'source':'asset','path':'../../outside.yaml'})),
            ('missing_asset','world.map.path',lambda d:d['world'].update(map={'source':'asset','path':'maps/does_not_exist.yaml'})),
            ('unknown','',lambda d:d.update(extra_script='module:run')),
        ]
        original=self.definition()
        for name,path,mutate in cases:
            with self.subTest(case=name):
                d=copy.deepcopy(original);mutate(d);self.write(d)
                with self.assertRaises(LevelValidationError) as raised:load_config(self.path)
                self.assertEqual(Path(raised.exception.filename).name,'c0.yaml')
                self.assertTrue(raised.exception.path.startswith(path),raised.exception)
                self.assertTrue(raised.exception.reason)

    def test_yaml_resource_limits_aliases_tags_and_duplicate_keys(self):
        path=self.levels/'c0.yaml';original=path.read_text()
        for source in ('schema_version: 1\nschema_version: 2\n','x: !!python/object:object {}','x: &a [1]\ny: *a\n','x: '+('['*40)+'1'+(']'*40)):
            with self.subTest(source=source[:30]):
                path.write_text(source)
                with self.assertRaises(LevelValidationError):load_config(self.path)
        path.write_text(original)
        self.base['level_plugins']['limits']['max_file_bytes']=10;self.write_base()
        with self.assertRaisesRegex(LevelValidationError,'max_file_bytes'):load_config(self.path)

    def test_live_metric_needs_explicit_visualization_grant_and_valid_display_parameters(self):
        original=self.definition('c2')
        cases=[('grant',lambda d:d['permissions']['visualization'].pop('allowed_metrics'),'evaluation.live_feedback.metric'),
               ('precision',lambda d:d['evaluation']['live_feedback'].update(precision=-1),'evaluation.live_feedback.precision'),
               ('history',lambda d:d['evaluation']['live_feedback'].update(history_points=0),'evaluation.live_feedback.history_points'),
               ('metric',lambda d:d['evaluation']['live_feedback'].update(metric='truth_pose'),'evaluation.live_feedback.metric')]
        for name,mutate,path in cases:
            with self.subTest(case=name):
                d=copy.deepcopy(original);mutate(d);self.write(d,'c2')
                with self.assertRaises(LevelValidationError) as raised:load_config(self.path)
                self.assertEqual(raised.exception.path,path)

    def test_duplicate_ids_prerequisites_and_discovery_count_are_validated(self):
        original=self.definition('c1')
        for field,value,expected in [('id','c0','metadata.id'),('order',0,'metadata.order'),('prerequisites',['missing'],'metadata.prerequisites')]:
            d=copy.deepcopy(original);d['metadata'][field]=value;self.write(d,'c1')
            with self.assertRaises(LevelValidationError) as raised:load_config(self.path)
            self.assertEqual(raised.exception.path,expected)
        self.write(original,'c1')
        self.base['level_plugins']['limits']['max_files']=4;self.write_base()
        with self.assertRaisesRegex(LevelValidationError,'too many level files'):load_config(self.path)

    def test_temporary_plugin_runs_with_arbitrary_id_and_no_engine_edits(self):
        d=self.definition('c1');lid='robotics.temporary_probe'
        d['metadata'].update(id=lid,name='Temporary test only',order=6,prerequisites=['c5'])
        d['robots'][0]['initial_pose']=[.5,-.5,.2]
        d['objectives']['time_limit_s']=7
        d['objectives']['parameters']['required_hits']=2
        self.write(d,'temporary')
        config=load_config(self.path)
        self.assertEqual(len(config['campaign']['levels']),7)
        resolved=configure(config,lid);files=starter(resolved);files['perception/transforms.py']=TRANSFORMS
        a=Authority(resolved,controlled=True,startup_sources=files);self.addCleanup(a.close)
        for _ in range(30):a.advance()
        for actual,expected in zip(a._private['truth_pose'],[.5,-.5,.2]):self.assertAlmostEqual(actual,expected)
        self.assertIsNotNone(a._target_estimate)
        self.assertEqual(a.campaign.limit_ticks,7*60)
        from tankbot_host.cli import make_parser
        self.assertEqual(make_parser().parse_args(['headless','--level',lid]).level,lid)
        state=ApplicationState(config,self.directory/'settings.yaml',self.directory/'progress.json')
        for key in state.levels[:-1]:state.complete(state.register_attempt(key),key)
        self.assertIn(lid,state.progress()['unlocked_levels'])
        self.assertEqual(len(list((ROOT/'levels').glob('*.yaml'))),6)

    def test_data_permission_is_independent_of_system_pose_visualization(self):
        d=self.definition();d['permissions']['data_access']['inputs']={}
        d['communication']['runtime']['contracts']['perception']['inputs']['self_pose']['required']=False
        self.write(d)
        config=configure(load_config(self.path),'c0');files=starter(config)
        files['campaign_robot.py']='''from tankbot import Module, TargetEstimate
class CampaignRobot(Module):
    def update(self, inputs, ctx):
        assert inputs.latest("self_pose") is None
        ctx.publish("target",TargetEstimate(1,2),frame_id="map")
'''
        a=Authority(config,controlled=True,startup_sources=files);self.addCleanup(a.close)
        for _ in range(24):a.advance()
        self.assertIsNotNone(a.view['payload']['selected_pose'])
        self.assertEqual(a._target_estimate['payload']['x_m'],1)
        self.assertFalse(a._faulted)

    def test_program_pose_access_does_not_authorize_its_visualization(self):
        d=self.definition();d['permissions']['visualization']['view_policy']['system_pose_allowed']=False
        self.write(d)
        config=configure(load_config(self.path),'c0');files=starter(config)
        files['campaign_robot.py']='''from tankbot import Module, TargetEstimate
class CampaignRobot(Module):
    def update(self, inputs, ctx):
        pose=inputs.latest("self_pose")
        assert pose is not None
        ctx.publish("target",TargetEstimate(pose.data.x_m,pose.data.y_m),frame_id="map")
'''
        a=Authority(config,controlled=True,startup_sources=files);self.addCleanup(a.close)
        for _ in range(24):a.advance()
        self.assertIsNone(a.view['payload']['selected_pose'])
        self.assertIsNotNone(a._target_estimate)

    def test_denied_pose_channels_do_not_prevent_other_authorized_views(self):
        d=self.definition();d['permissions']['data_access']['inputs']={}
        d['permissions']['visualization']['view_policy']['system_pose_allowed']=False
        d['communication']['runtime']['contracts']['perception']['inputs']['self_pose']['required']=False
        self.write(d)
        config=configure(load_config(self.path),'c0')
        a=Authority(config,controlled=True);self.addCleanup(a.close)
        for _ in range(12):a.advance()
        self.assertIsNone(a.view['payload']['selected_pose'])
        self.assertNotIn('/robot/localization/pose',a._sensors)
        self.assertTrue(any(obj['kind']=='target' for obj in a.view['payload']['objects']))

    def test_visualization_layer_permissions_also_cap_authority_messages(self):
        d=self.definition()
        denied={'truth_targets','projectiles','encoders','map'}
        d['permissions']['visualization']['allowed_layers']=[key for key in d['permissions']['visualization']['allowed_layers'] if key not in denied]
        for key in ('initial_enabled','user_toggleable'):
            d['visualization'][key]=[name for name in d['visualization'][key] if name not in denied]
        for key in denied:d['visualization']['sources'].pop(key,None)
        self.write(d)
        config=configure(load_config(self.path),'c0')
        a=Authority(config,controlled=True);self.addCleanup(a.close)
        for _ in range(12):a.advance()
        self.assertEqual(a.view['payload']['objects'],[])
        self.assertNotIn('/robot/sensors/joint_states',[m['channel'] for m in a.view['payload']['local_observations']])
        self.assertEqual(a.public_profile()['walls'],[])
        self.assertIn('/robot/localization/pose',a.runtime_inputs())

    def test_rule_composition_and_diagnostics_do_not_depend_on_ui(self):
        rule={'type':'any','conditions':[{'type':'compare','metric':'hits','operator':'>','value':2},{'type':'not','condition':{'type':'compare','metric':'player_alive','operator':'==','value':False}}]}
        self.assertTrue(evaluate(rule,{'hits':0,'player_alive':True},{}))
        config=configure(load_config(self.path),'c1');session=CampaignSession(config);session.start(0)
        config['view_policy']['target_estimates_allowed']=False
        session.estimate({'simulation_tick':6,'payload':{'x_m':1,'y_m':0}},[0,0,0])
        self.assertIsNone(session.public()['result'])
        result=session.finish(12)['result']
        self.assertEqual(result['rmse_m'],1.)
        self.assertEqual(result['scored_samples'],1)

    def test_old_generated_player_adapter_still_runs_unchanged(self):
        old=json.loads((ROOT/'tests/fixtures/level-behavior-before.json').read_text())['legacy_adapter']
        for lid in ('c0','c1','c2'):
            config=configure(load_config(self.path),lid);files=solutions(config);files['campaign_robot.py']=old
            a=Authority(config,controlled=True,startup_sources=files)
            try:
                for _ in range(36):a.advance()
                self.assertFalse(a._faulted)
                if lid!='c0':self.assertIsNotNone(a._target_estimate)
            finally:a.close()

    def test_existing_progress_file_bytes_and_unlocks_survive_new_catalogue(self):
        config=load_config(self.path)
        path=self.directory/'progress.json';settings=self.directory/'settings.yaml'
        old={'version':1,'completed_levels':['c0','c1'],'current_level':'c2','completions':{'c0':{'completed_at':'2026-10-24T12:00:00+00:00'},'c1':{'completed_at':'2026-10-24T12:01:00+00:00'}}}
        path.write_text(json.dumps(old));before=path.read_bytes()
        state=ApplicationState(config,settings,path)
        self.assertEqual(state.progress()['unlocked_levels'],['c0','c1','c2'])
        self.assertEqual(path.read_bytes(),before)
        reopened=ApplicationState(config,settings,path)
        self.assertEqual(reopened.progress()['completed_levels'],['c0','c1'])

    def test_switch_and_restart_clear_world_workers_topics_and_metrics_but_keep_code(self):
        from tankbot_host.server import LocalServer
        config=configure(load_config(self.path),'c0');config['host']['port']=0
        state=ApplicationState(config,self.directory/'settings.yaml',self.directory/'progress.json')
        value=state.public_settings();value['settings']['developer_mode']=True;state.update_settings(value={'revision':value['revision'],'settings':value['settings']})
        a=Authority(config,controlled=True)
        server=LocalServer(a,workspace_store=self.directory/'store',application=state)
        self.addCleanup(server.http.server_close)
        self.addCleanup(lambda:server.authority.close())
        snapshot=server.workspace.store.read()
        server.workspace.store.edit(snapshot['revision'],{'player_tools.py':'# preserve me\n'})
        runs={a.run_id}
        for lid in ('c1','c2','c3','c4','c5','c5','c0','c5'):
            old=server.authority
            for _ in range(12):old.advance()
            server.start_level(lid)
            current=server.authority
            self.assertIsNot(current,old)
            self.assertIsNotNone(old.worker.proc.poll())
            self.assertIsNotNone(old.core.proc.poll())
            self.assertNotIn(current.run_id,runs);runs.add(current.run_id)
            self.assertEqual(current.tick,0)
            self.assertEqual(current._private['truth_pose'],[0.,0.,0.])
            self.assertEqual(current._private['projectiles'],[])
            self.assertIsNone(current._target_estimate)
            self.assertIsNone(current.campaign.started_tick)
            self.assertEqual(current.campaign.estimates,0)
            self.assertEqual(current.campaign.hits,0)
            self.assertIsNone(current.campaign.result)
            self.assertEqual(server.workspace.store.read()['files']['player_tools.py'],'# preserve me\n')
