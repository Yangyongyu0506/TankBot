"""Byte-bounded feedback from the player's own Runtime, never from the private World."""
from collections import deque
import copy
import json
import re
import threading


def python_diagnostic(entries, files):
    """Extract a human summary and a project location; full output stays in bounded logs."""
    text = "".join(entry["text"] for entry in entries if entry.get("stream","output")=="output")
    if "Traceback (most recent call last):" not in text:
        return None
    summaries = [line for line in text.splitlines()
                 if re.match(r"^[A-Za-z_][\w.]*: .", line) and "PLAYER_TEST_FAILED" not in line]
    if not summaries:
        return None
    locations = [(path, int(line)) for path, line in re.findall(r'File "([^"]+\.py)", line ([0-9]+)', text)
                 if path in files]
    result = {"summary": summaries[-1]}
    if locations:
        result.update(path=locations[-1][0], line=locations[-1][1])
    return result


class RuntimeLogs:
    def __init__(self, max_bytes):
        self.limit = max_bytes
        self.entries = deque()
        self.bytes = 0
        self.sequence = 0
        self.dropped = 0
        self.lock = threading.RLock()

    def append(self, text, **metadata):
        if not isinstance(text, str) or not text:
            return
        with self.lock:
            for start in range(0, len(text), 2048):
                entry = {**metadata, "text": text[start:start + 2048], "sequence": self.sequence}
                self.sequence += 1
                size = len(json.dumps(entry, ensure_ascii=False).encode())
                if size > self.limit:
                    self.dropped += 1
                    continue
                self.entries.append((entry, size)); self.bytes += size
                while self.bytes > self.limit or len(self.entries) > 512:
                    _, removed = self.entries.popleft(); self.bytes -= removed; self.dropped += 1

    def public(self):
        with self.lock:
            return {"entries": [copy.deepcopy(entry) for entry, _ in self.entries],
                    "next_sequence": self.sequence, "dropped": self.dropped, "max_bytes": self.limit}

    def drain(self):
        with self.lock:
            result = self.public()
            self.entries.clear(); self.bytes = 0; self.dropped = 0
            return result
