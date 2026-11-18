extends RefCounted
## One client-only palette for controls, dialogs and layout surfaces.

static func box(spec: Dictionary, color_key: String, padding: Vector2, outlined: bool = true) -> StyleBoxFlat:
	var style = StyleBoxFlat.new()
	style.bg_color = Color(spec.colors[color_key])
	style.border_color = Color(spec.colors.border)
	style.set_border_width_all(int(spec.metrics.border_width) if outlined else 0)
	style.set_corner_radius_all(int(spec.metrics.corner_radius))
	style.content_margin_left = padding.x
	style.content_margin_right = padding.x
	style.content_margin_top = padding.y
	style.content_margin_bottom = padding.y
	return style

static func buttons(result: Theme, spec: Dictionary, type_name: String, prefix: String, text_key: String) -> void:
	var padding = Vector2(spec.metrics.button_padding_horizontal, spec.metrics.button_padding_vertical)
	for state in ["normal", "hover", "pressed", "disabled", "hover_pressed"]:
		var fill = "button_disabled" if state == "disabled" else prefix + ("pressed" if state == "hover_pressed" else state)
		result.set_stylebox(state, type_name, box(spec, fill, padding, false))
	for state in ["font_color", "font_hover_color", "font_pressed_color", "font_hover_pressed_color", "font_focus_color"]:
		result.set_color(state, type_name, Color(spec.colors[text_key]))
	result.set_color("font_disabled_color", type_name, Color(spec.colors.disabled_text))
	# OptionButton arrows use these colors as well as text.
	result.set_color("icon_normal_color", type_name, Color(spec.colors[text_key]))
	result.set_color("icon_hover_color", type_name, Color(spec.colors[text_key]))
	result.set_color("icon_pressed_color", type_name, Color(spec.colors[text_key]))
	result.set_color("icon_disabled_color", type_name, Color(spec.colors.disabled_text))
	var focus = box(spec, "focus", padding)
	focus.draw_center = false
	focus.border_color = Color(spec.colors.focus)
	focus.set_border_width_all(int(spec.metrics.focus_width))
	result.set_stylebox("focus", type_name, focus)

static func create(spec: Dictionary, font_size: int) -> Theme:
	var result = Theme.new()
	var c: Dictionary = spec.colors
	var m: Dictionary = spec.metrics
	result.default_font_size = font_size
	result.set_color("font_color", "Label", Color(c.text))
	for variant in ["HeadingLabel", "BrandLabel", "MutedLabel", "SmallLabel"]:
		result.set_type_variation(variant, "Label")
	result.set_font_size("font_size", "HeadingLabel", int(m.heading_font_size))
	result.set_font_size("font_size", "BrandLabel", int(m.brand_font_size))
	result.set_font_size("font_size", "SmallLabel", int(m.small_font_size))
	result.set_color("font_color", "MutedLabel", Color(c.muted))
	result.set_color("font_color", "SmallLabel", Color(c.muted))
	for container in ["VBoxContainer", "HBoxContainer", "HSplitContainer"]:
		result.set_constant("separation", container, int(m.gap))
	for axis in ["h_separation", "v_separation"]:
		result.set_constant(axis, "HFlowContainer", int(m.small_gap))
	for variant in ["StartButton", "StopButton", "LayerToggle"]:
		result.set_type_variation(variant, "Button")
	buttons(result, spec, "Button", "button_", "button_text")
	buttons(result, spec, "OptionButton", "button_", "button_text")
	result.set_constant("modulate_arrow", "OptionButton", 1)
	buttons(result, spec, "StartButton", "start_", "start_text")
	buttons(result, spec, "StopButton", "stop_", "stop_text")
	buttons(result, spec, "LayerToggle", "button_", "button_text")
	var toggle_padding = Vector2(m.toggle_padding_horizontal, m.small_gap)
	for state in ["normal", "hover"]:
		result.set_stylebox(state, "LayerToggle", box(spec, "button_" + state, toggle_padding, false))
	for state in ["pressed", "hover_pressed"]:
		result.set_stylebox(state, "LayerToggle", box(spec, "start_" + ("hover" if state == "hover_pressed" else "normal"), toggle_padding, false))
		result.set_color("font_" + state + "_color", "LayerToggle", Color(c.start_text))
	result.set_font_size("font_size", "LayerToggle", int(m.small_font_size))
	for variant in ["CardPanel", "ViewportPanel", "StatusPanel"]:
		result.set_type_variation(variant, "PanelContainer")
		result.set_stylebox("panel", variant, box(spec, "panel", Vector2(m.panel_padding, m.panel_padding)))
	result.set_type_variation("AppPanel", "Panel")
	result.set_stylebox("panel", "AppPanel", box(spec, "background", Vector2.ZERO, false))
	var inset = box(spec, "inset", Vector2(m.panel_padding, m.panel_padding))
	for state in ["normal", "read_only"]:
		result.set_stylebox(state, "TextEdit", inset)
	for item in ["font_color", "font_readonly_color", "caret_color"]:
		result.set_color(item, "TextEdit", Color(c.text))
	result.set_color("selection_color", "TextEdit", Color(c.selection))
	result.set_constant("line_spacing", "TextEdit", int(m.line_spacing))
	for scrollbar in ["VScrollBar", "HScrollBar"]:
		var track = box(spec, "scroll_track", Vector2.ZERO, false)
		var vertical: bool = scrollbar == "VScrollBar"
		track.content_margin_left = float(m.scrollbar_width) if vertical else 0.0
		track.content_margin_top = 0.0 if vertical else float(m.scrollbar_width)
		result.set_stylebox("scroll", scrollbar, track)
		result.set_stylebox("scroll_focus", scrollbar, track)
		for state in ["grabber", "grabber_highlight", "grabber_pressed"]:
			result.set_stylebox(state, scrollbar, box(spec, "scroll_grabber" if state == "grabber" else "scroll_hover", Vector2.ZERO, false))
	result.set_stylebox("panel", "PopupMenu", box(spec, "panel", Vector2(m.panel_padding, m.panel_padding)))
	result.set_stylebox("hover", "PopupMenu", box(spec, "button_hover", Vector2(m.small_gap, m.small_gap), false))
	result.set_color("font_color", "PopupMenu", Color(c.text))
	result.set_color("font_hover_color", "PopupMenu", Color(c.button_text))
	result.set_color("font_disabled_color", "PopupMenu", Color(c.muted))
	result.set_constant("v_separation", "PopupMenu", int(m.small_gap))
	result.set_stylebox("panel", "TooltipPanel", box(spec, "button_normal", Vector2(m.small_gap, m.small_gap), false))
	result.set_color("font_color", "TooltipLabel", Color(c.button_text))
	return result
