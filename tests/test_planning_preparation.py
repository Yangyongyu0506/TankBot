"""One-shot message/worker boundaries, independent of the periodic deadline."""
import copy
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','runtime','tests')]
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure
from preparation_runner import PreparationRunner


class PlanningPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=configure(load_config(ROOT/'assets/config/game.yaml'),'navigation.c5')
        cls.contract=cls.config['campaign']['levels']['navigation.c5']['runtime']['preparation']

    def test_native_preparation_budget_is_independent_and_not_player_selected(self):
        from tankbot_host.supervisor import Supervisor
        from unittest.mock import Mock
        supervisor=Supervisor.__new__(Supervisor)
        supervisor.preparation=copy.deepcopy(self.contract)
        supervisor.initialization_budget_ns=5_000_000_000
        supervisor._submit=Mock(return_value=True)
        request={'request_id':'planning','operation':'plan','wall_deadline_ms':999999}
        self.assertTrue(supervisor.submit_preparation(request))
        supervisor._submit.assert_called_once_with(request,5_000_000_000,task=True)
        from tankbot_host.execution_profiles import select_execution_profile
        self.assertEqual(select_execution_profile(self.config,'native').batch_wall_deadline_ms,30)

    def test_one_call_readonly_public_inputs_identity_and_no_planner_in_periodic_init(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'navigation').mkdir();(root/'navigation/__init__.py').write_text('')
            (root/'navigation/global_planner.py').write_text('''import numpy as np
class GlobalPlanner:
    def __init__(self, map_data, robot_radius_m, safety_margin_m):
        assert type(map_data).__name__ == "OccupancyGrid"
        assert robot_radius_m == .5 and safety_margin_m == .15
        try: map_data.grid.setflags(write=True)
        except ValueError: pass
        else: raise AssertionError("mutable map")
    def plan(self, start_xy, goal_xy):
        assert not start_xy.flags.writeable and not goal_xy.flags.writeable
        return np.array([start_xy, goal_xy],dtype=np.float64)
''')
            init={'workspace':directory,'run_id':'run','preparation':copy.deepcopy(self.contract),
                  'preparation_limits':{'max_path_points':512},'config':{'path_tracking_parameters':{'reference':None}}}
            request={'preparation_version':'1.0','request_id':'p','run_id':'run','deployment_id':'deployment',
                     'task_id':'a'*64,'operation':'plan','payload':{'map_data':{'grid':[[False,False],[False,False]],
                     'origin_xy':[0.,0.],'resolution_m':.2},'start_xy':[0.,0.],'goal_xy':[.1,0.],
                     'robot_radius_m':.5,'safety_margin_m':.15}}
            runner=PreparationRunner(init)
            self.assertNotIn('navigation.global_planner',sys.modules)
            result=runner.step(request)
            self.assertEqual(result['payload']['status'],'completed')
            self.assertEqual(result['payload']['result']['dtype'],'float64')
            self.assertEqual(runner.step(request)['payload']['status'],'failed')
            wrong={**request,'operation':'initialize','deployment_id':'old','payload':{'path':{}}}
            self.assertEqual(runner.step(wrong)['payload']['status'],'failed')
            class Periodic:
                def __init__(self,value):self.value=copy.deepcopy(value)
                def step(self,r):return r
                def close(self):pass
            accepted={'task_id':'a'*64,'path_id':'b'*64,'points_m':[[0.,0.],[.1,0.]],'length_m':.1}
            with patch.dict(sys.modules,{'module_runner':types.SimpleNamespace(ModuleRunner=Periodic)}):
                response=runner.step({**request,'operation':'initialize','payload':{'path':accepted}})
                self.assertNotIn('navigation.global_planner',list(sys.modules))
            self.assertEqual(response['payload']['status'],'completed')
            self.assertEqual(runner.runner.value['config']['path_tracking_parameters']['reference'],accepted)
            self.assertEqual(runner.step({'request_id':'periodic'}),{'request_id':'periodic'})
            self.assertEqual(runner.step(request)['payload']['status'],'failed')
            runner.close()
            from preparation_runner import clear_project_modules
            clear_project_modules(directory)
            sys.path[:]=[p for p in sys.path if p!=directory]
