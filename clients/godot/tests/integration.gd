extends SceneTree
## Isolated desktop smoke flow; the Python harness owns settings/store/server.
const AppScene = preload("res://main.tscn")
const Timeline = preload("res://timeline.gd")
const WorldView = preload("res://world_view.gd")
var app: Control
var failed: bool = false
var report_path: String = ""
var screenshot_path: String = ""
var visual_fixtures_path: String = ""
var checks: Array = []
var first_revision: String
var terminal: Dictionary = {}

func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--report="):
			report_path = argument.substr(9)
		if argument.begins_with("--screenshot="):
			screenshot_path = argument.substr(13)
		if argument.begins_with("--visual-fixtures="):
			visual_fixtures_path = argument.trim_prefix("--visual-fixtures=")
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

func save_source(path: String, content: String) -> void:
	var file = FileAccess.open(app.editable_directory.path_join(path), FileAccess.WRITE)
	file.store_string(content)
	file.close()

func theme_tests() -> bool:
	if not check(await until(func(): return not app.status_busy and not app.mission.text.is_empty()), "task feedback is loaded before visual inspection"):
		return false
	var colors: Dictionary = app.options.appearance.colors
	for entry in [[app.start_button, "start_normal", "start_pressed"], [app.stop_button, "stop_normal", "stop_pressed"], [app.edit_button, "button_normal", "button_pressed"]]:
		var control: Button = entry[0]
		if not check(control.get_theme_stylebox("normal").bg_color == Color(colors[entry[1]]) and control.get_theme_stylebox("pressed").bg_color == Color(colors[entry[2]]), control.text + " resolves its solid normal and pressed theme"):
			return false
		if not check(control.get_theme_stylebox("disabled").bg_color == Color(colors.button_disabled) and control.get_theme_color("font_disabled_color") == Color(colors.disabled_text), control.text + " has readable disabled colors"):
			return false
		if not check(control.focus_mode == Control.FOCUS_NONE, control.text + " preserves gameplay key focus behavior"):
			return false
	await process_frame
	for control in app.find_children("*", "Button", true, false):
		if control.is_visible_in_tree() and not check(app.get_global_rect().encloses(control.get_global_rect()), control.text + " stays within the viewport"):
			return false
	for control in app.find_children("*", "Button", true, false):
		if control.theme_type_variation == "LayerToggle" and control.text.begins_with("地图"):
			control.button_pressed = false
			if not check(not app.world.layers.map and control.text.ends_with("关"), "layer toggle has an explicit off state"):
				return false
			control.button_pressed = true
			if not check(app.world.layers.map and control.text.ends_with("开"), "layer toggle restores the authorized map presentation"):
				return false
	if not screenshot_path.is_empty() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(screenshot_path.get_basename() + "-ready.png")
		var motion = InputEventMouseMotion.new()
		motion.position = app.start_button.get_global_rect().get_center()
		Input.parse_input_event(motion)
		await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(screenshot_path.get_basename() + "-hover.png")
		motion.position = app.world.get_global_rect().get_center()
		Input.parse_input_event(motion)
		await process_frame
	return true

