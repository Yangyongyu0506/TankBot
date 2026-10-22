"""Two-origin, fixed-resource local browser launcher. No Python game execution on the server."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import urlsplit
from .authority import ROOT


class BrowserServer:
    def __init__(self, config, workspace=None):
        self.config = config
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
        workspace=Path(workspace or ROOT/"examples/robot").resolve()
        # Only Python sources, no symlink traversal, secrets or arbitrary repository reads.
        sources={str(p.relative_to(workspace)):p.read_text() for p in workspace.rglob("*.py")
                 if not p.is_symlink() and p.resolve().is_relative_to(workspace) and not any(x.startswith(".") for x in p.relative_to(workspace).parts)}
        if not sources or sum(len(v.encode()) for v in sources.values())>config["runtime"]["max_message_bytes"]:
            raise ValueError("M2 deployment snapshot empty or exceeds frame limit")
        meta=json.loads((ROOT/"config/browser-assets.lock.json").read_text())
        runtime_files={"/"+name:ROOT/"web"/name for name in ("runtime-frame.html","runtime-frame.js","robot-worker.js","python-bootstrap.js")}
        runtime_files["/player-bundle.json"]=assets/"player-bundle.json"
        shared={"/pyodide/"+name:assets/"pyodide"/name for name in meta["files"]}
        runtime_files.update(shared)
        ui_files={"/"+name:ROOT/"web"/name for name in ("index.html","app.js","style.css","rendering.js","browser-client.js","core-worker.js","wasm-core.js","python-loader.js","python-bootstrap.js")}
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
                def do_GET(self):
                    port=self.server.server_port
                    if self.headers.get("Host")!=f"127.0.0.1:{port}":
                        self.send_error(403);return
                    path=urlsplit(self.path).path
                    if not runtime and path in ui_json:
                        raw=json.dumps(ui_json[path],allow_nan=False).encode();kind="application/json"
                    elif path in files:
                        file=files[path];raw=file.read_bytes()
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
                    self.send_header("Content-Security-Policy",f"default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; connect-src 'self'; worker-src {worker_src}; frame-src {frame_src}; frame-ancestors {ancestors}; base-uri 'none'; form-action 'none'; object-src 'none'")
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
