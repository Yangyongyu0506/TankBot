extends SceneTree
## Isolated desktop smoke flow; the Python harness owns settings/store/server.
const AppScene = preload("res://main.tscn")
const Timeline = preload("res://timeline.gd")
var app: Control
var failed: bool = false
var report_path: String = ""
var screenshot_path: String = ""
var checks: Array = []
var first_revision: String
var terminal: Dictionary = {}

func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--report="):
			report_path = argument.substr(9)
		if argument.begins_with("--screenshot="):
			screenshot_path = argument.substr(13)
	call_deferred("run")

func check(condition: bool, description: String) -> bool:
	checks.append({"check": description, "passed": condition})
	if not condition:
		failed = true
		push_error(description)
		finish()
	return condition

func finish() -> void:
	if not report_path.is_empty():
		var output = FileAccess.open(report_path, FileAccess.WRITE)
		output.store_string(JSON.stringify({"passed": not failed, "checks": checks, "godot": Engine.get_version_info(), "display": DisplayServer.get_name(), "terminal": terminal, "deployment": app.deployment if app else {}, "client_status": {"connected": app.connected, "status": app.status_text.text, "message": app.message_text.text, "inflight": app.backend.inflight} if app else {}}, "  "))
	quit(1 if failed else 0)

func until(predicate: Callable, seconds: float = 15.0) -> bool:
	var end = Time.get_ticks_msec() + seconds * 1000
	while not predicate.call() and Time.get_ticks_msec() < end:
		await create_timer(0.05).timeout
	return predicate.call()

func key(code: int) -> void:
	var event = InputEventKey.new()
	event.keycode = code
	event.physical_keycode = code
	event.pressed = true
	Input.parse_input_event(event)
	await process_frame
	event = event.duplicate()
	event.pressed = false
	Input.parse_input_event(event)
	await process_frame

func timeline_tests() -> void:
	var t = Timeline.new()
	t.configure(app.profile)
	var first = {"run_id": "test", "sequence_number": 1, "simulation_tick": 0,
		"payload": {"view_revision": 0, "selected_pose": {"source_id": "system", "frame_id": "map", "simulation_tick": 0, "pose": {"x_m": 0.0, "y_m": 0.0, "yaw_rad": 0.0}}, "objects": [], "local_observations": []}}
	t.push(first, 0)
	var next = first.duplicate(true)
	next.sequence_number = 2
	next.simulation_tick = app.profile.physics_hz
	next.payload.selected_pose.simulation_tick = app.profile.physics_hz
	next.payload.selected_pose.pose.x_m = 0.5
	t.push(next, 0)
	var pair = t.bracket(t.poses, 500)
	check(is_equal_approx(t.pose_between(pair[0], pair[1], pair[2]).x_m, 0.25), "authorized pose interpolation")
	check(t.sample(10000).pose.x_m <= 0.5, "no extrapolation")
	t.push(first, 0)
	check(t.latest.sequence_number == 2, "old response rejected")
	next.sequence_number = 3
	next.payload.selected_pose = null
	t.push(next, 0)
	check(t.sample(10000).pose == null, "missing pose hidden without truth fallback")

func mission_scroll_tests() -> bool:
	var scrollbar = app.mission.get_v_scroll_bar()
	if not check(await until(func(): return scrollbar.max_value > scrollbar.page), "mission text has a scrollable viewport"):
		return false
	app.mission.scroll_vertical = (scrollbar.max_value - scrollbar.page) * 0.6
	await process_frame
	var position = app.mission.scroll_vertical
	if not check(position > 0, "player scrolls down the mission panel"):
		return false
	await create_timer(float(app.options.status_poll_ms) * 3.0 / 1000.0).timeout
	if not check(is_equal_approx(app.mission.scroll_vertical, position), "periodic status polls preserve mission scroll"):
		return false
	var previous = app.attempt.duplicate(true)
	app.attempt.live_metrics = {"estimate_rmse_m": 0.123}
	app.update_mission()
	await process_frame
	await process_frame
	if not check(is_equal_approx(app.mission.scroll_vertical, position), "changed feedback preserves mission scroll"):
		return false
	app.attempt = previous
	app.update_mission()
	return true

