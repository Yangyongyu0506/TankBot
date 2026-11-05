"""Runtime-owned JSON costs; previous encode cost is explicitly attributed to its step."""
import json
import time
from tankbot_protocol.wire import encode, strict_loads


class MeasuredExecution:
    def __init__(self,runner):
        self.runner=runner
        self.previous_encode_ms=None
        self.previous_step_id=None

    def run(self,request,decode_ms=0.):
        started=time.perf_counter();response=self.runner.step(request)
        cost=(time.perf_counter()-started)*1000
        transport={'worker_decode_ms':decode_ms,'runtime_python_ms':cost}
        if self.previous_encode_ms is not None:
            transport.update(worker_encode_previous_ms=self.previous_encode_ms,worker_encode_previous_step_id=self.previous_step_id)
        response['payload'].setdefault('telemetry',{'modules':[],'diagnostics':[]})['transport']=transport
        return response

    def encoded(self,response,limit=None):
        started=time.perf_counter()
        raw=encode(response,limit) if limit is not None else json.dumps(response,separators=(',',':'),allow_nan=False)
        self.previous_encode_ms=(time.perf_counter()-started)*1000
        self.previous_step_id=response['request_id']
        return raw

    def json_step(self,raw):
        started=time.perf_counter();request=strict_loads(raw);decode_ms=(time.perf_counter()-started)*1000
        return self.encoded(self.run(request,decode_ms))
