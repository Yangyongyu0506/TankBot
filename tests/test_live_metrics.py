"""Live UI feedback reuses scored sample-time estimates without exposing truth to robots."""
import math
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import CampaignSession,configure
from tankbot_host.deployment import DeploymentManager
from tankbot_host.workspace import digest
from campaign_support import solutions


class LiveMetricTests(unittest.TestCase):
    def setUp(self):self.base=load_config(ROOT/'config/game.yaml')
    def config(self,level='c2'):return configure(self.base,level)

    def test_cumulative_rmse_counts_only_new_scored_outputs_and_freezes_at_finish(self):
        session=CampaignSession(self.config())
        msg=lambda tick,x,y:{'simulation_tick':tick,'payload':{'x_m':x,'y_m':y}}
        session.estimate(msg(1,3,4),[0,0,0])
        self.assertEqual(session.public()['live_metrics'],{'rmse_m':None,'scored_samples':0})
        session.start(0)
        session.estimate(msg(6,3,4),[0,0,0])
        self.assertEqual(session.public()['live_metrics'],{'rmse_m':5.,'scored_samples':1})
        session.estimate(msg(12,0,0),[0,0,0])
        session.estimate(msg(12,99,99),[0,0,0])
        session.estimate(msg(3,99,99),[0,0,0])
        session.estimate(msg(18,99,99),None)
        live=session.public()['live_metrics']
        self.assertAlmostEqual(live['rmse_m'],math.sqrt(25/2))
        self.assertEqual(live['scored_samples'],2)
        self.assertIsNone(session.public()['result'])
        final=session.finish(30)
        self.assertEqual(final['result']['rmse_m'],live['rmse_m'])
        session.estimate(msg(36,99,99),[0,0,0])
        self.assertEqual(session.public(),final)

    def test_other_levels_do_not_publish_live_metrics_and_permission_is_checked_at_projection(self):
        for level in ('c0','c1','c3','c4'):
            session=CampaignSession(self.config(level));session.start(0)
            session.estimate({'simulation_tick':6,'payload':{'x_m':3,'y_m':4}},[0,0,0])
            self.assertNotIn('live_metrics',session.public())
        session=CampaignSession(self.config())
        session.definition['permissions']['visualization']['allowed_metrics']=[]
        self.assertNotIn('live_metrics',session.public())

    def test_active_feedback_uses_sample_time_truth_and_stays_out_of_robot_topics(self):
        config=self.config();a=Authority(config,controlled=True,startup_sources=solutions(config));self.addCleanup(a.close)
        truth_by_tick={};samples=[]
        observe=a.campaign.estimate
        def capture(message,truth):
            samples.append((message,truth_by_tick[message['simulation_tick']],a._private['targets'][0]['pose'][:]))
            observe(message,truth)
        a.campaign.estimate=capture
        for _ in range(60):
            truth_by_tick[a.tick]=a._private['targets'][0]['pose'][:]
            a.advance()
        attempt=a.campaign_status()['attempt']
        self.assertEqual(attempt['phase'],'running')
        self.assertIsNone(attempt['result'])
        self.assertGreater(attempt['live_metrics']['scored_samples'],0)
        self.assertTrue(math.isfinite(attempt['live_metrics']['rmse_m']))
        import json
        self.assertNotIn('live_metrics',json.dumps(a.view))
        self.assertNotIn('rmse_m',json.dumps(a.worker_init))
        self.assertFalse(any('metric' in channel or 'truth' in channel for channel in a.runtime_inputs()))
        def reference(index):
            return math.sqrt(sum((m['payload']['x_m']-row[index][0])**2+(m['payload']['y_m']-row[index][1])**2 for row in samples for m in [row[0]])/len(samples))
        self.assertAlmostEqual(attempt['live_metrics']['rmse_m'],reference(1))
        self.assertNotAlmostEqual(attempt['live_metrics']['rmse_m'],reference(2),places=8)
        self.assertNotIn('truth_pose',json.dumps(a.campaign_status()))

    def test_test_snapshots_do_not_count_redeploy_keeps_counts_and_restart_resets(self):
        config=self.config();a=Authority(config,controlled=True);self.addCleanup(a.close)
        a.deployment=DeploymentManager(a)
        snapshot={'files':solutions(config),'ledger':{}};snapshot['revision']=digest(snapshot)
        a.deployment.start('test',snapshot);self.finish(a)
        self.assertEqual(a.deployment.last['status'],'Ready',a.deployment.last)
        self.assertEqual(a.campaign.public()['live_metrics']['scored_samples'],0)
        a.deployment.start('deploy',snapshot);self.finish(a)
        for _ in range(36):a.advance()
        count=a.campaign.public()['live_metrics']['scored_samples']
        self.assertGreater(count,0)
        a.deployment.start('deploy',snapshot);self.finish(a)
        self.assertGreaterEqual(a.campaign.public()['live_metrics']['scored_samples'],count)
        a.finish_campaign()
        fresh=Authority(config,controlled=True);self.addCleanup(fresh.close)
        self.assertEqual(fresh.campaign.public()['live_metrics'],{'rmse_m':None,'scored_samples':0})

    def finish(self,a):
        end=time.monotonic()+10
        while a.deployment.job and time.monotonic()<end:
            a.advance()
            if a.deployment.job and not a.deployment.job['worker'].ready:time.sleep(.002)
        self.assertIsNone(a.deployment.job)
