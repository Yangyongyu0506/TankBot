"""Trusted-local CPython transport entry point; NOT an OS security sandbox."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "sdk/python"), str(ROOT / "protocol")]
from module_runner import ModuleRunner, runtime_packages
from source_loader import prepare
from tankbot_protocol.wire import receive, send


def main():
    limit = int(sys.argv[1])
    source, sink = sys.stdin.buffer, sys.stdout.buffer
    init = receive(source, limit)
    temporary = None
    try:
        temporary, tests = prepare(init)
        runner = ModuleRunner(init)
    except Exception as error:
        send(sink, {"ready": False, "error": type(error).__name__ + ": " + str(error)[:256]}, limit)
        if temporary:
            temporary.cleanup()
        return
    send(sink, {"ready": True, "unit_tests": tests, "runtime_packages": runtime_packages()}, limit)
    try:
        while True:
            send(sink, runner.step(receive(source, limit)), limit)
    except EOFError:
        runner.close()
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    main()
