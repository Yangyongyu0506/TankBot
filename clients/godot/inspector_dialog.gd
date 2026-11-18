extends AcceptDialog
signal closed
var tools: Dictionary
var topics = OptionButton.new()
var content = TextEdit.new()
var reveal = CheckButton.new()
var values: Dictionary = {}
var selected: String = ""

func configure(spec: Dictionary) -> void:
	tools = spec
	title = "数据查看器 · 授权消息 / 开发者诊断"
	ok_button_text = "关闭"
	var column = VBoxContainer.new()
	add_child(column)
	var toolbar = HBoxContainer.new()
	column.add_child(toolbar)
	topics.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	topics.item_selected.connect(func(index):
		selected = topics.get_item_metadata(index)
		refresh())
	toolbar.add_child(topics)
	reveal.text = "显示内容"
	reveal.button_pressed = true
	reveal.toggled.connect(func(_value): refresh())
	toolbar.add_child(reveal)
	content.editable = false
	content.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	column.add_child(content)
	visibility_changed.connect(func():
		if visible:
			refresh()
		else:
			closed.emit())

func accept(data: Dictionary) -> void:
	values = data
	var names = PackedStringArray(data.keys())
	var previous = PackedStringArray()
	for index in range(topics.item_count):
		previous.append(topics.get_item_metadata(index))
	if previous != names:
		topics.clear()
		for key in names:
			topics.add_item(key)
			topics.set_item_metadata(topics.item_count - 1, key)
			if key == selected:
				topics.select(topics.item_count - 1)
		if selected not in data:
			selected = names[0] if not names.is_empty() else ""
	if visible:
		refresh()

func revoke() -> void:
	values.clear()
	selected = ""
	topics.clear()
	content.text = ""

func refresh() -> void:
	var text = "暂无获授权的消息。"
	if not reveal.button_pressed:
		text = "消息内容已隐藏。"
	elif values.has(selected):
		text = JSON.stringify(values[selected], "  ")
		if text.length() > int(tools.inspector_max_chars):
			text = text.substr(0, int(tools.inspector_max_chars)) + "\n…内容已截断（显示容量上限）"
	if text != content.text:
		var scroll = content.scroll_vertical
		content.text = text
		content.scroll_vertical = scroll
