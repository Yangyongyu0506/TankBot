"""External watchdog: no player code is executed on the authority thread."""
import os
from collections import deque
from pathlib import Path
import subprocess
import sys
import threading
import time
from tankbot_protocol.wire import send, receive

ROOT = Path(__file__).resolve().parents[2]


class Supervisor:
    def __init__(self, config, init):
        self.limit = config["runtime"]["max_message_bytes"]
        self.budget = config["runtime"]["batch_budget_ms"] / 1000
        self.condition = threading.Condition()
        self.active = None
        self.result = None
        self.expires = None
        self.closed = False
        self.fault = None
        self.batch_times_ms = deque(maxlen=config["runtime"]["history_limit_ticks"])
        self.proc = subprocess.Popen([sys.executable, "-I", str(ROOT / "runtime/worker.py"), str(self.limit)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     cwd=init["workspace"], start_new_session=(os.name == "posix"))
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.watchdog = threading.Thread(target=self._watch, daemon=True)
        self.reader.start()
        send(self.proc.stdin, init, self.limit)
        deadline = time.monotonic() + config["runtime"]["startup_timeout_s"]
        with self.condition:
            while self.result is None and not self.fault:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    self.fault = "RESOURCE_LIMIT"
                    break
                self.condition.wait(remaining)
            ready, self.result = self.result, None
        if self.fault or not ready or ready[0] != {"ready": True}:
            self.close()
            raise RuntimeError("Worker initialization failed")
        self.watchdog.start()

    def _read(self):
        try:
            while True:
                value = receive(self.proc.stdout, self.limit)
                received = time.monotonic()
                with self.condition:
                    if self.closed:
                        return
                    if self.result is not None:
                        self.fault = "RESOURCE_LIMIT"
                        self._kill()
                        return
                    self.result = (value, received)
                    self.condition.notify_all()
        except (EOFError, ValueError, OSError, RecursionError):
            with self.condition:
                if not self.closed:
                    self.fault = self.fault or "MODULE_ERROR"
                    self.condition.notify_all()

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
                remaining = self.expires-time.monotonic()
                if remaining > 0:
                    self.condition.wait(remaining)
                else:
                    self.fault = "RESOURCE_LIMIT"
                    self._kill()
                    self.condition.notify_all()
                    return

    def submit(self, request):
        with self.condition:
            if self.fault or self.active is not None:
                return False
            self.started = time.monotonic()
            self.active = request["request_id"]
            self.expires = self.started+self.budget
            self.result = None
            send(self.proc.stdin, request, self.limit)
            self.condition.notify_all()
            return True

    def finish(self, *, controlled=False):
        """Called at the fixed commit gate. Only controlled tests may wait, bounded by budget."""
        with self.condition:
            if controlled:
                while self.result is None and not self.fault and self.expires is not None:
                    remaining = self.expires-time.monotonic()
                    if remaining <= 0:
                        break
                    self.condition.wait(remaining)
            result = self.result
            if self.fault or result is None or result[1] > self.expires:
                self.fault = self.fault or "MISSED_DEADLINE"
                self._kill()
                self.active = None
                self.condition.notify_all()
                return None
            self.batch_times_ms.append((result[1]-self.started)*1000)
            self.result, self.active = None, None
            self.condition.notify_all()
            return result[0]

    def close(self):
        with self.condition:
            self.closed = True
            self._kill()
            self.condition.notify_all()
        self.proc.wait(timeout=5)
        self.proc.stdin.close()
        self.proc.stdout.close()
        if self.reader.is_alive():
            self.reader.join(timeout=1)
        if self.watchdog.is_alive():
            self.watchdog.join(timeout=1)
