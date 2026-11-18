"""Launch override lifetime, protected previews and practice-only progress."""
import copy
import http.client
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('host','protocol','sdk/python')]
from tankbot_host.authority import Authority,load_config
from tankbot_host.campaign import configure
from tankbot_host.maps import set_override,preview_catalog,asset_path,discover_maps
from tankbot_host.cli import parse_args
from tankbot_host.application import ApplicationState
from tankbot_host.server import LocalServer


class MapOverrideTests(unittest.TestCase):
    def setUp(self):
        self.base=load_config(ROOT/'assets/config/game.yaml')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)

    def state(self):return ApplicationState(self.base,self.directory/'settings.yaml',self.directory/'progress.json')

    def get(self,port,path):
        c=http.client.HTTPConnection('127.0.0.1',port,timeout=5);c.request('GET',path)
        response=c.getresponse();status=response.status;data=response.read();c.close()
        return status,data

    def test_cli_names_and_configure_preserve_override_without_mutating_plugins(self):
        _,args=parse_args(['--level','c0','--map','open_large'])
        self.assertEqual(args.map,'open_large')
        self.assertTrue(parse_args(['--list-maps'])[1].list_maps)
        original=copy.deepcopy(self.base)
        c=set_override(configure(self.base,'c0'),'open_large')
        for lid in self.base['campaign']['levels']:
            changed=configure(c,lid)
            self.assertEqual(changed['scene']['walls'],c['map_override']['walls'])
            self.assertEqual(changed['campaign']['levels'],original['campaign']['levels'])
            if 'path_tracking' in changed['campaign']['levels'][lid]['rules']:
                # Empty practice maps cannot satisfy the explicit obstacle-detour
                # constraint. Refuse boundedly rather than changing the course.
                from tankbot_host.path_generation import PathGenerationError
                with self.assertRaisesRegex(PathGenerationError,'PATH_GENERATION_FAILED'):
                    Authority(changed,controlled=True)
                changed=set_override(configure(self.base,lid),'navigation_warehouse')
            if 'global_planning' in changed['campaign']['levels'][lid]['rules']:
                from tankbot_host.global_planning import PlanningError
                with self.assertRaisesRegex(PlanningError,'PLANNING_TASK_GENERATION_FAILED'):
                    Authority(changed,controlled=True)
                changed=set_override(configure(self.base,lid),'navigation_warehouse')
            a=Authority(changed,controlled=True)
            try:
                self.assertEqual(a.public_profile()['walls'],changed['map_override']['walls'])
                self.assertTrue(a.public_profile()['custom_map_practice'])
            finally:a.close()
        self.assertEqual(self.base,original)
        for name in ('open_large','open_large.yaml','maps/open_large.yaml','assets/maps/open_large.yaml'):
            self.assertEqual(asset_path(name),'maps/open_large.yaml')
        for name in ('.','/etc/passwd','../../outside.yaml','maps/missing.yaml'):
            with self.assertRaises(ValueError):asset_path(name)

    def test_collision_is_reported_without_changing_scene(self):
        c=configure(self.base,'c0');before=copy.deepcopy(c)
        with self.assertRaisesRegex(ValueError,'MAP_SPAWN_BLOCKED.*player'):
            set_override(c,'navigation_slalom')
        self.assertEqual(c,before)
        # No automatic teleport: author an explicit safe initial pose instead.
        c['scene']['initial_pose']=[-6.,-4.,0.]
        changed=set_override(c,'navigation_slalom')
        self.assertEqual(changed['scene']['initial_pose'],[-6.,-4.,0.])

    def test_catalog_is_read_only_and_does_not_disclose_hidden_map(self):
        c=set_override(configure(self.base,'c0'),'open_large')
        player=preview_catalog(c)
        self.assertEqual(player['maps'],[])
        self.assertEqual(player['current']['walls'],c['scene']['walls'])
        developer=preview_catalog(c,True)
        self.assertEqual(len(developer['maps']),len(discover_maps(c)))
        c['scene']['public_map']=False
        hidden=preview_catalog(c)
        self.assertIsNone(hidden['current']);self.assertEqual(hidden['maps'],[])
        self.assertIsNone(hidden['override_path'])
        c['scene']['public_map']=True
        c['campaign']['levels']['c0']['permissions']['visualization']['allowed_layers'].remove('map')
        self.assertIsNone(preview_catalog(c)['current'])
        self.assertIsNotNone(preview_catalog(c,True)['current'])

    def test_native_retry_preview_and_practice_progress(self):
        config=set_override(configure(self.base,'c0'),'open_large');config['host']['port']=0
        state=self.state();authority=Authority(config,controlled=True)
        server=LocalServer(authority,workspace_store=self.directory/'workspace',application=state)
        thread=threading.Thread(target=server.http.serve_forever,daemon=True);thread.start()
        try:
            port=server.http.server_port
            status,raw=self.get(port,'/api/maps');self.assertEqual(status,200)
            self.assertEqual(json.loads(raw)['current']['walls'],config['scene']['walls'])
            self.assertEqual(self.get(port,'/map-preview.js')[0],404)
            self.assertEqual(self.get(port,'/assets/maps/navigation_slalom.yaml')[0],404)
            with patch('tankbot_host.maps.preview_catalog',side_effect=ValueError('地图资产无效')):
                status,raw=self.get(port,'/api/maps')
                self.assertEqual(status,400);self.assertEqual(json.loads(raw)['error'],'地图资产无效')
            first=server.authority.run_id
            server.authority.campaign.status='passed';server.save_progress()
            self.assertEqual(state.progress()['completed_levels'],[])
            server.start_level('c0')
            self.assertNotEqual(first,server.authority.run_id)
            self.assertEqual(server.authority.config['map_override'],config['map_override'])
            self.assertEqual(server.authority.config['scene']['walls'],config['scene']['walls'])
            server.authority.campaign.status='passed';server.save_progress()
            self.assertEqual(state.progress()['completed_levels'],[])
            # A normal attempt still awards progress; practice is bound to the ticket.
            state.complete(state.register_attempt('c0'),'c0')
            self.assertEqual(state.progress()['completed_levels'],['c0'])
        finally:
            server.http.shutdown();thread.join(timeout=5);server.http.server_close();server.authority.close()



if __name__=='__main__':unittest.main()
