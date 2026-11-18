extends RefCounted
## Actual settings API and isolated GUI; no developer completion is fabricated.
var h
var app

func capture(suffix: String) -> void:
	if not h.screenshot_path.is_empty() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		h.root.get_texture().get_image().save_png(h.screenshot_path.get_basename() + suffix + ".png")

func open_settings() -> bool:
	await app.show_settings()
	if not h.check(await h.until(func(): return app.settings_dialog.visible), "settings opens inside the fixed game viewport"):
		return false
	await h.process_frame
	return h.check(app.get_global_rect().encloses(app.settings_dialog.get_ok_button().get_global_rect()), "save/cancel footer stays within the game viewport")

func save() -> bool:
	app.settings_dialog.submit()
	var finished = await h.until(func(): return not app.settings_dialog.visible)
	return h.check(finished, "settings save completes through the authenticated API" + ("" if finished else ": " + str([app.settings_dialog.note.text, app.settings_dialog.recording, app.settings_dialog.busy, app.settings_busy, app.layer_save_busy, app.transaction_busy])))

func choose(id: String) -> bool:
	for index in range(app.levels.item_count):
		if app.levels.get_item_metadata(index) == id:
			app.levels.select(index)
			await app.choose_level(index)
			return h.check(app.profile.campaign.active_level == id, "developer can select " + id)
	return h.check(false, "catalogue contains " + id)

func translucent(entity: CanvasItem, description: String) -> bool:
	return h.check(is_equal_approx(entity.self_modulate.a, float(app.options.tools.rendering.developer_entity_opacity)), description + " uses the shared 50 percent developer opacity")

func top_annotations() -> bool:
	var view = app.world
	var sprites: Array = [view.vehicle, view.developer.vehicle]
	sprites.append_array(view.entities.values())
	sprites.append_array(view.developer.targets.values())
	sprites.append_array(view.developer.projectile_sprites.values())
	for node in sprites:
		if not h.check(view.diagnostics.z_index > node.z_index and view.developer.annotations.z_index > node.z_index, "public and developer annotations stay above dynamically spawned entities"):
			return false
	return h.check(view.diagnostics.map_layer.z_as_relative == false and view.diagnostics.map_layer.z_index < view.vehicle.z_index, "occupancy and safety fills remain below translucent entities")

func visible_axes() -> bool:
	if DisplayServer.get_name() == "headless":
		return true
	await h.process_frame
	await RenderingServer.frame_post_draw
	var view = app.world
	var center: Vector2 = view.point(view.draw_pose)
	var offset = Vector2(float(app.options.tools.rendering.frame_length_m) * 0.3, 0).rotated(view.draw_pose.yaw_rad)
	var pixel: Vector2 = view.get_global_transform() * view.project(center + offset)
	var image = h.root.get_texture().get_image()
	var actual = image.get_pixelv(Vector2i(pixel.round()))
	var expected = Color(app.options.tools.rendering.frame_x)
	return h.check(Vector3(actual.r, actual.g, actual.b).distance_to(Vector3(expected.r, expected.g, expected.b)) < 0.15, "real frame-axis pixels stay opaque above the tank hull and turret")

