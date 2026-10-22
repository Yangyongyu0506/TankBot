"""Small bounded JSON adapters. Session/Router still owns all protocol validation.

send() acknowledges enqueue only. A caller must run receive() outside the physics thread.
"""
import asyncio
import json
import struct
from .wire import strict_loads


class Transport:
    def __init__(self, limit, capacity):
        if type(limit) is not int or type(capacity) is not int or min(limit,capacity)<=0:
            raise ValueError("Transport requires positive bounds")
        self.limit=limit
        self.outgoing=asyncio.Queue(capacity)
        self.closed=False
        self.writer=asyncio.create_task(self._write())

    async def send(self, message):
        if self.closed:
            return {"status":"rejected","code":"CLOSED"}
        try:
            raw=json.dumps(message,allow_nan=False,separators=(",",":")).encode()
            if len(raw)>self.limit:
                raise ValueError("RESOURCE_LIMIT")
            strict_loads(raw)  # Same depth/finite rules before enqueue; takes an immutable copy.
            self.outgoing.put_nowait(raw)
        except (ValueError, TypeError, RecursionError, asyncio.QueueFull):
            return {"status":"rejected","code":"RESOURCE_LIMIT"}
        return {"status":"queued"}

    async def _write(self):
        try:
            while True:
                await self._send_raw(await self.outgoing.get())
        except Exception:
            self.closed=True

    async def receive(self):
        try:
            while not self.closed:
                raw=await self._receive_raw()
                if isinstance(raw,str):raw=raw.encode()
                if len(raw)>self.limit:raise ValueError("RESOURCE_LIMIT")
                yield strict_loads(raw)
        except Exception:
            self.closed=True
            self.writer.cancel()
            raise

    async def close(self, reason="closed"):
        self.closed=True
        self.writer.cancel()
        await asyncio.gather(self.writer,return_exceptions=True)
        await self._close()


class MemoryTransport(Transport):
    """In-process/Test transport; no object aliases survive serialization."""
    @classmethod
    def pair(cls,limit,capacity):
        a,b=asyncio.Queue(capacity),asyncio.Queue(capacity)
        return cls(a,b,limit,capacity),cls(b,a,limit,capacity)

    def __init__(self,incoming,peer,limit,capacity):
        self.incoming,self.peer=incoming,peer
        super().__init__(limit,capacity)

    async def _send_raw(self,raw):await self.peer.put(raw)
    async def _receive_raw(self):
        raw=await self.incoming.get()
        if raw is None:raise EOFError("Transport closed")
        return raw
    async def _close(self):
        for queue in (self.incoming,self.peer):
            while not queue.empty():queue.get_nowait()
            queue.put_nowait(None)


class IpcTransport(Transport):
    def __init__(self,reader,stream,limit,capacity):
        self.reader,self.stream=reader,stream
        super().__init__(limit,capacity)

    async def _send_raw(self,raw):
        self.stream.write(struct.pack("!I",len(raw))+raw)
        await self.stream.drain()
    async def _receive_raw(self):
        size=struct.unpack("!I",await self.reader.readexactly(4))[0]
        if size>self.limit:raise ValueError("RESOURCE_LIMIT")
        return await self.reader.readexactly(size)
    async def _close(self):
        self.stream.close()
        await self.stream.wait_closed()


class WebSocketTransport(Transport):
    """Caller binds authenticated role/Origin and configures WS max_size/max_queue first."""
    def __init__(self,socket,limit,capacity):
        self.socket=socket
        super().__init__(limit,capacity)

    async def _send_raw(self,raw):await self.socket.send(raw.decode())
    async def _receive_raw(self):
        raw=await self.socket.recv()
        if not isinstance(raw,str):raise ValueError("JSON text frame required")
        return raw
    async def _close(self):await self.socket.close()


class ReplayTransport(MemoryTransport):
    """Test scheduler injects recorded deliveries at their logical arrival tick, without sleeping."""
    async def inject(self, message):
        raw=json.dumps(message,allow_nan=False,separators=(",",":")).encode()
        if len(raw)>self.limit:raise ValueError("RESOURCE_LIMIT")
        self.incoming.put_nowait(raw)
