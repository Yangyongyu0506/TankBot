"""Authority-owned self GPS and encoder measurement errors, never actuator models."""
import copy
import json
import random


class GpsSimulator:
    def __init__(self, instance):
        self.parameters = json.loads(instance.parameters_json)

    def reset(self, seed):
        self.random = random.Random(seed)
        self.last_tick = None
        self.cached = None

    def measure(self, private, tick):
        if tick == self.last_tick:
            return copy.deepcopy(self.cached)
        stddev = self.parameters["noise"]["position_stddev_m"]
        self.cached = {"position_m":[value+self.random.gauss(0.,stddev) for value in private["truth_pose"][:2]],
                       "covariance":[stddev*stddev,0.,0.,stddev*stddev]}
        self.last_tick = tick
        return copy.deepcopy(self.cached)


class EncoderMeasurement:
    def __init__(self, instance, physics_hz):
        self.parameters = json.loads(instance.parameters_json)
        self.physics_hz = physics_hz

    def reset(self, seed):
        self.random = random.Random(seed)
        p = self.parameters
        self.gains = [1+self.random.uniform(p["gain_error_min"],p["gain_error_max"]) for _ in range(2)]
        self.noise_angles = [0.,0.]
        self.last_tick = None
        self.cached = None

    def measure(self, private, tick):
        if tick == self.last_tick:
            return copy.deepcopy(self.cached)
        sample = copy.deepcopy(private["sensors"]["joint_states"])
        dt = 0. if self.last_tick is None else (tick-self.last_tick)/self.physics_hz
        for wheel,name in enumerate(("left","right")):
            index = sample["name"].index(name)
            noise = self.random.gauss(0.,self.parameters["velocity_stddev_radps"])
            self.noise_angles[wheel] += noise*dt
            sample["position"][index] = self.gains[wheel]*sample["position"][index]+self.noise_angles[wheel]
            sample["velocity"][index] = self.gains[wheel]*sample["velocity"][index]+noise
        self.last_tick = tick
        self.cached = sample
        return copy.deepcopy(sample)
