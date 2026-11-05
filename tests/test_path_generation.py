"""Generated references, complete-body safety, bounded failure and immutable preparation."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import unittest
from unittest.mock import patch
import numpy as np
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot import readonly_path
from tankbot_host.authority import load_config
from tankbot_host.campaign import configure
from tankbot_host.scene_definition import resolve_scene,SceneResolver
from tankbot_host.path_generation import (generate_path,validate_path,segment_safe,wall_boxes,
    PathGenerationError,round_corners,resample_polyline,self_intersects,sample_arclength)


class PathGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=load_config(ROOT/'config/game.yaml')
        cls.config=configure(cls.base,'navigation.c4')
        cls.spec=cls.config['campaign']['levels']['navigation.c4']['rules']['path_tracking']

    def generate(self,seed=0,parameters=None):
        c=self.config
        return generate_path(c['scene']['walls'],c['body'],c['scene']['initial_pose'],
                             parameters or self.spec['generation'],seed,self.spec['checkpoint_spacing_m']).to_dict()

    def test_multiple_seeds_deliver_safe_nonintersecting_resampled_paths_and_no_global_rng_changes(self):
        before=random.getstate();identities=set()
        for seed in range(32):
            with self.subTest(seed=seed):
                r=self.generate(seed);p=r['parameters'];points=readonly_path(r['points_m'])
                self.assertEqual(points.dtype,np.float64);self.assertFalse(points.flags.writeable)
                spans=np.linalg.norm(np.diff(points,axis=0),axis=1)
                np.testing.assert_allclose(spans[:-1],p['sample_spacing_m'],atol=p['numeric_tolerance_m'])
                self.assertLessEqual(spans[-1],p['sample_spacing_m']+p['numeric_tolerance_m'])
                validate_path(r['points_m'],self.config['scene']['walls'],self.config['body'],self.config['scene']['initial_pose'],p)
                self.assertEqual(r['checkpoints_m'][0],r['points_m'][0])
                self.assertEqual(r['checkpoints_m'][-1],r['points_m'][-1])
                self.assertFalse(self_intersects(r['points_m'],p['numeric_tolerance_m']))
                self.assertLessEqual(r['attempts'],p['max_attempts']);identities.add(r['path_id'])
        self.assertEqual(before,random.getstate());self.assertGreater(len(identities),1)
        self.assertEqual(self.generate(),self.generate())

    def test_retries_and_javascript_json_preserve_identity_without_regenerating(self):
        scene=resolve_scene(self.config);cache=SceneResolver(scene)
        raw=json.dumps(scene.to_config())
        roundtrip=json.loads(subprocess.check_output(['node','-e',
            "process.stdout.write(JSON.stringify(JSON.parse(require('fs').readFileSync(0,'utf8'))))"],input=raw,text=True))
        with patch('tankbot_host.path_generation.generate_path',side_effect=AssertionError('must reuse')):
            self.assertIs(cache.get('navigation.c4'),scene)
            other=resolve_scene(roundtrip)
            self.assertEqual(other.path_reference.identity,scene.path_reference.identity)
            self.assertEqual(other.path_reference.to_dict(),scene.path_reference.to_dict())

    def test_changed_map_or_forged_reference_fails_instead_of_silently_regenerating(self):
        c=resolve_scene(self.config).to_config()
        for kind in ('point','map','seed'):
            candidate=copy.deepcopy(c)
            if kind=='point':candidate['navigation_path']['points_m'][1][0]+=1.
            elif kind=='map':candidate['scene']['walls'][0]['center'][0]+=.1
            else:candidate['runtime']['seed']+=1
            with self.subTest(kind=kind),self.assertRaisesRegex(PathGenerationError,'REFERENCE_MISMATCH'):
                resolve_scene(candidate)

    def test_limits_and_impossible_geometry_stop_without_relaxing_constraints(self):
        for changes in ({'grid_resolution_m':1.e-6},{'max_search_expansions':1},
                        {'min_total_turn_rad':100.,'max_attempts':1},
                        {'smoothing_step_m':1.e-12,'max_attempts':1},
                        {'sample_spacing_m':1.e-12,'max_attempts':1}):
            with self.subTest(changes=changes),self.assertRaises(PathGenerationError):
                self.generate(parameters={**self.spec['generation'],**changes})
        c=self.config
        with self.assertRaisesRegex(PathGenerationError,'SPAWN_BLOCKED'):
            generate_path(c['scene']['walls'],c['body'],[0.,1.5,0.],self.spec['generation'],0,1.)

    def test_smoothing_and_resampling_do_not_bypass_the_final_corridor_check(self):
        # Synthetic geometry exercises a smoothing shortcut through an obstacle;
        # these are not course route points or an alternative playable reference.
        control=[[-3.,0.],[-3.,3.],[3.,3.]]
        smooth=round_corners(control,1.,.025,1.e-8,8192)
        points=resample_polyline(smooth,.1,1.e-8,256)
        wall=[{'center':[-2.7,2.7],'size':[.2,.2]}]
        p={**self.spec['generation'],'min_length_m':1.,'min_endpoint_distance_m':1.,'require_blocked_chord':False,'min_detour_m':.01,'min_total_turn_rad':.1}
        with self.assertRaisesRegex(PathGenerationError,'unsafe final'):
            validate_path(points,wall,self.config['body'],[-3.,0.,0.],p)
        self.assertTrue(segment_safe([-1.,0.],[1.,0.],wall_boxes([{'center':[0.,1.],'size':[.2,.2]}])))
        self.assertFalse(segment_safe([-1.,0.],[1.,0.],wall_boxes([{'center':[0.,1.],'size':[.2,.2]}],1.)))

    def test_reference_array_rejects_bad_shape_duplicate_nan_and_cannot_be_made_writable(self):
        r=self.generate();array=readonly_path(r['points_m'])
        with self.assertRaises(ValueError):array.setflags(write=True)
        with self.assertRaises(ValueError):array[0,0]=999.
        for value in ([],[[0.,0.]],[[0.,0.],[0.,0.]],[[0.,0.],[np.nan,1.]],[[0.,0.,0.],[1.,1.,1.]]):
            with self.subTest(value=str(value)),self.assertRaises(ValueError):readonly_path(value)
