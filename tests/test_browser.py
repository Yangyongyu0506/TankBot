"""Browser deployment boundary and nonblocking supervisor semantics."""
import copy
import http.client
import json
from pathlib import Path
import socket
import sys
import threading
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"host"),str(ROOT/"protocol"),str(ROOT/"runtime")]
from tankbot_host.authority import load_config
from tankbot_host.browser_server import BrowserServer
from browser_authority import BrowserSupervisor


class BrowserTests(unittest.TestCase):
    def test_browser_supervisor_commits_only_buffered_timely_result(self):
        config=load_config(ROOT/"config/m1.json");sent=[]
        with patch.dict(sys.modules,{"js":types.SimpleNamespace(runtime_send=lambda raw:sent.append(json.loads(raw)))}):
            sup=BrowserSupervisor(config,{"workspace":"/workspace"})
            with patch("browser_authority.time.monotonic",return_value=1):
                self.assertTrue(sup.submit({"request_id":"step-6"}))
                sup.receive('{"result":1}',1)
                self.assertEqual(sup.finish(),{"result":1})
                self.assertTrue(sup.submit({"request_id":"step-12"}))
                self.assertIsNone(sup.finish())
                self.assertEqual(sup.fault,"MISSED_DEADLINE")
                self.assertFalse(sup.submit({"request_id":"step-18"}))
            self.assertEqual(sent[-1]["op"],"close")

    def test_browser_supervisor_rejects_duplicate_oversized_and_late_responses(self):
        config=load_config(ROOT/"config/m1.json")
        for raw,elapsed in [('{"x":1,"x":2}',1),('x'*65537,1),('{}',21)]:
            with self.subTest(raw=raw[:20],elapsed=elapsed),patch.dict(sys.modules,{"js":types.SimpleNamespace(runtime_send=lambda raw:None)}):
                sup=BrowserSupervisor(config,{})
                with patch("browser_authority.time.monotonic",return_value=1):
                    sup.submit({"request_id":"step-6"});sup.receive(raw,elapsed)
                    self.assertIsNone(sup.finish());self.assertEqual(sup.fault,"RESOURCE_LIMIT")

    @unittest.skipUnless((ROOT/"build/browser/authority-bundle.json").exists(),"Run tools/prepare_browser.py for launcher HTTP checks")
    def test_runtime_origin_never_serves_authority_workspace_or_private_config(self):
        config=load_config(ROOT/"config/m1.json")
        leases=[]
        try:
            for _ in range(2):
                lease=socket.socket();lease.bind(("127.0.0.1",0));leases.append(lease)
            ports=[lease.getsockname()[1] for lease in leases]
        finally:
            for lease in leases:lease.close()
        config["host"]["port"],config["browser"]["runtime_port"]=ports
        launcher=BrowserServer(config)
        threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (launcher.ui,launcher.runtime)]
        for t in threads:t.start()
        def request(port,path):
            c=http.client.HTTPConnection("127.0.0.1",port,timeout=2);c.request("GET",path)
            response=c.getresponse();status,headers,raw=response.status,dict(response.getheaders()),response.read();c.close()
            return status,headers,raw
        try:
            for path in ("/authority-bundle.json","/authority-config.json","/deployment.json","/api/view","/../config/m1.json","/tankbot_core.wasm"):
                self.assertEqual(request(ports[1],path)[0],404,path)
            status,headers,raw=request(ports[1],"/robot-worker.js")
            self.assertEqual(status,200);self.assertIn("worker-src 'none'",headers["Content-Security-Policy"])
            self.assertIn("connect-src 'self'",headers["Content-Security-Policy"])
            bundle=json.loads(request(ports[1],"/player-bundle.json")[2])
            self.assertFalse(any(p.startswith(("host/","config/","core/","docs/")) for p in bundle))
            self.assertNotIn("protocol/tankbot_protocol/validation.py",bundle)
        finally:
            for s in (launcher.ui,launcher.runtime):s.shutdown();s.server_close()
            for t in threads:t.join(timeout=3)
