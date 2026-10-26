"""Anonymous armor geometry, visibility, bounded SDK, grants and symmetric scoring."""
import copy
import math
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot import ArmorDetections
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure
from tankbot_host.weapon_sensors import ArmorDetectionSimulator
from tankbot_host.level_rules import Diagnostics
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_protocol.validation import Validator,Rejected,envelope


class ArmorObservationTests(unittest.TestCase):
    def config(self,ideal=True):
        c=configure(load_config(ROOT/'config/game.yaml'),'c5')
        c['scene']['walls']=[]
        sensor=next(s for s in c['campaign']['levels']['c5']['sensors'] if s['type']=='armor_detector')
        if ideal:sensor['parameters']['noise'].update(range_stddev_m=0.,bearing_stddev_rad=0.,drop_probability=0.)
        return c

    def world(self,c,pose=(2.,2.,0.),own=(0.,0.,0.)):
        return {'truth_pose':list(own),'targets':[{'target_id':c['weapons']['targets'][0]['target_id'],'pose':list(pose),'alive':True}]}

    def test_actual_armor_centers_are_in_own_frame_without_identity_or_center_fix(self):
        c=self.config();private=self.world(c,own=(0.,0.,math.pi/2))
        sampler=ArmorDetectionSimulator(c);result=sampler.sample(private,0)
        self.assertEqual(set(result),{'measurements_rt'})
        self.assertEqual(len(result['measurements_rt']),2)
        z=np.array(result['measurements_rt']);xy=z[:,0,None]*np.column_stack((np.cos(z[:,1]),np.sin(z[:,1])))
        expected=np.array([[2.,-1.79],[1.79,-2.]])
        for point in xy:self.assertLess(np.min(np.linalg.norm(expected-point,axis=1)),1e-12)
        self.assertIsNone(sampler.sample(private,0));self.assertIsNone(sampler.sample(private,1))
        self.assertEqual(sampler.sample(private,6),result)

    def test_facing_walls_range_death_and_missing_points_are_filtered_before_noise(self):
        c=self.config();private=self.world(c,pose=(3.,0.,0.))
        np.testing.assert_allclose(ArmorDetectionSimulator(c).sample(private,0)['measurements_rt'],[[2.79,0.]])
        sensor=next(s for s in c['campaign']['levels']['c5']['sensors'] if s['type']=='armor_detector')
        limit=sensor['parameters']['range_m']
        private['targets'][0]['pose'][0]=limit+.21
        self.assertEqual(len(ArmorDetectionSimulator(c).sample(private,0)['measurements_rt']),1)
        private['targets'][0]['pose'][0]+=1e-5
        self.assertEqual(ArmorDetectionSimulator(c).sample(private,0),{'measurements_rt':[]})
        private=self.world(c);c['scene']['walls']=[{'center':[1.,1.12],'size':[.05,.05]}]
        self.assertEqual(len(ArmorDetectionSimulator(c).sample(private,0)['measurements_rt']),1)
        c['scene']['walls']=[{'center':[1.,1.],'size':[.2,4.]}]
        self.assertEqual(ArmorDetectionSimulator(c).sample(private,0),{'measurements_rt':[]})
        c['scene']['walls']=[];private['targets'][0]['alive']=False
        self.assertEqual(ArmorDetectionSimulator(c).sample(private,0),{'measurements_rt':[]})

    def test_quarter_turn_and_mount_relabeling_preserve_anonymous_observations(self):
        c=self.config();first=self.world(c)
        expected=ArmorDetectionSimulator(c).sample(first,0)['measurements_rt']
        for yaw in (math.pi/2,math.pi,-math.pi/2):
            np.testing.assert_allclose(ArmorDetectionSimulator(c).sample(self.world(c,pose=(2.,2.,yaw)),0)['measurements_rt'],expected,atol=1e-12)
        changed=copy.deepcopy(c);changed['weapons']['targets'][0]['armor']['mounts_m'].reverse()
        np.testing.assert_allclose(ArmorDetectionSimulator(changed).sample(first,0)['measurements_rt'],expected,atol=1e-12)

    def test_seeded_noise_dropout_and_negative_range_wrap_boundaries(self):
        c=self.config(False);private=self.world(c,pose=(3.,0.,0.))
        a,b=ArmorDetectionSimulator(c),ArmorDetectionSimulator(c);values=[]
        for tick in range(0,6000,6):
            value=a.sample(private,tick);self.assertEqual(value,b.sample(private,tick));values.extend(value['measurements_rt'])
        self.assertGreater(len(values),850);self.assertLess(len(values),950)
        errors=np.asarray(values)-np.array([2.79,0.])
        self.assertLess(abs(errors[:,0].std()-.03),.005);self.assertLess(abs(errors[:,1].std()-.005),.001)
        class Noise:
            def random(self):return 1.
            def gauss(self,*args):return -100.
        a=ArmorDetectionSimulator(c);a.random=Noise();z=a.sample(private,0)['measurements_rt'][0]
        self.assertEqual(z[0],0.);self.assertGreaterEqual(z[1],-math.pi);self.assertLess(z[1],math.pi)

    def test_sdk_schema_and_authority_keep_only_bounded_sensor_input(self):
        source=np.array([[2.,.1],[3.,-.2]])
        data=ArmorDetections(source);source[0,0]=99
        self.assertEqual(data.measurements_rt[0,0],2.);self.assertFalse(data.measurements_rt.flags.writeable)
        self.assertEqual(ArmorDetections([]).measurements_rt.shape,(0,2))
        for invalid in (np.zeros((3,2)),[[1.,math.pi]],[[-1.,0.]],[[1.,float('nan')]],np.zeros((1,3))):
            with self.subTest(invalid=str(invalid)),self.assertRaises(ValueError):ArmorDetections(invalid)
        c=self.config();a=Authority(c,controlled=True);self.addCleanup(a.close)
        self.assertIn('/robot/sensors/armor_detections',a.runtime_inputs())
        for topic in ('/robot/sensors/radar','/robot/sensors/intercepted_gps'):
            self.assertNotIn(topic,a.runtime_inputs());self.assertNotIn(topic,a._sensors)
        validator=Validator(c,'test')
        message=envelope('armor_detections@1','/robot/sensors/armor_detections',{'measurements_rt':[[2.,.1]]},tick=0,hz=60,run_id='test',publisher_id='sensor:armor_detector',sequence=0,frame_id='base_link')
        validator.structure(message)
        for payload in ({'measurements_rt':[[1.,.1]]*3},{'measurements_rt':[[1.,.1]],'armor_id':0},{'measurements_rt':[[1.,math.pi]]}):
            bad=copy.deepcopy(message);bad['payload']=payload
            with self.assertRaises(Rejected):validator.structure(bad)
        bad=copy.deepcopy(message);bad['frame_id']='map'
        with self.assertRaises(Rejected):validator.structure(bad)

    def test_equivalent_phase_scores_identically_and_legacy_sources_are_preserved(self):
        c=self.config();d=Diagnostics(c['campaign']['levels']['c5']['evaluation'])
        d.observe({'x_m':2.,'y_m':3.,'yaw_rad':math.pi/2+.1},[2.,3.,0.])
        self.assertAlmostEqual(d.report()['yaw_rmse_rad'],.1)
        self.assertEqual(d.report()['rmse_m'],0.)
        old=Diagnostics(configure(c,'c4')['campaign']['levels']['c4']['evaluation'])
        old.observe({'x_m':2.,'y_m':3.,'yaw_rad':math.pi/2+.1},[2.,3.,0.])
        self.assertAlmostEqual(old.report()['yaw_rmse_rad'],math.pi/2+.1)
        with tempfile.TemporaryDirectory() as directory:
            api=WorkspaceAPI(configure(c,'c4'),directory=directory);before=api.store.read()
            kept={'perception/fusion_tracker.py':'# retained legacy fusion\n','weapons/auto_aim.py':'# my controller\n'}
            api.store.edit(before['revision'],kept);view=api.unlock(c)
            self.assertEqual(view['learning']['lesson']['edit_files'],['perception/armor_tracker.py','weapons/target_prediction.py','weapons/auto_aim.py'])
            plan=api.post('upgrade',{'revision':view['snapshot']['revision']})
            self.assertFalse(any(item['path'] in kept for item in plan['entries']))
            for path,text in kept.items():self.assertEqual(api.store.read()['files'][path],text)
