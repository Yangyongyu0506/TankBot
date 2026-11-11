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
from browser_authority import BrowserSupervisor,runtime_event


class PlanningPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=configure(load_config(ROOT/'config/game.yaml'),'navigation.c5')
        cls.contract=cls.config['campaign']['levels']['navigation.c5']['runtime']['preparation']

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

    def browser(self):
        return BrowserSupervisor(self.config,{'preparation':copy.deepcopy(self.contract)})

    def test_preparation_uses_trusted_five_seconds_not_telemetry_and_periodic_stays_forty(self):
        with patch.dict(sys.modules,{'js':types.SimpleNamespace(runtime_send=lambda raw:None)}):
            sup=self.browser()
            with patch('browser_authority.time.monotonic_ns',return_value=100):
                self.assertTrue(sup.submit_preparation({'request_id':'plan','operation':'plan','wall_deadline_ms':999999}))
                self.assertEqual(sup.expires_ns,5_000_000_100)
            with patch('browser_authority.time.monotonic_ns',return_value=5_000_000_100):
                sup.receive('{}',0);self.assertEqual(sup.poll_preparation(),{})
            self.assertIsNone(sup.fault);self.assertEqual(sup.timing.public()['total_batches'],0)
            with patch('browser_authority.time.monotonic_ns',return_value=6_000_000_000):
                sup.submit({'request_id':'periodic'})
                self.assertEqual(sup.expires_ns,6_040_000_000)
            sup.close()

    def test_decode_crossing_or_late_preparation_is_killed_and_old_worker_cannot_reply(self):
        for scenario in ('late','decode'):
            with patch.dict(sys.modules,{'js':types.SimpleNamespace(runtime_send=lambda raw:None)}):
                sup=self.browser()
                with patch('browser_authority.time.monotonic_ns',return_value=100):
                    sup.submit_preparation({'request_id':'p','operation':'plan'})
                with patch('browser_authority.time.monotonic_ns',return_value=5_000_000_101 if scenario=='late' else 5_000_000_099) as clock:
                    def decode(raw):clock.return_value=5_000_000_101;return {}
                    with patch('browser_authority.strict_loads',side_effect=decode):sup.receive('{}',0)
                self.assertEqual(sup.fault,'RESOURCE_LIMIT');self.assertTrue(sup.closed)
                self.assertNotIn(sup.worker_id,BrowserSupervisor.workers)
                runtime_event({'op':'result','worker_id':sup.worker_id,'raw':'{}','elapsed_ms':0})
                self.assertIsNone(sup.result)
