extends Control
const Backend = preload("res://backend.gd")
const WorldView = preload("res://world_view.gd")
const UITheme = preload("res://ui_theme.gd")
const Keyboard = preload("res://keyboard.gd")
const SettingsDialog = preload("res://settings_dialog.gd")
const InspectorDialog = preload("res://inspector_dialog.gd")
var backend = Backend.new()
var world = WorldView.new()
var options: Dictionary
var profile: Dictionary = {}
var settings: Dictionary = {}
var snapshot: Dictionary = {}
var learning: Dictionary = {}
var deployment: Dictionary = {}
var attempt: Dictionary = {}
var keys: Dictionary = {}
var running: bool = false
var status_busy: bool = false
var view_busy: bool = false
var command_busy: bool = false
var transaction_busy: bool = false
var last_log: String = ""
var last_launch_phase: String = ""
var connected: bool = false
var plan: Dictionary = {}
var editable_directory: String = ""
var guide_dialog = AcceptDialog.new()
var levels = OptionButton.new()
var status_text = Label.new()
var mission = TextEdit.new()
var guide = TextEdit.new()
var logs = TextEdit.new()
var message_text = Label.new()
var edit_button: Button
var start_button: Button
var stop_button: Button
var upgrade_button: Button
var plan_dialog = ConfirmationDialog.new()
var plan_text = TextEdit.new()
var settings_dialog = SettingsDialog.new()
var inspector = InspectorDialog.new()
var settings_button: Button
var quick_checks: Dictionary = {}
var developer_busy: bool = false
var settings_busy: bool = false
var layer_save_busy: bool = false
var pending_layers: Dictionary = {}
var preparing: bool = false
var grant_epoch: int = 0
var status_epoch: int = 0
var grant_suspended: bool = true

func _ready() -> void:
	get_tree().auto_accept_quit = false
	var arguments: Dictionary = {}
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--") and "=" in argument:
			arguments[argument.get_slice("=", 0)] = argument.substr(argument.find("=")+1)
	if not arguments.has("--client-settings"):
		push_error("请通过 python3 main.py 启动客户端。")
		get_tree().quit(2)
		return
	options = JSON.parse_string(FileAccess.get_file_as_string(arguments["--client-settings"]))
	get_viewport().gui_embed_subwindows = bool(options.tools.embed_subwindows)
	add_child(backend)
	if not backend.configure(arguments.get("--backend-url", ""), options):
		get_tree().quit(2)
		return
	get_window().title = options.title
	get_window().size = Vector2i(options.window_width, options.window_height)
	theme = UITheme.create(options.appearance, int(options.font_size))
	if not world.load_assets(options.sprites):
		get_tree().quit(2)
		return
	world.tools = options.tools
	build_ui()
	await reload_session()
	if not connected:
		return
	start_timer(float(profile.view.poll_ms)/1000.0, poll_view)
	start_timer(float(options.status_poll_ms)/1000.0, poll_status)
	start_timer(float(profile.view.keyboard_refresh_ms)/1000.0, send_controls)
	start_timer(float(profile.view.poll_ms)/1000.0, poll_developer)
	start_timer(float(options.tools.settings_poll_ms)/1000.0, poll_settings)

func button(parent: Node, text: String, action: Callable, variant: String = "") -> Button:
	var node = Button.new()
	node.text = text
	node.focus_mode = Control.FOCUS_NONE
	node.theme_type_variation = variant
	node.custom_minimum_size.y = int(options.appearance.metrics.button_height)
	node.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	node.pressed.connect(action)
	parent.add_child(node)
	return node

func full(node: Control) -> void:
	node.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

func text_box(node: TextEdit) -> void:
	node.editable = false
	node.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	node.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	node.size_flags_vertical = Control.SIZE_EXPAND_FILL

func card(parent: Node, variant: String = "CardPanel") -> PanelContainer:
	var node = PanelContainer.new()
	node.theme_type_variation = variant
	parent.add_child(node)
	return node

