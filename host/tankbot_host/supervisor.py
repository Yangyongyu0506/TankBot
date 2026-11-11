"""External watchdog: no player code is executed on the authority thread."""
import os
from collections import deque
from pathlib import Path
import subprocess
import sys
import threading
import time
import copy
import tempfile
import codecs
from .logs import RuntimeLogs
from tankbot_protocol.wire import receive, encode
from .execution_profiles import select_execution_profile

ROOT = Path(__file__).resolve().parents[2]


class Supervisor:
    runtime_backend = "native"

    def __init__(self, config, init, *, deferred=False, execution_profile=None):
        self.execution_profile = execution_profile or select_execution_profile(config, self.runtime_backend)
        if self.execution_profile.backend != self.runtime_backend:
            raise ValueError("RUNTIME_PROFILE_BACKEND")
        init = copy.deepcopy(init)
        self.preparation = copy.deepcopy(init.get("preparation"))
        self.task_pending = False
        self.task_elapsed_ms = None
        self.initialization_budget_ns = round(config["runtime"]["startup_timeout_s"]*1_000_000_000)
        self.workspace_temp = None
        if "sources" in init:
            from .workspace import validate_files
            sources = init.pop("sources")
            validate_files(sources, config["workspace"])
            self.workspace_temp = tempfile.TemporaryDirectory(prefix="tankbot-deployment-")
            for relative, source in sources.items():
                path = Path(self.workspace_temp.name) / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
            init["workspace"] = self.workspace_temp.name
        self.limit = config["runtime"]["max_message_bytes"]
        self.logs = RuntimeLogs(config["runtime"]["max_log_bytes"])
        self.workspace_path = init["workspace"]
        self.budget = self.execution_profile.batch_wall_deadline_ms / 1000
        self.budget_ns = self.execution_profile.wall_deadline_ns
        from .runtime_timing import RuntimeTiming
        self.timing = RuntimeTiming(self.execution_profile.batch_wall_deadline_ms, self.runtime_backend,
                                    profile=self.execution_profile.public())
        self.condition = threading.Condition()
        self.active = None
        self.result = None
        self.expires_ns = None
        self.outgoing = None
        self.closed = False
        self.fault = None
        self.ready = False
        self.startup_result = None
        self.detail = None
        self.batch_times_ms = deque(maxlen=config["runtime"]["history_limit_ticks"])
        self.proc = subprocess.Popen([sys.executable, "-I", str(ROOT / "runtime/worker.py"), str(self.limit)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     cwd=init["workspace"], start_new_session=(os.name == "posix"))
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.log_reader = threading.Thread(target=self._read_logs, daemon=True)
        self.watchdog = threading.Thread(target=self._watch, daemon=True)
        self.writer = threading.Thread(target=self._write, daemon=True)
        self.reader.start()
        self.log_reader.start()
        self.outgoing = (None, encode(init, self.limit), time.monotonic_ns())
        self.writer.start()
        deadline = time.monotonic_ns() + round(config["runtime"]["startup_timeout_s"]*1_000_000_000)
        self.startup_deadline_ns = deadline
        if deferred:
            self.watchdog.start()
            return
        with self.condition:
            while self.result is None and not self.fault:
                remaining = (deadline-time.monotonic_ns())/1_000_000_000
                if remaining <= 0:
                    self.fault = "RESOURCE_LIMIT"
                    break
                self.condition.wait(remaining)
            ready, self.result = self.result, None
        if self.fault or not ready or ready[0].get("ready") is not True:
            self.close()
            raise RuntimeError("Worker initialization failed" + (": " + self.detail if self.detail else ""))
        self.ready = True
        self.startup_result = ready[0]
        self.watchdog.start()

    def poll_ready(self):
        with self.condition:
            if self.ready or self.fault:
                return self.ready
            if self.result is not None:
                value, received = self.result
                self.result = None
                if value.get("ready") is True and received <= self.startup_deadline_ns:
                    self.ready = True
                    self.startup_result = value
                else:
                    self.fault = "MODULE_ERROR"
                    self.detail = str(value.get("error", "Startup handshake rejected"))[:256]
            elif time.monotonic_ns() > self.startup_deadline_ns:
                self.fault = "RESOURCE_LIMIT"
            if self.fault:
                self._kill()
            return self.ready

    def _read(self):
        try:
            while True:
                decode = {}
                value = receive(self.proc.stdout, self.limit, timing=decode)
                decoded_at = time.monotonic_ns()
                with self.condition:
                    if self.closed:
                        return
                    received = time.monotonic_ns()
                    decode['response_delivery_ms']=(received-decoded_at)/1_000_000
                    if isinstance(value, dict) and value.get("ready") is False:
                        self.detail = str(value.get("error", "Startup failed"))[:256]
                        self.fault = "MODULE_ERROR"
                        self.condition.notify_all()
                        return
                    if self.fault:
                        return
                    if self.result is not None or (self.ready and self.active is None):
                        self.fault = "RESOURCE_LIMIT"
                        self.timing.finish(self.fault, "duplicate_or_unsolicited_response")
                        self._kill()
                        self.condition.notify_all()
                        return
                    if not self.task_pending:
                        self.timing.received(value, received_ns=received, **decode)
                    if self.active is not None and received > self.expires_ns:
                        self.fault = "RESOURCE_LIMIT"
                        decode_started=decode.get("response_decode_started_monotonic_ns")
                        location = "response_decode_deadline" if type(decode_started) is int and decode_started<=self.expires_ns else "wall_deadline"
                        self.timing.finish(self.fault, location)
                        self._kill()
                        self.condition.notify_all()
                        return
                    self.result = (value, received)
                    self.condition.notify_all()
        except (EOFError, ValueError, OSError, RecursionError):
            with self.condition:
                if not self.closed:
                    self.fault = self.fault or "MODULE_ERROR"
                    self.timing.finish(self.fault,"response_decode_or_transport")
                    self.condition.notify_all()

    def _write(self):
        """One bounded frame at a time; pipe backpressure never waits on the physics thread."""
        try:
            while True:
                with self.condition:
                    while self.outgoing is None and not self.closed and not self.fault:
                        self.condition.wait()
                    if self.closed or self.fault:return
                    (step_id, raw, encoded_at), self.outgoing = self.outgoing, None
                writing = time.monotonic_ns()
                self.proc.stdin.write(raw)
                self.proc.stdin.flush()
                written = time.monotonic_ns()
                with self.condition:
                    if step_id is not None:
                        self.timing.sent(step_id=step_id,request_queue_ms=(writing-encoded_at)/1_000_000,
                                         request_write_ms=(written-writing)/1_000_000)
                    self.condition.notify_all()
        except (ValueError, OSError):
            with self.condition:
                if not self.closed:
                    self.fault=self.fault or "MODULE_ERROR"
                    self.timing.finish(self.fault,"request_transport")
                    self._kill()
                    self.condition.notify_all()

    def _read_logs(self):
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        pending = ""
        def emit(text):
            self.logs.append(text.replace(str(self.workspace_path).rstrip("/") + "/", "").replace(str(ROOT) + "/", ""), stream="output")
        try:
            while True:
                raw = os.read(self.proc.stderr.fileno(), 4096)
                if not raw:
                    break
                pending += decoder.decode(raw)
                while "\n" in pending:
                    line, pending = pending.split("\n", 1); emit(line + "\n")
                while len(pending) > 2048:
                    emit(pending[:2048]); pending = pending[2048:]
            if pending:
                emit(pending)
        except (ValueError, OSError):
            pass

    def _kill(self):
        if self.proc.poll() is None:
            try:
                if os.name == "posix":
                    import signal
                    os.killpg(self.proc.pid, signal.SIGKILL)
                else:
                    self.proc.kill()
            except ProcessLookupError:
                pass

    def _watch(self):
        with self.condition:
            while not self.closed:
                if self.active is None or self.result is not None:
                    self.condition.wait()
                    continue
                remaining = self.expires_ns-time.monotonic_ns()
                if remaining >= 0:
                    self.condition.wait(remaining/1_000_000_000)
                else:
                    self.fault = "RESOURCE_LIMIT"
                    self.timing.finish(self.fault, "wall_deadline")
                    self._kill()
                    self.condition.notify_all()
                    return

    def submit(self, request):
        return self._submit(request, self.budget_ns, task=False)

    def submit_preparation(self, request):
        """Trusted preparation controller only; no budget field is read from a response."""
        if not self.preparation or request.get("operation") not in ("plan", "initialize"):
            raise ValueError("UNAUTHORIZED_PREPARATION")
        from .execution_profiles import milliseconds_ns
        budget = milliseconds_ns(self.preparation["wall_deadline_ms"]) if request["operation"] == "plan" else self.initialization_budget_ns
        return self._submit(request, budget, task=True)

    def poll_preparation(self):
        # Preparation has no six-tick gate. Poll without making physics await it.
        with self.condition:
            if self.result is None and not self.fault:
                return None
        return self.finish()

    def _submit(self, request, budget_ns, *, task):
        with self.condition:
            if self.closed or self.fault or self.active is not None:
                return False
            self.started_ns = time.monotonic_ns()
            self.active = request["request_id"]
            self.expires_ns = self.started_ns+budget_ns
            self.task_pending = task
            self.result = None
            if not task:
                self.timing.begin(request, started_ns=self.started_ns)
            try:
                encoded = encode(request, self.limit)
            except (ValueError, TypeError, RecursionError):
                self.fault="RESOURCE_LIMIT"
                self.timing.finish(self.fault,"request_encode")
                self._kill()
                self.condition.notify_all()
                return False
            encoded_at = time.monotonic_ns()
            self.timing.sent(request_encode_ms=(encoded_at-self.started_ns)/1_000_000)
            self.outgoing = (self.active, encoded, encoded_at)
            self.condition.notify_all()
            return True

    def finish(self, *, controlled=False):
        """Called at the fixed commit gate. Only controlled tests may wait, bounded by budget."""
        with self.condition:
            if controlled:
                while self.result is None and not self.fault and self.expires_ns is not None:
                    remaining = (self.expires_ns-time.monotonic_ns())/1_000_000_000
                    if remaining <= 0:
                        break
                    self.condition.wait(remaining)
            result = self.result
            if self.fault or result is None or result[1] > self.expires_ns:
                expired = self.expires_ns is not None and time.monotonic_ns()>self.expires_ns
                self.fault = self.fault or ("RESOURCE_LIMIT" if expired else "MISSED_DEADLINE")
                self.timing.finish(self.fault, "commit_gate" if self.fault == "MISSED_DEADLINE" else "wall_deadline",at_gate=True)
                self._kill()
                self.active = None
                self.condition.notify_all()
                return None
            elapsed = (result[1]-self.started_ns)/1_000_000
            if self.task_pending:
                self.task_elapsed_ms = elapsed
            else:
                self.batch_times_ms.append(elapsed)
                self.timing.finish(at_gate=True)
            self.result, self.active = None, None
            self.task_pending = False
            self.condition.notify_all()
            return result[0]

    def close(self):
        with self.condition:
            self.closed = True
            self.timing.finish(self.fault or "CANCELLED", "worker_close")
            self._kill()
            self.condition.notify_all()
        self.proc.wait(timeout=5)
        self.proc.stdin.close()
        self.proc.stdout.close()
        if self.reader.is_alive():
            self.reader.join(timeout=1)
        if self.watchdog.is_alive():
            self.watchdog.join(timeout=1)
        if self.writer.is_alive():
            self.writer.join(timeout=1)
        if self.log_reader.is_alive():
            self.log_reader.join(timeout=1)
        self.proc.stderr.close()
        if self.workspace_temp is not None:
            self.workspace_temp.cleanup()
