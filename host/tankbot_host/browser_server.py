"""Two-origin, fixed-resource local browser launcher. No Python game execution on the server."""
import json
import secrets
from tankbot_protocol.wire import strict_loads
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import urlsplit
from .authority import ROOT


class BrowserServer:
    def __init__(self, config, workspace=None, workspace_store=None):
        self.config = config
        from .workspace_api import WorkspaceAPI
        self.workspace = WorkspaceAPI(config, workspace, workspace_store)
        self.token = secrets.token_urlsafe()
        self.ui_origin = f"http://127.0.0.1:{config['host']['port']}"
        self.runtime_origin = f"http://127.0.0.1:{config['browser']['runtime_port']}"
        if config["host"]["bind"]!="127.0.0.1" or self.ui_origin==self.runtime_origin:
            raise ValueError("Browser launcher requires distinct loopback origins")
        assets=ROOT/"build/browser"
        if not (assets/"authority-bundle.json").is_file():
            raise ValueError("Run tools/prepare_browser.py first")
        wasm=ROOT/"target/wasm32-unknown-unknown/release/tankbot_core.wasm"
        if not wasm.is_file():
            raise ValueError("Run tools/build.py --wasm --release first")
        from .workspace import read_sources
        sources = read_sources(workspace or ROOT/"examples/robot", config["workspace"])
        meta=json.loads((ROOT/"config/browser-assets.lock.json").read_text())
        runtime_files={"/"+name:ROOT/"web"/name for name in ("runtime-frame.html","runtime-frame.js","robot-worker.js","python-bootstrap.js")}
        runtime_files["/player-bundle.json"]=assets/"player-bundle.json"
        shared={"/pyodide/"+name:assets/"pyodide"/name for name in meta["files"]}
        runtime_files.update(shared)
        ui_files={"/"+name:ROOT/"web"/name for name in ("index.html","app.js","style.css","rendering.js","browser-client.js","core-worker.js","wasm-core.js","python-loader.js","python-bootstrap.js","workspace-ui.js")}
        ui_files["/THIRD_PARTY_NOTICES.txt"] = ROOT/"build/web/THIRD_PARTY_NOTICES.txt"
        ui_files["/editor-bundle.js"] = ROOT/"build/web/editor-bundle.js"
        ui_files.update(shared)
        ui_files.update({"/":ROOT/"web/index.html","/tankbot_core.wasm":wasm,"/authority-bundle.json":assets/"authority-bundle.json"})
        ui_json={"/authority-config.json":config,"/deployment.json":sources,
                 "/browser-profile.json":{"runtime_origin":self.runtime_origin,**config["browser"]}}
        owner=self

        def handler(runtime):
            files=runtime_files if runtime else ui_files
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):
                    pass
                def do_POST(self):
                    if runtime or self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}" or self.headers.get("Origin") != owner.ui_origin or self.headers.get("X-TankBot-Control") != owner.token:
                        self.send_error(403); return
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                        if self.headers.get("Content-Type") != "application/json" or not 0 < size <= config["runtime"]["max_message_bytes"] or not self.path.startswith("/api/workspace/"):
                            raise ValueError("INVALID_REQUEST")
                        self.connection.settimeout(config["runtime"]["startup_timeout_s"])
                        value = strict_loads(self.rfile.read(size))
                        result = owner.workspace.post(self.path.rsplit("/", 1)[1], value)
                        status = 200
                    except (ValueError, KeyError, TypeError, OSError, RecursionError) as error:
                        result = {"error": str(error)[:512]}; status = 400
                    raw = json.dumps(result).encode()
                    self.send_response(status); self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store")
                    self.end_headers(); self.wfile.write(raw)
                def do_GET(self):
                    port=self.server.server_port
                    if self.headers.get("Host")!=f"127.0.0.1:{port}":
                        self.send_error(403);return
                    path=urlsplit(self.path).path
                    if not runtime and path == "/api/workspace":
                        value = owner.workspace.get()
                        value["control_token"] = owner.token
                        raw=json.dumps(value).encode();kind="application/json"
                    elif not runtime and path in ui_json:
                        raw=json.dumps(ui_json[path],allow_nan=False).encode();kind="application/json"
                    elif path in files:
                        file=files[path]
                        if not file.is_file():
                            self.send_error(404);return
                        raw=file.read_bytes()
                        kind={".html":"text/html; charset=utf-8",".js":"text/javascript",".mjs":"text/javascript",".css":"text/css",".wasm":"application/wasm",".json":"application/json"}.get(file.suffix,"application/octet-stream")
                    else:
                        self.send_error(404);return
                    self.send_response(200)
                    self.send_header("Content-Type",kind);self.send_header("Content-Length",str(len(raw)))
                    self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff")
                    self.send_header("Cross-Origin-Resource-Policy","same-origin")
                    worker_src="'none'" if runtime and path=="/robot-worker.js" else "'self'"
                    ancestors=owner.ui_origin if runtime else "'none'"
                    frame_src="'none'" if runtime else owner.runtime_origin
                    styles = "'self'" if runtime else "'self' 'unsafe-inline'"
                    self.send_header("Content-Security-Policy",f"default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src {styles}; connect-src 'self'; worker-src {worker_src}; frame-src {frame_src}; frame-ancestors {ancestors}; base-uri 'none'; form-action 'none'; object-src 'none'")
                    self.send_header("Permissions-Policy","camera=(), microphone=(), geolocation=(), usb=(), serial=()")
                    self.end_headers();self.wfile.write(raw)
            return Handler
        self.ui=ThreadingHTTPServer(("127.0.0.1",config["host"]["port"]),handler(False))
        try:
            self.runtime=ThreadingHTTPServer(("127.0.0.1",config["browser"]["runtime_port"]),handler(True))
        except BaseException:
            self.ui.server_close();raise

    def serve(self):
        thread=threading.Thread(target=self.runtime.serve_forever,daemon=True);thread.start()
        print(f"TankBot browser: {self.ui_origin}/?runtime=browser  [local public scenario; no Arena]",flush=True)
        try:
            self.ui.serve_forever()
        finally:
            self.runtime.shutdown();thread.join(timeout=5)
            self.runtime.server_close();self.ui.server_close()
