extends Control
const Backend = preload("res://backend.gd")
const WorldView = preload("res://world_view.gd")
var backend = Backend.new()
var world = WorldView.new()
var options: Dictionary
var profile: Dictionary = {}
var settings: Dictionary = {}
var snapshot: Dictionary = {}
var files: Dictionary = {}
var learning: Dictionary = {}
var deployment: Dictionary = {}
var attempt: Dictionary = {}
var selected_path: String = ""
var keys: Dictionary = {}
var file_items: Dictionary = {}
var running: bool = false
var pending_deploy: String = ""
var status_busy: bool = false
var view_busy: bool = false
var command_busy: bool = false
var transaction_busy: bool = false
var ready_revision: String = ""
var last_log: String = ""
var connected: bool = false
var plan: Dictionary = {}
var editor_panel = PanelContainer.new()
var editor = CodeEdit.new()
var tree = Tree.new()
var levels = OptionButton.new()
var status_text = Label.new()
var mission = TextEdit.new()
var guide = TextEdit.new()
var logs = TextEdit.new()
var editor_logs = TextEdit.new()
var message_text = Label.new()
var path_label = Label.new()
var edit_button: Button
var test_button: Button
var deploy_button: Button
var plan_dialog = ConfirmationDialog.new()
var plan_text = TextEdit.new()
var quit_dialog = ConfirmationDialog.new()

func _ready() -> void:
	get_tree().auto_accept_quit = false
	var arguments: Dictionary = {}
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--") and "=" in argument:
			arguments[argument.get_slice("=", 0)] = argument.substr(argument.find("=")+1)
	if not arguments.has("--client-settings"):
		push_error("请通过 python3 tools/tankbot.py godot 启动客户端。")
		get_tree().quit(2)
		return
	options = JSON.parse_string(FileAccess.get_file_as_string(arguments["--client-settings"]))
	add_child(backend)
	if not backend.configure(arguments.get("--backend-url", ""), options):
		get_tree().quit(2)
		return
	get_window().title = options.title
	get_window().size = Vector2i(options.window_width, options.window_height)
	theme = Theme.new()
	theme.default_font_size = int(options.font_size)
	add_theme_font_size_override("font_size", int(options.font_size))
	build_ui()
	await reload_session()
	if not connected:
		return
	start_timer(float(profile.view.poll_ms)/1000.0, poll_view)
	start_timer(float(options.status_poll_ms)/1000.0, poll_status)
	start_timer(float(profile.view.keyboard_refresh_ms)/1000.0, send_controls)

func button(parent: Node, text: String, action: Callable) -> Button:
	var node = Button.new()
	node.text = text
	node.focus_mode = Control.FOCUS_NONE
	node.pressed.connect(action)
	parent.add_child(node)
	return node

func full(node: Control) -> void:
	node.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

func text_box(node: TextEdit) -> void:
	node.editable = false
	node.add_theme_color_override("font_readonly_color", Color("d9e2ef"))
	var surface = StyleBoxFlat.new()
	surface.bg_color = Color("101b29")
	node.add_theme_stylebox_override("normal", surface)
	node.add_theme_stylebox_override("read_only", surface)
	node.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	node.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	node.size_flags_vertical = Control.SIZE_EXPAND_FILL