func label_in(parent: Node, text: String, variant: String = "HeadingLabel") -> Label:
	var node = Label.new()
	node.text = text
	node.theme_type_variation = variant
	parent.add_child(node)
	return node

func build_ui() -> void:
	var background = Panel.new()
	background.theme_type_variation = "AppPanel"
	add_child(background)
	full(background)
	var margin = MarginContainer.new()
	add_child(margin)
	full(margin)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, int(options.appearance.metrics.outer_margin))
	var root = VBoxContainer.new()
	margin.add_child(root)
	var header = VBoxContainer.new()
	card(root).add_child(header)
	var title_row = HBoxContainer.new()
	header.add_child(title_row)
	var brand = label_in(title_row, "TankBot", "BrandLabel")
	brand.tooltip_text = "Godot 桌面客户端 · CPython 独立进程 · 仅运行本人可信代码"
	var caption = label_in(title_row, "机器人算法训练", "MutedLabel")
	caption.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	levels.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	levels.custom_minimum_size.y = int(options.appearance.metrics.button_height)
	title_row.add_child(levels)
	var toolbar = HFlowContainer.new()
	header.add_child(toolbar)
	start_button = button(toolbar, "Start · 运行 / 重试", start_level, "StartButton")
	start_button.tooltip_text = "保存 VS Code 中的代码后点击；自动检查并运行新快照。"
	stop_button = button(toolbar, "结束尝试", finish_attempt, "StopButton")
	stop_button.tooltip_text = "结束本次运行，然后可以启动修改后的代码。"
	edit_button = button(toolbar, "VS Code · F2", open_editor)
	button(toolbar, "任务说明", show_guide)
	upgrade_button = button(toolbar, "框架升级", preview_upgrade)
	settings_button = button(toolbar, "设置", show_settings)
	button(toolbar, "数据查看", show_inspector)
	levels.item_selected.connect(choose_level)
	card(root, "StatusPanel").add_child(status_text)
	status_text.theme_type_variation = "SmallLabel"
	status_text.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	status_text.text = "连接本机 Authority…"
	var content = HSplitContainer.new()
	content.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(content)
	world.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	world.size_flags_vertical = Control.SIZE_EXPAND_FILL
	world.clip_contents = true
	world.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var viewport_panel = card(content, "ViewportPanel")
	viewport_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	viewport_panel.add_child(world)
	var sidebar = VBoxContainer.new()
	var sidebar_panel = card(content)
	sidebar_panel.custom_minimum_size.x = int(options.guide_width)
	sidebar_panel.add_child(sidebar)
	label_in(sidebar, "任务与授权反馈")
	text_box(mission)
	sidebar.add_child(mission)
	var layers = HFlowContainer.new()
	label_in(sidebar, "显示图层", "SmallLabel")
	sidebar.add_child(layers)
	for key in options.tools.quick_layers:
		var check = Button.new()
		check.theme_type_variation = "LayerToggle"
		check.toggle_mode = true
		check.focus_mode = Control.FOCUS_NONE
		check.custom_minimum_size.y = int(options.appearance.metrics.toggle_height)
		check.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		check.text = options.tools.layers[key] + " · 开"
		check.button_pressed = true
		check.toggled.connect(func(enabled):
			toggle_layer(key, enabled))
		quick_checks[key] = check
		layers.add_child(check)
	button(sidebar, "全部图层与键位设置", show_settings)
	text_box(logs)
	var log_panel = card(root)
	log_panel.custom_minimum_size.y = int(options.log_height)
	var log_column = VBoxContainer.new()
	log_panel.add_child(log_column)
	label_in(log_column, "运行日志", "SmallLabel")
	log_column.add_child(logs)
	message_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	message_text.theme_type_variation = "SmallLabel"
	root.add_child(message_text)
	add_child(guide_dialog)
	guide_dialog.theme = theme
	guide_dialog.title = "本关任务、类型与算法接口"
	guide_dialog.add_child(guide)
	text_box(guide)
	full(guide)
	add_child(plan_dialog)
	plan_dialog.theme = theme
	plan_dialog.title = "教学框架升级预览 · 确认后创建新 revision"
	plan_dialog.ok_button_text = "保留算法，应用此框架升级"
	plan_dialog.add_child(plan_text)
	text_box(plan_text)
	full(plan_text)
	plan_dialog.confirmed.connect(apply_upgrade)
	add_child(settings_dialog)
	settings_dialog.theme = theme
	settings_dialog.configure(options.tools)
	settings_dialog.save_requested.connect(save_settings)
	settings_dialog.visibility_changed.connect(func():
		keys.clear()
		get_viewport().gui_release_focus())
	add_child(inspector)
	inspector.theme = theme
	inspector.configure(options.tools)
	inspector.closed.connect(func():
		keys.clear()
		get_viewport().gui_release_focus())

