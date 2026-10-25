"""Authority-owned graph admission, frozen inputs and module-level output transactions."""
import copy
from tankbot_protocol.validation import Rejected, envelope
from tankbot_protocol.wire import strict_loads


def setup_order(modules):
    remaining = set(modules)
    order = []
    while remaining:
        ready = sorted(mid for mid in remaining if set(modules[mid]["contract"]["dependencies"]) <= set(order))
        if not ready:
            raise ValueError("DEPENDENCY_CYCLE_OR_UNKNOWN_MODULE")
        order.extend(ready)
        remaining.difference_update(ready)
    return order


def inspect_graph(files, manifest, authority):
    a, limits = authority, authority.config["robot_graph"]
    if not 1 <= len(manifest["modules"]) <= limits["max_modules"] or len(manifest["connections"]) > limits["max_connections"]:
        raise ValueError("GRAPH_RESOURCE_LIMIT")
    allowed_inputs = dict(a.graph_inputs())
    allowed_outputs = dict(a.graph_outputs())
    modules = {}
    for item in manifest["modules"]:
        mid = item["module_id"]
        if mid in modules:
            raise ValueError("DUPLICATE_MODULE")
        contract = strict_loads(files[item["contract"]])
        a.validator.structure(contract, "module-contract.schema.json")
        if contract["module_id"] != mid:
            raise ValueError("CONTRACT_MODULE_MISMATCH")
        execution = contract["execution"]
        interval = execution["period_ticks"] if execution["mode"] == "periodic" else execution["min_interval_ticks"]
        if execution["deadline_ticks"] != a.delay or interval < a.delay:
            raise ValueError("UNSUPPORTED_GRAPH_SCHEDULE")
        if execution["mode"] == "event" and not set(execution["trigger_inputs"]) <= contract["inputs"].keys():
            raise ValueError("UNKNOWN_EVENT_INPUT")
        if any(port["schema"] not in limits["schemas"] for port in [*contract["inputs"].values(), *contract["outputs"].values()]):
            raise ValueError("UNSUPPORTED_GRAPH_TYPE")
        if any(port["schema"] == "fire_command@1" for port in contract["inputs"].values()):
            raise ValueError("NON_TOPIC_INPUT: read weapon_state feedback instead of subscribing to fire commands")
        modules[mid] = {"contract":contract,"config":copy.deepcopy(item["config"]),"input_channels":{},"output_channels":{}}
    if sum(m["contract"]["execution"]["budget_ms"] for m in modules.values()) > a.config["runtime"]["batch_budget_ms"]:
        raise ValueError("GRAPH_BUDGET_EXCEEDED")
    order = setup_order(modules)
    if manifest["entry_point"] not in {m["contract"]["entry_point"] for m in modules.values()}:
        raise ValueError("GRAPH_ENTRY_POINT_MISMATCH")
    # Declaration order is irrelevant. Publishers are registered before subscriptions.
    writers = {}
    for connection in manifest["connections"]:
        source, channel = connection["from"], connection["to"]
        if source.startswith("/"):
            continue
        if not channel.startswith("/"):
            raise ValueError("USE_EXPLICIT_TOPIC_CONNECTION")
        mid, port = source.split(".")
        if mid not in modules or port not in modules[mid]["contract"]["outputs"]:
            raise ValueError("UNKNOWN_OUTPUT_PORT")
        schema = modules[mid]["contract"]["outputs"][port]["schema"]
        internal = channel == f"/robot/modules/{mid}/{port}" and schema in limits["internal_schemas"]
        candidate = channel == f"/robot/estimates/{mid}/" + {"pose2d@1":"pose","target_estimate@1":"target","target_pose_estimate@1":"target_pose"}.get(schema, "") and schema in allowed_outputs
        actuator = channel in allowed_outputs and schema == allowed_outputs[channel]
        if not (internal or candidate or actuator):
            raise ValueError("UNAUTHORIZED_GRAPH_OUTPUT")
        if channel in writers or port in modules[mid]["output_channels"]:
            raise ValueError("MULTIPLE_PUBLISHERS_OR_OUTPUT_BINDINGS")
        modules[mid]["output_channels"][port] = channel
        writers[channel] = (mid, schema)
    for connection in manifest["connections"]:
        channel, destination = connection["from"], connection["to"]
        if not channel.startswith("/"):
            continue
        if destination.startswith("/"):
            raise ValueError("INVALID_TOPIC_CONNECTION")
        mid, port = destination.split(".")
        if mid not in modules or port not in modules[mid]["contract"]["inputs"]:
            raise ValueError("UNKNOWN_INPUT_PORT")
        expected = modules[mid]["contract"]["inputs"][port]["schema"]
        schema = writers[channel][1] if channel in writers else allowed_inputs.get(channel)
        if schema is None:
            raise ValueError("UNAUTHORIZED_GRAPH_INPUT")
        if schema != expected:
            raise ValueError("GRAPH_TYPE_MISMATCH")
        if port in modules[mid]["input_channels"]:
            raise ValueError("MULTIPLE_INPUT_BINDINGS")
        modules[mid]["input_channels"][port] = channel
    for module in modules.values():
        if module["input_channels"].keys() != module["contract"]["inputs"].keys() or module["output_channels"].keys() != module["contract"]["outputs"].keys():
            raise ValueError("UNBOUND_GRAPH_PORT")
    source = manifest["pose_source"]
    if source["mode"] == "system":
        if not a.config["view_policy"]["system_pose_allowed"]:
            raise ValueError("UNAUTHORIZED_POSE_SOURCE")
    elif (not a.config["view_policy"]["player_pose_allowed"] or source["module_id"] not in modules or
          not any(channel == f"/robot/estimates/{source['module_id']}/pose" for channel in modules[source["module_id"]]["output_channels"].values())):
        raise ValueError("UNAUTHORIZED_POSE_SOURCE")
    return {"modules":modules,"setup_order":order,"pose_source":copy.deepcopy(source)}


