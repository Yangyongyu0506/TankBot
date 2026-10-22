"""Executable fixture verdicts, shared unchanged by CPython and trusted Pyodide Authority."""
import copy
from pathlib import Path
from .wire import strict_loads
from .validation import Validator, Rejected

DOMAIN = {"asymmetric-covariance","indefinite-covariance","wrong-time-formula","wrong-run",
          "ungranted-publisher","forbidden-frame","differential-cannot-strafe",
          "velocity-expired-at-controller","future-velocity-stamp","old-target-cannot-replace-newer"}


def cases(root):
    root=Path(root)
    result=[]
    for path in sorted(root.glob("*.json")):
        value=strict_loads(path.read_bytes())
        if "message_type" in value:
            result.append({"id":path.stem,"message":value,"expected":"accepted","structure_only":True})
    for case in strict_loads((root/"validation-cases.json").read_bytes())["cases"]:
        message=strict_loads((root/case["fixture"]).read_bytes())
        if "message_type" not in message or (case["layer"]!="schema" and case["case_id"] not in DOMAIN):continue
        grant=[message[k] for k in ("publisher_id","channel","schema","frame_id")]
        for mutation in case.get("mutations",[case.get("mutation")]):
            if not mutation:continue
            keys=mutation["pointer"].strip("/").split("/")
            target=message
            for key in keys[:-1]:target=target[int(key)] if isinstance(target,list) else target[key]
            target[int(keys[-1]) if isinstance(target,list) else keys[-1]]=mutation["value"]
        result.append({"id":case["case_id"],"message":message,"grant":grant,"context":case.get("context",{}),
                       "expected":"INVALID_SCHEMA" if case["layer"]=="schema" else case["expected_code"],
                       "structure_only":case["layer"]=="schema"})
    return result


def verdict(case, config, message=None):
    # This named fixture explicitly describes a differential controller, irrespective of UI chassis.
    if case["id"]=="differential-cannot-strafe":
        config=copy.deepcopy(config)
        config["scene"]["default_chassis"]="differential"
    validator=Validator(config,"run-demo-001")
    try:
        msg=case["message"] if message is None else message
        if case["structure_only"]:validator.structure(msg)
        else:
            context=case["context"];grant=tuple(case["grant"])
            if "last_target_tick" in context:
                validator.target_ticks[grant]=context["last_target_tick"]
                validator.sequences[grant]=context["last_sequence_number"]
            validator.validate(msg,now=context.get("controller_tick",126),grants={grant})
        return "accepted"
    except Rejected as error:return error.code


def run(root,config):
    return [{"id":case["id"],"verdict":verdict(case,config)} for case in cases(root)]