func start_timer(seconds: float, action: Callable) -> void:
	var timer = Timer.new()
	timer.wait_time = seconds
	timer.timeout.connect(action)
	add_child(timer)
	timer.start()

func message(text: String) -> void:
	message_text.text = text
	status_text.tooltip_text = text

func request(path: String, payload: Variant = null) -> Dictionary:
	var value = await backend.call_api(path, payload)
	if value.has("error"):
		message(str(value.error))
	return value

func reload_session() -> void:
	status_epoch += 1
	fence_developer()
	connected = false
	mission.text = ""
	running = false
	last_launch_phase = ""
	profile = await request("/api/profile")
	if profile.has("error"):
		status_text.text = "无法连接 Authority。"
		return
	backend.token = profile.control_token
	settings = await request("/api/settings")
	world.configure(profile)
	world.apply_preferences(settings.settings)
	grant_suspended = false
	refresh_settings_ui()
	var project = await request("/api/workspace")
	if project.has("error"):
		return
	learning = project.learning
	accept_snapshot(project.snapshot)
	editable_directory = project.editable_directory
	guide.text = lesson_text()
	var progress = await request("/api/progress")
	levels.clear()
	for level in profile.campaign.levels:
		var unlocked = progress.get("developer_mode", false) or level.level_id in progress.get("unlocked_levels", [])
		levels.add_item(level_name(level.level_id) + (" [已通关]" if level.level_id in progress.get("completed_levels", []) else "" if unlocked else " [未解锁]"))
		var index = levels.item_count-1
		levels.set_item_metadata(index, level.level_id)
		levels.set_item_disabled(index, not unlocked)
		var prerequisites = PackedStringArray()
		for prerequisite in level.prerequisites:
			prerequisites.append(level_name(prerequisite, "", true))
		levels.set_item_tooltip(index, level.problem + "\n前置：" + ("无" if prerequisites.is_empty() else "、".join(prerequisites)))
		if level.level_id == profile.campaign.active_level:
			levels.select(index)
	connected = true
	await poll_status()
	await poll_view()
	await poll_developer()
	message("VS Code 保存后点击 Start 自动检查并运行。代码目录：" + editable_directory)

func fence_developer() -> void:
	grant_epoch += 1
	grant_suspended = true
	world.revoke_developer()
	inspector.revoke()

func refresh_settings_ui() -> void:
	edit_button.text = "VS Code · " + Keyboard.label(settings.settings.keyboard.editor)
	settings_button.text = "设置 · " + Keyboard.label(settings.settings.keyboard.settings)
	for key in quick_checks:
		var check: Button = quick_checks[key]
		check.visible = world.policy.allowed(key)
		check.disabled = not world.policy.toggleable(key)
		check.set_pressed_no_signal(world.policy.enabled(key))
		check.text = str(options.tools.layers[key]) + (" · 开" if world.policy.enabled(key) else " · 关")
		check.tooltip_text = "更多图层请打开设置。"