func build_ui() -> void:
	var root = VBoxContainer.new()
	add_child(root)
	full(root)
	var toolbar = HBoxContainer.new()
	root.add_child(toolbar)
	button(toolbar, "TankBot · Godot", func(): message("桌面原型 · 玩家 CPython 独立进程 · 仅运行本人可信代码"))
	levels.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	toolbar.add_child(levels)
	button(toolbar, "开始 / 重试", start_level)
	button(toolbar, "结束尝试", finish_attempt)
	edit_button = button(toolbar, "代码编辑器 · F2", toggle_editor)
	root.add_child(status_text)
	status_text.text = "连接本机 Authority…"
	var content = HSplitContainer.new()
	content.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(content)
	world.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	world.size_flags_vertical = Control.SIZE_EXPAND_FILL
	world.clip_contents = true
	world.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_child(world)
	var sidebar = VBoxContainer.new()
	sidebar.custom_minimum_size.x = int(options.file_tree_width)
	content.add_child(sidebar)
	var heading = Label.new()
	heading.text = "任务与授权反馈"
	sidebar.add_child(heading)
	text_box(mission)
	sidebar.add_child(mission)
	var layers = HFlowContainer.new()
	sidebar.add_child(layers)
	for item in [["map", "地图"], ["robot", "车体"], ["projectiles", "炮弹"], ["target_estimates", "目标估计"], ["path", "路径"], ["radar", "局部雷达"]]:
		var check = CheckButton.new()
		check.text = item[1]
		check.button_pressed = true
		check.toggled.connect(func(enabled): world.layers[item[0]] = enabled)
		layers.add_child(check)
	text_box(logs)
	logs.custom_minimum_size.y = int(options.log_height)
	logs.size_flags_vertical = Control.SIZE_FILL
	root.add_child(logs)
	add_child(editor_panel)
	full(editor_panel)
	var background = StyleBoxFlat.new()
	background.bg_color = Color("101b29")
	editor_panel.add_theme_stylebox_override("panel", background)
	editor_panel.hide()
	var workspace = VBoxContainer.new()
	editor_panel.add_child(workspace)
	var actions = HBoxContainer.new()
	workspace.add_child(actions)
	button(actions, "保存 · Ctrl+S", save_files)
	test_button = button(actions, "测试快照", test_snapshot)
	deploy_button = button(actions, "部署已测试版本", deploy_snapshot)
	deploy_button.disabled = true
	button(actions, "框架升级预览", preview_upgrade)
	path_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	actions.add_child(path_label)
	button(actions, "× 关闭 · F2", toggle_editor)
	message_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	workspace.add_child(message_text)
	var split = HSplitContainer.new()
	split.size_flags_vertical = Control.SIZE_EXPAND_FILL
	workspace.add_child(split)
	var left = VBoxContainer.new()
	left.custom_minimum_size.x = int(options.file_tree_width)
	split.add_child(left)
	tree.hide_root = true
	tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tree.item_selected.connect(select_file)
	left.add_child(tree)
	var new_path = LineEdit.new()
	new_path.placeholder_text = "新文件：package/algorithm.py"
	left.add_child(new_path)
	button(left, "添加文件", func(): add_file(new_path.text))
	editor.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	editor.size_flags_vertical = Control.SIZE_EXPAND_FILL
	editor.gutters_draw_line_numbers = true
	editor.indent_automatic = true
	editor.indent_use_spaces = true
	editor.indent_size = 4
	editor.add_theme_font_size_override("font_size", int(options.font_size))
	editor.add_theme_color_override("font_color", Color("d9e2ef"))
	var mono = SystemFont.new()
	mono.font_names = PackedStringArray(["DejaVu Sans Mono", "Noto Sans Mono CJK SC", "monospace"])
	editor.add_theme_font_override("font", mono)
	editor.text_changed.connect(edit_changed)
	var highlighter = CodeHighlighter.new()
	highlighter.number_color = Color("e7b77e")
	highlighter.function_color = Color("9cd6d0")
	highlighter.member_variable_color = Color("d9e2ef")
	highlighter.symbol_color = Color("c6d5e6")
	highlighter.add_color_region("#", "", Color("8d9cae"), true)
	highlighter.add_color_region('"', '"', Color("9fe0b0"))
	highlighter.add_color_region("'", "'", Color("9fe0b0"))
	for keyword in ["class", "def", "return", "if", "elif", "else", "for", "while", "import", "from", "as", "raise", "try", "except", "None", "True", "False"]:
		highlighter.add_keyword_color(keyword, Color("92b9ff"))
	editor.syntax_highlighter = highlighter
	split.add_child(editor)
	text_box(guide)
	guide.custom_minimum_size.x = int(options.file_tree_width)
	split.add_child(guide)
	text_box(editor_logs)
	editor_logs.custom_minimum_size.y = int(options.log_height)
	editor_logs.size_flags_vertical = Control.SIZE_FILL
	workspace.add_child(editor_logs)
	add_child(plan_dialog)
	plan_dialog.title = "教学框架升级预览 · 确认后创建新 revision"
	plan_dialog.ok_button_text = "保留算法，应用此框架升级"
	plan_dialog.add_child(plan_text)
	text_box(plan_text)
	full(plan_text)
	plan_dialog.confirmed.connect(apply_upgrade)
	add_child(quit_dialog)
	quit_dialog.dialog_text = "还有未保存的源码。关闭会丢失当前草稿，已保存历史不受影响。"
	quit_dialog.ok_button_text = "放弃草稿并退出"
	quit_dialog.confirmed.connect(func(): get_tree().quit())

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
	connected = false
	mission.text = ""
	running = false
	pending_deploy = ""
	ready_revision = ""
	profile = await request("/api/profile")
	if profile.has("error"):
		status_text.text = "无法连接 Authority。"
		return
	backend.token = profile.control_token
	settings = await request("/api/settings")
	world.configure(profile)
	var project = await request("/api/workspace")
	if project.has("error"):
		return
	learning = project.learning
	accept_snapshot(project.snapshot)
	guide.text = lesson_text()
	var progress = await request("/api/progress")
	levels.clear()
	for level in profile.campaign.levels:
		var unlocked = progress.get("developer_mode", false) or level.level_id in progress.get("unlocked_levels", [])
		levels.add_item(level.title + (" [已通关]" if level.level_id in progress.get("completed_levels", []) else "" if unlocked else " [未解锁]"))
		var index = levels.item_count-1
		levels.set_item_metadata(index, level.level_id)
		levels.set_item_disabled(index, not unlocked)
		levels.set_item_tooltip(index, level.problem + "\n前置：" + str(level.prerequisites))
		if level.level_id == profile.campaign.active_level:
			levels.select(index)
	connected = true
	await poll_status()
	await poll_view()
	message("已连接原生 CPython。保存修改后测试；测试是接口短测，不等于闭环通关。")

