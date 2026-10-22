"""Minimal Firefox Marionette client shared by local M2 probes (no Selenium dependency)."""
import json
import socket
import time


class Browser:
    def __init__(self, port=2828):
        self.connection=socket.create_connection(("127.0.0.1",port),timeout=60)
        self.stream=self.connection.makefile("rwb",buffering=0)
        self.counter=0
        self.read()
        try:
            self.call("WebDriver:DeleteSession",{})
        except RuntimeError:
            pass
        self.capabilities=self.call("WebDriver:NewSession",{})

    def read(self):
        length=bytearray()
        while True:
            ch=self.stream.read(1)
            if ch==b":":break
            if not ch:raise EOFError("Browser closed")
            length.extend(ch)
        raw=bytearray()
        while len(raw)<int(length):raw.extend(self.stream.read(int(length)-len(raw)))
        return json.loads(raw)

    def call(self,name,params):
        self.counter+=1
        raw=json.dumps([0,self.counter,name,params]).encode()
        self.stream.write(str(len(raw)).encode()+b":"+raw)
        result=self.read()
        if result[2]:raise RuntimeError(result[2])
        return result[3]

    def script(self,code):
        return self.call("WebDriver:ExecuteScript",{"script":code,"args":[],"newSandbox":False,"sandbox":"default"})["value"]

    def until(self,code,timeout=60):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            result=self.script(code)
            if result:return result
            time.sleep(.1)
        raise AssertionError("Browser timeout: "+code+"; state="+str(self.script("return document.body.innerText;")))

    def navigate(self,url):
        self.call("WebDriver:Navigate",{"url":url})

    def close(self):
        self.call("WebDriver:DeleteSession",{})
        self.stream.close();self.connection.close()
