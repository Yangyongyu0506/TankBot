"""Shared maps: authoritative loading, real contact, topology and safe references."""
import copy
from collections import deque
from pathlib import Path
import sys
import tempfile
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_host.authority import CoreAdapter,load_config
from tankbot_host.campaign import configure,blocked
from tankbot_host.configuration import load_yaml
from tankbot_host.level_plugins import resolve_map,LevelValidationError


class MapAssetTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config(ROOT/'config/game.yaml')

    def test_shared_teaching_map_and_unchanged_legacy_scene(self):
        legacy=load_yaml(ROOT/'assets/maps/training_legacy.yaml')['walls']
        opened=load_yaml(ROOT/'assets/maps/open_training.yaml')['walls']
        self.assertEqual(self.config['scene']['walls'],legacy)
        self.assertEqual(opened,legacy[:4])
        self.assertEqual(set(self.config['campaign']['levels']),{'c0','c1','c2','c3','c4','c5','navigation.c0','navigation.c1','navigation.c2','navigation.c3','navigation.c4','navigation.c5'})
        definitions={value['metadata']['id']:value for path in (ROOT/'levels').glob('*.yaml') for value in [load_yaml(path)]}
        for lid in self.config['campaign']['levels']:
            source=definitions[lid]
            expected_map='navigation_warehouse.yaml' if lid in ('navigation.c4','navigation.c5') else 'open_training.yaml'
            self.assertEqual(source['world']['map'],{'source':'asset','path':'maps/'+expected_map})
            c=configure(self.config,lid)
            self.assertEqual(c['scene']['walls'],load_yaml(ROOT/'assets/maps'/expected_map)['walls'])
            if lid in ('navigation.c4','navigation.c5'):continue  # Both reuse the existing warehouse.
            self.assertFalse(blocked((0,0),(4,0),c['scene']['walls']))
            self.assertTrue(blocked((0,0),(8,0),c['scene']['walls']))
        self.assertTrue(blocked((0,0),(4,0),legacy))
        c['scene']['walls'][0]['center'][0]=999
        self.assertEqual(configure(self.config,'c0')['scene']['walls'],opened)

    def test_core_crosses_removed_wall_but_stops_at_boundary(self):
        c=configure(self.config,'c0');core=CoreAdapter(c,'differential')
        self.addCleanup(core.close)
        for tick in range(480):
            state=core.call({'op':'step','target':{'vx':1.,'vy':0.,'wz':0.,'source_tick':tick}})
            if tick==299:self.assertGreater(state['truth_pose'][0],3.)
        self.assertGreater(state['truth_pose'][0],5.)
        self.assertLessEqual(state['truth_pose'][0],6.-c['body']['length_m']/2+c['validation']['contact_measurement_tolerance_m'])

    def test_all_assets_load_and_navigation_free_space_is_connected(self):
        sizes=set()
        for path in sorted((ROOT/'assets/maps').glob('*.yaml')):
            with self.subTest(asset=path.name):
                walls=resolve_map({'source':'asset','path':str(path.relative_to(ROOT/'assets'))},path,self.config)
                self.assertEqual(walls,load_yaml(path)['walls'])
                # First four walls enclose the documented clear dimensions.
                right,left,top,bottom=walls[:4]
                xmax=right['center'][0]-right['size'][0]/2
                xmin=left['center'][0]+left['size'][0]/2
                ymax=top['center'][1]-top['size'][1]/2
                ymin=bottom['center'][1]+bottom['size'][1]/2
                sizes.add((round(xmax-xmin),round(ymax-ymin)))
                # Conservative 0.5 m circular clearance exceeds either body's
                # half-diagonal. Flood fill catches accidentally sealed corridors.
                spacing=.25;clearance=.5
                free=set()
                for i in range(round((xmax-xmin)/spacing)):
                    for j in range(round((ymax-ymin)/spacing)):
                        x=xmin+(i+.5)*spacing;y=ymin+(j+.5)*spacing
                        if not any(abs(x-w['center'][0])<=w['size'][0]/2+clearance and abs(y-w['center'][1])<=w['size'][1]/2+clearance for w in walls):free.add((i,j))
                self.assertTrue(free)
                seen={next(iter(free))};queue=deque(seen)
                while queue:
                    i,j=queue.popleft()
                    for cell in ((i-1,j),(i+1,j),(i,j-1),(i,j+1)):
                        if cell in free and cell not in seen:seen.add(cell);queue.append(cell)
                self.assertEqual(seen,free,'map contains disconnected traversable regions')
        self.assertEqual(sizes,{(12,8),(20,14),(16,12),(24,18)})

    def test_asset_errors_are_bounded_and_report_asset_geometry(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'assets/maps') as folder:
            path=Path(folder)/'invalid.yaml'
            spec={'source':'asset','path':str(path.relative_to(ROOT/'assets'))}
            for content,field in [('walls: [{center: [0, 0], size: [0, 1]}]','walls[0].size'),
                                  ('walls: [{center: [0], size: [1, 1]}]','walls[0].center'),
                                  ('walls: []\nscript: malicious','$')]:
                path.write_text(content)
                with self.assertRaises(LevelValidationError) as error:resolve_map(spec,'test',self.config)
                self.assertEqual(error.exception.filename,str(path))
                self.assertEqual(error.exception.path,field)
            path.write_text('walls: []\n')
            c=copy.deepcopy(self.config);c['level_plugins']['limits']['max_file_bytes']=2
            with self.assertRaisesRegex(LevelValidationError,'max_file_bytes'):resolve_map(spec,'test',c)
        for path in ('../../outside.yaml','maps/missing.yaml'):
            with self.assertRaises(LevelValidationError) as error:resolve_map({'source':'asset','path':path},'game.yaml',self.config,'scene.map')
            self.assertEqual(error.exception.path,'scene.map.path')

    def test_standalone_map_and_legacy_inline_configuration(self):
        raw=load_yaml(ROOT/'config/game.yaml')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'game.yaml'
            raw['scene']['map']['path']='maps/open_large.yaml'
            path.write_text(yaml.safe_dump(raw,allow_unicode=True))
            loaded=load_config(path)
            self.assertEqual(loaded['scene']['walls'],load_yaml(ROOT/'assets/maps/open_large.yaml')['walls'])
            raw['scene']['walls']=loaded['scene']['walls']
            path.write_text(yaml.safe_dump(raw))
            with self.assertRaisesRegex(LevelValidationError,'cannot both'):load_config(path)
            del raw['scene']['map']
            path.write_text(yaml.safe_dump(raw))
            self.assertEqual(load_config(path)['scene']['walls'],loaded['scene']['walls'])


if __name__=='__main__':unittest.main()
