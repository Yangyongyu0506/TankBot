"""Loopback development server with a narrow, authorized HTTP adapter."""
import copy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit
from tankbot_protocol.wire import strict_loads
from tankbot_protocol.validation import Rejected

ROOT = Path(__file__).resolve().parents[2]


class LocalServer:
    def __init__(self, authority, workspace=None, workspace_store=None, *, application=None):
        self.authority = authority
        self.application = application
        self.saved_runs = set()
        self.save_error = None
        if application and authority.campaign:
            application.register_attempt(authority.campaign.level_id, authority.run_id)
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.token = secrets.token_urlsafe()
        config = authority.config
        from .workspace_api import WorkspaceAPI
        from .deployment import DeploymentManager
        self.workspace = WorkspaceAPI(config, workspace, workspace_store)
        self.campaign_directory = (Path(workspace_store) / "campaign" if workspace_store and not config.get("campaign", {}).get("active_level") else workspace_store)
        authority.deployment = DeploymentManager(authority)
        if config["host"]["bind"] != "127.0.0.1":
            raise ValueError("M1 supports loopback only")
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def valid_host(self):
                port = owner.http.server_port
                return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

            def reply(self, status, raw, content_type="application/json"):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # Navigation can close a polling request after its response was prepared.

            def do_GET(self):
                if not self.valid_host():
                    self.reply(403, b'{}')
                    return
                path = urlsplit(self.path).path
                if path in ("/api/settings", "/api/progress") and owner.application:
                    value = owner.application.public_settings() if path.endswith("settings") else owner.application.progress()
                    if path.endswith("settings"):
                        value["control_token"] = owner.token
                    self.reply(200, json.dumps(value).encode())
                elif path == "/api/developer":
                    with owner.lock:
                        if not owner.application or not owner.application.developer:
                            self.reply(403, b'{"error":"UNAUTHORIZED"}'); return
                        value = owner.authority.developer_snapshot()
                    self.reply(200, json.dumps(value, allow_nan=False).encode())
                elif path == "/api/workspace":
                    value = owner.workspace.get()
                    value["control_token"] = owner.token
                    self.reply(200, json.dumps(value).encode())
                elif path == "/api/campaign":
                    with owner.lock:
                        owner.save_progress()
                        value = owner.authority.campaign_status()
                        value["save_error"] = owner.save_error
                    self.reply(200, json.dumps(value).encode())
                elif path == "/api/deployment":
                    with owner.lock:
                        value = owner.authority.deployment.status()
                    self.reply(200, json.dumps(value).encode())
                elif path in ("/editor-bundle.js", "/THIRD_PARTY_NOTICES.txt"):
                    file = ROOT / "build/web" / path[1:]
                    self.reply(200 if file.exists() else 404, file.read_bytes() if file.exists() else b"", "text/javascript" if path.endswith(".js") else "text/plain; charset=utf-8")
                elif path in ("/api/profile", "/api/view"):
                    with owner.lock:
                        if path == "/api/profile":
                            value = owner.authority.public_profile()
                            value["control_token"] = owner.token
                        else:
                            value = copy.deepcopy(owner.authority.view)
                    self.reply(200, json.dumps(value, allow_nan=False).encode())
                elif path in ("/", "/index.html", "/app.js", "/rendering.js", "/browser-client.js", "/style.css", "/workspace-ui.js", "/campaign-ui.js", "/live-metrics.js", "/learning-ui.js", "/gamepad.js", "/settings-ui.js", "/keyboard.js", "/visualization.js", "/runtime-logs.js", "/robot-graph.js"):
                    file = ROOT / "web" / ("index.html" if path == "/" else path[1:])
                    kind = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}[file.suffix]
                    self.reply(200, file.read_bytes(), kind)
                else:
                    self.reply(404, b'{}')

            def do_POST(self):
                port = owner.http.server_port
                origins = (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
                if not self.valid_host() or self.headers.get("Origin") not in origins or self.headers.get("X-TankBot-Control") != owner.token:
                    self.reply(403, b'{}')
                    return
                if self.path not in ("/api/settings", "/api/cmd_vel", "/api/turret_cmd_vel", "/api/fire", "/api/campaign/start", "/api/campaign/finish", "/api/pose_source") and not self.path.startswith(("/api/workspace/", "/api/deployment/")):
                    self.reply(404, b'{}')
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if self.headers.get("Content-Type") != "application/json" or not 0 < size <= config["runtime"]["max_message_bytes"]:
                        raise ValueError("Invalid frame size/type")
                    self.connection.settimeout(config["runtime"]["startup_timeout_s"])
                    value = strict_loads(self.rfile.read(size))
                    if self.path.startswith("/api/workspace/"):
                        result = owner.workspace.post(self.path.rsplit("/", 1)[1], value)
                        self.reply(200, json.dumps(result).encode())
                        return
                    with owner.lock:
                        if self.path == "/api/settings":
                            if owner.application is None:
                                raise ValueError("SETTINGS_UNAVAILABLE")
                            owner.save_progress()
                            result = owner.application.update_settings(value)
                            if result["mode_changed"]:
                                level = owner.authority.campaign.level_id if owner.authority.campaign else None
                                if not owner.application.developer or level is None:
                                    level = owner.application.progress()["current_level"] or owner.application.levels[0]
                                owner.start_level(level)
                        elif self.path == "/api/campaign/start":
                            if not isinstance(value, dict) or set(value) != {"level_id"}:
                                raise ValueError("INVALID_LEVEL_REQUEST")
                            result = owner.start_level(value["level_id"])
                        elif self.path == "/api/campaign/finish":
                            if value != {}:
                                raise ValueError("INVALID_LEVEL_REQUEST")
                            result = owner.authority.finish_campaign()
                        elif self.path.startswith("/api/deployment/"):
                            operation = self.path.rsplit("/", 1)[1]
                            snapshot = owner.workspace.store.read(value["revision"]) if operation in ("test", "deploy") else None
                            result = owner.authority.deployment.start(operation, snapshot=snapshot, sha256=value.get("sha256"))
                        elif self.path == "/api/pose_source":
                            if not isinstance(value,dict) or set(value)!={"module_id"}:
                                raise ValueError("INVALID_POSE_SOURCE_REQUEST")
                            owner.authority.select_pose_source(value["module_id"])
                            result = {"selected_source":owner.authority.selector.source_id}
                        elif self.path == "/api/cmd_vel":
                            owner.authority.keyboard(value)
                            result = {"accepted": True}
                        elif self.path == "/api/turret_cmd_vel":
                            owner.authority.turret_keyboard(value)
                            result = {"accepted": True}
                        else:
                            result = owner.authority.fire_keyboard(value)
                    self.reply(200, json.dumps(result).encode())
                except (ValueError, Rejected, RecursionError, KeyError, TypeError, OSError) as error:
                    self.reply(400, json.dumps({"accepted": False, "error": str(error)[:512]}).encode())

        self.http = ThreadingHTTPServer((config["host"]["bind"], config["host"]["port"]), Handler)
        self.http.daemon_threads = True
        self.thread = threading.Thread(target=self._simulate, daemon=True)

    def start_level(self, level_id):
        from .authority import Authority
        from .campaign import configure, active, ensure_native_numpy
        from .workspace_api import WorkspaceAPI
        from .deployment import DeploymentManager
        old = self.authority
        if self.application:
            self.application.require_level(level_id)
        ensure_native_numpy()
        config = configure(old.config, level_id)
        candidate = Authority(config, binary=getattr(old.core, "binary", None),
                              developer_mode=bool(self.application and self.application.developer))
        try:
            if active(old.config):
                self.workspace.unlock(config)
            else:
                self.workspace = WorkspaceAPI(config, directory=self.campaign_directory)
            candidate.deployment = DeploymentManager(candidate)
            if self.application:
                self.application.select_level(level_id)
                self.application.register_attempt(level_id, candidate.run_id)
        except BaseException:
            candidate.close()
            raise
        self.authority = candidate
        old.close()
        return candidate.public_profile()

    def save_progress(self):
        a = self.authority
        if self.application and a.campaign and a.campaign.status == "passed" and a.run_id not in self.saved_runs:
            try:
                self.application.complete(a.run_id, a.campaign.level_id)
                self.saved_runs.add(a.run_id)
                self.save_error = None
            except (OSError, ValueError) as error:
                self.save_error = "通关存档失败：" + str(error)

    def _simulate(self):
        deadline = time.monotonic()
        while not self.stopped.is_set():
            now = time.monotonic()
            if now < deadline:
                self.stopped.wait(deadline-now)
                continue
            catchup = 0
            while time.monotonic() >= deadline and catchup < self.authority.config["host"]["max_catchup_ticks"]:
                with self.lock:
                    self.authority.advance()
                    if self.authority.tick % self.authority.hz == 0 or (self.authority.campaign and self.authority.campaign.status == "passed" and not self.save_error):
                        self.save_progress()
                deadline += 1/self.authority.hz
                catchup += 1
            if time.monotonic() >= deadline:
                with self.lock:
                    self.authority.audit.append({"event": "host_overrun", "tick": self.authority.tick})
                deadline = time.monotonic()+1/self.authority.hz

    def serve(self):
        self.thread.start()
        host, port = self.http.server_address
        print(f"TankBot: http://{host}:{port}  [trusted local code only]", flush=True)
        try:
            self.http.serve_forever()
        finally:
            self.stopped.set()
            self.thread.join(timeout=5)
            self.http.server_close()