func run(harness) -> bool:
	h = harness
	app = h.app
	await app.finish_attempt()
	var before = app.snapshot.duplicate(true)
	var progress = await app.backend.call_api("/api/progress")
	var denied = await app.backend.call_api("/api/developer")
	if not h.check(denied.get("error") == "UNAUTHORIZED", "player API cannot fetch developer DTOs"):
		return false
	await h.key(KEY_F10)
	if not h.check(await h.until(func(): return app.settings_dialog.visible), "configured F10 opens settings"):
		return false
	var dialog = app.settings_dialog
	dialog.tabs.current_tab = 1
	dialog.capture("forward")
	await h.key(KEY_F2)
	if not h.check(dialog.recording == "forward" and dialog.note.text.contains("已用于"), "duplicate key capture is rejected without opening VS Code"):
		return false
	await h.key(KEY_ESCAPE)
	if not h.check(dialog.visible and dialog.recording.is_empty(), "Escape cancels capture before closing settings"):
		return false
	dialog.capture("forward")
	await h.key(KEY_UP)
	if not h.check(dialog.draft.keyboard.forward == "ArrowUp" and app.settings.settings.keyboard.forward == "KeyW", "physical ArrowUp is a draft until saved"):
		return false
	await capture("-settings-keyboard")
	if not await save():
		return false
	if not h.check(app.settings.settings.keyboard.forward == "ArrowUp", "saved key mapping is active"):
		return false
	var yaml_text = FileAccess.get_file_as_string(app.settings.settings_file)
	if not h.check(yaml_text.contains("forward: ArrowUp"), "key mapping persists in the isolated YAML file"):
		return false
	if not await open_settings():
		return false
	if not h.check(dialog.draft.keyboard.forward == "ArrowUp", "reopening reads the saved mapping"):
		return false
	dialog.reset_bindings()
	dialog.hide()
	if not h.check(app.settings.settings.keyboard.forward == "ArrowUp", "closing discards unsaved default reset"):
		return false
	if not await open_settings():
		return false
	dialog.reset_bindings()
	if not await save():
		return false
	if not await open_settings():
		return false
	dialog.state.revision = "stale-test-revision"
	dialog.submit()
	if not h.check(await h.until(func(): return not dialog.busy and dialog.note.text.contains("其他窗口")), "stale settings revision is rejected without hiding the user's draft"):
		return false
	dialog.hide()
	if not await open_settings():
		return false
	dialog.tabs.current_tab = 2
	if not h.check(not dialog.layer_checks.truth_robot.visible and not app.world.policy.allowed("truth_robot"), "player settings cannot enable a forbidden truth layer"):
		return false
	dialog.tabs.current_tab = 0
	dialog.developer.button_pressed = true
	dialog.draft.layers.velocities = true
	dialog.draft.layers.colliders = true
	dialog.draft.layers.frames = true
	if not await save():
		return false
	if not h.check(await h.until(func(): return app.connected and app.settings.settings.developer_mode and not app.grant_suspended), "mode change rebuilds the native session with an explicit developer grant"):
		return false
	for index in range(app.levels.item_count):
		if not h.check(not app.levels.is_item_disabled(index), "developer catalogue permits " + str(app.levels.get_item_metadata(index))):
			return false
	if not await choose("c0"):
		return false
	if not h.check(await h.until(func(): return not app.world.developer.targets.is_empty() and app.world.draw_pose != null), "developer static target and system-selected tank are ready"):
		return false
	if not translucent(app.world.vehicle, "selected tank") or not translucent(app.world.developer.vehicle, "truth tank") or not translucent(app.world.developer.targets.values()[0], "bullseye target"):
		return false
	if not h.check(not app.world.vehicle.visible and app.world.developer.vehicle.visible, "system-selected and truth views do not draw the same tank twice"):
		return false
	if not await visible_axes():
		return false
	await app.backend.call_api("/api/fire", {"request_id": "developer-translucency-check"})
	if not h.check(await h.until(func(): return not app.world.developer.projectile_sprites.is_empty()), "developer projectile is spawned through the existing weapon API"):
		return false
	if not translucent(app.world.developer.projectile_sprites.values()[0], "projectile") or not top_annotations():
		return false
	await capture("-developer-translucent-target")
	await app.finish_attempt()
	if not await choose("c2"):
		return false
	if not h.check(await h.until(func(): return not app.world.developer.targets.is_empty()), "differential enemy reaches the developer overlay"):
		return false
	var differential = app.world.developer.targets.values()[0]
	if not h.check(differential is CanvasGroup and differential.model_kind == "tracked", "differential enemy composes hull and turret as one entity") or not translucent(differential, "differential enemy"):
		return false
	await capture("-developer-translucent-differential")
	if not await choose("c5"):
		return false
	if not h.check(await h.until(func(): return not app.world.developer.targets.is_empty()), "C5 real enemy reaches the developer sprite overlay"):
		return false
	var enemy = app.world.developer.targets.values()[0]
	if not h.check(enemy is CanvasGroup, "omni hull, wheels and armor use whole-entity compositing") or not translucent(enemy, "omni enemy") or not top_annotations():
		return false
	if not h.check(enemy.model_kind == "radial_omni" and enemy.wheel_sprites.size() == 4 and app.world.vehicle.model_kind == "tracked", "enemy uses its own fourfold omni model independently of the player"):
		return false
	var yaw = enemy.rotation
	await h.create_timer(0.4).timeout
	if not h.check(abs(enemy.rotation - yaw) > 0.05, "developer enemy sprite follows actual spinning yaw"):
		return false
	await capture("-developer-weapons")
	if not await open_settings():
		return false
	dialog.tabs.current_tab = 2
	dialog.layer_checks.truth_targets.button_pressed = false
	if not await save():
		return false
	if not h.check(await h.until(func(): return app.world.developer.targets.is_empty()), "turning off truth targets removes only the display"):
		return false
	var physical = await app.backend.call_api("/api/developer")
	if not h.check(physical.truth.targets[0].alive, "hiding a layer does not remove the authoritative target"):
		return false
	if not await open_settings():
		return false
	dialog.layer_checks.truth_targets.button_pressed = true
	if not await save():
		return false
	await app.show_inspector()
	if not h.check(await h.until(func(): return app.inspector.values.has("developer/truth")), "developer inspector receives separate authorized diagnostics"):
		return false
	app.inspector.selected = "developer/truth"
	for index in range(app.inspector.topics.item_count):
		if app.inspector.topics.get_item_metadata(index) == "developer/truth":
			app.inspector.topics.select(index)
	app.inspector.refresh()
	if not h.check(app.inspector.content.text.contains("truth_pose"), "developer data viewer shows native JSON fields"):
		return false
	await capture("-developer-inspector")
	app.inspector.hide()
	if not await choose("navigation.c6"):
		return false
	if not h.check(await h.until(func(): return app.world.data.scan() != null and not app.world.developer.latest.is_empty()), "Navigation C6 local scan and independent developer snapshot arrive"):
		return false
	if not h.check(app.world.data.scan_pose() == null and app.world.draw_pose == null, "developer truth never substitutes for missing same-tick player EKF"):
		return false
	if not await open_settings():
		return false
	dialog.tabs.current_tab = 2
	dialog.layer_checks.private_obstacles.button_pressed = true
	await capture("-settings-layers")
	if not await save():
		return false
	await capture("-developer-navigation")
	var stale: Dictionary = app.world.developer.latest.duplicate(true)
	if not h.check(not stale.private_obstacles.is_empty(), "private geometry exists only in the developer response"):
		return false
	if not await open_settings():
		return false
	dialog.developer.button_pressed = false
	if not await save():
		return false
	if not h.check(await h.until(func(): return app.connected and not app.settings.settings.developer_mode), "returning to player mode revokes the grant"):
		return false
	app.world.developer.accept(stale)
	if not h.check(not app.world.developer.enabled and app.world.developer.latest.is_empty() and app.world.developer.targets.is_empty(), "late former-run developer data cannot restore privileged sprites"):
		return false
	app.refresh_inspector()
	if not h.check(app.inspector.values.keys().all(func(key): return not str(key).begins_with("developer/")), "developer inspector categories are purged on revocation"):
		return false
	denied = await app.backend.call_api("/api/developer")
	if not h.check(denied.get("error") == "UNAUTHORIZED", "authority rejects developer requests after mode revocation"):
		return false
	var locked = await app.backend.call_api("/api/campaign/start", {"level_id": "c5"})
	if not h.check(str(locked.get("error", "")).contains("LEVEL_LOCKED"), "player still cannot enter unearned developer preview levels"):
		return false
	var after = await app.backend.call_api("/api/progress")
	if not h.check(after.completed_levels == progress.completed_levels and app.profile.campaign.active_level == progress.current_level, "developer previews do not award progress or replace the player's selected level"):
		return false
	if not h.check(before.files.keys().all(func(path): return app.snapshot.files.get(path) == before.files[path]) and before.ledger.keys().all(func(key): return app.snapshot.ledger.get(key) == before.ledger[key]), "mode and scope changes preserve existing source and ledger entries"):
		return false
	var original = await app.backend.call_api("/api/workspace/revision", {"revision": before.revision})
	return h.check(original.get("revision") == before.revision, "authored revision remains readable after developer tools use")
