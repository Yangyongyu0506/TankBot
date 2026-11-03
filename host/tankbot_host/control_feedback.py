"""Bounded, explicitly authorized control plots from public commands and encoders."""
from collections import deque
import copy


SIGNALS = {
    "command_vx_mps": "m/s", "encoder_vx_mps": "m/s",
    "command_wz_radps": "rad/s", "encoder_wz_radps": "rad/s",
    "left_wheel_radps": "rad/s", "right_wheel_radps": "rad/s",
    "left_voltage_v": "V", "right_voltage_v": "V",
}


class ControlFeedback:
    def __init__(self, config):
        self.config = config
        level = config["campaign"]["levels"][config["campaign"]["active_level"]]
        self.level = level
        self.spec = level["visualization"].get("control_feedback")
        self.points = deque(maxlen=self.spec["history_points"] if self.spec else 0)
        self.voltage = None
        self.last_tick = None

    def command(self, message):
        self.voltage = copy.deepcopy(message)

    def revoke(self):
        self.voltage = None

    def sample(self, tick, sensors, campaign):
        if not self.spec or campaign.started_tick is None or campaign.status != "active":
            return
        elapsed = tick-campaign.started_tick
        if elapsed % self.spec["period_ticks"] or tick == self.last_tick:
            return
        wheels = sensors.get("/robot/sensors/joint_states")
        reference = sensors.get(campaign.sequence["topic"])
        if wheels is None or reference is None or wheels["simulation_tick"] != tick:
            return
        state = wheels["payload"]
        left, right = (state["velocity"][state["name"].index(name)] for name in ("left", "right"))
        radius = self.config["wheels"]["radius_m"]
        track = self.config["wheels"]["differential_track_m"]
        target = reference["payload"]
        volts = [0., 0.]
        if self.voltage and 0 <= (tick-self.voltage["simulation_tick"])/self.config["clock"]["physics_hz"] < self.config["wheel_drive"]["command_timeout_s"]:
            limit = self.config["wheel_drive"]["max_voltage_v"]
            volts = [max(-limit, min(limit, self.voltage["payload"][key])) for key in ("left_voltage_v", "right_voltage_v")]
        values = {"command_vx_mps":target["linear"]["x"], "encoder_vx_mps":radius*(left+right)/2,
                  "command_wz_radps":target["angular"]["z"], "encoder_wz_radps":radius*(right-left)/track,
                  "left_wheel_radps":left, "right_wheel_radps":right,
                  "left_voltage_v":volts[0], "right_voltage_v":volts[1]}
        self.points.append({"simulation_tick": tick, "elapsed_ticks": elapsed,
                            **campaign.sequence_phase(tick), "values": values})
        self.last_tick = tick

    def public(self, after_tick=None):
        if not self.spec:
            return None
        allowed = set(self.level["permissions"]["visualization"].get("allowed_control_signals", []))
        return {"complete":after_tick is None,"points": [{**{k: v for k, v in point.items() if k != "values"},
                            "values": {k: v for k, v in point["values"].items() if k in allowed}}
                           for point in self.points if after_tick is None or point["simulation_tick"]>after_tick]}
