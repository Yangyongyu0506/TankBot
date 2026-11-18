extends RefCounted
## Interpolate authorized samples; never extrapolate, simulate or recover hidden poses.
var frames: Array = []
var poses: Array = []
var turrets: Array = []
var latest: Dictionary = {}
var context: String = ""
var received_ms: float = 0.0
var render_ms: float = -INF
var hz: float
var options: Dictionary
var jump_m: float

func configure(profile: Dictionary) -> void:
	hz = float(profile.physics_hz)
	options = profile.rendering
	jump_m = float(profile.view.interpolation_jump_m)
	clear()

func clear() -> void:
	frames.clear()
	poses.clear()
	turrets.clear()
	latest = {}
	context = ""
	render_ms = -INF

func put(samples: Array, time: float, value: Variant) -> void:
	if not samples.is_empty() and time == samples[-1].time:
		samples[-1] = {"time": time, "value": value}
	elif samples.is_empty() or time > samples[-1].time:
		samples.append({"time": time, "value": value})

func push(message: Dictionary, now_ms: float) -> bool:
	if not latest.is_empty() and message.run_id == latest.run_id:
		if message.sequence_number <= latest.sequence_number or message.simulation_tick < latest.simulation_tick or message.payload.view_revision < latest.payload.view_revision:
			return false
	var selected = message.payload.selected_pose
	var key = str([message.run_id, message.payload.view_revision, selected.get("source_id") if selected else null, selected.get("frame_id") if selected else null])
	var reset_camera = not latest.is_empty() and (latest.run_id != message.run_id or latest.payload.view_revision != message.payload.view_revision or (selected and latest.payload.selected_pose and context != key))
	if context != key:
		clear()
	context = key
	latest = message.duplicate(true)
	received_ms = now_ms
	var time = float(message.simulation_tick) * 1000.0 / hz
	put(frames, time, message.payload)
	if selected:
		if not poses.is_empty() and Vector2(selected.pose.x_m - poses[-1].value.x_m, selected.pose.y_m - poses[-1].value.y_m).length() > jump_m:
			poses.clear()
		put(poses, float(selected.simulation_tick) * 1000.0 / hz, selected.pose)
	for observation in message.payload.local_observations:
		if observation.channel == "/robot/turret/joint_states":
			put(turrets, float(observation.simulation_tick) * 1000.0 / hz, observation.payload.position[0])
	for samples in [frames, poses, turrets]:
		while samples.size() > 2 and samples[1].time < time - float(options.history_ms):
			samples.pop_front()
	return reset_camera

func bracket(samples: Array, time: float) -> Array:
	if samples.is_empty():
		return []
	if time <= samples[0].time:
		return [samples[0].value, samples[0].value, 0.0]
	for i in range(1, samples.size()):
		if time < samples[i].time:
			return [samples[i-1].value, samples[i].value, (time - samples[i-1].time) / (samples[i].time - samples[i-1].time)]
	return [samples[-1].value, samples[-1].value, 0.0]

func pose_between(a: Dictionary, b: Dictionary, t: float) -> Dictionary:
	return {"x_m": lerp(float(a.x_m), float(b.x_m), t), "y_m": lerp(float(a.y_m), float(b.y_m), t), "yaw_rad": lerp_angle(float(a.yaw_rad), float(b.yaw_rad), t)}

func sample(now_ms: float) -> Dictionary:
	if latest.is_empty():
		return {"pose": null, "objects": [], "turret": 0.0}
	var selected = latest.payload.selected_pose
	var delay = float(options.estimate_interpolation_delay_ms) if (selected and selected.source_id != "system") or not latest.payload.get("target_estimates", []).is_empty() else float(options.interpolation_delay_ms)
	var newest = float(latest.simulation_tick) * 1000.0 / hz
	render_ms = min(newest, max(render_ms, min(newest, newest + max(0.0, now_ms - received_ms) - delay)))
	var pair = bracket(frames, render_ms)
	var objects: Array = []
	for item in pair[0].objects:
		var obj = item.duplicate(true)
		for next in pair[1].objects:
			if obj.kind != next.kind or obj.get("projectile_id", obj.get("target_id")) != next.get("projectile_id", next.get("target_id")):
				continue
			if obj.kind == "projectile":
				obj.x_m = lerp(float(obj.x_m), float(next.x_m), pair[2])
				obj.y_m = lerp(float(obj.y_m), float(next.y_m), pair[2])
			else:
				obj.pose = pose_between(obj.pose, next.pose, pair[2])
		objects.append(obj)
	var pose_pair = bracket(poses, render_ms)
	var turret_pair = bracket(turrets, render_ms)
	return {"pose": pose_between(pose_pair[0], pose_pair[1], pose_pair[2]) if selected and not pose_pair.is_empty() else null,
		"objects": objects, "turret": lerp(float(turret_pair[0]), float(turret_pair[1]), turret_pair[2]) if not turret_pair.is_empty() else 0.0}
