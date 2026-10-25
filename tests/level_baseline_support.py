"""Observable pre-refactoring projections; capture before changing the level system."""
import copy
from tankbot_host.authority import Authority
from tankbot_host.campaign import CampaignSession, RadarSimulator, configure
from tankbot_host.learning import learning_bundle
from tankbot_host.workspace import starter


def projection(base, level_id):
    config = configure(base,level_id)
    a = Authority(config,controlled=True)
    try:
        profile = a.public_profile()
        profile.pop("run_id")
        profile.pop("campaign")
        radar = RadarSimulator(config)
        sensor_frames = [radar.sample(a._private,tick) for tick in range(0,600,6)]
        session = CampaignSession(config)
        session.start(0)
        private = copy.deepcopy(a._private)
        private["truth_pose"] = [2.0,1.0,.8]
        private["target_hits"][config["weapons"]["targets"][0]["target_id"]] = 2
        for tick,x,y,yaw in ((6,1.0,2.0,.2),(12,1.5,2.5,-.1),(12,999.,999.,0.)):
            session.estimate({"simulation_tick":tick,"payload":{"x_m":x,"y_m":y,"yaw_rad":yaw}},[-3.,1.5,.4])
        before = session.public()
        normal = session.outcome(private,60)
        private["targets"][0].update(alive=False,hp=0 if session.hp is not None else None)
        killed = session.outcome(private,60)
        private["player_alive"] = False
        tied = session.outcome(private,session.limit_ticks)
        final = session.finish(60,passed=True,reason="objective_completed")
        guide = learning_bundle(config)
        # Functions are API examples; preserve signatures and help text, not wrapper implementation bytes.
        return {"physics":{key:copy.deepcopy(config[key]) for key in ("clock","body","chassis","servo","motion_limits","controller","sensors","scene","weapons","control_sources","view_policy")},
                "initial":copy.deepcopy(a._private),"profile":profile,"radar_frames":sensor_frames,
                "module_contract":copy.deepcopy(a.contract),"inputs":a.input_channels,"outputs":a.output_channels,
                "rules":{"preterminal":before,"normal":normal,"killed":killed,"death_tie":tied,"terminal":final},
                "guide":guide["lesson"],"types":guide["types"],"files":sorted(starter(config)),
                "player_config":copy.deepcopy(a.worker_init["config"])}
    finally:a.close()