func modal_open() -> bool:
	return guide_dialog.visible or plan_dialog.visible or settings_dialog.visible or inspector.visible

func show_settings() -> void:
	if settings_dialog.visible:
		settings_dialog.hide()
		return
	if transaction_busy or settings_busy:
		return
	if guide_dialog.visible or plan_dialog.visible or inspector.visible:
		return
	keys.clear()
	await send_controls()
	var current = await request("/api/settings")
	if current.has("error"):
		return
	if current.settings.developer_mode != settings.settings.developer_mode:
		await reload_session()
	settings = current
	settings_dialog.open(settings, world.policy, running or preparing)

func save_settings(revision: String, candidate: Dictionary) -> void:
	if settings_busy or layer_save_busy or transaction_busy:
		settings_dialog.fail("设置正在保存或关卡正在切换，请稍后重试。")
		return
	var changed: bool = candidate.developer_mode != settings.settings.developer_mode
	if changed and (running or preparing):
		settings_dialog.fail("切换模式前请先结束尝试，并等待自动检查完成。")
		return
	settings_busy = true
	keys.clear()
	await send_controls()
	if changed:
		fence_developer()
	var result = await write_settings(revision, candidate)
	settings_busy = false
	if result.has("error"):
		settings_dialog.fail(str(result.error) + " 关闭后重新打开设置可读取最新版本。")
		if changed:
			await reload_session()
		return
	settings = result
	settings_dialog.hide()
	if result.mode_changed:
		await reload_session()
	else:
		world.apply_preferences(settings.settings, true)
		refresh_settings_ui()
		refresh_inspector()
	message("设置已保存到 YAML。" + ("开发者模式：不记录正式通关。" if settings.settings.developer_mode else "玩家模式：按正式进度解锁。"))

func write_settings(revision: String, candidate: Dictionary) -> Dictionary:
	var value = candidate.duplicate(true)
	# Godot JSON parses numbers as floats; retain the version-1 YAML integer contract.
	if typeof(value.get("version")) not in [TYPE_INT, TYPE_FLOAT] or value.version != 1:
		return {"error": "不支持此设置版本。"}
	value.version = int(value.version)
	return await request("/api/settings", {"revision": revision, "settings": value})

func toggle_layer(key: String, enabled: bool) -> void:
	if not world.policy.set_layer(key, enabled):
		refresh_settings_ui()
		return
	refresh_settings_ui()
	pending_layers = world.policy.values.duplicate(true)
	if layer_save_busy:
		return
	layer_save_busy = true
	while not pending_layers.is_empty():
		var selected = pending_layers
		pending_layers = {}
		var candidate: Dictionary = settings.settings.duplicate(true)
		for layer in selected:
			if world.policy.allowed(layer):
				candidate.layers[layer] = selected[layer]
		var result = await write_settings(settings.revision, candidate)
		if result.has("error"):
			pending_layers.clear()
			message("图层保存失败：" + str(result.error))
			break
		settings = result
	layer_save_busy = false

func show_inspector() -> void:
	if modal_open():
		return
	keys.clear()
	await send_controls()
	refresh_inspector()
	inspector.popup_centered_ratio(float(options.tools.dialog_ratio))

func refresh_inspector() -> void:
	var debug: Dictionary = world.developer.latest if not grant_suspended and settings.get("settings", {}).get("developer_mode", false) else {}
	inspector.accept(world.data.messages(debug, attempt))

func poll_developer() -> void:
	if not connected or grant_suspended or developer_busy or not settings.settings.developer_mode:
		return
	developer_busy = true
	var epoch = grant_epoch
	var session = profile.run_id
	var value = await backend.call_api("/api/developer")
	developer_busy = false
	if epoch != grant_epoch or grant_suspended or not connected or session != profile.run_id:
		return
	if value.has("error"):
		world.clear_developer_data()
		inspector.revoke()
		if value.error == "UNAUTHORIZED":
			fence_developer()
			await reload_session()
		return
	if value.get("run_id") == session:
		world.developer.accept(value)
		refresh_inspector()