func lesson_text() -> String:
	var lesson = learning.get("lesson", {})
	var result = str(lesson.get("title", "")) + "\n\n" + str(lesson.get("summary", "")) + "\n\n"
	for step in lesson.get("steps", []):
		result += "• " + str(step) + "\n"
	result += "\n" + str(lesson.get("execution", "")) + "\n" + str(lesson.get("completion", ""))
	result += "\n\n函数 / 类型 / 标定\n" + JSON.stringify(lesson.get("functions", []), "  ") + "\n" + JSON.stringify(lesson.get("calibration", {}), "  ")
	result += "\n\n测试范围\n" + JSON.stringify(learning.get("testing", {}), "  ")
	return result

func dirty() -> bool:
	return not snapshot.is_empty() and files != snapshot.files

func accept_snapshot(value: Dictionary) -> void:
	snapshot = value
	files = value.files.duplicate(true)
	ready_revision = ""
	tree.clear()
	file_items.clear()
	var root = tree.create_item()
	var directories = {"": root}
	var paths = files.keys()
	paths.sort()
	var highlighted = learning.get("lesson", {}).get("edit_files", [])
	if highlighted.is_empty():
		for entry in learning.get("lesson", {}).get("functions", []):
			highlighted.append(entry.path)
	for path in paths:
		var parent = ""
		var parts = path.split("/")
		for i in range(parts.size()):
			var current = parent + ("/" if parent else "") + parts[i]
			if not directories.has(current):
				var item = tree.create_item(directories[parent])
				item.set_text(0, parts[i])
				directories[current] = item
			if i == parts.size()-1:
				var item = directories[current]
				item.set_metadata(0, path)
				file_items[path] = item
				if path in highlighted:
					item.set_custom_color(0, Color("ffd27e"))
			parent = current
	var preferred = learning.get("lesson", {}).get("ui", {}).get("default_file", "")
	if not files.has(selected_path):
		selected_path = preferred if files.has(preferred) else paths[0]
	open_file(selected_path)

