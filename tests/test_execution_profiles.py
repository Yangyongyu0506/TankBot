"""Profiles are trusted immutable leases; module telemetry never extends a deadline."""
import copy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','runtime','tests')]
from tankbot_host.authority import Authority,load_config
from tankbot_host.execution_profiles import admission_cap,select_execution_profile,validate_execution_profiles
from tankbot_host.campaign import configure
from tankbot_host.runtime_timing import RuntimeTiming
from browser_authority import BrowserSupervisor,runtime_event
from campaign_support import solutions


class ExecutionProfileTests(unittest.TestCase):
    def setUp(self):self.config=load_config(ROOT/'config/game.yaml')

    def test_backend_selection_legacy_compatibility_and_conflict_rejection(self):
        runtime=self.config['runtime'];catalog=runtime['profiles']
        for backend,wall in [('native',30),('pyodide',50)]:
            catalog['profiles'][catalog['defaults'][backend]]['batch_wall_deadline_ms']=wall
            p=select_execution_profile(self.config,backend)
            self.assertEqual(p.batch_wall_deadline_ms,wall)
            self.assertEqual(p.module_declared_budget_cap_ms,20)
            self.assertEqual(p.backend,backend)
            self.assertEqual(len(p.public()['sha256']),64)
        runtime['batch_budget_ms']=20
        with self.assertRaisesRegex(ValueError,'CONFLICT'):validate_execution_profiles(self.config)
        runtime.pop('profiles')
        for backend in ('native','pyodide'):
            p=select_execution_profile(self.config,backend)
            self.assertEqual((p.module_declared_budget_cap_ms,p.batch_wall_deadline_ms),(20,20))
            self.assertEqual(p.source,'batch_budget_ms')
        runtime.pop('batch_budget_ms')
        with self.assertRaisesRegex(ValueError,'CONFLICT'):validate_execution_profiles(self.config)

    def test_profile_references_backend_version_and_values_are_checked(self):
        for mutate in (
            lambda c:c['defaults'].update(native='unknown'),
            lambda c:c['defaults'].update(native=c['defaults']['pyodide']),
            lambda c:c.update(schema_version='2.0'),
            lambda c:c.update(module_declared_budget_cap_ms=0),
            lambda c:c['profiles'][c['defaults']['native']].update(batch_wall_deadline_ms=float('nan')),
        ):
            config=copy.deepcopy(self.config);mutate(config['runtime']['profiles'])
            with self.subTest(config=config['runtime']),self.assertRaises(ValueError):validate_execution_profiles(config)

    def test_attempt_freezes_backend_limits_and_new_workers_inherit_same_profile(self):
        config=configure(self.config,'c2')
        a=Authority(config,controlled=True,startup_sources=solutions(config))
        try:
            p=a.runtime_profile
            with self.assertRaises(FrozenInstanceError):p.batch_wall_deadline_ms=999
            a.config['runtime']['profiles']['profiles'][p.profile_id]['batch_wall_deadline_ms']=80
            self.assertEqual(a.worker.execution_profile,p)
            with patch.object(a,'worker_factory') as factory:
                a.create_worker({},deferred=True)
                self.assertIs(factory.call_args.kwargs['execution_profile'],p)
            self.assertEqual(a.public_profile()['runtime_execution_profile'],p.public())
            self.assertEqual(p.module_declared_budget_cap_ms,20)
        finally:a.close()

    def test_graph_cap_does_not_follow_wall_deadline(self):
        from tankbot_host.robot_graph import inspect_graph
        from tankbot_host.workspace import starter
        config=configure(self.config,'navigation.c4')
        catalog=config['runtime']['profiles']
        catalog['profiles'][catalog['defaults']['native']]['batch_wall_deadline_ms']=80
        a=Authority(config,controlled=True)
        try:
            files=starter(config);manifest=json.loads(files['tankbot.json'])
            first=manifest['modules'][0]['contract'];contract=json.loads(files[first])
            contract['execution']['budget_ms']=21;files[first]=json.dumps(contract)
            with self.assertRaisesRegex(ValueError,'GRAPH_BUDGET_EXCEEDED'):inspect_graph(files,manifest,a)
            self.assertEqual(a.runtime_profile.batch_wall_deadline_ms,80)
            self.assertEqual(admission_cap(config),20)
        finally:a.close()

    def browser(self):
        config=copy.deepcopy(self.config)
        config['runtime'].pop('profiles');config['runtime']['batch_budget_ms']=20
        return BrowserSupervisor(config,{})

    def test_browser_decode_crosses_deadline_and_delayed_watchdog_cannot_accept_it(self):
        with patch.dict(sys.modules,{'js':types.SimpleNamespace(runtime_send=lambda raw:None)}):
            sup=self.browser()
            with patch('browser_authority.time.monotonic_ns',return_value=1_000_000_000):sup.submit({'request_id':'a'})
            def decode(raw):
                clock.return_value=1_020_000_001
                return {'payload':{'telemetry':{'budget_ms':90000,'runtime_python_ms':0}}}
            with patch('browser_authority.time.monotonic_ns',return_value=1_019_000_000) as clock,patch('browser_authority.strict_loads',side_effect=decode):
                sup.receive('{}',0)
                self.assertIsNone(sup.finish())
            self.assertEqual(sup.fault,'RESOURCE_LIMIT')
            self.assertEqual(sup.timing.samples[-1]['failure_location'],'response_decode_deadline')
            self.assertEqual(sup.execution_profile.batch_wall_deadline_ms,20)
            self.assertNotIn(sup.worker_id,BrowserSupervisor.workers)
            runtime_event({'op':'result','worker_id':sup.worker_id,'raw':'{}','elapsed_ms':0})
            self.assertIsNone(sup.result)

    def test_browser_duplicate_response_and_early_gate_reject_without_waiting(self):
        with patch.dict(sys.modules,{'js':types.SimpleNamespace(runtime_send=lambda raw:None)}),patch('browser_authority.time.monotonic_ns',return_value=100):
            sup=self.browser();sup.submit({'request_id':'a'});sup.receive('{}',0);sup.receive('{}',0)
            self.assertIsNone(sup.finish());self.assertEqual(sup.fault,'RESOURCE_LIMIT')
            sup=self.browser();sup.submit({'request_id':'b'})
            self.assertIsNone(sup.finish());self.assertEqual(sup.fault,'MISSED_DEADLINE')

    def test_late_undecoded_bytes_are_a_censored_arrival_not_a_complete_roundtrip(self):
        with patch.dict(sys.modules,{'js':types.SimpleNamespace(runtime_send=lambda raw:None)}):
            sup=self.browser()
            with patch('browser_authority.time.monotonic_ns',return_value=100_000_000):sup.submit({'request_id':'late'})
            with patch('browser_authority.time.monotonic_ns',return_value=120_000_001),patch('browser_authority.strict_loads') as decode:
                sup.receive('{}',5)
                decode.assert_not_called()
            row=sup.timing.samples[-1]
            self.assertTrue(row['censored']);self.assertNotIn('round_trip_ms',row)
            self.assertEqual(row['response_arrival_ms'],20.000001)
            self.assertEqual(sup.timing.public()['wall_timeouts'],1)

    def test_legacy_loader_and_conflicting_asset_modes(self):
        import tempfile
        from tankbot_host.execution_profiles import load_execution_profiles
        legacy=copy.deepcopy(self.config);legacy['runtime'].pop('profiles');legacy['runtime']['batch_budget_ms']=30
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.json';path.write_text(json.dumps(legacy))
            loaded=load_config(path)
        self.assertEqual(admission_cap(loaded),30)
        self.assertEqual(select_execution_profile(loaded,'pyodide').batch_wall_deadline_ms,30)
        for runtime in (
            {**self.config['runtime'],'profiles_file':'config/runtime-profiles.yaml'},
            {**legacy['runtime'],'profiles_file':'config/runtime-profiles.yaml'},
        ):
            with self.assertRaisesRegex(ValueError,'CONFLICT'):load_execution_profiles({'runtime':runtime})
        with self.assertRaisesRegex(ValueError,'PATH'):
            load_execution_profiles({'runtime':{'profiles_file':'userdata/forbidden-profile.yaml'}})

    def test_catchup_does_not_move_fixed_gate_to_the_wall_deadline(self):
        import os,signal
        if sys.platform!='linux':self.skipTest('SIGSTOP injection is Linux-only')
        config=configure(self.config,'c2')
        catalog=config['runtime']['profiles'];catalog['profiles'][catalog['defaults']['native']]['batch_wall_deadline_ms']=80
        a=Authority(config,startup_sources=solutions(config))
        try:
            os.kill(a.worker.proc.pid,signal.SIGSTOP)
            for _ in range(13):a.advance()
            failures=[e for e in a.audit if e.get('code')=='MISSED_DEADLINE']
            self.assertTrue(failures)
            self.assertEqual(failures[0]['tick'],12)
            self.assertFalse(any(e['event']=='target_commit' for e in a.audit))
        finally:a.close()

    def test_journal_stream_exceeds_window_without_loss_and_sums_inside_batch(self):
        t=RuntimeTiming(30,'test')
        request={'request_id':'a','payload':{'modules':[{'module_id':'a'},{'module_id':'b'}]}}
        journal=[]
        for index in range(1200):
            request['request_id']=str(index)
            t.begin(request)
            t.received({'payload':{'telemetry':{'modules':[{'module_id':'a','update_ms':index%2},
                {'module_id':'b','update_ms':1-index%2}]}}})
            t.finish(at_gate=True);t.decision(None,str(index));journal.extend(t.drain()['events'])
        self.assertEqual(len(journal),2400);self.assertEqual(t.journal_dropped,0)
        self.assertEqual(t.public()['costs']['batch_module_update_ms']['p99_ms'],1)
        self.assertEqual(t.public()['window_batches'],512)
        self.assertEqual(journal[0]['phase'],'first_activation')
        for index in range(600):t.begin(request);t.finish('RESOURCE_LIMIT','wall_deadline')
        self.assertGreater(t.drain()['dropped_events'],0)

    def test_native_integer_receive_boundary_and_decode_crossing_ignore_delayed_watchdog(self):
        from collections import deque
        import threading
        from unittest.mock import Mock
        from tankbot_host.supervisor import Supervisor
        class ReaderStopped(BaseException):pass
        for received,accepted in ((120_000_000,True),(120_000_001,False)):
            with self.subTest(received=received):
                s=Supervisor.__new__(Supervisor)
                s.condition=threading.Condition();s.closed=False;s.ready=True;s.active='a'
                s.result=None;s.fault=None;s.detail=None;s.expires_ns=120_000_000;s.started_ns=100_000_000
                s.timing=RuntimeTiming(20,'native');s.timing.begin({'request_id':'a'},started_ns=s.started_ns)
                s.proc=types.SimpleNamespace(stdout=None);s.limit=65536;s._kill=Mock();s.batch_times_ms=deque()
                calls=0
                def receive(stream,limit,timing):
                    nonlocal calls
                    calls+=1
                    if calls>1:raise ReaderStopped()
                    timing.update(response_decode_started_monotonic_ns=119_000_000,response_decode_ms=(received-119_000_000)/1e6)
                    return {'payload':{}}
                with patch('tankbot_host.supervisor.receive',side_effect=receive),patch('tankbot_host.supervisor.time.monotonic_ns',return_value=received):
                    if accepted:
                        with self.assertRaises(ReaderStopped):s._read()
                        # A timely buffered response stays valid after wall expiry until its fixed gate.
                        with patch('tankbot_host.supervisor.time.monotonic_ns',return_value=200_000_000):
                            self.assertEqual(s.finish(),{'payload':{}})
                        self.assertIsNone(s.fault)
                    else:
                        s._read();self.assertIsNone(s.result);self.assertEqual(s.fault,'RESOURCE_LIMIT')
                        self.assertEqual(s.timing.samples[-1]['failure_location'],'response_decode_deadline')
                        s._kill.assert_called()

    def test_native_pipe_backpressure_is_off_authority_thread(self):
        from collections import deque
        import threading
        from tankbot_host.supervisor import Supervisor
        from unittest.mock import Mock
        s=Supervisor.__new__(Supervisor);s.condition=threading.Condition();s.closed=False;s.fault=None
        s.active=None;s.result=None;s.budget_ns=20_000_000;s.limit=65536;s.outgoing=None
        s.timing=RuntimeTiming(20,'native');s._kill=Mock()
        entered=threading.Event();release=threading.Event()
        def write(raw):entered.set();release.wait(1)
        s.proc=types.SimpleNamespace(stdin=types.SimpleNamespace(write=write,flush=lambda:None))
        writer=threading.Thread(target=s._write);writer.start()
        try:
            self.assertTrue(s.submit({'request_id':'blocking-pipe'}))
            self.assertTrue(entered.wait(1))
            # The writer is blocked but the Authority can take its lock and visit a gate.
            self.assertIsNone(s.finish());self.assertIn(s.fault,('MISSED_DEADLINE','RESOURCE_LIMIT'))
        finally:
            with s.condition:s.closed=True;release.set();s.condition.notify_all()
            writer.join(1);self.assertFalse(writer.is_alive())

    def test_native_nonreturning_update_is_killed_and_physics_keeps_ticking(self):
        import time
        config=configure(self.config,'c2');files=solutions(config)
        files['perception/tracker.py']='class Tracker:\n    def update(self, measurements, dt):\n        while True: pass\n'
        a=Authority(config,startup_sources=files)
        worker=a.worker
        try:
            for _ in range(32):a.advance();time.sleep(1/a.hz)
            self.assertEqual(worker.fault,'RESOURCE_LIMIT')
            self.assertGreater(a.tick,24);self.assertIsNotNone(worker.proc.poll())
            self.assertTrue(any(e.get('code')=='RESOURCE_LIMIT' for e in a.audit))
        finally:a.close()
        self.assertFalse(worker.writer.is_alive());self.assertFalse(worker.reader.is_alive())
        self.assertFalse(worker.watchdog.is_alive())

    def test_forged_wall_limit_telemetry_is_rejected_without_changing_attempt_limits(self):
        config=configure(self.config,'c2');a=Authority(config,controlled=True,startup_sources=solutions(config))
        try:
            frozen=a.runtime_profile;finish=a.worker.finish
            def forged(**kwargs):
                response=finish(**kwargs)
                if response is not None:
                    response['payload']['telemetry']['transport']['batch_wall_deadline_ms']=1000
                return response
            with patch.object(a.worker,'finish',side_effect=forged):
                for _ in range(25):a.advance()
            self.assertIs(a.runtime_profile,frozen)
            self.assertEqual(a.worker.execution_profile,frozen)
            self.assertTrue(any(e.get('code')=='INVALID_SCHEMA' for e in a.audit))
            self.assertFalse(any(e['event']=='target_commit' for e in a.audit))
        finally:a.close()

    def test_finish_without_an_active_batch_is_a_controlled_failure_not_a_clock_type_error(self):
        with patch.dict(sys.modules,{'js':types.SimpleNamespace(runtime_send=lambda raw:None)}):
            sup=self.browser();self.assertIsNone(sup.finish());self.assertEqual(sup.fault,'MISSED_DEADLINE')
        config=configure(self.config,'c2');a=Authority(config,controlled=True)
        try:
            self.assertIsNone(a.worker.finish());self.assertEqual(a.worker.fault,'MISSED_DEADLINE')
        finally:a.close()
