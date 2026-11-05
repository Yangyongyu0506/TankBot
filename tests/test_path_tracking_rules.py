"""Judge semantics use synthetic component geometry, independent of a playable route."""
import copy
import math
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure,CampaignSession
from tankbot_host.path_tracking import PathTracking
from tankbot_host.path_generation import distance_to_polyline


class PathTrackingRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=configure(load_config(ROOT/'config/game.yaml'),'navigation.c4')
        rules=cls.config['campaign']['levels']['navigation.c4']['rules']
        cls.spec,cls.parameters=rules['path_tracking'],rules['parameters']
        cls.reference={'path_id':'unit-reference','points_m':np.column_stack((np.linspace(-2.,0.,21),np.zeros(21))).tolist(),
                       'checkpoints_m':[[-2.,0.],[-1.,0.],[0.,0.]]}

    def task(self):
        return PathTracking(self.spec,self.reference,self.parameters,60)

    def private(self,pose=None,velocity=None,contact=False):
        return {'truth_pose':pose or [0.,0.,0.],'truth_velocity':velocity or [0.,0.,0.],
                'targets':[],'target_hits':{},'player_hp':None,'wall_contact':contact}

    def final_goal(self,task):
        task.start(0)
        task.observe([-2.,0.,0.],[0.,0.,0.],1)
        task.observe([-1.,0.,0.],[0.,0.,0.],2)

    def test_distance_is_to_all_segments_including_caps_and_weighted_by_time(self):
        self.assertAlmostEqual(distance_to_polyline([.5,.2],[[0.,0.],[1.,0.],[1.,1.]]),.2)
        self.assertAlmostEqual(distance_to_polyline([-1.,0.],[[0.,0.],[1.,0.]]),1.)
        task=self.task();task.start(0)
        task.observe([-1.5,.1,0.],[0.,0.,0.],1)
        task.observe([-1.5,.3,0.],[0.,0.,0.],3)
        self.assertAlmostEqual(task.rmse_m,math.sqrt((.1**2+2*.3**2)/3))
        before=task.report();task.observe([-1.5,99.,0.],[0.,0.,0.],3)
        self.assertEqual(task.report(),before);self.assertEqual(task.tracking_samples,2)

    def test_checkpoints_are_ordered_inclusive_radius_and_one_per_tick(self):
        task=self.task();task.start(0)
        task.observe([0.,0.,0.],[0.,0.,0.],1)
        self.assertEqual(task.reached_count,0)
        task.observe([-1.5,0.,0.],[0.,0.,0.],2)
        self.assertEqual(task.reached_count,1)
        task.observe([-1.5,0.,0.],[0.,0.,0.],2)
        self.assertEqual(task.reached_count,1)
        task.observe([-1.5,0.,0.],[0.,0.,0.],3)
        self.assertEqual(task.reached_count,2)
        self.assertEqual(task.settled_ticks,0)

    def test_exact_maximum_is_allowed_and_larger_deviation_or_contact_latches_failure(self):
        task=self.task();task.start(0)
        task.observe([-1.,self.parameters['max_deviation_m'],0.],[0.,0.,0.],1)
        self.assertFalse(task.deviation_exceeded)
        task.observe([-1.,float(np.nextafter(self.parameters['max_deviation_m'],np.inf)),0.],[0.,0.,0.],2)
        task.observe([-1.,0.,0.],[0.,0.,0.],3,True)
        task.observe([-1.,0.,0.],[0.,0.,0.],4,False)
        self.assertTrue(task.deviation_exceeded);self.assertTrue(task.collision)

    def test_continuous_stop_uses_both_translation_axes_and_resets_on_gap(self):
        task=self.task();self.final_goal(task)
        for tick in range(3,20):task.observe([0.,0.,2.],[0.,0.,0.],tick)
        task.observe([0.,0.,2.],[0.,self.spec['stop_linear_speed_mps']*2,0.],20)
        self.assertEqual(task.settled_ticks,0)
        task.observe([0.,0.,2.],[0.,0.,0.],25)
        self.assertEqual(task.settled_ticks,0)
        for tick in range(26,25+self.spec['stop_duration_ticks']+1):task.observe([0.,0.,2.],[0.,0.,self.spec['stop_yaw_rate_radps']],tick)
        self.assertTrue(task.complete)

    def test_terminal_priority_last_tick_and_immediate_error_grade_without_dilution(self):
        for kind in ('pass','timeout','collision','fault','deviation','bad_rmse'):
            with self.subTest(kind=kind):
                s=CampaignSession(copy.deepcopy(self.config));s.navigation=self.task();s.start(0)
                self.final_goal(s.navigation)
                first=s.limit_ticks-self.spec['stop_duration_ticks']+(kind=='timeout')
                if kind=='bad_rmse':
                    s.navigation.weighted_squared_error=(self.parameters['tracking_rmse_limit_m']*2)**2*s.limit_ticks/60
                    s.navigation.scored_duration_s=1.
                result=None
                for tick in range(first,s.limit_ticks+1):
                    s.controller_faulted=kind=='fault' and tick==s.limit_ticks
                    if kind=='deviation' and tick==s.limit_ticks:s.navigation.deviation_exceeded=True
                    result=s.outcome(self.private(contact=kind=='collision' and tick==s.limit_ticks),tick)
                expected={'pass':'objective_completed','timeout':'timeout','collision':'collision','fault':'controller_error','deviation':'path_deviation','bad_rmse':'tracking_error'}[kind]
                self.assertEqual(result,expected)
                s.finish(s.limit_ticks,passed=result=='objective_completed',reason=result)
                before=s.navigation.report();s.outcome(self.private(),s.limit_ticks+60)
                self.assertEqual(s.navigation.report(),before)