func open_file(path: String) -> void:
	selected_path = path
	editor.text = files[path]
	path_label.text = path + " · " + snapshot.revision.substr(0, 10)
	if file_items.has(path):
		file_items[path].select(0)

func select_file() -> void:
	var path = tree.get_selected().get_metadata(0)
	if path is String and path != selected_path:
		open_file(path)

func edit_changed() -> void:
	if not selected_path.is_empty():
		files[selected_path] = editor.text
	deploy_button.disabled = dirty() or ready_revision != snapshot.get("revision", "")
	path_label.text = selected_path + (" *" if dirty() else "")

func save_files() -> bool:
	if transaction_busy or running:
		return false
	# CodeEdit may defer text_changed until the next idle frame.
	if files.has(selected_path):
		files[selected_path] = editor.text
	if not dirty():
		return true
	transaction_busy = true
	var changes: Dictionary = {}
	for path in files:
		if files[path] != snapshot.files.get(path):
			changes[path] = files[path]
	var value = await request("/api/workspace/save", {"revision": snapshot.revision, "changes": changes})
	transaction_busy = false
	if value.has("error"):
		return false
	accept_snapshot(value)
	message("已原子保存新 revision；此前源码历史保留。")
	return true

func add_file(path: String) -> void:
	if path.is_empty() or files.has(path) or not await save_files():
		return
	var value = await request("/api/workspace/save", {"revision": snapshot.revision, "changes": {path: ""}})
	if not value.has("error"):
		accept_snapshot(value)
		open_file(path)

func test_snapshot() -> void:
	if not await save_files():
		return
	var value = await request("/api/deployment/test", {"revision": snapshot.revision})
	if not value.has("error"):
		message("独立 CPython 中测试此快照…")
		deploy_button.disabled = true

func deploy_snapshot() -> void:
	if dirty() or ready_revision != snapshot.revision:
		message("请先测试当前已保存快照。")
		return
	var value = await request("/api/deployment/deploy", {"revision": snapshot.revision})
	if not value.has("error"):
		pending_deploy = value.job.id
		message("启动候选版本；Active 后自动返回游戏。")

func preview_upgrade() -> void:
	if not await save_files():
		return
	plan = await request("/api/workspace/upgrade", {"revision": snapshot.revision})
	if plan.has("error"):
		return
	var preview = "仅应用下列系统升级建议；已有算法不在计划内。历史 revision 保留，可通过原工作区恢复。\n"
	for entry in plan.entries:
		preview += "\n=== " + entry.path + " [" + entry.action + "] ===\n原内容：\n" + str(entry.get("current", "")) + "\n建议：\n" + str(entry.incoming) + "\n"
	plan_text.text = preview
	plan_dialog.popup_centered_ratio(0.85)

func apply_upgrade() -> void:
	var resolutions: Dictionary = {}
	for entry in plan.entries:
		resolutions[entry.path] = "incoming"
	var value = await request("/api/workspace/apply", {"revision": plan.base_revision, "plan_id": plan.plan_id, "resolutions": resolutions})
	if not value.has("error"):
		accept_snapshot(value)
		message("已显式应用升级。请重新测试；此前版本仍在历史中。")

func toggle_editor() -> void:
	if not editor_panel.visible and running:
		message("运行期间不能编辑；请先结束尝试。")
		return
	keys.clear()
	await send_controls()
	editor_panel.visible = not editor_panel.visible
	if editor_panel.visible:
		editor.grab_focus()
	else:
		get_viewport().gui_release_focus()

