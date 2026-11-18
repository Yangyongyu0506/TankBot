extends RefCounted
## This selects displays only. Data is already cropped by the Authority.
var developer: bool = false
var level: Dictionary = {}
var values: Dictionary = {}
var labels: Dictionary = {}

func configure(profile: Dictionary, preferences: Dictionary, names: Dictionary) -> void:
	developer = preferences.get("developer_mode", false)
	labels = names
	level = {}
	for entry in profile.campaign.levels:
		if entry.level_id == profile.campaign.active_level:
			level = entry
	var visualization: Dictionary = level.get("visualization", {})
	values.clear()
	for key in labels:
		var saved: bool = preferences.get("layers", {}).get(key, false)
		var initial: bool = key in visualization.get("initial_enabled", [])
		var keep: bool = visualization.get("preserve_user_settings", true)
		values[key] = allowed(key) and (saved if keep or (developer and key not in level.get("allowed_layers", [])) else initial)

func allowed(key: String) -> bool:
	return labels.has(key) and (developer or key in level.get("allowed_layers", []))

func toggleable(key: String) -> bool:
	return allowed(key) and (developer or key in level.get("visualization", {}).get("user_toggleable", []))

func enabled(key: String) -> bool:
	return allowed(key) and values.get(key, false)

func set_layer(key: String, value: bool) -> bool:
	if not toggleable(key):
		return false
	values[key] = value
	return true