func sprite_tests() -> bool:
	for key in app.world.sprites.textures:
		var texture: AtlasTexture = app.world.sprites.textures[key]
		if not check(texture.atlas is ImageTexture and texture.region.has_area(), key + " loads a shared prebuilt image texture"):
			return false
	var profiles: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(visual_fixtures_path))
	var gallery = HBoxContainer.new()
	root.add_child(gallery)
	gallery.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	app.visible = false
	var views: Array = []
	for chassis_type in profiles:
		var column = VBoxContainer.new()
		column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		gallery.add_child(column)
		var heading = Label.new()
		heading.text = "Sprite 美术预览（隔离显示夹具） · " + str(chassis_type)
		heading.theme = app.theme
		column.add_child(heading)
		var view = WorldView.new()
		view.sprites = app.world.sprites
		view.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		view.size_flags_vertical = Control.SIZE_EXPAND_FILL
		view.clip_contents = true
		column.add_child(view)
		var profile: Dictionary = profiles[chassis_type]
		profile.rendering.viewport_width_m = 3.0
		view.configure(profile)
		var frame = {"run_id": "visual-fixture", "sequence_number": 1, "simulation_tick": 0,
			"payload": {"view_revision": 0, "selected_pose": {"source_id": "system", "frame_id": "map", "simulation_tick": 0, "pose": {"x_m": 0.0, "y_m": 0.0, "yaw_rad": 0.0}},
			"objects": [{"kind": "target", "target_id": "board", "pose": {"x_m": 1.0, "y_m": 0.0, "yaw_rad": 0.0}}], "local_observations": []}}
		view.accept(frame)
		await process_frame
		view._process(0.0)
		if not check(view.vehicle.visible and not view.vehicle.find_children("*", "Sprite2D", true, false).is_empty(), str(chassis_type) + " is rendered with Sprite2D parts"):
			return false
		if chassis_type == "omnidirectional":
			if not check(view.vehicle.wheel_sprites.size() == profile.wheel_calibration.wheels.size(), "omni has four independently mounted wheel sprites"):
				return false
			for i in range(view.vehicle.wheel_sprites.size()):
				var angle = deg_to_rad(float(profile.wheel_calibration.wheels[i].azimuth_deg))
				var wheel: Sprite2D = view.vehicle.wheel_sprites[i]
				var expected = Vector2(cos(angle), -sin(angle)) * float(profile.wheel_calibration.center_radius_m)
				if not check(wheel.position.distance_to(expected) < 1e-6 and is_equal_approx(wheel.rotation, -angle - PI * 0.5), "omni wheel uses calibrated centre and tangential orientation"):
					return false
		var entity: Sprite2D = view.entities.values()[0]
		if not check(entity.texture == app.world.sprites.textures.target, "authorized target uses the stored bullseye image"):
			return false
		var id = entity.get_instance_id()
		view._process(0.0)
		if not check(view.entities.values()[0].get_instance_id() == id, "same entity reuses its sprite across render frames"):
			return false
		view.vehicle.present(Vector2.ZERO, 0.6, view.scale_m, 0.7)
		if not check(is_equal_approx(view.vehicle.rotation, -0.6) and is_equal_approx(view.vehicle.weapon.rotation, -0.7), "turret sprite rotates independently about its body pivot"):
			return false
		var barrel: Sprite2D = view.vehicle.weapon.get_node("barrel")
		var muzzle = Vector2(profile.turret_muzzle_offset_m[0], profile.turret_muzzle_offset_m[1])
		if not check(barrel.position.distance_to(Vector2(muzzle.x, -muzzle.y) * 0.5) < 1e-6 and is_equal_approx(barrel.scale.x * barrel.texture.get_width(), muzzle.length()), "barrel sprite ends at the configured muzzle without padding distortion"):
			return false
		view._process(0.0)
		views.append({"view": view, "frame": frame, "profile": profile})
	await process_frame
	if not screenshot_path.is_empty() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(screenshot_path.get_basename() + "-sprites.png")
	for entry in views:
		var view = entry.view
		var frame: Dictionary = entry.frame
		frame.sequence_number = 2
		frame.simulation_tick = 1
		frame.payload.selected_pose = null
		frame.payload.objects = []
		view.accept(frame)
		view._process(0.0)
		if not check(not view.vehicle.visible and view.entities.is_empty(), "missing pose and despawn remove sprites without truth fallback"):
			return false
		view.configure(entry.profile)
		if not check(view.entities.is_empty() and not view.vehicle.visible, "reconfigure clears prior run sprites"):
			return false
	gallery.free()
	app.visible = true
	return true

