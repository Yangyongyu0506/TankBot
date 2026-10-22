"""Real IPC and WebSocket boundaries feed the same production validator as Replay/Test."""
import asyncio
import json
from pathlib import Path
import socket
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"protocol"),str(ROOT/"host"),str(ROOT/".tools/python")]
from tankbot_protocol.transport import MemoryTransport, IpcTransport, WebSocketTransport, ReplayTransport
from tankbot_protocol.conformance import cases, verdict
from tankbot_host.authority import load_config
from websockets.asyncio.server import serve
from websockets.asyncio.client import connect


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_fixtures_through_memory_ipc_websocket_and_replay(self):
        config=load_config(ROOT/"config/m1.json")
        limit=config["runtime"]["max_message_bytes"];capacity=config["browser"]["max_pending_requests"]
        fixtures=cases(ROOT/"docs/examples")
        async def check(tx,rx):
            incoming=rx.receive()
            for case in fixtures:
                self.assertEqual(await tx.send(case["message"]),{"status":"queued"})
                value=await asyncio.wait_for(anext(incoming),2)
                self.assertEqual(value,case["message"])
                self.assertEqual(verdict(case,config,value),case["expected"],case["id"])
        a,b=MemoryTransport.pair(limit,capacity)
        try:await check(a,b)
        finally:await a.close();await b.close()
        left,right=socket.socketpair()
        ar,aw=await asyncio.open_connection(sock=left);br,bw=await asyncio.open_connection(sock=right)
        a,b=IpcTransport(ar,aw,limit,capacity),IpcTransport(br,bw,limit,capacity)
        try:await check(a,b)
        finally:await a.close();await b.close()
        async def echo(ws):
            async for raw in ws:await ws.send(raw)
        async with serve(echo,"127.0.0.1",0,origins=["http://127.0.0.1"],max_size=limit,max_queue=capacity) as server:
            port=server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}",origin="http://127.0.0.1",max_size=limit,max_queue=capacity) as ws:
                adapter=WebSocketTransport(ws,limit,capacity)
                try:await check(adapter,adapter)
                finally:await adapter.close()
        replay=ReplayTransport(asyncio.Queue(capacity),asyncio.Queue(capacity),limit,capacity)
        try:
            incoming=replay.receive()
            for case in fixtures:
                await replay.inject(case["message"])
                self.assertEqual(verdict(case,config,await anext(incoming)),case["expected"])
        finally:await replay.close()

    async def test_bounded_queue_copy_close_and_strict_framing(self):
        with self.assertRaises(ValueError):MemoryTransport(asyncio.Queue(),asyncio.Queue(),128,0)
        a,b=MemoryTransport.pair(128,1)
        try:
            value={"x":[1]}
            self.assertEqual((await a.send(value))["status"],"queued");value["x"].append(2)
            self.assertEqual((await a.send({}))["code"],"RESOURCE_LIMIT")
            self.assertEqual(await anext(b.receive()),{"x":[1]})
            self.assertEqual((await a.send({"x":"a"*129}))["code"],"RESOURCE_LIMIT")
            self.assertEqual((await a.send({"x":float("nan")}))["code"],"RESOURCE_LIMIT")
        finally:await a.close();await b.close()
        self.assertEqual((await a.send({}))["code"],"CLOSED")
        a,b=MemoryTransport.pair(128,2)
        try:
            await b.incoming.put(b'{"a":1,"a":2}')
            with self.assertRaises(ValueError):await anext(b.receive())
        finally:await a.close();await b.close()

    async def test_ipc_rejects_length_before_reading_payload(self):
        left,right=socket.socketpair()
        ar,aw=await asyncio.open_connection(sock=left);br,bw=await asyncio.open_connection(sock=right)
        adapter=IpcTransport(ar,aw,128,1)
        try:
            bw.write((129).to_bytes(4,"big"));await bw.drain()
            with self.assertRaisesRegex(ValueError,"RESOURCE_LIMIT"):
                await asyncio.wait_for(anext(adapter.receive()),1)
        finally:
            await adapter.close();bw.close();await bw.wait_closed()

    async def test_websocket_disconnect_and_binary_fail_closed(self):
        config=load_config(ROOT/"config/m1.json")
        limit=config["runtime"]["max_message_bytes"];capacity=config["browser"]["max_pending_requests"]
        async def binary(ws):await ws.send(b'{}')
        async with serve(binary,"127.0.0.1",0,max_size=limit,max_queue=capacity) as server:
            async with connect(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}",max_size=limit,max_queue=capacity) as ws:
                adapter=WebSocketTransport(ws,limit,capacity)
                try:
                    with self.assertRaises(ValueError):await anext(adapter.receive())
                    self.assertEqual((await adapter.send({}))["code"],"CLOSED")
                finally:await adapter.close()
        async def disconnect(ws):await ws.close()
        async with serve(disconnect,"127.0.0.1",0,max_size=limit,max_queue=capacity) as server:
            async with connect(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}",max_size=limit,max_queue=capacity) as ws:
                from websockets.exceptions import ConnectionClosed
                adapter=WebSocketTransport(ws,limit,capacity)
                try:
                    with self.assertRaises(ConnectionClosed):await anext(adapter.receive())
                    self.assertEqual((await adapter.send({}))["code"],"CLOSED")
                finally:await adapter.close()
