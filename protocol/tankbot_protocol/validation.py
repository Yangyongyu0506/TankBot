"""Authority-side structural and semantic validation; no truth-based pose correction."""
from pathlib import Path
import math
from jsonschema import Draft202012Validator, validators
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from .wire import strict_loads

ROOT = Path(__file__).resolve().parents[2]


from .message import envelope


class Rejected(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _discriminated_all_of(validator, clauses, instance, schema):
    """Skip only provably false, else-free schema-tag conditionals.

    Envelope contains one such clause per message type, including recursively
    nested view messages. Keep every other JSON Schema check unchanged.
    """
    for index, clause in enumerate(clauses):
        if isinstance(instance,dict) and 'schema' in instance and isinstance(clause,dict) and set(clause)=={'if','then'}:
            condition=clause['if']
            if isinstance(condition,dict) and set(condition)=={'properties'}:
                properties=condition['properties']
                if isinstance(properties,dict) and set(properties)=={'schema'}:
                    tag=properties['schema']
                    if isinstance(tag,dict) and set(tag)=={'const'} and instance['schema']!=tag['const']:
                        continue
        yield from validator.descend(instance,clause,schema_path=index)


def _scan_primitive_items(validator, item_schema, instance, schema):
    """Equivalent primitive-array check for the two bounded scan arrays only.

    Keep all container/size and semantic checks. Invalid or unfamiliar values
    take the standard path, preserving JSON Schema error locations.
    """
    if schema.get('$comment') == 'tankbot-scan-primitive-array-v1' and type(instance) is list:
        if item_schema == {'type':'boolean'} and all(type(v) is bool for v in instance):
            return
        if item_schema == {'type':'number','minimum':0} and all(type(v) in (int,float) and v >= 0 for v in instance):
            return
    yield from Draft202012Validator.VALIDATORS['items'](validator,item_schema,instance,schema)


_StructuralValidator = validators.extend(Draft202012Validator, {
    'allOf':_discriminated_all_of, 'items':_scan_primitive_items})


class Validator:
    def __init__(self, config, run_id):
        schemas = [strict_loads(p.read_bytes()) for p in (ROOT / "docs/schemas").glob("*.schema.json")]
        # All local resources declare 2020-12. Carry that dialect explicitly so
        # following a recursive $ref does not replace our equivalent dispatch
        # with the library's slower default class. No validation keyword changes.
        def resource(schema):
            if schema.get('$schema') == Draft202012Validator.META_SCHEMA['$id']:
                return Resource.from_contents({k:v for k,v in schema.items() if k!='$schema'},default_specification=DRAFT202012)
            return Resource.from_contents(schema)
        registry = Registry().with_resources((s["$id"], resource(s)) for s in schemas)
        self.schemas = {s["$id"].rsplit("/", 1)[1]: Draft202012Validator(s, registry=registry) for s in schemas}
        # Keep the original schema documents available to configuration loaders.
        envelope_schema=self.schemas['envelope.schema.json'].schema
        self._envelope_validator=_StructuralValidator(resource(envelope_schema).contents,registry=registry)
        self.config, self.run_id, self.sequences, self.target_ticks = config, run_id, {}, {}

    def structure(self, value, schema="envelope.schema.json"):
        # Re-encode recursively to reject NaN/Infinity and unsupported Python objects.
        def finite(v, depth=0):
            if depth > 16:
                raise Rejected("RESOURCE_LIMIT")
            if isinstance(v, float) and not math.isfinite(v):
                raise Rejected("NON_FINITE")
            if isinstance(v, dict):
                for x in v.values():
                    finite(x, depth + 1)
            elif isinstance(v, (list, tuple)):
                for x in v:
                    finite(x, depth + 1)
        finite(value)
        validator=self._envelope_validator if schema=='envelope.schema.json' else self.schemas[schema]
        if not validator.is_valid(value):
            raise Rejected("INVALID_SCHEMA")

    def validate(self, msg, *, now, grants, source_tick=None, consume=True):
        self.structure(msg)
        if msg["run_id"] != self.run_id:
            raise Rejected("WRONG_RUN")
        key = (msg["publisher_id"], msg["channel"], msg["schema"], msg["frame_id"])
        if key not in grants:
            if any(g[:3] == key[:3] for g in grants):
                raise Rejected("INVALID_FRAME")
            raise Rejected("UNAUTHORIZED")
        tick = msg["simulation_tick"]
        if msg["simulation_time_ns"] != tick * 1_000_000_000 // self.config["clock"]["physics_hz"]:
            raise Rejected("INVALID_TIMESTAMP")
        if tick > now or (source_tick is not None and tick > source_tick):
            raise Rejected("INVALID_TIMESTAMP")
        if msg["schema"] in ("pose2d@1", "target_estimate@1", "target_pose_estimate@1", "target_points@1", "target_polar_estimate@1"):
            stale = (now if source_tick is None else source_tick)-tick > self.config["runtime"]["estimate_history_ticks"]
        elif msg["schema"] in ("twist@1", "wheel_voltage@1", "turret_velocity@1", "turret_acceleration@1", "fire_command@1"):
            timeout = self.config["wheel_drive"]["command_timeout_s"] if msg["schema"]=="wheel_voltage@1" else self.config["controller"]["cmd_vel_timeout_s"] if msg["schema"] == "twist@1" else self.config["weapons"]["turret"]["acceleration_control"]["timeout_s"] if msg["schema"] == "turret_acceleration@1" else self.config["weapons"]["turret"]["cmd_vel_timeout_s"]
            stale = (now-tick)/self.config["clock"]["physics_hz"] >= timeout
        else:
            stale = now-tick > self.config["runtime"]["input_max_age_ticks"]
        if stale:
            raise Rejected("STALE_DATA")
        if msg["sequence_number"] <= self.sequences.get(key, -1):
            raise Rejected("OUT_OF_ORDER")
        if msg["schema"] in ("pose2d@1", "target_pose_estimate@1"):
            self.covariance(msg["payload"]["covariance"])
        if msg["schema"] in ("position_fix2d@1", "target_estimate@1", "target_polar_estimate@1") and msg["payload"]["covariance"] is not None:
            a, b, c, d = msg["payload"]["covariance"]
            self.covariance([a, b, 0, c, d, 0, 0, 0, 0])
        if msg["schema"] in ("twist@1", "wheel_voltage@1", "turret_velocity@1", "turret_acceleration@1"):
            if tick < self.target_ticks.get(key, -1):
                raise Rejected("OUT_OF_ORDER")
            if msg["schema"] == "twist@1" and not self.config["chassis"][self.config["scene"]["default_chassis"]]["lateral_actuation"] and msg["payload"]["linear"]["y"] != 0:
                raise Rejected("UNSUPPORTED_MOTION")
        if msg["schema"] == "scan2d@1":
            p = msg["payload"]
            if (len(p["ranges_m"]) != len(p["hit_mask"]) or p["range_min_m"] >= p["range_max_m"]
                    or any(not p["range_min_m"] <= r <= p["range_max_m"] or (not hit and r != p["range_max_m"])
                           for r,hit in zip(p["ranges_m"],p["hit_mask"]))):
                raise Rejected("INVALID_SCAN")
            if p["sample_tick"] != tick:
                raise Rejected("INVALID_TIMESTAMP")
        if msg["schema"] == "joint_state@1":
            p = msg["payload"]
            if any(len(p[k]) not in (0, len(p["name"])) for k in ("velocity", "effort")) or len(p["position"]) != len(p["name"]):
                raise Rejected("INVALID_SCHEMA")
        if consume:
            self.sequences[key] = msg["sequence_number"]
            if msg["schema"] in ("twist@1", "wheel_voltage@1", "turret_velocity@1", "turret_acceleration@1"):
                self.target_ticks[key] = tick

    def covariance(self, values):
        if values is None:
            return
        a = values
        tol = self.config["validation"]["covariance_tolerance"]
        # Scale only to keep arithmetic finite. The acceptance tolerance stays ABSOLUTE.
        scale = max(1.0, max(abs(x) for x in a))
        if any(a[i] < 0 for i in (0,4,8)) or any(abs(a[i]-a[j]) > tol for i,j in ((1,3),(2,6),(5,7))):
            raise Rejected("INVALID_COVARIANCE")
        b = [[(a[3*i+j]/2+a[3*j+i]/2)/scale for j in range(3)] for i in range(3)]
        threshold = tol/scale
        # Symmetric 3x3 Jacobi eigensolver, not determinant tolerances (units differ).
        for _ in range(self.config["validation"]["covariance_max_iterations"]):
            p,q = max(((0,1),(0,2),(1,2)), key=lambda pair: abs(b[pair[0]][pair[1]]))
            off = b[p][q]
            if abs(off) <= threshold/16:
                break
            angle = math.atan2(2*off,b[q][q]-b[p][p])/2
            c,s = math.cos(angle),math.sin(angle)
            pp,qq = b[p][p],b[q][q]
            b[p][p],b[q][q] = c*c*pp-2*s*c*off+s*s*qq,s*s*pp+2*s*c*off+c*c*qq
            b[p][q] = b[q][p] = 0.0
            r = 3-p-q
            rp,rq = b[r][p],b[r][q]
            b[r][p] = b[p][r] = c*rp-s*rq
            b[r][q] = b[q][r] = s*rp+c*rq
        if max(abs(b[i][j]) for i,j in ((0,1),(0,2),(1,2))) > threshold/16 or any(b[i][i]-sum(abs(b[i][j]) for j in range(3) if i!=j) < -threshold for i in range(3)):
            raise Rejected("INVALID_COVARIANCE")
