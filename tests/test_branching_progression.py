"""Public root, independent prerequisites and unchanged saved player projects."""
import contextlib
import copy
import hashlib
import http.client
import io
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_host.application import ApplicationState
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import catalog,configure
from tankbot_host.cli import main
from tankbot_host.level_plugins import LevelValidationError
from tankbot_host.server import LocalServer
from tankbot_host.browser_server import BrowserServer
from tankbot_host.workspace import workspace_scope
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_protocol.validation import Validator

DEPENDENCIES={'c0':[],'c1':['c0'],'c2':['c1'],'c3':['c2'],'c4':['c3'],'c5':['c4'],
              'navigation.c0':['c0'],'navigation.c1':['navigation.c0'],'navigation.c2':['navigation.c1'],'navigation.c3':['navigation.c2'],'navigation.c4':['navigation.c3'],'navigation.c5':['navigation.c4'],'navigation.c6':['navigation.c5']}


class BranchingProgressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.config=load_config(ROOT/'config/game.yaml')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.state=ApplicationState(self.config,self.directory/'settings.yaml',self.directory/'progress.json')

    def complete(self,lid):return self.state.complete(self.state.register_attempt(lid),lid)

    def test_new_save_root_completion_and_independent_navigation_line(self):
        self.assertEqual(self.state.progress()['unlocked_levels'],['c0'])
        self.assertEqual(self.state.progress()['completed_levels'],[])
        self.assertEqual(self.complete('c0')['unlocked_levels'],['c0','c1','navigation.c0'])
        for lid in ('navigation.c0','navigation.c1','navigation.c2','navigation.c3'):
            self.state.require_level(lid);self.state.select_level(lid);self.complete(lid)
        p=self.state.progress()
        self.assertEqual(p['completed_levels'],['c0','navigation.c0','navigation.c1','navigation.c2','navigation.c3'])
        self.assertNotIn('c2',p['unlocked_levels']);self.assertEqual(p['current_level'],'navigation.c3')
        self.assertIn('navigation.c4',p['unlocked_levels'])
        with self.assertRaisesRegex(ValueError,'navigation.c4'):self.state.require_level('navigation.c5')
        self.complete('navigation.c4');self.assertIn('navigation.c5',self.state.progress()['unlocked_levels'])
        self.state.require_level('c1')
        for lid,parent in (('c2','c1'),('c3','c2'),('c4','c3'),('c5','c4')):
            with self.subTest(lid=lid),self.assertRaisesRegex(ValueError,parent):self.state.require_level(lid)

    def test_weapons_line_does_not_complete_or_unlock_later_navigation(self):
        for lid in ('c0','c1','c2','c3','c4','c5'):self.complete(lid)
        p=self.state.progress();self.assertIn('navigation.c0',p['unlocked_levels'])
        for lid,parent in (('navigation.c1','navigation.c0'),('navigation.c2','navigation.c1'),('navigation.c3','navigation.c2'),('navigation.c4','navigation.c3')):
            with self.subTest(lid=lid),self.assertRaisesRegex(ValueError,parent):self.state.require_level(lid)
        self.assertFalse(any(lid.startswith('navigation.') for lid in p['completed_levels']))

    def test_explicit_prerequisite_lists_are_all_required(self):
        self.complete('c0');self.complete('c1')
        self.state.prerequisites['c2']=['c1','navigation.c0']
        with self.assertRaisesRegex(ValueError,'navigation.c0'):self.state.require_level('c2')
        self.complete('navigation.c0');self.state.require_level('c2')

    def test_nonprefix_and_old_chain_saves_preserve_bytes_current_level_and_records(self):
        for done,current in ((['c0','navigation.c0','navigation.c1'],'navigation.c2'),
                             (['c0','c1'],'c2'),
                             (list(DEPENDENCIES)[:-1],'navigation.c1')):
            with self.subTest(done=done):
                value={'version':1,'completed_levels':done,'current_level':current,
                       'completions':{lid:{'completed_at':'2026-10-24T12:00:00+00:00'} for lid in done}}
                self.state.progress_path.write_text(json.dumps(value,ensure_ascii=False))
                raw=self.state.progress_path.read_bytes()
                reopened=ApplicationState(self.config,self.state.settings_path,self.state.progress_path)
                self.assertEqual(reopened.read_progress(),value);self.assertEqual(reopened.progress()['current_level'],current)
                self.assertEqual(self.state.progress_path.read_bytes(),raw)
                Validator(self.config,'progress').structure(value,'progress.schema.json')

    def test_interleaved_completion_serializes_in_existing_catalogue_order(self):
        self.complete('c0');self.complete('navigation.c0');self.complete('c1')
        old=self.state.read_progress()['completions'].copy();self.state.select_level('navigation.c1')
        self.assertEqual(self.state.progress()['completed_levels'],['c0','c1','navigation.c0'])
        raw=self.state.progress_path.read_bytes();self.complete('c1')
        self.assertEqual(raw,self.state.progress_path.read_bytes())
        self.assertEqual(old,self.state.read_progress()['completions'])

    def test_practice_and_developer_modes_do_not_award_branch_progress(self):
        self.state.complete(self.state.register_attempt('c0',practice=True),'c0')
        self.assertEqual(self.state.progress()['unlocked_levels'],['c0'])
        settings=self.state.public_settings();settings['settings']['developer_mode']=True
        self.state.update_settings({'revision':settings['revision'],'settings':settings['settings']})
        self.state.complete(self.state.register_attempt('navigation.c2'),'navigation.c2')
        self.assertEqual(self.state.progress()['completed_levels'],[])
        settings=self.state.public_settings();settings['settings']['developer_mode']=False
        self.state.update_settings({'revision':settings['revision'],'settings':settings['settings']})
        self.assertEqual(self.state.progress()['unlocked_levels'],['c0'])

    def test_catalogue_exposes_only_declared_graph_and_all_nine_gameplay_definitions_are_unchanged(self):
        self.assertEqual({lid:d['metadata']['prerequisites'] for lid,d in self.config['campaign']['levels'].items()},DEPENDENCIES)
        public=catalog(self.config)
        for level in public:
            metadata=self.config['campaign']['levels'][level['level_id']]['metadata']
            for field in ('prerequisites','order','description'):self.assertEqual(level[field],metadata[field])
        frozen=json.loads((ROOT/'tests/fixtures/progression-gameplay-before.json').read_text())
        seen=set()
        for path in (ROOT/'levels').glob('*.yaml'):
            value=yaml.safe_load(path.read_text());lid=value['metadata']['id'];value['metadata'].pop('prerequisites')
            if lid not in frozen:continue
            value['evaluation'].pop('experiment',None)  # New lab capability is independent of frozen gameplay.
            seen.add(lid)
            hints=value['tutorial'].pop('hints')
            self.assertEqual([hint for hint in hints if not hint.startswith('可选补充练习：')],frozen[lid]['hints'])
            digest=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            self.assertEqual(digest,frozen[lid]['configuration_sha256'],lid)
        self.assertEqual(seen,set(frozen))

    def test_unknown_and_cyclic_prerequisites_fail_but_display_order_is_independent(self):
        directory=self.directory/'levels';shutil.copytree(ROOT/'levels',directory)
        base=yaml.safe_load((ROOT/'config/game.yaml').read_text());base['level_plugins']['directory']=str(directory)
        path=self.directory/'game.yaml';path.write_text(yaml.safe_dump(base))
        source=directory/'hello_robot.C0.yaml';original=yaml.safe_load(source.read_text())
        for prerequisites in (['absent'],['c1']):
            value=copy.deepcopy(original);value['metadata']['prerequisites']=prerequisites;source.write_text(yaml.safe_dump(value,allow_unicode=True))
            with self.subTest(prerequisites=prerequisites),self.assertRaises(LevelValidationError):load_config(path)
        # Move the root after its child in display order, retaining a valid DAG.
        original['metadata']['order']=1;source.write_text(yaml.safe_dump(original,allow_unicode=True))
        child=directory/'weapons.C1.yaml';value=yaml.safe_load(child.read_text());value['metadata']['order']=0;child.write_text(yaml.safe_dump(value,allow_unicode=True))
        config=load_config(path);configure(config,'c0')
        state=ApplicationState(config,self.directory/'ordered-settings.yaml',self.directory/'ordered-progress.json')
        self.assertEqual(state.progress()['current_level'],'c0');self.assertEqual(state.progress()['unlocked_levels'],['c0'])

    def test_locked_cli_paths_and_authorized_diagnostic_start_use_same_progress(self):
        common=['--settings-file',str(self.state.settings_path),'--save-file',str(self.state.progress_path)]
        for mode in ('serve','browser','headless','probe'):
            with self.subTest(mode=mode),patch.object(sys,'argv',['tankbot.py',mode,'--level','navigation.c0',*common]),contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as raised:main()
                self.assertEqual(raised.exception.code,2);self.assertIn('LEVEL_LOCKED',errors.getvalue());self.assertIn('(c0)',errors.getvalue())
        self.complete('c0');self.state.select_level('navigation.c0')
        raw=self.state.progress_path.read_bytes();settings=self.state.settings_path.read_bytes()
        for mode in ('headless','probe'):
            with patch.object(sys,'argv',['tankbot.py',mode,'--level','c1','--ticks','0',*common]),contextlib.redirect_stdout(io.StringIO()):main()
        self.assertEqual(raw,self.state.progress_path.read_bytes());self.assertEqual(settings,self.state.settings_path.read_bytes())
        for mode,target in (('serve','tankbot_host.server.LocalServer'),('browser','tankbot_host.browser_server.BrowserServer')):
            with patch(target) as launcher,patch.object(sys,'argv',['tankbot.py',mode,'--level','navigation.c0',*common]):main()
            self.assertTrue(launcher.return_value.serve.called)

    def test_native_http_selection_preserves_both_projects_history_and_cleans_old_tests(self):
        config=configure(self.config,'c0');config['host']['port']=0
        authority=Authority(config,controlled=True);server=LocalServer(authority,workspace_store=self.directory/'store',application=self.state)
        thread=threading.Thread(target=server.http.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:server.authority.close());self.addCleanup(server.http.server_close);self.addCleanup(server.http.shutdown)
        def request(lid):
            c=http.client.HTTPConnection('127.0.0.1',server.http.server_port,timeout=10)
            c.request('POST','/api/campaign/start',json.dumps({'level_id':lid}),{'Content-Type':'application/json','Origin':f'http://127.0.0.1:{server.http.server_port}','X-TankBot-Control':server.token})
            r=c.getresponse();result=(r.status,json.loads(r.read()));c.close();return result
        self.assertEqual(request('navigation.c0')[0],400)
        self.complete('c0')
        old=server.workspace.store.read();server.workspace.store.edit(old['revision'],{'player_note.py':'note: str = "weapons source"\n'})
        weapons=server.workspace;before=weapons.store.read()
        old_authority=server.authority
        old_authority.deployment.start('test',snapshot=before)
        pending=old_authority.deployment.job['worker']
        self.assertEqual(request('navigation.c0')[0],200)
        self.assertTrue(pending.closed);self.assertIsNone(old_authority.deployment.job)
        self.assertEqual(workspace_scope(server.workspace.config),'navigation')
        self.assertNotIn('player_note.py',server.workspace.store.read()['files'])
        self.assertIsNone(server.authority.deployment.active);self.assertEqual(server.authority.deployment.reports,{})
        nav=server.workspace;state=nav.store.read();nav.store.edit(state['revision'],{'nav_note.py':'note: str = "navigation source"\n'})
        nav_before=nav.store.read()
        self.assertEqual(request('navigation.c1')[0],400)
        self.assertEqual(server.workspace.store.read(),nav_before)
        self.assertEqual(request('c1')[0],200);self.assertIs(server.workspace,weapons)
        self.assertEqual(weapons.store.read()['files']['player_note.py'],before['files']['player_note.py'])
        self.assertEqual(weapons.store.read(before['revision']),before)
        self.assertEqual(request('navigation.c0')[0],200);self.assertIs(server.workspace,nav)
        self.assertEqual(nav.store.read(),nav_before)
        self.assertEqual(self.state.progress()['completed_levels'],['c0'])

    @unittest.skipUnless((ROOT/'build/browser/authority-bundle.json').is_file() and (ROOT/'target/wasm32-unknown-unknown/release/tankbot_core.wasm').is_file(),'browser artifacts not prepared')
    def test_browser_launcher_checks_player_gate_and_preserves_scope_revisions(self):
        config=configure(self.config,'c0');config['host']['port']=0
        with socket.socket() as handle:handle.bind(('127.0.0.1',0));config['browser']['runtime_port']=handle.getsockname()[1]
        server=BrowserServer(config,workspace_store=self.directory/'browser-store',application=self.state)
        self.addCleanup(server.ui.server_close);self.addCleanup(server.runtime.server_close)
        with self.assertRaisesRegex(ValueError,'LEVEL_LOCKED'):server.start_level('navigation.c0')
        self.complete('c0');weapons=server.workspace;before=weapons.store.read()
        server.start_level('navigation.c0');nav=server.workspace;nav_before=nav.store.read()
        self.assertEqual(workspace_scope(nav.config),'navigation');self.assertNotIn('perception/transforms.py',nav_before['files'])
        with self.assertRaisesRegex(ValueError,'navigation.c0'):server.start_level('navigation.c1')
        server.start_level('c1');self.assertIs(server.workspace,weapons);self.assertEqual(weapons.store.read(before['revision']),before)
        server.start_level('navigation.c0');self.assertIs(server.workspace,nav);self.assertEqual(nav.store.read(),nav_before)


if __name__=='__main__':unittest.main()
