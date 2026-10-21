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
    def __init__(self, authority):
        self.authority = authority
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.token = secrets.token_urlsafe()
        config = authority.config
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
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if not self.valid_host():
                    self.reply(403, b'{}')
                    return
                path = urlsplit(self.path).path
                if path in ("/api/profile", "/api/view"):
                    with owner.lock:
                        if path == "/api/profile":
                            value = owner.authority.public_profile()
                            value["control_token"] = owner.token
                        else:
                            value = copy.deepcopy(owner.authority.view)
                    self.reply(200, json.dumps(value, allow_nan=False).encode())
                elif path in ("/", "/index.html", "/app.js", "/style.css"):
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
                if self.path not in ("/api/cmd_vel", "/api/turret_cmd_vel", "/api/fire"):
                    self.reply(404, b'{}')
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if self.headers.get("Content-Type") != "application/json" or not 0 < size <= config["runtime"]["max_message_bytes"]:
                        raise ValueError("Invalid frame size/type")
                    self.connection.settimeout(config["runtime"]["startup_timeout_s"])
                    value = strict_loads(self.rfile.read(size))
                    with owner.lock:
                        if self.path == "/api/cmd_vel":
                            owner.authority.keyboard(value)
                            result = {"accepted": True}
                        elif self.path == "/api/turret_cmd_vel":
                            owner.authority.turret_keyboard(value)
                            result = {"accepted": True}
                        else:
                            result = owner.authority.fire_keyboard(value)
                    self.reply(200, json.dumps(result).encode())
                except (ValueError, Rejected, RecursionError):
                    self.reply(400, b'{"accepted":false}')

        self.http = ThreadingHTTPServer((config["host"]["bind"], config["host"]["port"]), Handler)
        self.http.daemon_threads = True
        self.thread = threading.Thread(target=self._simulate, daemon=True)

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
                deadline += 1/self.authority.hz
                catchup += 1
            if time.monotonic() >= deadline:
                with self.lock:
                    self.authority.audit.append({"event": "host_overrun", "tick": self.authority.tick})
                deadline = time.monotonic()+1/self.authority.hz

    def serve(self):
        self.thread.start()
        host, port = self.http.server_address
        print(f"TankBot M1: http://{host}:{port}  [trusted local code only]", flush=True)
        try:
            self.http.serve_forever()
        finally:
            self.stopped.set()
            self.thread.join(timeout=5)
            self.http.server_close()

