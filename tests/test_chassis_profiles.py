"""Shared collision/armor/GPS geometry and persistent-project level switching."""
import copy
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure
from tankbot_host.chassis_profiles import target_geometry,load_profiles
from tankbot_host.learning import learning_bundle
from tankbot_host.weapon_sensors import GpsInterceptSimulator
from tankbot_host.workspace import starter,WorkspaceStore
from tankbot_host.workspace_api import WorkspaceAPI
from tankbot_host.level_plugins import LevelValidationError


class ChassisProfileTests(unittest.TestCase):
    def setUp(self):self.base=load_config(ROOT/'config/game.yaml')

    def test_geometry_is_shared_by_core_public_calibration_runtime_and_gps(self):
        for level,half in (('c4',.4),('c5',.21)):
            with self.subTest(level=level):
                config=configure(self.base,level);a=Authority(config,controlled=True,developer_mode=True)
                try:
                    geometry=target_geometry(config)
                    self.assertEqual(geometry['armor_mounts'][0],[half,0.,0.])
                    self.assertEqual(a.public_profile()['target_geometry'],geometry)
                    self.assertEqual(a.worker_init['config']['actuators']['armor_mounts'],geometry['armor_mounts'])
                    self.assertEqual(a.worker_init['config']['observations']['gps_mount'],[half,0.])
                    calibration=learning_bundle(config)['lesson']['calibration']
                    self.assertEqual(calibration['armor_mounts'],geometry['armor_mounts'])
                    self.assertEqual(calibration['gps_mount'],[half,0.])
                    target=config['weapons']['targets'][0]
                    self.assertEqual(a.developer_snapshot()['target_visuals'][target['target_id']]['body'],geometry['body'])
                    if level=='c5':
                        self.assertEqual(target['body']['length_m'],.42)
                        self.assertEqual(target['body']['width_m'],.42)
                        self.assertEqual(config['body']['length_m'],.8,'player differential body stays independent')
                    sensor=GpsInterceptSimulator(config);sensor.sensor['parameters']['noise'].update(position_stddev_m=0,drop_probability=0)
                    private={'truth_pose':[0.,0.,0.],'targets':[{'target_id':target['target_id'],'alive':True,'pose':[2.,0.,math.pi/2]}]}
                    sample=sensor.sample(private,0)['positions_m'][0]
                    self.assertAlmostEqual(sample[0],2.)
                    self.assertAlmostEqual(sample[1],half)
                finally:a.close()

    def test_invalid_profile_mounts_version_size_and_visual_report_paths(self):
        for field,value,expected in (('schema_version','99','schema_version'),('mount',.4,'armor.mounts_m'),('width',1.,'armor.width_m'),('visual','unknown','visual.kind')):
            c=copy.deepcopy(self.base);p=c['chassis_profiles']['omnidirectional']
            if field=='mount':p['armor']['mounts_m'][0][0]=value
            elif field=='width':p['armor']['width_m']=value
            elif field=='visual':p['visual']['kind']=value
            else:p[field]=value
            with self.subTest(field=field),self.assertRaises(LevelValidationError) as error:load_profiles(c)
            self.assertEqual(error.exception.path,expected)
        c=copy.deepcopy(self.base);c['chassis_profiles']['omnidirectional']='../../tmp/chassis.yaml'
        with self.assertRaisesRegex(LevelValidationError,'inside config/chassis'):load_profiles(c)
        c=copy.deepcopy(self.base);del c['chassis_profiles']['omnidirectional']['visual']['armor']['front_length_m']
        with self.assertRaises(LevelValidationError) as error:load_profiles(c)
        self.assertEqual(error.exception.path,'visual.armor')

    def test_c0_project_can_unlock_c5_without_removing_player_sources(self):
        config=configure(self.base,'c0');files=starter(config)
        files['player_notes.py']='# preserved player module\n'+'#'*29000+'\n'
        size=lambda f:sum(len(p.encode())+len(s.encode()) for p,s in f.items())
        self.assertLess(size(files),32768)
        combined={**starter(configure(self.base,'c5')),**files}
        self.assertGreater(size(combined),32768,'exercise the old source-cap failure')
        with tempfile.TemporaryDirectory() as directory:
            store=WorkspaceStore(directory,files,config['workspace']);before=store.read()
            api=WorkspaceAPI(config,directory=directory)
            for level in ('c1','c4','c5','c0','c5'):
                current=api.unlock(configure(self.base,level))
                self.assertEqual(current['level_id'],level)
                self.assertEqual(current['snapshot']['files']['player_notes.py'],files['player_notes.py'])
            self.assertEqual(api.store.read(before['revision'])['files'],before['files'])

