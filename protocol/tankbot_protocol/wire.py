"""Length-prefixed JSON IPC; framing limit is enforced before allocation."""
import json
import math
import struct


def strict_loads(data):
    # Public protocol nesting ceiling, checked before JSON allocation. Ignore brackets in strings.
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 16:
                raise ValueError("RESOURCE_LIMIT")
        elif char in "]}":
            depth -= 1
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("Duplicate JSON key")
            out[k] = v
        return out

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("NON_FINITE")
        return result

    def invalid(value):
        raise ValueError("NON_FINITE")

    return json.loads(text, object_pairs_hook=pairs, parse_float=number, parse_constant=invalid)


def encode(value, limit):
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > limit:
        raise ValueError("RESOURCE_LIMIT")
    return struct.pack("!I", len(raw)) + raw


def read_exact(stream, size):
    chunks = bytearray()
    while len(chunks) < size:
        part = stream.read(size - len(chunks))
        if not part:
            raise EOFError("IPC closed")
        chunks.extend(part)
    return bytes(chunks)


def receive(stream, limit):
    size = struct.unpack("!I", read_exact(stream, 4))[0]
    if size > limit:
        raise ValueError("RESOURCE_LIMIT")
    return strict_loads(read_exact(stream, size))


def send(stream, value, limit):
    stream.write(encode(value, limit))
    stream.flush()