func start_level() -> void:
	if dirty():
		message("切关 / 重试前请保存草稿。")
		return
	keys.clear()
	var value = await request("/api/campaign/start", {"level_id": levels.get_item_metadata(levels.selected)})
	if not value.has("error"):
		editor_panel.hide()
		await reload_session()

func finish_attempt() -> void:
	keys.clear()
	await request("/api/campaign/finish", {})
	await poll_status()

func poll_view() -> void:
	if view_busy or not connected:
		return
	view_busy = true
	var value = await request("/api/view")
	if not value.has("error") and value.get("run_id") == profile.run_id:
		world.accept(value)
	view_busy = false

func poll_status() -> void:
	if status_busy or not connected:
		return
	status_busy = true
	var session = profile.run_id
	var status = await request("/api/deployment")
	var campaign = await request("/api/campaign")
	if session != profile.run_id or status.get("run_id") != session or campaign.get("run_id") != session:
		status_busy = false
		return
	deployment = status
	attempt = campaign.get("attempt", {}) if campaign.get("attempt") else {}
	running = attempt.get("phase") == "running" or (attempt.get("status") == "active" and status.get("active") != null)
	var last = status.get("last")
	if last and last.get("status") == "Ready" and last.get("revision") == snapshot.revision:
		ready_revision = snapshot.revision
	deploy_button.disabled = dirty() or ready_revision != snapshot.revision or status.get("job") != null or running
	test_button.disabled = running or status.get("job") != null
	edit_button.disabled = running
	if last and last.get("status") == "Failed":
		message(str(last.get("error", "测试或部署失败")))
	if not pending_deploy.is_empty() and status.get("active") and status.active.deployment_id == pending_deploy:
		pending_deploy = ""
		editor_panel.hide()
		get_viewport().gui_release_focus()
		running = true
	if running:
		editor_panel.hide()
	status_text.text = "%s · %s · %.1f s · 原生 profile %s" % [profile.campaign.active_level, attempt.get("status", "sandbox"), attempt.get("timing", {}).get("remaining_s", 0), profile.runtime_execution_profile.profile_id]
	update_mission()
	var output = ""
	for entry in status.get("logs", {}).get("entries", []):
		output += "[%s tick=%s %s]\n%s" % [entry.get("source", "runtime"), entry.get("tick", "?"), str(entry.get("revision", "")).substr(0, 10), entry.text]
	if output != last_log:
		last_log = output
		logs.text = output
		editor_logs.text = output
		logs.scroll_vertical = logs.get_line_count()
		editor_logs.scroll_vertical = editor_logs.get_line_count()
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
	return result

func dom_code(event: InputEventKey) -> String:
	var key = event.physical_keycode if event.physical_keycode else event.keycode
	if key >= KEY_A and key <= KEY_Z:
		return "Key" + OS.get_keycode_string(key)
	if key == KEY_SPACE:
		return "Space"
	if key == KEY_ENTER:
		return "Enter"
	return OS.get_keycode_string(key)

func _input(event: InputEvent) -> void:
	if not connected or not event is InputEventKey:
		return
	var code = dom_code(event)
	if code == settings.settings.keyboard.editor and event.pressed and not event.echo:
		toggle_editor()
		get_viewport().set_input_as_handled()
		return
	if editor_panel.visible:
		if event.pressed and (event.ctrl_pressed or event.meta_pressed) and event.keycode == KEY_S:
			save_files()
			get_viewport().set_input_as_handled()
		return
	if not event.echo:
		keys[code] = event.pressed
	if code == settings.settings.keyboard.fire and event.pressed and not event.echo and profile.control_sources.weapon == "keyboard":
		request("/api/fire", {"request_id": "godot-" + str(Time.get_ticks_usec())})

func pressed(action: String) -> float:
	return 1.0 if keys.get(settings.settings.keyboard.get(action, ""), false) else 0.0

func send_controls() -> void:
	if command_busy or not connected:
		return
	command_busy = true
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
		if dirty():
			quit_dialog.popup_centered()
		else:
			get_tree().quit()