func poll_settings() -> void:
	if not connected or settings_busy or transaction_busy or layer_save_busy:
		return
	var epoch = grant_epoch
	var previous_revision: String = settings.revision
	var current = await backend.call_api("/api/settings")
	if current.has("error") or epoch != grant_epoch or settings_busy or layer_save_busy or settings.revision != previous_revision:
		return
	if current.settings.developer_mode != settings.settings.developer_mode:
		fence_developer()
		settings_dialog.hide()
		await reload_session()
	elif current.revision != settings.revision and not settings_dialog.visible:
		settings = current
		keys.clear()
		world.apply_preferences(settings.settings, true)
		refresh_settings_ui()

func level_name(level_id: String, title: String = "", code_only: bool = false) -> String:
	var entry: Dictionary = {}
	for level in profile.campaign.levels:
		if level.level_id == level_id:
			entry = level
			break
	if entry.is_empty():
		return level_id
	var chapter_title = str(entry.chapter_id)
	var legacy_code = level_id.get_slice(".", level_id.get_slice_count(".") - 1).to_upper()
	var local_code = legacy_code
	for chapter in profile.campaign.chapters:
		if chapter.chapter_id == entry.chapter_id:
			chapter_title = str(chapter.title)
			var index = chapter.levels.find(level_id)
			if index >= 0:
				local_code = "C%d" % index
			break
	var display_code = chapter_title + "." + local_code
	if code_only:
		return display_code
	if title.is_empty():
		title = str(entry.title)
	for prefix in [legacy_code, chapter_title + " " + legacy_code, chapter_title + "." + legacy_code, local_code, chapter_title + " " + local_code, display_code]:
		if title.begins_with(prefix + " · "):
			title = title.trim_prefix(prefix + " · ")
			break
	return display_code + " · " + title

func lesson_text() -> String:
	var lesson = learning.get("lesson", {})
	var result = level_name(profile.campaign.active_level, str(lesson.get("title", ""))) + "\n\n" + str(lesson.get("summary", "")) + "\n\n"
	for step in lesson.get("steps", []):
		result += "• " + str(step) + "\n"
	result += "\n" + str(lesson.get("execution", "")) + "\n" + str(lesson.get("completion", ""))
	result += "\n\n函数 / 类型 / 标定\n" + JSON.stringify(lesson.get("functions", []), "  ") + "\n" + JSON.stringify(lesson.get("calibration", {}), "  ")
	result += "\n\n测试范围\n" + JSON.stringify(learning.get("testing", {}), "  ")
	return result

func accept_snapshot(value: Dictionary) -> void:
	snapshot = value

func open_editor() -> void:
	keys.clear()
	await send_controls()
	var value = await request("/api/workspace/external_open", {})
	if not value.has("error"):
		editable_directory = value.directory
		message(value.message + "  " + editable_directory)
	get_viewport().gui_release_focus()

func show_guide() -> void:
	keys.clear()
	await send_controls()
	guide_dialog.popup_centered_ratio(0.9)

func preview_upgrade() -> void:
	if running or transaction_busy:
		return
	plan = await request("/api/workspace/external_upgrade", {})
	if plan.has("error"):
		return
	var preview = "已有算法保留。下列框架文件经确认后更新；原源码版本仍可恢复。\n"
	for entry in plan.entries:
		preview += "\n=== " + entry.path + " [" + entry.action + "] ===\n原内容：\n" + str(entry.get("current", "")) + "\n建议：\n" + str(entry.incoming) + "\n"
	plan_text.text = preview
	plan_dialog.popup_centered_ratio(0.85)

