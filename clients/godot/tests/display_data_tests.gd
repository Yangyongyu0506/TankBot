extends RefCounted
const Data = preload("res://display_data.gd")
const Policy = preload("res://display_policy.gd")
const Keyboard = preload("res://keyboard.gd")
const Timeline = preload("res://timeline.gd")

func frame(sequence: int, tick: int, selected_tick: int = -1, scan_tick: int = -1) -> Dictionary:
	var pose = {"x_m": 1.0, "y_m": 2.0, "yaw_rad": 0.5, "child_frame_id": "base_link", "covariance": null}
	var selected = {"source_id": "ekf", "frame_id": "map", "simulation_tick": selected_tick, "pose": pose} if selected_tick >= 0 else null
	var observations: Array = []
	if scan_tick >= 0:
		var ranges: Array = []
		var hits: Array = []
		ranges.resize(180)
		ranges.fill(1.0)
		hits.resize(180)
		hits.fill(true)
		observations.append({"schema": "scan2d@1", "channel": "/robot/sensors/scan", "publisher_id": "scan", "frame_id": "base_link", "simulation_tick": scan_tick,
			"payload": {"ranges_m": ranges, "hit_mask": hits, "sample_tick": scan_tick, "angle_min_rad": -PI, "angle_increment_rad": TAU / 180, "range_min_m": 0.05, "range_max_m": 6.0, "noise_stddev_m": 0.02}})
	var estimates: Array = []
	if selected:
		estimates.append({"channel": "/robot/estimates/ekf/pose", "publisher_id": "ekf", "frame_id": "map", "simulation_tick": selected_tick, "payload": pose})
	return {"run_id": "display-test", "sequence_number": sequence, "simulation_tick": tick,
		"payload": {"view_revision": 0, "selected_pose": selected, "local_observations": observations, "pose_estimates": estimates, "target_estimates": [], "objects": []}}

func run(h) -> bool:
	var app = h.app
	var profile: Dictionary = app.profile.duplicate(true)
	var tools: Dictionary = app.options.tools.duplicate(true)
	tools.history_limit = 3
	tools.scan_history_limit = 2
	var data = Data.new()
	data.configure(profile, tools)
	data.accept(frame(1, 12, -1, 12))
	if not h.check(data.scan() != null and data.scan_pose() == null, "scan without player localization remains a body-frame view"):
		return false
	data.accept(frame(2, 18, 6, 12))
	if not h.check(data.scan_pose() == null, "a newer or older mismatched player tick cannot project a scan"):
		return false
	data.accept(frame(3, 24, 12, 12))
	if not h.check(data.scan() != null and data.scan_pose() != null, "exact 0.20s scan age and matching EKF tick permit projection"):
		return false
	data.accept(frame(4, 25, 12, 12))
	if not h.check(data.scan() == null and data.scan_pose() == null, "scan beyond 0.20s is hidden instead of being relabelled current"):
		return false
	var next = frame(5, 30, 30, 30)
	next.payload.selected_pose.source_id = "system"
	data.accept(next)
	if not h.check(data.scan_pose() == null, "system truth cannot supply the map scan projection"):
		return false
	next = frame(6, 36, 36, 36)
	next.payload.local_observations[0].frame_id = "unknown_scan_frame"
	data.accept(next)
	if not h.check(data.scan() == null, "unknown scan frames are not silently treated as base_link"):
		return false
	for tick in range(40, 60):
		data.accept(frame(tick, tick, tick, tick))
	if not h.check(data.trail.size() == 3 and data.scans.size() <= 2 and data.estimates.values()[0].size() == 3, "pose and scan history enforce independent finite bounds"):
		return false
	next = frame(61, 61, -1, -1)
	next.run_id = "new-display-run"
	data.accept(next)
	if not h.check(data.trail.is_empty() and data.scans.is_empty() and data.estimates.is_empty(), "run change purges old pose/scan associations"):
		return false
	var policy = Policy.new()
	var preferences: Dictionary = app.settings.settings.duplicate(true)
	preferences.developer_mode = false
	preferences.layers.truth_robot = true
	policy.configure(profile, preferences, tools.layers)
	if not h.check(not policy.enabled("truth_robot") and not policy.set_layer("truth_robot", true), "saved truth preferences cannot cross a player visualization policy"):
		return false
	preferences.developer_mode = true
	policy.configure(profile, preferences, tools.layers)
	if not h.check(policy.enabled("truth_robot") and policy.toggleable("truth_targets") and not policy.allowed("unknown_display"), "developer grant enables supported displays without an arbitrary plugin escape"):
		return false
	for entry in [[KEY_UP, "ArrowUp"], [KEY_2, "Digit2"], [KEY_KP_3, "Numpad3"], [KEY_F10, "F10"]]:
		var event = InputEventKey.new()
		event.physical_keycode = entry[0]
		if not h.check(Keyboard.code(event) == entry[1] and Keyboard.valid(Keyboard.code(event)), "physical key mapping supports " + str(entry[1])):
			return false
	var timeline = Timeline.new()
	timeline.configure(profile)
	var first = frame(1, 0, 0)
	first.payload.selected_pose.source_id = "system"
	timeline.push(first, 0)
	var second = frame(2, int(profile.physics_hz), int(profile.physics_hz))
	second.payload.selected_pose.source_id = "system"
	second.payload.selected_pose.pose.x_m = 2.0
	timeline.push(second, 0)
	if not h.check(is_equal_approx(timeline.sample(1000, 500.0).pose.x_m, 1.5), "developer and player histories can use the same simulation display time"):
		return false
	return h.check(timeline.sample(1000, 5000.0).pose.x_m <= 2.0, "shared display time never extrapolates beyond authorized samples")
