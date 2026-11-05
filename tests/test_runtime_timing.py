import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]
from tankbot_host.runtime_timing import RuntimeTiming,distribution
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure
from campaign_support import solutions


class RuntimeTimingTests(unittest.TestCase):
    def test_malformed_untrusted_telemetry_cannot_break_transport_observation(self):
        request={'request_id':'bad-response','payload':{'modules':[{'module_id':'filter'}]}}
        values=[None, [], {'payload':None}, {'payload':[]},
                {'payload':{'telemetry':[],'results':None}},
                {'payload':{'telemetry':{'transport':[],'modules':None},'results':'bad'}},
                {'payload':{'telemetry':{'transport':{'worker_decode_ms':float('nan')},
                    'modules':[None,{'module_id':'ungranted','update_ms':1}]}}}]
        for value in values:
            with self.subTest(value=value):
                timing=RuntimeTiming(20,'test')
                timing.begin(request);timing.received(value);timing.finish()
                # Observation grants nothing: the normal validator still rejects it.
                timing.decision('INVALID_SCHEMA',request['request_id'])
                report=timing.public()
                self.assertEqual(report['recent'][-1]['status'],'INVALID_SCHEMA')
                self.assertEqual(report['recent'][-1]['failure_location'],'authority_validation')
                self.assertEqual(report['modules'],{})
                self.assertEqual(report['costs']['worker_decode_ms']['count'],0)

    def test_bounded_percentiles_failures_and_distinct_sample_activation_commit_times(self):
        timing=RuntimeTiming(20,'test');capacity=timing.limits['max_batches']
        request={'request_id':'batch','payload':{'activation_tick':12,'output_commit_tick':18,'inputs':[{'simulation_tick':10}], 'modules':[{'module_id':'filter'}]}}
        for index in range(capacity+3):
            timing.begin(request);timing.sent(request_encode_ms=.1);timing.received({'payload':{}},response_decode_ms=.2);timing.finish()
        timing.begin(request);timing.finish('MISSED_DEADLINE','commit_gate')
        report=timing.public()
        self.assertEqual(report['window_batches'],capacity)
        self.assertEqual(report['total_batches'],capacity+4)
        self.assertEqual(report['timeouts'],1)
        self.assertEqual(report['recent'][-1]['failure_location'],'commit_gate')
        self.assertEqual(report['recent'][-1]['sample_ticks'],[10])
        self.assertEqual(report['recent'][-1]['activation_tick'],12)
        self.assertEqual(report['recent'][-1]['commit_tick'],18)
        self.assertEqual(distribution([1,2,3,4,5])['p99_ms'],5)
        self.assertTrue(report['observational_only'])

    def test_native_measures_module_serialization_and_roundtrip_without_increasing_budget(self):
        config=configure(load_config(ROOT/'config/game.yaml'),'c2')
        a=Authority(config,controlled=True,startup_sources=solutions(config))
        try:
            for _ in range(90):a.advance()
            report=a.worker.timing.public()
            self.assertEqual(report['budget_ms'],20)
            self.assertGreater(report['costs']['request_encode_ms']['count'],0)
            self.assertGreater(report['costs']['response_decode_ms']['count'],0)
            self.assertGreater(report['costs']['worker_decode_ms']['count'],0)
            self.assertGreater(report['costs']['worker_encode_previous_ms']['count'],0)
            self.assertGreater(report['modules']['perception']['update_ms']['count'],0)
            self.assertTrue(all(e['commit_tick']-e['activation_tick']==6 for e in report['recent']))
            self.assertNotIn('truth',json.dumps(report))
        finally:a.close()
