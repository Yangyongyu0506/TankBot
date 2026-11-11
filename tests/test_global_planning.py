"""Public grid, bounded goal generation and independent continuous path contract."""
import copy
import math
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python','tests')]
from tankbot import OccupancyGrid
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure
from tankbot_host.global_planning import (map_grid,inflate_grid,SafeGrid,prepare_planning,
                                         validate_planned_path,PlanningError,safe_task,reference_distances)


def wire(points):
    return {'dtype':'float64','shape':list(points.shape),'points_m':points.tolist()}


class GlobalPlanningGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=configure(load_config(ROOT/'config/game.yaml'),'navigation.c5')
        cls.spec=cls.config['campaign']['levels']['navigation.c5']['rules']['global_planning']

    def test_grid_axes_floor_centres_bounds_and_irrevocable_readonly(self):
        data=OccupancyGrid(np.zeros((5,7),dtype=np.bool_),np.array([-1.,-2.]),.20)
        self.assertEqual(data.world_to_grid(np.array([-.8,-1.8])),(1,1))
        self.assertEqual(data.world_to_grid(np.array([-.80001,-1.80001])),(0,0))
        np.testing.assert_allclose(data.grid_to_world(1,1),[-.7,-1.7])
        for row in range(5):
            for col in range(7):self.assertEqual(data.world_to_grid(data.grid_to_world(row,col)),(row,col))
        for value in ([-1.001,-2.],[.4,-2.],[-1.,-1.],[-1.,-2.001]):
            with self.assertRaises(IndexError):data.world_to_grid(np.array(value))
        for index in ((-1,0),(0,-1),(5,0),(0,7)):
            with self.assertRaises(IndexError):data.grid_to_world(*index)
        for array in (data.grid,data.origin_xy,data.grid_to_world(0,0)):
            with self.assertRaises(ValueError):array.setflags(write=True)
        with self.assertRaises(Exception):data.resolution_m=1.

    def test_closed_raster_square_inflation_and_outside_band(self):
        walls=[{'center':[0.,0.],'size':[2.,2.]},{'center':[2.,2.],'size':[.2,.2]}]
        data,bounds=map_grid(walls,.2,1000)
        self.assertEqual(bounds,[-1.,-1.,2.1,2.1])
        self.assertTrue(data.grid[10,10])  # cell starts at the first wall's upper corner
        raw=np.zeros((25,25),dtype=np.bool_);raw[12,12]=True
        expanded=inflate_grid(raw,4)
        self.assertTrue(expanded[8:17,8:17].all())
        self.assertTrue(expanded[:4].all());self.assertTrue(expanded[:,:4].all())
        self.assertFalse(expanded[6,6])

    def test_seeded_tasks_safe_reachable_blocked_direct_and_reproducible(self):
        ids=[]
        for seed in (0,1,2):
            c=copy.deepcopy(self.config);c['runtime']['seed']=seed
            task=prepare_planning(c).to_dict();safe=safe_task(task)
            self.assertEqual(task,prepare_planning(c).to_dict())
            self.assertEqual(task['inflation_cells'],4)
            self.assertEqual(task['robot_radius_m'],.5)
            goal=safe.map.world_to_grid(np.array(task['goal_xy']))
            self.assertFalse(safe.map.grid[goal]);self.assertFalse(safe.blocked[goal])
            row,col=goal
            self.assertTrue(4<=row<safe.blocked.shape[0]-4 and 4<=col<safe.blocked.shape[1]-4)
            self.assertFalse(safe.map.grid[row-4:row+5,col-4:col+5].any())
            self.assertGreaterEqual(math.dist(task['start_xy'],task['goal_xy']),5.)
            self.assertFalse(safe.segment_safe(task['start_xy'],task['goal_xy']))
            distances=reference_distances(safe,task['start_xy'],self.spec['max_search_nodes'])
            self.assertAlmostEqual(task['reference_length_m'],distances[goal])
            self.assertTrue(12<=task['reference_length_m']<=18)
            ids.append(task['task_id'])
        self.assertEqual(len(set(ids)),3)

    def test_generation_and_grid_limits_fail_without_relaxation(self):
        for field,value,code in [('max_search_nodes',1,'NODE_LIMIT'),('max_goal_attempts',0,'GENERATION_FAILED'),
                                 ('max_grid_cells',1,'GRID_LIMIT'),('min_endpoint_distance_m',1000.,'GENERATION_FAILED')]:
            c=copy.deepcopy(self.config)
            c['campaign']['levels']['navigation.c5']['rules']['global_planning'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(PlanningError,code):prepare_planning(c)

    def synthetic(self,points,blocked=None):
        data=OccupancyGrid(np.zeros((10,10),dtype=np.bool_) if blocked is None else blocked,np.zeros(2),.2)
        task={'task_id':'a'*64,'start_xy':points[0].tolist(),'goal_xy':points[-1].tolist(),
              'map':{'grid':data.grid.tolist(),'origin_xy':[0.,0.],'resolution_m':.2},
              'robot_radius_m':0.,'safety_margin_m':0.}
        return task

    def test_output_shape_capacity_finite_endpoints_spacing_and_no_repair(self):
        points=np.array([[.3,.3],[.4,.3],[.5,.3]],dtype=np.float64);task=self.synthetic(points)
        result=validate_planned_path(wire(points),task,self.spec)
        self.assertEqual(result['points_m'],points.tolist())
        self.assertAlmostEqual(result['length_m'],.2)
        for code,value in [('NO_PATH',None),('DTYPE',{**wire(points),'dtype':'float32'}),
                           ('SHAPE',{**wire(points),'shape':[3,3]}),('CAPACITY',wire(np.zeros((513,2)))),
                           ('FINITE',wire(np.array([[.3,.3],[np.nan,.3],[.5,.3]]))),
                           ('ENDPOINT',wire(points+1.)),('SPACING',wire(points[[0,2]])),
                           ('SPACING',wire(np.vstack((points[0],points[0],points[-1]))))]:
            with self.subTest(code=code),self.assertRaisesRegex(PlanningError,code):validate_planned_path(value,task,self.spec)

    def test_nodes_safe_but_segment_crosses_or_touches_corner_is_rejected(self):
        blocked=np.zeros((10,10),dtype=np.bool_);blocked[2,2]=True
        for first,last in (([.395,.415],[.415,.395]),([.39,.41],[.41,.39])):
            points=np.array([first,last],dtype=np.float64);task=self.synthetic(points,blocked)
            safe=safe_task(task)
            self.assertTrue(safe.segment_safe(points[0],points[0]));self.assertTrue(safe.segment_safe(points[1],points[1]))
            with self.assertRaisesRegex(PlanningError,r'SEGMENT_UNSAFE.*segment\[0\]'):
                validate_planned_path(wire(points),task,self.spec)
        contact=np.array([[.4,.45],[.4,.5]],dtype=np.float64);task=self.synthetic(contact,blocked)
        with self.assertRaisesRegex(PlanningError,'NODE_UNSAFE'):validate_planned_path(wire(contact),task,self.spec)
        outside=np.array([[-.01,.3],[.05,.3]],dtype=np.float64);task=self.synthetic(outside)
        with self.assertRaisesRegex(PlanningError,'NODE_UNSAFE'):validate_planned_path(wire(outside),task,self.spec)

    def test_reference_search_forbids_diagonal_corner_cut_and_no_route_exposure(self):
        raw=np.ones((3,3),dtype=np.bool_);raw[0,0]=raw[1,1]=False
        safe=SafeGrid(OccupancyGrid(raw,np.zeros(2),.2),0.,0.)
        distances=reference_distances(safe,[.1,.1],100)
        self.assertNotIn((1,1),distances)

    def test_nonoptimal_retraced_longer_than_reference_range_is_still_a_legal_path(self):
        points=np.array([[.3 if index%2==0 else .4,.3] for index in range(201)]+[[.4,.3],[.5,.3]],dtype=np.float64)
        task=self.synthetic(points)
        result=validate_planned_path(wire(points),task,self.spec)
        self.assertGreater(result['length_m'],18.)
        self.assertEqual(result['points_m'],points.tolist())

