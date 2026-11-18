extends RefCounted
## Physical-key names retain the existing YAML format; no new binding protocol.
static func code(event: InputEventKey) -> String:
	var key = event.physical_keycode if event.physical_keycode else event.keycode
	if key >= KEY_A and key <= KEY_Z:
		return "Key" + OS.get_keycode_string(key)
	if key >= KEY_0 and key <= KEY_9:
		return "Digit" + OS.get_keycode_string(key)
	if key >= KEY_KP_0 and key <= KEY_KP_9:
		return "Numpad%d" % (key - KEY_KP_0)
	var special = {KEY_SPACE: "Space", KEY_UP: "ArrowUp", KEY_DOWN: "ArrowDown", KEY_LEFT: "ArrowLeft", KEY_RIGHT: "ArrowRight"}
	return special.get(key, OS.get_keycode_string(key))

static func valid(value: String) -> bool:
	var pattern = RegEx.new()
	pattern.compile("^(Key[A-Z]|Digit[0-9]|Arrow(Up|Down|Left|Right)|Space|F([1-9]|1[0-2])|Numpad[0-9])$")
	return pattern.search(value) != null

static func label(value: String) -> String:
	if value.begins_with("Key"):
		return value.trim_prefix("Key")
	if value.begins_with("Digit"):
		return value.trim_prefix("Digit")
	return {"Space": "Space / 空格", "ArrowUp": "↑", "ArrowDown": "↓", "ArrowLeft": "←", "ArrowRight": "→"}.get(value, value)
