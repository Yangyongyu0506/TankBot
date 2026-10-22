"""Trusted-local CPython transport entry point; NOT an OS security sandbox."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "sdk/python"), str(ROOT / "protocol")]
from module_runner import ModuleRunner
from tankbot_protocol.wire import receive, send


def main():
    limit = int(sys.argv[1])
    source, sink = sys.stdin.buffer, sys.stdout.buffer
    runner = ModuleRunner(receive(source, limit))
    send(sink, {"ready": True}, limit)
    try:
        while True:
            send(sink, runner.step(receive(source, limit)), limit)
    except EOFError:
        runner.close()


if __name__ == "__main__":
    main()
