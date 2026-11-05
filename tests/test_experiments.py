"""Fixed inputs, independent runtimes, authorized diagnostics and reproducible failures."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure
from tankbot_host.workspace import digest,starter
from tankbot_host.deployment import DeploymentManager
from tankbot_host.experiments import check_diagnostics
from tankbot import ModuleContext,diagnostic
from tankbot.diagnostics import diagnostic_scope
from campaign_support import solutions,EMA,WINDOW


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.config=configure(load_config(ROOT/'config/game.yaml'),'c2')

    def snapshot(self,tracker=EMA):
        files=solutions(self.config,tracker)
        value={'files':files,'ledger':{}}
        value['revision']=digest(value)
        return value

    def recorded(self,steps=180):
        snapshot=self.snapshot();a=Authority(self.config,controlled=True,startup_sources=snapshot['files'])
        self.addCleanup(a.close)
        a.worker.revision=snapshot['revision'];a.deployment=DeploymentManager(a)
        a.lab.start()
        for _ in range(steps):a.advance()
        a.lab.stop();a.finish_campaign()
        return a,snapshot

    def finish(self,a):
        for _ in range(2000):
            a.advance()
            if a.lab.job is None:return a.lab.reports[-1]
        self.fail('Experiment did not finish')

    def test_two_revisions_replay_identical_inputs_without_truth_or_world_outputs(self):
        a,one=self.recorded();two=self.snapshot(WINDOW)
        original=copy.deepcopy(a._target_estimate)
        submitted=[];factory=a.worker_factory
        def inspect(config,init,**kw):submitted.append(copy.deepcopy(init));return factory(config,init,**kw)
        a.worker_factory=inspect
        a.lab.compare(one);first=self.finish(a)
        a.lab.compare(two);second=self.finish(a)
        self.assertEqual(first['status'],'Completed',first)
        self.assertEqual(second['status'],'Completed',second)
        self.assertEqual(first['input_sha256'],second['input_sha256'])
        self.assertNotEqual(first['revision'],second['revision'])
        self.assertGreater(first['scored_samples'],0)
        self.assertTrue(first['segments']);self.assertTrue(first['missing_intervals'])
        self.assertEqual(a._target_estimate,original)
        self.assertTrue(all('truth' not in json.dumps(init) for init in submitted))
        self.assertTrue(all(set(init['output_channels'].values())=={'/robot/estimates/perception/target'} for init in submitted))
        exported=a.lab.export();self.assertFalse(exported['evaluation_reference_exported'])
        self.assertNotIn('references',exported);self.assertNotIn('truth',json.dumps(exported))
        self.assertEqual(exported['record']['source_revision'],one['revision'])
        self.assertEqual(exported['comparisons'][0]['source_snapshot'],one)

    def test_same_version_and_record_produce_same_estimates_not_a_closed_loop_grade(self):
        a,snapshot=self.recorded()
        a.lab.compare(snapshot);first=self.finish(a)
        a.lab.compare(snapshot);second=self.finish(a)
        self.assertEqual(first['points'],second['points'])
        self.assertEqual(a.lab.status()['kind'],'sensor_replay')
        self.assertEqual(a.campaign.status,'ended')

    def test_export_import_keeps_inputs_but_does_not_reveal_or_reconstruct_score_references(self):
        a,snapshot=self.recorded();record=a.lab.export()['record']
        a.validator.structure(record,'experiment.schema.json')
        a.lab.import_record(record)
        self.assertFalse(a.lab.status()['private_scoring_available'])
        a.lab.compare(snapshot);report=self.finish(a)
        self.assertEqual(report['status'],'Completed',report)
        self.assertIsNone(report['rmse_m']);self.assertEqual(report['scored_samples'],0)
        bad=copy.deepcopy(record);bad['frames'][0]['request']['payload']['inputs'][0]['channel']='/ground_truth/pose'
        with self.assertRaises(ValueError):a.lab.import_record(bad)

    def test_failure_has_python_traceback_revision_and_sample_location(self):
        a,_=self.recorded()
        bad=self.snapshot(EMA.replace('        if measurements:', '        raise ValueError("lab-filter-failed")\n        if measurements:',1))
        a.lab.compare(bad);report=self.finish(a)
        self.assertEqual(report['status'],'Failed',report)
        self.assertEqual(report['failure']['frame_index'],0)
        self.assertEqual(report['revision'],bad['revision'])
        self.assertIn('lab-filter-failed',json.dumps(report['logs']))
        self.assertIsNone(a.lab.job)

    def test_capacity_stops_recording_without_unbounded_growth_and_other_lessons_are_denied(self):
        a,snapshot=self.recorded(30)
        a.lab.limits={**a.lab.limits,'max_batches':2}
        a.worker.revision=snapshot['revision']
        # Start another active attempt in an isolated Authority.
        b=Authority(self.config,controlled=True,startup_sources=snapshot['files']);self.addCleanup(b.close)
        b.worker.revision=snapshot['revision'];b.lab.limits=a.lab.limits;b.lab.start()
        for _ in range(120):b.advance()
        self.assertFalse(b.lab.recording);self.assertEqual(len(b.lab.record['frames']),2)
        self.assertEqual(b.lab.record['stop_reason'],'capacity_reached')
        c=Authority(configure(load_config(ROOT/'config/game.yaml'),'navigation.c3'),controlled=True);self.addCleanup(c.close)
        with self.assertRaisesRegex(ValueError,'NOT_AUTHORIZED'):c.lab.start()
        self.assertFalse(c.lab.status()['enabled'])

    def test_optional_diagnostics_require_a_grant_and_are_finite_and_bounded(self):
        ctx=ModuleContext(6,.1,12,{'diagnostic_policy':{'channels':{'innovation':2},'max_events':1}})
        with diagnostic_scope(ctx):
            diagnostic('innovation',[.1,.2])
            with self.assertRaises(ValueError):diagnostic('innovation',[.3,.4])
            with self.assertRaises(PermissionError):diagnostic('truth',[1])
        self.assertEqual(ctx._diagnostics,[{'name':'innovation','values':[.1,.2]}])
        with self.assertRaises(RuntimeError):diagnostic('innovation',[1,2])
        with self.assertRaises(ValueError):check_diagnostics({'payload':{'telemetry':{'diagnostics':[{'module_id':'perception','name':'truth','values':[1]}]}}},{},['perception'])

    def test_failure_logs_cannot_exceed_the_record_quota_or_discard_frozen_inputs(self):
        a,_=self.recorded(90)
        requests=[copy.deepcopy(frame['request']) for frame in a.lab.record['frames']]
        size=len(json.dumps(a.lab.record,separators=(',',':')).encode())
        a.lab.limits={**a.lab.limits,'max_record_bytes':size+1000}
        for index in range(32):a.logs.append(str(index)+' '+('x'*1024),stream='error')
        a.lab.complete(requests[-1],None,'MODULE_ERROR')
        self.assertLessEqual(len(json.dumps(a.lab.record,separators=(',',':')).encode()),a.lab.limits['max_record_bytes'])
        self.assertEqual([frame['request'] for frame in a.lab.record['frames']],requests)
        self.assertEqual(a.lab.record['stop_reason'],'capacity_reached')

    def test_revoked_visualization_permission_denies_results_and_export_without_widening_inputs(self):
        a,_=self.recorded(30)
        before=a.runtime_inputs()
        a.campaign.definition['permissions']['visualization']['allowed_metrics'].remove('rmse_m')
        self.assertFalse(a.lab.status()['enabled']);self.assertEqual(a.lab.status()['comparisons'],[])
        with self.assertRaisesRegex(ValueError,'NOT_AUTHORIZED'):a.lab.export()
        self.assertEqual(a.runtime_inputs(),before)

    def test_replay_rejects_duplicate_publications_like_the_formal_runtime(self):
        a,snapshot=self.recorded(30)
        snapshot=copy.deepcopy(snapshot)
        snapshot['files']['campaign_robot.py']+='\n_original_update = CampaignRobot.update\ndef _duplicate(self, inputs, ctx):\n    _original_update(self, inputs, ctx)\n    ctx._outputs += list(ctx._outputs)\nCampaignRobot.update = _duplicate\n'
        snapshot['revision']=digest({'files':snapshot['files'],'ledger':snapshot['ledger']})
        a.lab.compare(snapshot);report=self.finish(a)
        self.assertEqual(report['status'],'Failed',report)
        self.assertEqual(report['failure']['code'],'RATE_LIMITED')