func run() -> void:
	app = AppScene.instantiate()
	root.add_child(app)
	if not check(await until(func(): return app.connected), "native Host connection"):
		return
	if not await mission_scroll_tests():
		return
	timeline_tests()
	if failed:
		return
	first_revision = app.snapshot.revision
	check(app.profile.runtime_execution_profile.backend == "native", "native profile; no Pyodide")
	check(app.profile.runtime_execution_profile.batch_wall_deadline_ms == 30, "native experimental 30ms deadline unchanged")
	await key(KEY_F2)
	if not check(await until(func(): return app.editor_panel.visible and app.editor_panel.size == app.size), "F2 full-screen editor"):
		return
	check(app.editor_panel.get_theme_stylebox("panel").bg_color.a == 1, "editor has opaque background over game view")
	app.open_file("perception/transforms.py")
	app.editor.text = "def broken(:\n"
	await app.save_files()
	await app.test_snapshot()
	if not check(await until(func(): return app.editor_logs.text.contains("SyntaxError")), "invalid Python rejected"):
		return
	check(app.editor_logs.text.contains("SyntaxError"), "Python source diagnostic visible")
	# Reference confined to this test. Production templates remain empty exercises.
	app.editor.text = "import math\nimport numpy as np\nfrom numpy.typing import NDArray\nfrom tankbot import Pose2D\n\ndef radar_to_map(own_pose: Pose2D) -> NDArray[np.float64]:\n    T: NDArray[np.float64] = np.eye(4, dtype=np.float64)\n    c: float = math.cos(own_pose.yaw_rad)\n    s: float = math.sin(own_pose.yaw_rad)\n    T[:2, :2] = [[c, -s], [s, c]]\n    T[0, 3] = own_pose.x_m\n    T[1, 3] = own_pose.y_m\n    return T\n"
	await app.save_files()
	await app.add_file("my_notes.py")
	app.editor.text = "# preserved custom file\n"
	await app.save_files()
	var revision = app.snapshot.revision
	await app.test_snapshot()
	if not check(await until(func(): return app.ready_revision == revision), "C1 snapshot Ready in isolated CPython"):
		return
	check(not app.deploy_button.disabled, "deployment button enabled after test")
	await app.deploy_snapshot()
	if not check(await until(func(): return app.deployment.get("active") != null), "real deployment Active"):
		return
	await create_timer(0.2).timeout
	check(not app.editor_panel.visible, "deployment closes editor")
	await key(KEY_F2)
	check(not app.editor_panel.visible, "running attempt blocks editor")
	var view = await app.backend.call_api("/api/view")
	check(not view.payload.get("target_estimates", []).is_empty(), "player estimate reaches authorized renderer")
	if not screenshot_path.is_empty() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(screenshot_path)
	# Aim using only the same authorized estimate + turret encoder available to the GUI.
	# The fixture supplies a proportional manual velocity reference through the same
	# HTTP adapter, avoiding frame-dependent key pulse aiming. Space is still a real key.
	app.command_busy = true
	var end = Time.get_ticks_msec() + 15000
	while Time.get_ticks_msec() < end:
		view = await app.backend.call_api("/api/view")
		var selected = view.payload.selected_pose
		var estimates = view.payload.get("target_estimates", [])
		var turret = 0.0
		var turret_rate = 0.0
		for observation in view.payload.local_observations:
			if observation.channel == "/robot/turret/joint_states":
				turret = float(observation.payload.position[0])
				turret_rate = float(observation.payload.velocity[0])
		if selected and not estimates.is_empty():
			var target = estimates[0].payload
			var own = selected.pose
			var error = wrapf(atan2(target.y_m-own.y_m, target.x_m-own.x_m) - own.yaw_rad - turret, -PI, PI)
			app.keys.clear()
			await app.backend.call_api("/api/turret_cmd_vel", {"velocity_radps": clamp(3.0 * error, -float(app.profile.view.keyboard_turret_radps), float(app.profile.view.keyboard_turret_radps))})
			if abs(error) < 0.025 and abs(turret_rate) < 0.1:
				await key(KEY_SPACE)
		var campaign = await app.backend.call_api("/api/campaign")
		if campaign.attempt.status == "passed":
			break
		await create_timer(0.05).timeout
	app.keys.clear()
	app.command_busy = false
	await app.send_controls()
	if not check(await until(func(): return app.attempt.get("status") == "passed", 2), "C1 actual authoritative pass using authorized estimates"):
		return
	terminal = {"attempt": app.attempt.duplicate(true), "deployment": app.deployment.duplicate(true)}
	await app.start_level()
	check(app.snapshot.files["my_notes.py"] == "# preserved custom file\n", "custom source preserved after retry")
	check(is_zero_approx(app.mission.scroll_vertical), "new attempt starts mission text at the top")
	var original = await app.backend.call_api("/api/workspace/revision", {"revision": first_revision})
	check(original.get("revision") == first_revision, "original revision and ledger preserved")
	check(not app.running, "retry resets attempt lifecycle")
	var campaign_revision = app.snapshot.revision
	var campaign_files = app.snapshot.files.duplicate(true)
	var campaign_ledger = app.snapshot.ledger.duplicate(true)
	for index in range(app.levels.item_count):
		if app.levels.get_item_metadata(index) == "c0":
			app.levels.select(index)
	await app.start_level()
	var initial = await app.backend.call_api("/api/view")
	var x0 = float(initial.payload.selected_pose.pose.x_m)
	var forward = InputEventKey.new()
	forward.keycode = KEY_W
	forward.physical_keycode = KEY_W
	forward.pressed = true
	Input.parse_input_event(forward)
	await create_timer(0.7).timeout
	forward = forward.duplicate()
	forward.pressed = false
	Input.parse_input_event(forward)
	var moved = await app.backend.call_api("/api/view")
	check(float(moved.payload.selected_pose.pose.x_m) > x0 + 0.05, "C0 keyboard driving moves the authoritative body")
	await app.finish_attempt()
	for index in range(app.levels.item_count):
		if app.levels.get_item_metadata(index) == "navigation.c0":
			app.levels.select(index)
	await app.start_level()
	check(app.profile.campaign.active_level == "navigation.c0" and not app.profile.weapons_enabled, "Navigation scope switches to unarmed native scene")
	check(not app.snapshot.files.has("perception/transforms.py"), "Navigation never copies Weapons algorithms")
	for index in range(app.levels.item_count):
		if app.levels.get_item_metadata(index) == "c1":
			app.levels.select(index)
	await app.start_level()
	check(campaign_files.keys().all(func(path): return app.snapshot.files.get(path) == campaign_files[path]), "returning to Weapons preserves all existing source bytes")
	check(campaign_ledger.keys().all(func(name): return app.snapshot.ledger.get(name) == campaign_ledger[name]), "returning preserves prior ledger entries; new unlock may append provenance")
	var saved = await app.backend.call_api("/api/workspace/revision", {"revision": campaign_revision})
	check(saved.get("revision") == campaign_revision, "authored revision remains readable after C0 and Navigation visits")
	app.open_file("perception/transforms.py")
	await key(KEY_F2)
	check(await until(func(): return app.editor_panel.visible), "retry restores editor access")
	if not screenshot_path.is_empty() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(screenshot_path.get_basename() + "-editor.png")
	finish()
