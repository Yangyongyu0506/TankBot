#!/usr/bin/env python3
"""Optional Firefox Marionette smoke test against an already running local M1 host."""
import argparse
import base64
import json
from pathlib import Path
import socket
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weapons", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--marionette-port", type=int, default=2828)
    parser.add_argument("--screenshot", type=Path, default=Path(".m1-cache/browser.png"))
    args = parser.parse_args()
    connection = socket.create_connection(("127.0.0.1", args.marionette_port), timeout=10)
    stream = connection.makefile("rwb", buffering=0)

    def read():
        length = bytearray()
        while True:
            ch = stream.read(1)
            if ch == b":":
                break
            if not ch:
                raise EOFError("Browser closed")
            length.extend(ch)
        size = int(length)
        data = bytearray()
        while len(data) < size:
            data.extend(stream.read(size-len(data)))
        return json.loads(data)

    counter = 0

    def call(name, params):
        nonlocal counter
        counter += 1
        raw = json.dumps([0, counter, name, params]).encode()
        stream.write(str(len(raw)).encode()+b":"+raw)
        result = read()
        if result[2]:
            raise RuntimeError(result[2])
        return result[3]

    def script(code):
        result = call("WebDriver:ExecuteScript", {"script": code, "args": [], "newSandbox": True, "sandbox": "default"})
        return result["value"]

    def until(code):
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            value = script(code)
            if value:
                return value
            time.sleep(.1)
        raise AssertionError("Browser condition timed out: "+code)

    try:
        read()
        try:
            call("WebDriver:DeleteSession", {})
        except RuntimeError:
            pass
        call("WebDriver:NewSession", {})
        call("WebDriver:Navigate", {"url": args.url})
        until("return document.getElementById('connection').textContent.includes('在线');")
        before = float(until("return document.getElementById('x').textContent !== '—' && document.getElementById('x').textContent;"))
        script("window.dispatchEvent(new KeyboardEvent('keydown',{code:'KeyW',bubbles:true})); return true;")
        until(f"return Number(document.getElementById('x').textContent) > {before} + 0.1;")
        script("for(const code of ['KeyW','KeyJ','Space'])window.dispatchEvent(new KeyboardEvent('keyup',{code,bubbles:true})); return true;")
        after = float(script("return document.getElementById('x').textContent;"))
        weapon_check=None
        if args.weapons:
            before_q=script("return document.getElementById('turret').textContent;")
            script("window.dispatchEvent(new KeyboardEvent('keydown',{code:'KeyJ',bubbles:true}));return true;")
            until("return document.getElementById('turret').textContent!=="+json.dumps(before_q)+";")
            script("window.dispatchEvent(new KeyboardEvent('keyup',{code:'KeyJ',bubbles:true}));return true;")
            before_shots=script("return Number(document.getElementById('weapon').textContent.match(/发射 (\\d+)/)[1]);")
            script("window.dispatchEvent(new KeyboardEvent('keydown',{code:'Space',bubbles:true}));return true;")
            until(f"return document.getElementById('weapon').textContent.includes('发射 {before_shots+1}');")
            # Repeated keydown must not generate another shot, even after cooldown.
            for _ in range(5):
                script("window.dispatchEvent(new KeyboardEvent('keydown',{code:'Space',repeat:true,bubbles:true}));return true;")
                time.sleep(.1)
            script("window.dispatchEvent(new KeyboardEvent('keyup',{code:'Space',bubbles:true}));return true;")
            after_shots=script("return Number(document.getElementById('weapon').textContent.match(/发射 (\\d+)/)[1]);")
            assert after_shots==before_shots+1
            weapon_check={"turret":script("return document.getElementById('turret').textContent;"),"single_shot_count":after_shots-before_shots,"view":script("return document.getElementById('mode-label').textContent;")}
        image = call("WebDriver:TakeScreenshot", {"id": None, "full": True, "scroll": False})
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        args.screenshot.write_bytes(base64.b64decode(image["value"]))
        print(json.dumps({"browser": "Firefox", "before_x_m": before, "after_x_m": after, "screenshot": str(args.screenshot), "weapons": weapon_check}))
    finally:
        try:
            script("for(const code of ['KeyW','KeyJ','Space'])window.dispatchEvent(new KeyboardEvent('keyup',{code,bubbles:true})); return true;")
            call("WebDriver:DeleteSession", {})
        except Exception:
            pass
        stream.close()
        connection.close()


if __name__ == "__main__":
    main()