func run() -> void:
	app = AppScene.instantiate()
	root.add_child(app)
	if not check(await until(func(): return app.connected), "native Host connection"):
		return
	if not await theme_tests():
		return
	if not await sprite_tests():
		return
	if not await mission_scroll_tests():
		return
	timeline_tests()
	if failed:
		return
	first_revision = app.snapshot.revision
	check(app.profile.runtime_execution_profile.backend == "native", "native profile; no Pyodide")
	check(app.profile.runtime_execution_profile.batch_wall_deadline_ms == 30, "native experimental 30ms deadline unchanged")
	check(app.find_children("*", "CodeEdit", true, false).is_empty(), "built-in source editor removed")
	await key(KEY_F2)
	if not check(await until(func(): return FileAccess.file_exists(app.editable_directory.path_join("perception/transforms.py"))), "F2 exports real source files for external editor"):
		return
	save_source("perception/transforms.py", "def broken(:\n")
	await app.start_level()
	if not check(await until(func(): return app.last_log.contains("SyntaxError")), "Start shows native Python source diagnostic"):
		return
	check(app.deployment.get("active") == null, "invalid source cannot become active")
	# Reference confined to this test; save real files, never fill a production template.
	save_source("perception/transforms.py", "import math\nimport numpy as np\nfrom numpy.typing import NDArray\nfrom tankbot import Pose2D\n\ndef radar_to_map(own_pose: Pose2D) -> NDArray[np.float64]:\n    T: NDArray[np.float64] = np.eye(4, dtype=np.float64)\n    c: float = math.cos(own_pose.yaw_rad)\n    s: float = math.sin(own_pose.yaw_rad)\n    T[:2, :2] = [[c, -s], [s, c]]\n    T[0, 3] = own_pose.x_m\n    T[1, 3] = own_pose.y_m\n    return T\n")
	save_source("my_notes.py", "# preserved custom file\n")
	await app.start_level()
	if not check(await until(func(): return app.deployment.get("active") != null and app.running), "single Start checks and activates isolated CPython"):
		return
	var active_revision = app.deployment.active.revision
	check(not app.deployment.reports.is_empty(), "Start retained preflight checks automatically")
	save_source("my_notes.py", "# edited while running\n")
	await key(KEY_F2)
	check(not app.edit_button.disabled, "external editor remains available while running")
	check(app.start_button.disabled, "stop is required before starting another code version")
	check(app.deployment.active.revision == active_revision, "disk edits do not modify the active revision")
	var view = await app.backend.call_api("/api/view")
	if not check(await until(func(): return not app.world.timeline.latest.get("payload", {}).get("target_estimates", []).is_empty()), "player estimate reaches authorized renderer"):
		return
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
	check(app.snapshot.files["my_notes.py"] == "# edited while running\n", "retry captures externally saved code")
	check(is_zero_approx(app.mission.scroll_vertical), "new attempt starts mission text at the top")
	var original = await app.backend.call_api("/api/workspace/revision", {"revision": first_revision})
	check(original.get("revision") == first_revision, "original revision and ledger preserved")
	await app.finish_attempt()
	var campaign_revision = app.snapshot.revision
	var campaign_files = app.snapshot.files.duplicate(true)
	var campaign_ledger = app.snapshot.ledger.duplicate(true)
	for index in range(app.levels.item_count):
		if app.levels.get_item_metadata(index) == "c0":
			app.levels.select(index)
			await app.choose_level(index)
			break
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
	if not screenshot_path.is_empty() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(screenshot_path.get_basename() + "-c0.png")
	await app.finish_attempt()
	for index in range(app.levels.item_count):
		if app.levels.get_item_metadata(index) == "navigation.c0":
			app.levels.select(index)
			await app.choose_level(index)
			break
	check(app.profile.campaign.active_level == "navigation.c0" and not app.profile.weapons_enabled, "Navigation scope switches to unarmed native scene")
	check(not app.world.vehicle.weapon.visible, "Navigation hides the weapon sprite layer")
	check(not app.snapshot.files.has("perception/transforms.py"), "Navigation never copies Weapons algorithms")
	for index in range(app.levels.item_count):
		if app.levels.get_item_metadata(index) == "c1":
			app.levels.select(index)
			await app.choose_level(index)
			break
	check(campaign_files.keys().all(func(path): return app.snapshot.files.get(path) == campaign_files[path]), "returning to Weapons preserves all existing source bytes")
	check(campaign_ledger.keys().all(func(name): return app.snapshot.ledger.get(name) == campaign_ledger[name]), "returning preserves prior ledger entries; new unlock may append provenance")
	var saved = await app.backend.call_api("/api/workspace/revision", {"revision": campaign_revision})
	check(saved.get("revision") == campaign_revision, "authored revision remains readable after C0 and Navigation visits")
	await key(KEY_F2)
	check(app.editable_directory.ends_with("/files"), "returning opens the original editable project")
	app.show_guide()
	check(await until(func(): return app.guide_dialog.visible), "read-only lesson remains available without a code editor")
	if not screenshot_path.is_empty() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(screenshot_path.get_basename() + "-guide.png")
	finish()
