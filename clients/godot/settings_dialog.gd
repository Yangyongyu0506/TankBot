extends Control
const Keyboard = preload("res://keyboard.gd")
signal save_requested(revision: String, candidate: Dictionary)
var state: Dictionary = {}
var draft: Dictionary = {}
var tools: Dictionary = {}
var policy: RefCounted
var recording: String = ""
var busy: bool = false
var mode_locked: bool = false
var bindings: Dictionary = {}
var layer_checks: Dictionary = {}
var developer = CheckButton.new()
var note = Label.new()
var tabs = TabContainer.new()
var panel = PanelContainer.new()
var ok_button = Button.new()
var cancel_button = Button.new()
var close_button = Button.new()

func configure(spec: Dictionary) -> void:
	tools = spec
	visible = false
	z_index = 100
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var shade = ColorRect.new()
	shade.color = Color(spec.rendering.modal_shade)
	add_child(shade)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	panel.theme_type_variation = "CardPanel"
	add_child(panel)
	var inset = (1.0 - float(spec.dialog_ratio)) * 0.5
	panel.anchor_left = inset
	panel.anchor_top = inset
	panel.anchor_right = 1.0 - inset
	panel.anchor_bottom = 1.0 - inset
	visibility_changed.connect(func():
		if not visible:
			recording = "")
	var column = VBoxContainer.new()
	panel.add_child(column)
	var header = HBoxContainer.new()
	column.add_child(header)
	var title = Label.new()
	title.text = "设置"
	title.theme_type_variation = "HeadingLabel"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	close_button.text = "×"
	close_button.tooltip_text = "关闭并放弃未保存修改"
	close_button.pressed.connect(cancel)
	header.add_child(close_button)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(note)
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(tabs)
	var general = page("通用与模式")
	developer.text = "开发者模式"
	developer.toggled.connect(func(value): draft.developer_mode = value)
	general.add_child(developer)
	var description = Label.new()
	description.text = "开发者可自由选关并查看独立授权真值，不获得玩家通关记录。\n玩家程序权限不变。运行中仍计时；切换模式前请先结束尝试。\nVS Code 保存的文件、历史版本和正式进度会保留。"
	description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	general.add_child(description)
	var paths = Label.new()
	paths.name = "paths"
	paths.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	general.add_child(paths)
	var keyboard = page("键位映射")
	for action in tools.actions:
		var row = HBoxContainer.new()
		keyboard.add_child(row)
		var text = Label.new()
		text.text = tools.actions[action]
		text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(text)
		var button = Button.new()
		bindings[action] = button
		button.pressed.connect(func(): capture(action))
		row.add_child(button)
	var reset = Button.new()
	reset.text = "恢复默认键位"
	reset.pressed.connect(reset_bindings)
	keyboard.add_child(reset)
	var layers = page("图层")
	var hint = Label.new()
	hint.text = "玩家只列出本关授权图层；不可切换项由课程固定。开发者可独立选择所有图层。"
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	layers.add_child(hint)
	for key in tools.layers:
		var check = CheckButton.new()
		check.text = tools.layers[key]
		check.toggled.connect(func(value): draft.layers[key] = value)
		layer_checks[key] = check
		layers.add_child(check)
	var footer = HBoxContainer.new()
	footer.alignment = BoxContainer.ALIGNMENT_END
	column.add_child(footer)
	cancel_button.text = "取消"
	cancel_button.pressed.connect(cancel)
	footer.add_child(cancel_button)
	ok_button.text = "保存设置"
	ok_button.theme_type_variation = "StartButton"
	ok_button.pressed.connect(submit)
	footer.add_child(ok_button)

func get_ok_button() -> Button:
	return ok_button

func get_cancel_button() -> Button:
	return cancel_button

func cancel() -> void:
	if not busy:
		hide()

func page(label: String) -> VBoxContainer:
	var scroll = ScrollContainer.new()
	scroll.name = label
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	tabs.add_child(scroll)
	var column = VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(column)
	return column

func open(value: Dictionary, displays: RefCounted, locked: bool) -> void:
	state = value.duplicate(true)
	draft = state.settings.duplicate(true)
	policy = displays
	for key in policy.values:
		draft.layers[key] = policy.values[key] if policy.allowed(key) else draft.layers.get(key, false)
	mode_locked = locked
	recording = ""
	busy = false
	developer.set_pressed_no_signal(draft.developer_mode)
	developer.disabled = locked
	developer.tooltip_text = "请先结束尝试并等待自动检查完成。" if locked else ""
	for key in layer_checks:
		var check: CheckButton = layer_checks[key]
		check.visible = policy.allowed(key)
		check.disabled = not policy.toggleable(key)
		check.set_pressed_no_signal(draft.layers.get(key, false))
	var paths = tabs.find_child("paths", true, false)
	paths.text = "设置 YAML：" + str(state.settings_file) + "\n进度文件：" + str(state.progress_file)
	note.text = "修改后保存生效。键位捕获期间 Esc 取消；关闭窗口会放弃未保存修改。"
	refresh_bindings()
	get_ok_button().disabled = false
	cancel_button.disabled = false
	close_button.disabled = false
	show()

func refresh_bindings() -> void:
	for action in bindings:
		bindings[action].text = "请按一个键…" if recording == action else Keyboard.label(draft.keyboard[action])

func capture(action: String) -> void:
	if busy:
		return
	recording = action
	note.text = "按下新的物理按键；Esc 取消。不支持重复键位或组合键。"
	refresh_bindings()

func handle_input(event: InputEvent) -> void:
	if not visible or not event is InputEventKey:
		return
	if not event.pressed or event.echo:
		return
	if busy:
		get_viewport().set_input_as_handled()
		return
	if event.keycode == KEY_ESCAPE:
		if recording.is_empty():
			hide()
		else:
			recording = ""
			refresh_bindings()
		get_viewport().set_input_as_handled()
		return
	var code = Keyboard.code(event)
	if not recording.is_empty():
		get_viewport().set_input_as_handled()
		if not Keyboard.valid(code) or event.ctrl_pressed or event.alt_pressed or event.meta_pressed or event.shift_pressed:
			note.text = "请选择字母、数字、方向键、空格、F1–F12 或小键盘数字，不使用组合键。"
			return
		for action in draft.keyboard:
			if action != recording and draft.keyboard[action] == code:
				note.text = "此键已用于“" + str(tools.actions[action]) + "”，请先更换该操作。"
				return
		draft.keyboard[recording] = code
		recording = ""
		note.text = "键位已修改，保存后生效。"
		refresh_bindings()
	elif code == state.settings.keyboard.settings:
		hide()
		get_viewport().set_input_as_handled()

func reset_bindings() -> void:
	if not busy:
		draft.keyboard = state.defaults.keyboard.duplicate(true)
		recording = ""
		refresh_bindings()

func submit() -> void:
	if busy or not recording.is_empty():
		return
	if mode_locked and draft.developer_mode != state.settings.developer_mode:
		fail("请先结束尝试再切换模式。")
		return
	busy = true
	get_ok_button().disabled = true
	cancel_button.disabled = true
	close_button.disabled = true
	save_requested.emit(state.revision, draft.duplicate(true))

func fail(error: String) -> void:
	busy = false
	get_ok_button().disabled = false
	cancel_button.disabled = false
	close_button.disabled = false
	note.text = error