def bind_publishers(graph, deployment_id):
    result = copy.deepcopy(graph)
    for mid, module in result["modules"].items():
        # Bounded publisher IDs independent of the user's module-name length.
        import hashlib
        module["publisher_id"] = "module:" + hashlib.sha256((deployment_id+":"+mid).encode()).hexdigest()[:48]
    return result


class GraphExecution:
    def __init__(self, authority, graph, origin_tick):
        self.a, self.graph, self.origin = authority, graph, origin_tick
        self.cache = {}
        self.last_called = {mid:origin_tick for mid in graph["modules"]}
        self.events = {mid:None for mid in graph["modules"]}
        self.failures = {mid:0 for mid in graph["modules"]}
        self.faults = {}

    def request(self, tick, *, prefix="step"):
        a = self.a
        available = {**a._sensors, **self.cache}
        calls, samples = [], {}
        for mid, module in sorted(self.graph["modules"].items()):
            if mid in self.faults:
                continue
            contract, last = module["contract"], self.last_called[mid]
            execution = contract["execution"]
            inputs = {}
            missing = False
            for port, binding in contract["inputs"].items():
                msg = available.get(module["input_channels"][port])
                if msg is None or not 0 <= tick-msg["simulation_tick"] <= binding["max_age_ticks"]:
                    missing |= binding["required"]
                else:
                    inputs[port] = msg
            if execution["mode"] == "periodic":
                due = tick > self.origin and (tick-self.origin) % execution["period_ticks"] == 0
                token = None
            else:
                token = tuple((p,inputs[p]["publisher_id"],inputs[p]["sequence_number"]) for p in execution["trigger_inputs"] if p in inputs)
                due = bool(token) and token != self.events[mid] and tick-last >= execution["min_interval_ticks"]
            if not due:
                continue
            if missing:
                a.audit.append({"event":"skipped","module_id":mid,"tick":tick,"code":"INPUT_UNAVAILABLE"})
                continue
            calls.append({"module_id":mid,"dt_ticks":tick-last})
            for msg in inputs.values():
                samples[msg["channel"]] = copy.deepcopy(msg)
            # Applied only after the transport accepts this frozen request.
        if not calls:
            return None
        request_id = f"{prefix}-{tick}"
        return envelope("runtime_step_request@1", "/runtime/step", {
            "step_id":request_id,"activation_tick":tick,"origin_tick":self.origin,"output_commit_tick":tick+a.delay,
            "modules":calls,"inputs":[samples[key] for key in sorted(samples)]},
            tick=tick,hz=a.hz,run_id=a.run_id,publisher_id="supervisor",sequence=tick,
            message_type="service_request",request_id=request_id)

    def submitted(self, request):
        p = request["payload"]
        for call in p["modules"]:
            mid = call["module_id"]
            self.last_called[mid] = p["activation_tick"]
            module = self.graph["modules"][mid]
            execution = module["contract"]["execution"]
            if execution["mode"] == "event":
                messages = {m["channel"]:m for m in p["inputs"]}
                self.events[mid] = tuple((port,messages[module["input_channels"][port]]["publisher_id"],messages[module["input_channels"][port]]["sequence_number"])
                                         for port in execution["trigger_inputs"] if module["input_channels"][port] in messages and
                                         0 <= p["activation_tick"]-messages[module["input_channels"][port]]["simulation_tick"] <= module["contract"]["inputs"][port]["max_age_ticks"])

    def check(self, response, request, validator, *, test=False):
        a, tick = self.a, request["payload"]["activation_tick"]
        try:
            outputs = response["payload"]["outputs"]
            if not isinstance(outputs,list) or len(outputs) > a.config["robot_graph"]["max_batch_outputs"]:
                raise Rejected("RESOURCE_LIMIT")
            header = copy.deepcopy(response)
            header["payload"]["outputs"] = []
        except (KeyError,TypeError) as error:
            raise Rejected("INVALID_GRAPH_RESPONSE") from error
        validator.validate(header, now=a.tick, source_tick=tick, grants={("runtime","/runtime/step","runtime_step_result@1",None)})
        p = header["payload"]
        expected = [m["module_id"] for m in request["payload"]["modules"]]
        if response["request_id"] != request["request_id"] or p["step_id"] != request["request_id"] or response["simulation_tick"] != tick or [r["module_id"] for r in p["results"]] != expected:
            raise Rejected("INVALID_GRAPH_RESPONSE")
        publishers = {m["publisher_id"]:mid for mid,m in self.graph["modules"].items()}
        grouped = {mid:[] for mid in expected}
        for message in outputs:
            mid = publishers.get(message.get("publisher_id")) if isinstance(message,dict) else None
            if mid not in grouped:
                raise Rejected("UNAUTHORIZED")
            grouped[mid].append(message)
        accepted = []
        for result in p["results"]:
            mid = result["module_id"]
            module, outputs = self.graph["modules"][mid], grouped[mid]
            old_sequences, old_ticks = dict(validator.sequences), dict(validator.target_ticks)
            try:
                if result["status"] != "completed":
                    raise Rejected(result["error_code"])
                for message in outputs:
                    validator.structure(message)
                if len(outputs) != len({m["channel"] for m in outputs}):
                    raise Rejected("DUPLICATE_OUTPUT")
                grants = {(module["publisher_id"],ch,module["contract"]["outputs"][port]["schema"],frame)
                          for port,ch in module["output_channels"].items()
                          for frame in a.config["robot_graph"]["schemas"][module["contract"]["outputs"][port]["schema"]]}
                for message in outputs:
                    validator.validate(message,now=a.tick,source_tick=tick,grants=grants)
                    if message["schema"] == "fire_command@1" and (message["publisher_id"],message["request_id"]) not in a._fire_journal:
                        limits = a.config["weapons"]["firing"]
                        if len(a._fire_journal)>=limits["request_cache_capacity"] or len(a._fire_pending)>=limits["pending_capacity"]:
                            raise Rejected("RESOURCE_LIMIT")
                accepted.extend((mid,message) for message in outputs)
                self.failures[mid] = 0
            except Rejected as error:
                validator.sequences, validator.target_ticks = old_sequences, old_ticks
                if test:
                    raise ValueError(mid+": "+error.code) from error
                self.failures[mid] += 1
                a.audit.append({"event":"rejected","module_id":mid,"tick":a.tick,"code":error.code})
                a.logs.append(mid+": "+error.code+"\n",source="runtime",module_id=mid,tick=a.tick,stream="error")
                if self.failures[mid] >= a.config["runtime"]["max_failures"]:
                    self.faults[mid] = error.code
                    if any(ch in ("/robot/cmd_vel","/robot/turret/cmd_vel","/robot/turret/cmd_accel","/robot/weapons/cannon/fire") for ch in module["output_channels"].values()):
                        a._revoke_robot = True
        return accepted

    def commit(self, accepted, *, apply=True):
        a = self.a
        for mid, message in accepted:
            old = self.cache.get(message["channel"])
            if old is None or (message["simulation_tick"],message["sequence_number"]) > (old["simulation_tick"],old["sequence_number"]):
                self.cache[message["channel"]] = copy.deepcopy(message)
                if apply:
                    a.accept_graph_output(mid,message,activation_tick=self.last_called[mid])
                elif (self.graph["pose_source"]["mode"] == "player" and mid == self.graph["pose_source"]["module_id"]
                      and message["channel"] == f"/robot/estimates/{mid}/pose"):
                    self.cache["/robot/localization/pose"] = envelope("pose2d@1","/robot/localization/pose",copy.deepcopy(message["payload"]),
                        tick=message["simulation_tick"],hz=a.hz,run_id=a.run_id,publisher_id="pose_selector",sequence=message["sequence_number"],frame_id=message["frame_id"])

    def public(self):
        available = {**self.a._sensors, **self.cache}
        def waiting(module):
            missing = []
            for port,binding in module["contract"]["inputs"].items():
                msg = available.get(module["input_channels"][port])
                if binding["required"] and (msg is None or not 0 <= self.a.tick-msg["simulation_tick"] <= binding["max_age_ticks"]):
                    missing.append(port)
            return missing
        return {"origin_tick":self.origin,"pose_source":self.graph["pose_source"],
                "pose_selection_allowed":self.a.config["view_policy"]["player_pose_allowed"],
                "topics":self.a.gateway.robot_topics(self.cache,self.a.config["robot_graph"]["max_view_topic_bytes"]),
                "modules":[{"module_id":mid,"execution":m["contract"]["execution"],"inputs":m["input_channels"],"outputs":m["output_channels"],
                            "dependencies":m["contract"]["dependencies"],"waiting_inputs":waiting(m),"last_activation_tick":self.last_called[mid],"failures":self.failures[mid],"fault":self.faults.get(mid)} for mid,m in sorted(self.graph["modules"].items())]}
