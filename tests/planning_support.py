"""Isolated reference sources only. The production template contains no search solution."""
from pathlib import Path
from path_tracking_support import solution as tracking_solution

FIXTURES=Path(__file__).parent/'fixtures'


def solution(config, algorithm='astar'):
    if algorithm not in ('astar','dijkstra'):
        raise ValueError(algorithm)
    files=tracking_solution(config)
    files['navigation/planning_geometry.py']=(FIXTURES/'planning_common.py').read_text()
    files['navigation/global_planner.py']=(FIXTURES/f'planner_{algorithm}.py').read_text()
    files['tests/test_planner_unsolvable.py']='''import unittest
import numpy as np
from tankbot import OccupancyGrid
from navigation.global_planner import GlobalPlanner

class UnsolvableTest(unittest.TestCase):
    def test_confirmed_no_solution_returns_none(self):
        data = OccupancyGrid(np.ones((8,8),dtype=np.bool_),np.zeros(2),.2)
        planner = GlobalPlanner(data,.5,.15)
        self.assertIsNone(planner.plan(np.array([.1,.1]),np.array([.5,.5])))
'''
    return files


def standalone_source(algorithm='astar'):
    """One editor file for real-player QA; still exclusively a test reference."""
    search=(FIXTURES/f'planner_{algorithm}.py').read_text().replace('from navigation.planning_geometry import PlanningGeometry\n','')
    return (FIXTURES/'planning_common.py').read_text()+'\n'+search
