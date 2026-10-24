"""Bootstrap reliability without network access or modification of the caller's Python."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import venv

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('tankbot_python_env',ROOT/'tools/python_env.py')
bootstrap=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)
READY={'ready':True,'versions':{'numpy':'2.3.3'},'problems':[]}
MISSING={'ready':False,'versions':{},'problems':['numpy: missing']}


class PythonEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='tankbot-python-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'config').mkdir()
        for name in ('requirements.txt','config/python-bootstrap.lock.json'):
            (self.root/name).write_bytes((ROOT/name).read_bytes())

    def test_current_complete_environment_never_installs_or_writes_cache(self):
        with mock.patch.object(bootstrap,'probe',return_value=READY),mock.patch.object(bootstrap,'install') as install:
            self.assertIsNone(bootstrap.ensure_environment(self.root))
        install.assert_not_called()
        self.assertFalse((self.root/'.m1-cache').exists())

    def test_first_prepare_and_reuse_have_verified_metadata(self):
        with mock.patch.object(bootstrap,'probe',side_effect=[MISSING,MISSING,READY]),mock.patch.object(bootstrap,'install') as install:
            python=bootstrap.ensure_environment(self.root)
        self.assertTrue(python.is_file())
        install.assert_called_once()
        metadata=python.parent.parent/'ready.json'
        self.assertEqual(json.loads(metadata.read_text())['versions'],READY['versions'])
        with mock.patch.object(bootstrap,'probe',side_effect=[MISSING,READY]),mock.patch.object(bootstrap,'install') as install:
            self.assertEqual(bootstrap.ensure_environment(self.root,offline=True),python)
        install.assert_not_called()

    def test_failed_install_is_retried_and_never_touches_player_files(self):
        player=self.root/'workspace/player.py';player.parent.mkdir();player.write_text('# my algorithm\n')
        with mock.patch.object(bootstrap,'probe',return_value=MISSING),mock.patch.object(bootstrap,'install',side_effect=bootstrap.BootstrapError('network')):
            with self.assertRaisesRegex(bootstrap.BootstrapError,'network'):bootstrap.ensure_environment(self.root)
        self.assertFalse(list(self.root.rglob('ready.json')))
        with mock.patch.object(bootstrap,'probe',side_effect=[MISSING,MISSING,READY]),mock.patch.object(bootstrap,'install') as install:
            bootstrap.ensure_environment(self.root,offline=True)
        install.assert_called_once()
        self.assertEqual(player.read_text(),'# my algorithm\n')

    def test_manifest_changes_choose_new_environment_and_pins_are_required(self):
        key=bootstrap.environment_key(self.root)
        with (self.root/'requirements.txt').open('a') as out:out.write('new-package==1.0\n')
        self.assertNotEqual(bootstrap.environment_key(self.root),key)
        self.assertEqual(bootstrap.requirements(self.root/'requirements.txt')['new-package'],'1.0')
        (self.root/'requirements.txt').write_text('numpy>=2\n')
        with self.assertRaises(bootstrap.BootstrapError):bootstrap.requirements(self.root/'requirements.txt')

    def test_import_probe_uses_isolated_interpreter_without_pip_or_site_overrides(self):
        env=self.root/'empty';venv.EnvBuilder(with_pip=False).create(env)
        python=bootstrap.environment_python(env)
        poisoned=self.root/'poison';poisoned.mkdir();(poisoned/'not_installed.py').write_text('pass\n')
        with mock.patch.dict(os.environ,{'PYTHONPATH':str(poisoned)}):
            result=bootstrap.probe(python,{},['not_installed'])
        self.assertFalse(result['ready'])
        self.assertTrue(bootstrap.probe(python,{},['json'])['ready'])
        self.assertFalse(bootstrap.probe(python,{'numpy':'2.3.3'},[])['ready'])

    def test_verified_installer_cache_repairs_corruption_and_is_offline_safe(self):
        raw=b'pretend-wheel-for-download-test'
        lock={'filename':'pip-test.whl','url':'https://example.invalid/pip.whl','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        with self.assertRaisesRegex(bootstrap.BootstrapError,'离线缓存'):bootstrap.installer_wheel(self.root,lock,True)
        with mock.patch.object(bootstrap.urllib.request,'urlopen',return_value=io.BytesIO(raw)):
            wheel=bootstrap.installer_wheel(self.root,lock,False)
        self.assertEqual(bootstrap.installer_wheel(self.root,lock,True),wheel)
        wheel.write_bytes(b'damaged')
        with mock.patch.object(bootstrap.urllib.request,'urlopen',return_value=io.BytesIO(b'bad')):
            with self.assertRaisesRegex(bootstrap.BootstrapError,'校验失败'):bootstrap.installer_wheel(self.root,lock,False)
        with mock.patch.object(bootstrap.urllib.request,'urlopen',return_value=io.BytesIO(raw)):
            self.assertEqual(bootstrap.installer_wheel(self.root,lock,False).read_bytes(),raw)

    def test_offline_install_only_targets_private_environment_and_filters_overrides(self):
        python=bootstrap.environment_python(self.root/'env')
        with mock.patch.object(bootstrap,'installer_wheel',return_value=self.root/'pip.whl'),mock.patch.object(bootstrap.subprocess,'run') as run,\
             mock.patch.dict(os.environ,{'PIP_TARGET':'/outside','PIP_PREFIX':'/outside','PYTHONPATH':'/outside'}):
            bootstrap.install(python,self.root/'cache',self.root,{'pip':{}},True)
        self.assertEqual(run.call_count,2)
        for call in run.call_args_list:
            command=call.args[0]
            self.assertEqual(command[0],str(python))
            self.assertIn('--require-virtualenv',command)
            self.assertIn('--no-index',command)
            self.assertNotIn('PIP_TARGET',call.kwargs['env'])
            self.assertNotIn('PYTHONPATH',call.kwargs['env'])
            self.assertEqual(call.kwargs['env']['PIP_CONFIG_FILE'],os.devnull)

    def test_lock_is_exclusive_and_released_after_failure(self):
        path=self.root/'install.lock'
        with bootstrap.installation_lock(path):
            with self.assertRaises(bootstrap.BootstrapError):
                with bootstrap.installation_lock(path,timeout=0):pass
        with self.assertRaises(RuntimeError):
            with bootstrap.installation_lock(path):raise RuntimeError('interrupted')
        with bootstrap.installation_lock(path,timeout=0):pass

    def test_help_and_invalid_arguments_work_without_site_packages(self):
        for args,expected in ((['--help'],0),(['unknown-mode'],2),(['serve','--level','c0','--view','estimated'],2)):
            result=subprocess.run([sys.executable,'-I','-S',str(ROOT/'tools/tankbot.py'),*args],capture_output=True,text=True)
            self.assertEqual(result.returncode,expected,result.stderr)
            self.assertNotIn('首次运行',result.stdout+result.stderr)
            self.assertIn('usage:',result.stdout+result.stderr)
        # The entry script tankbot.py must not shadow the SDK package of the same name.
        source="import runpy, importlib.util;runpy.run_path("+repr(str(ROOT/'tools/tankbot.py'))+",run_name='launcher_probe');assert importlib.util.find_spec('tankbot').origin == "+repr(str(ROOT/'sdk/python/tankbot/__init__.py'))
        result=subprocess.run([sys.executable,'-I','-S','-c',source],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_relaunch_preserves_arguments_and_isolated_worker_interpreter(self):
        python=self.root/'path with spaces/python'
        entry=self.root/'path with spaces/tankbot.py'
        with mock.patch.object(bootstrap,'ensure_environment',return_value=python),mock.patch.object(bootstrap.os,'execv') as execute,\
             mock.patch.object(sys,'argv',['tankbot.py','serve','--level','c0']):
            bootstrap.relaunch_if_needed(entry,offline=True)
        execute.assert_called_once_with(str(python),[str(python),'-I',str(entry),'serve','--level','c0'])


if __name__=='__main__':unittest.main()
