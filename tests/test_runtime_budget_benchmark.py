"""The long-run collector must retain failures, phases and within-batch totals."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('sdk/python','host','protocol','tools')]
from runtime_budget_support import Journal
from tankbot_host.configuration import load_yaml
from tankbot_host.runtime_timing import RuntimeTiming


class RuntimeBudgetBenchmarkTests(unittest.TestCase):
    def test_stream_rotates_and_retains_censored_sample_and_exact_attempt_failure(self):
        limits=load_yaml(ROOT/'config/runtime-benchmark.yaml')['limits']
        limits.update(max_jsonl_part_bytes=3000,max_jsonl_parts=128)
        with tempfile.TemporaryDirectory() as directory:
            collector=Journal(directory,limits);timing=RuntimeTiming(30,'test')
            for index in range(30):
                timing.begin({'request_id':str(index),'payload':{'modules':[{'module_id':'a'},{'module_id':'b'}]}})
                if index<29:
                    timing.received({'payload':{'telemetry':{'modules':[{'module_id':'a','update_ms':index%2},
                        {'module_id':'b','update_ms':1-index%2}]}}});timing.finish();timing.decision(None,str(index))
                else:timing.finish('RESOURCE_LIMIT','wall_deadline')
                snapshot={'run_id':'r','tick':6*index,'runtime_fault':None,'attempt_status':'active','timing':timing.drain()}
                collector.ingest(snapshot)
                collector.ingest(snapshot)  # A repeated last poll must not invent extra batches.
            snapshot.update(runtime_fault='RESOURCE_LIMIT',attempt_status='ended',result={'reason':'controller_error'},timing=timing.drain())
            collector.end_attempt(snapshot,'runtime_failure',startup_ms=3)
            report=collector.summary();collector.close()
            self.assertEqual(report['batches'],30);self.assertEqual(report['censored_batches'],1)
            self.assertEqual(report['wall_timeouts'],1);self.assertEqual(report['missed_commit_gates'],0)
            self.assertEqual(report['costs']['batch_module_update_ms']['p99_ms'],1)
            self.assertEqual(report['runtime_complete_attempt_failure_rate'],1)
            self.assertGreater(len(list(Path(directory).glob('events-*.jsonl'))),1)
            raw=''.join(p.read_text() for p in Path(directory).glob('events-*.jsonl'))
            self.assertNotIn('truth',raw);self.assertEqual(sum(json.loads(line)['event']=='batch_finish' for line in raw.splitlines()),30)

    def test_short_slice_is_not_reported_as_successful_complete_attempt(self):
        limits=load_yaml(ROOT/'config/runtime-benchmark.yaml')['limits']
        with tempfile.TemporaryDirectory() as directory:
            collector=Journal(directory,limits)
            snapshot={'run_id':'r','tick':1,'runtime_fault':None,'attempt_status':'active','timing':{'events':[],'dropped_events':0}}
            collector.end_attempt(snapshot,'sample_target');report=collector.summary();collector.close()
            self.assertEqual(report['complete_attempts'],0)
            self.assertIsNone(report['runtime_complete_attempt_failure_rate'])
            self.assertIsNone(report['attempt_failure_wilson_95'])

    def test_benchmark_config_is_validated_and_late_bytes_are_not_completed_observations(self):
        from runtime_budget_support import benchmark_options
        from summarize_runtime_benchmark import normalize_event
        from jsonschema import ValidationError
        options=benchmark_options(ROOT/'config/runtime-benchmark.yaml')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.json';options['limits']['max_summary_batches']=0
            path.write_text(json.dumps(options))
            with self.assertRaises(ValidationError):benchmark_options(path)
        row={'failure_location':'wall_deadline','received_monotonic_ns':121,'round_trip_ms':21,
             'received_monotonic_s':.121,'censored':False}
        result=normalize_event(row)
        self.assertTrue(result['censored']);self.assertNotIn('round_trip_ms',result)
        self.assertEqual(result['response_arrival_ms'],21)
        self.assertFalse(row['censored'])  # The source evidence remains immutable.

    def test_artifact_changes_abort_instead_of_pooling_versions(self):
        from runtime_budget_support import ArtifactGuard
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.py';path.write_text('VALUE=1\n')
            guard=ArtifactGuard([path]);guard.check()
            path.write_text('VALUE=2\n')
            with self.assertRaisesRegex(RuntimeError,'ARTIFACT_CHANGED'):guard.check()

    def test_browser_helpers_do_not_shadow_the_sdk_with_the_launcher(self):
        before=list(sys.path)
        import browser_support
        self.assertEqual(sys.path,before)
        import tankbot
        self.assertTrue(hasattr(tankbot,'__path__'))