func apply_upgrade() -> void:
	var resolutions: Dictionary = {}
	for entry in plan.entries:
		resolutions[entry.path] = "incoming"
	var value = await request("/api/workspace/external_apply", {"revision": plan.base_revision, "plan_id": plan.plan_id, "resolutions": resolutions})
	if not value.has("error"):
		accept_snapshot(value)
		await start_level()

func choose_level(_index: int) -> void:
	if transaction_busy or running:
		return
	transaction_busy = true
	keys.clear()
	var value = await request("/api/campaign/start", {"level_id": levels.get_item_metadata(levels.selected)})
	if not value.has("error"):
		await reload_session()
	transaction_busy = false

func start_level() -> void:
	if transaction_busy or running:
		return
	transaction_busy = true
	keys.clear()
	var value = await request("/api/campaign/run", {"level_id": levels.get_item_metadata(levels.selected)})
	if not value.has("error"):
		await reload_session()
	transaction_busy = false
	var launch = value.get("player_start")
	if launch and str(launch.get("error", "")).begins_with("TEACHING_TEMPLATE_UPGRADE_REQUIRED"):
		await preview_upgrade()

func finish_attempt() -> void:
	keys.clear()
	status_epoch += 1
	var result = await request("/api/campaign/finish", {})
	if not result.has("error") and result.get("run_id") == profile.run_id:
		status_epoch += 1
		running = false
		preparing = false
		attempt = result.get("attempt", {})
		world.task = attempt
		update_mission()
	await poll_status()

func poll_view() -> void:
	if view_busy or not connected:
		return
	view_busy = true
	var value = await request("/api/view")
	if not value.has("error") and value.get("run_id") == profile.run_id:
		world.accept(value)
		refresh_inspector()
	view_busy = false

func poll_status() -> void:
	if status_busy or not connected:
		return
	status_busy = true
	var session = profile.run_id
	var epoch = status_epoch
	var status = await request("/api/deployment")
	var campaign = await request("/api/campaign")
	if epoch != status_epoch or session != profile.run_id or status.get("run_id") != session or campaign.get("run_id") != session:
		status_busy = false
		return
	deployment = status
	attempt = campaign.get("attempt", {}) if campaign.get("attempt") else {}
	running = attempt.get("phase") == "running" or (attempt.get("status") == "active" and status.get("active") != null)
	var launch = status.get("player_start")
	preparing = status.get("job") != null or (launch != null and launch.get("phase") in ["Checking", "Starting"])
	start_button.disabled = running or preparing or transaction_busy
	upgrade_button.disabled = running or preparing or transaction_busy
	levels.disabled = running or preparing or transaction_busy
	settings_dialog.mode_locked = running or preparing
	settings_dialog.developer.disabled = running or preparing or settings_dialog.busy
	var phase = str(launch.get("phase", "")) if launch else ""
	if phase != last_launch_phase:
		last_launch_phase = phase
		if phase == "Failed":
			message(str(launch.get("error", "程序启动失败；修正并保存后再次点击 Start。")))
		elif phase in ["Checking", "Starting"]:
			message("正在自动检查并启动已保存版本… 无需额外点击测试或部署。")
		elif phase == "Running":
			message("程序已运行 · revision " + str(launch.revision).substr(0, 12) + "。VS Code 后续修改在下次 Start 生效。")
		elif phase in ["Finished", "Cancelled"]:
			message("本次尝试已结束。修改并保存后可再次 Start。")
	status_text.text = "%s · %s · %s · %.1f s · 原生 profile %s" % ["开发者模式" if settings.settings.developer_mode else "玩家模式", level_name(profile.campaign.active_level, "", true), attempt.get("status", "sandbox"), attempt.get("timing", {}).get("remaining_s", 0), profile.runtime_execution_profile.profile_id]
	world.task = attempt
	refresh_inspector()
	update_mission()
	var output = ""
	for entry in status.get("logs", {}).get("entries", []):
		output += "[%s tick=%s %s]\n%s" % [entry.get("source", "runtime"), entry.get("tick", "?"), str(entry.get("revision", "")).substr(0, 10), entry.text]
	if output != last_log:
		last_log = output
		logs.text = output
		logs.scroll_vertical = logs.get_line_count()
	status_busy = false

