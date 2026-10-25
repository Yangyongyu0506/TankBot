"""One robot process, multiple modules. Inputs are frozen by Authority, never locally routed."""
import copy
import contextlib
import sys
from tankbot_protocol.message import envelope


class GraphRunner:
    def __init__(self, init):
        from module_runner import ModuleRunner
        self.init, self.runners, self.sequence = init, {}, 0
        self.reset_done = False
        try:
            for mid in init["graph"]["setup_order"]:
                module = init["graph"]["modules"][mid]
                child = {key:copy.deepcopy(value) for key,value in init.items() if key != "graph"}
                child.update({key:copy.deepcopy(module[key]) for key in ("contract","input_channels","output_channels","publisher_id")})
                child["config"]["module"] = copy.deepcopy(module["config"])
                child["defer_reset"] = True
                self.runners[mid] = ModuleRunner(child)
        except BaseException:
            self.close()
            raise

    def step(self, request):
        if not self.reset_done:
            from tankbot import ModuleContext
            origin = request["payload"]["origin_tick"]
            for mid in self.init["graph"]["setup_order"]:
                runner = self.runners[mid]
                context = ModuleContext(origin,0.0,origin,runner.init["config"])
                with contextlib.redirect_stdout(sys.stderr):
                    runner.module.reset(context,self.init.get("reset_reason","new_run"))
                runner.context = context
            self.reset_done = True
        results, outputs = [], []
        for call in request["payload"]["modules"]:
            mid = call["module_id"]
            child = copy.deepcopy(request)
            child["payload"]["modules"] = [call]
            result = self.runners[mid].step(child)["payload"]
            results.extend(result["results"])
            outputs.extend(result["outputs"])
        tick = request["payload"]["activation_tick"]
        response = envelope("runtime_step_result@1","/runtime/step",{
            "step_id":request["request_id"],"results":results,"outputs":outputs},tick=tick,
            hz=self.init["physics_hz"],run_id=self.init["run_id"],publisher_id="runtime",sequence=self.sequence,
            message_type="service_response",request_id=request["request_id"])
        self.sequence += 1
        return response

    def close(self):
        for mid in reversed(self.init["graph"]["setup_order"]):
            if mid in self.runners:
                try:
                    self.runners[mid].close()
                except Exception:
                    import traceback
                    traceback.print_exc(file=sys.stderr)
