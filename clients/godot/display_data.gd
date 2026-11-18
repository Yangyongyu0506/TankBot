extends RefCounted
## Bounded authorized history. Exact scan/pose tick matching, no truth projection.
var tools: Dictionary = {}
var profile: Dictionary = {}
var latest: Dictionary = {}
var context: String = ""
var trail: Array = []
var estimates: Dictionary = {}
var gps: Array = []
var scans: Array = []

func configure(value: Dictionary, spec: Dictionary) -> void:
	profile = value
	tools = spec
	clear()

func clear() -> void:
	latest = {}
	context = ""
	trail.clear()
	estimates.clear()
	gps.clear()
	scans.clear()

func put(history: Array, sample: Dictionary, limit: int) -> void:
	var tick = sample.simulation_tick
	if history.is_empty() or tick > history[-1].simulation_tick:
		history.append(sample.duplicate(true))
	elif tick == history[-1].simulation_tick:
		history[-1] = sample.duplicate(true)
	while history.size() > limit:
		history.pop_front()

func accept(view: Dictionary) -> void:
	if not latest.is_empty() and latest.run_id == view.run_id and view.sequence_number <= latest.sequence_number:
		return
	var selected = view.payload.selected_pose
	var identity = str([view.run_id, view.payload.view_revision, selected.get("source_id") if selected else null, selected.get("frame_id") if selected else null])
	if identity != context:
		clear()
	context = identity
	latest = view.duplicate(true)
	var limit = int(tools.history_limit)
	if selected and selected.frame_id == "map":
		if not trail.is_empty():
			var p = trail[-1].pose
			if Vector2(p.x_m - selected.pose.x_m, p.y_m - selected.pose.y_m).length() > float(profile.view.interpolation_jump_m):
				trail.clear()
		put(trail, selected, limit)
	for message in view.payload.get("pose_estimates", []):
		if message.frame_id != "map":
			continue
		var key = str([message.publisher_id, message.channel, message.frame_id])
		if not estimates.has(key):
			estimates[key] = []
		put(estimates[key], message, limit)
	for message in view.payload.local_observations:
		if message.schema == "position_fix2d@1" and message.frame_id == "map":
			put(gps, message, limit)
		if message.schema == "scan2d@1" and message.frame_id == "base_link":
			put(scans, message, int(tools.scan_history_limit))
	var cutoff = view.simulation_tick - float(tools.scan_max_age_s) * profile.physics_hz
	while not scans.is_empty() and scans[0].simulation_tick < cutoff:
		scans.pop_front()

func scan() -> Variant:
	if latest.is_empty() or scans.is_empty():
		return null
	var result = scans[-1]
	return result if latest.simulation_tick - result.simulation_tick <= float(tools.scan_max_age_s) * profile.physics_hz else null

func scan_pose() -> Variant:
	var sample = scan()
	var selected = latest.get("payload", {}).get("selected_pose")
	if sample == null or selected == null or selected.source_id == "system" or selected.frame_id != "map":
		return null
	# Canonical selected pose and candidate use their original sample ticks.
	if selected.simulation_tick == sample.simulation_tick:
		return selected.pose
	for history in estimates.values():
		for message in history:
			if message.simulation_tick == sample.simulation_tick and message.publisher_id == selected.source_id and message.frame_id == "map":
				return message.payload
	return null

func messages(debug: Dictionary = {}, task: Dictionary = {}) -> Dictionary:
	var result: Dictionary = {}
	if not latest.is_empty():
		result["view / 授权快照"] = latest
		for field in ["local_observations", "pose_estimates", "target_estimates"]:
			for message in latest.payload.get(field, []):
				result[message.channel] = message
	if not task.is_empty():
		result["task / 授权任务反馈"] = task
	if not debug.is_empty():
		for message in debug.sensors.values():
			result[message.channel] = message
		for field in ["truth", "pose_candidates", "selected_pose", "target_estimate", "runtime", "audit"]:
			result["developer/" + field] = debug.get(field)
	return result