func update_mission() -> void:
	var text = task_text()
	if mission.text == text:
		return
	var vertical = mission.scroll_vertical
	var horizontal = mission.scroll_horizontal
	mission.text = text
	mission.scroll_vertical = vertical
	mission.scroll_horizontal = horizontal

func task_text() -> String:
	var result = str(learning.get("lesson", {}).get("summary", "")) + "\n\n"
	for level in profile.campaign.levels:
		if level.level_id == profile.campaign.active_level:
			result += level.problem + "\n\n"
			for hint in level.hints:
				result += "• " + str(hint) + "\n"
	result += "\n状态：" + str(attempt.get("status", "准备中"))
	if attempt.get("player_hp") != null:
		result += "\n我方 HP：" + str(attempt.player_hp)
	if attempt.get("enemy_hp") != null:
		result += "\n敌方 HP：" + str(attempt.enemy_hp)
	if attempt.get("live_metrics"):
		result += "\n\n授权误差指标\n" + JSON.stringify(attempt.live_metrics, "  ")
	if attempt.get("result"):
		result += "\n\n最终报告\n" + JSON.stringify(attempt.result, "  ")
	result += "\n\n按键：" + str(settings.settings.keyboard)
	result += world.sensor_summary()
	return result

func dom_code(event: InputEventKey) -> String:
	return Keyboard.code(event)

func _input(event: InputEvent) -> void:
	if not connected or not event is InputEventKey:
		return
	var code = dom_code(event)
	if settings_dialog.visible:
		settings_dialog.handle_input(event)
		return
	if code == settings.settings.keyboard.settings and event.pressed and not event.echo:
		show_settings()
		get_viewport().set_input_as_handled()
		return
	if modal_open():
		return
	if code == settings.settings.keyboard.editor and event.pressed and not event.echo:
		open_editor()
		get_viewport().set_input_as_handled()
		return
	if code == settings.settings.keyboard.get("help", "") and event.pressed and not event.echo:
		show_guide()
		get_viewport().set_input_as_handled()
		return
	if not event.echo:
		keys[code] = event.pressed
	if code == settings.settings.keyboard.fire and event.pressed and not event.echo and profile.control_sources.weapon == "keyboard":
		request("/api/fire", {"request_id": "godot-" + str(Time.get_ticks_usec())})

func pressed(action: String) -> float:
	return 1.0 if keys.get(settings.settings.keyboard.get(action, ""), false) else 0.0

func send_controls() -> void:
	if command_busy or not connected or attempt.get("phase") == "finished":
		return
	command_busy = true
	if modal_open():
		keys.clear()
	var vx = (pressed("forward") - pressed("backward")) * float(profile.view.keyboard_linear_mps)
	var vy = (pressed("left") - pressed("right")) * float(profile.view.keyboard_linear_mps)
	var wz = (pressed("turn_left") - pressed("turn_right")) * float(profile.view.keyboard_yaw_radps)
	if profile.chassis == "differential":
		wz += (pressed("left") - pressed("right")) * float(profile.view.keyboard_yaw_radps)
		vy = 0.0
	if profile.control_sources.chassis == "keyboard":
		await request("/api/cmd_vel", {"linear": {"x": vx, "y": vy, "z": 0}, "angular": {"x": 0, "y": 0, "z": wz}})
	if profile.control_sources.turret == "keyboard":
		await request("/api/turret_cmd_vel", {"velocity_radps": (pressed("turret_left") - pressed("turret_right")) * float(profile.view.keyboard_turret_radps)})
	command_busy = false

func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT:
		keys.clear()
		if connected:
			send_controls()
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		get_tree().quit()
