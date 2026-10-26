"""Shared player projects can return to earlier runtime profiles without losing code."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure
from tankbot_host.campaign_templates import framework_upgrade
from tankbot_host.deployment import DeploymentManager,inspect_snapshot
from tankbot_host.workspace import starter,digest
from tankbot_host.workspace_api import WorkspaceAPI
from campaign_support import solutions


class FrameworkTransitionTests(unittest.TestCase):
    def setUp(self):
        self.base=load_config(ROOT/'config/game.yaml')

    def test_retained_current_wrapper_does_not_mask_graph_manifest_in_single_profile(self):
        for graph_level in ('c3','c4'):
            for level in ('c1','c2'):
                with self.subTest(origin=graph_level,destination=level):
                    config=configure(self.base,level)
                    files={**starter(config),**starter(configure(self.base,graph_level))}
                    self.assertIn('managed scaffold 1.2.0',files['campaign_robot.py'])
                    self.assertEqual(len(json.loads(files['tankbot.json'])['modules']),len(self.base['campaign']['levels'][graph_level]['runtime']['manifest']['modules']))
                    upgrade=framework_upgrade(config,files)
                    self.assertTrue(upgrade['required'])
                    self.assertIn('模块配置与本关不匹配',upgrade['message'])

    def test_returning_across_profiles_preserves_sources_history_and_test_deploy_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            api=WorkspaceAPI(configure(self.base,'c2'),directory=directory)
            initial=api.store.read()
            files=solutions(configure(self.base,'c2'))
            files['player_helpers.py']='# keep custom player code\n'
            files['tests/test_player_custom.py']='import unittest\nclass CustomTest(unittest.TestCase):\n    def test_custom(self):\n        self.assertTrue(True)\n'
            saved=api.store.edit(initial['revision'],files)
            for level in ('c3','c1','c2','c4','c2','c3','c1'):
                with self.subTest(level=level):
                    config=configure(self.base,level)
                    view=api.unlock(config);before=view['snapshot']
                    if view['learning']['upgrade_required']:
                        plan=api.post('upgrade',{'revision':before['revision']})
                        self.assertEqual(api.store.read()['revision'],before['revision'])
                        self.assertTrue(plan['message'])
                        managed=set(view['learning']['managed_files'])
                        self.assertFalse(any(e['path'] in ('perception/transforms.py','perception/tracker.py','player_helpers.py','tests/test_player_custom.py') for e in plan['entries']))
                        current=api.post('apply',{'revision':plan['base_revision'],'plan_id':plan['plan_id'],
                            'resolutions':{e['path']:'incoming' for e in plan['entries']}})
                        for path,source in before['files'].items():
                            if path not in managed:self.assertEqual(current['files'][path],source,path)
                        self.assertEqual(api.store.read(before['revision'])['files'],before['files'])
                    self.assertFalse(api.get()['learning']['upgrade_required'])
                    snapshot=api.store.read()
                    for path in ('perception/transforms.py','perception/tracker.py','player_helpers.py','tests/test_player_custom.py'):
                        self.assertEqual(snapshot['files'][path],saved['files'][path])
                    a=Authority(config,controlled=True)
                    try:
                        a.deployment=DeploymentManager(a)
                        artifact=inspect_snapshot(snapshot,a)
                        self.assertEqual('graph' in artifact,config['campaign']['levels'][level]['runtime']['mode']=='graph')
                        a.deployment.start('test',snapshot)
                        self.finish(a)
                        self.assertEqual(a.deployment.last['status'],'Ready',a.deployment.last)
                        a.deployment.start('deploy',snapshot)
                        self.finish(a)
                        self.assertEqual(a.deployment.last['status'],'Active',a.deployment.last)
                        if a.graph_profile() is None:
                            self.assertIsNone(a.graph)
                            self.assertEqual(a.config['control_sources']['turret'],'keyboard')
                            self.assertEqual(a.config['control_sources']['weapon'],'keyboard')
                    finally:a.close()

    def finish(self,a):
        deadline=time.monotonic()+10
        while a.deployment.job and time.monotonic()<deadline:
            a.advance()
            if a.deployment.job and not a.deployment.job['worker'].ready:time.sleep(.002)
        self.assertIsNone(a.deployment.job)

    def test_valid_single_custom_entrypoint_still_passes_without_forcing_template(self):
        config=configure(self.base,'c1');files=solutions(config)
        manifest=json.loads(files['tankbot.json']);contract=json.loads(files['contracts/perception.json'])
        manifest['entry_point']=contract['entry_point']='player_module:Custom'
        files['tankbot.json']=json.dumps(manifest);files['contracts/perception.json']=json.dumps(contract)
        files['player_module.py']='from tankbot import Module\nclass Custom(Module):\n    def update(self, inputs, ctx):\n        pass\n'
        snapshot={'files':files,'ledger':{}};snapshot['revision']=digest(snapshot)
        self.assertFalse(framework_upgrade(config,files)['required'])
        a=Authority(config,controlled=True)
        try:self.assertEqual(inspect_snapshot(snapshot,a)['contract']['entry_point'],'player_module:Custom')
        finally:a.close()
