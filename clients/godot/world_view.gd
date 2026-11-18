extends Control
## Drawing consumes only public profile and ViewGateway messages.
const Timeline = preload("res://timeline.gd")
const SpriteLibrary = preload("res://sprite_library.gd")
const VehicleSprite = preload("res://vehicle_sprite.gd")
const DisplayPolicy = preload("res://display_policy.gd")
const DisplayData = preload("res://display_data.gd")
const DeveloperOverlay = preload("res://developer_overlay.gd")
const DiagnosticOverlay = preload("res://diagnostic_overlay.gd")
var timeline = Timeline.new()
var sprites = SpriteLibrary.new()
var vehicle: Node2D
var entities: Dictionary = {}
var scene: Dictionary = {"pose": null, "objects": [], "turret": 0.0}
var profile: Dictionary = {}
var camera = Vector2.ZERO
var layers = {"map": true, "robot": true, "projectiles": true, "target_estimates": true, "path": true, "radar": true}
var scale_m: float = 1.0
var draw_pose: Variant = null
var tools: Dictionary = {}
var policy = DisplayPolicy.new()
var data = DisplayData.new()
var developer = DeveloperOverlay.new()
var diagnostics = DiagnosticOverlay.new()
var task: Dictionary = {}

func load_assets(value: Dictionary) -> bool:
	return sprites.configure(value)

func configure(value: Dictionary) -> void:
	clear_entities()
	profile = value
	data.configure(value, tools)
	policy.configure(value, {"developer_mode": false, "layers": {}}, tools.layers)
	for key in policy.values:
		policy.values[key] = policy.allowed(key) and key in policy.level.get("visualization", {}).get("initial_enabled", [])
	layers = policy.values
	task = {}
	timeline.configure(value)
	camera = Vector2(value.rendering.camera_origin_m[0], value.rendering.camera_origin_m[1])
	vehicle = VehicleSprite.new()
	vehicle.z_index = int(tools.rendering.draw_order.entities)
	vehicle.name = "player_vehicle"
	vehicle.configure(sprites, value.chassis_visual, value.body, value.wheel_calibration, value.weapons_enabled)
	vehicle.mount_barrel(sprites, vector(value.turret_muzzle_offset_m), value.rendering.barrel_width_m, Color(value.chassis_visual.colors.barrel))
	vehicle.visible = false
	add_child(vehicle)
	if developer.get_parent() == null:
		add_child(developer)
		add_child(diagnostics)
	developer.configure(self)
	diagnostics.configure(self)
	draw_pose = null
	scene = {"pose": null, "objects": [], "turret": 0.0}

func apply_preferences(preferences: Dictionary, apply_saved: bool = false) -> void:
	if not preferences.developer_mode:
		developer.revoke()
	policy.configure(profile, preferences, tools.layers)
	if apply_saved:
		for key in preferences.layers:
			if policy.toggleable(key):
				policy.values[key] = preferences.layers[key]
	layers = policy.values
	developer.enabled = preferences.developer_mode

func revoke_developer() -> void:
	developer.revoke()
	data.clear()

func clear_developer_data() -> void:
	developer.clear()

func clear_entities() -> void:
	if is_instance_valid(vehicle):
		vehicle.free()
	for entity in entities.values():
		entity.free()
	entities.clear()

func accept(message: Dictionary) -> void:
	data.accept(message)
	if timeline.push(message, Time.get_ticks_msec()):
		camera = Vector2(profile.rendering.camera_origin_m[0], profile.rendering.camera_origin_m[1])

func _process(_dt: float) -> void:
	if not profile.is_empty() and size.x > 0:
		scale_m = size.x / float(profile.rendering.viewport_width_m)
		scene = timeline.sample(Time.get_ticks_msec())
		draw_pose = scene.pose
		if draw_pose:
			camera = point(draw_pose)
		developer.update_frame(Time.get_ticks_msec(), timeline.render_ms)
		vehicle.visible = draw_pose != null and policy.enabled("robot")
		# A system-selected pose and its truth display represent the same body.
		var selected = timeline.latest.get("payload", {}).get("selected_pose")
		if selected != null and selected.source_id == "system" and developer.visible and is_instance_valid(developer.vehicle) and developer.vehicle.visible:
			vehicle.visible = false
		vehicle.self_modulate = entity_color()
		if vehicle.visible:
			vehicle.present(project(point(draw_pose)), float(draw_pose.yaw_rad), scale_m, float(scene.turret))
		sync_entities()
	queue_redraw()

func entity_color(tint: Color = Color.WHITE) -> Color:
	return Color(tint.r, tint.g, tint.b, float(tools.rendering.developer_entity_opacity) if developer.enabled else 1.0)

func sync_entities() -> void:
	var active: Dictionary = {}
	for object in scene.objects:
		var projectile: bool = object.kind == "projectile"
		if developer.enabled and not developer.latest.is_empty():
			continue
		if (projectile and not policy.enabled("projectiles")) or (not projectile and not policy.enabled("truth_targets")):
			continue
		var key = str([object.kind, object.get("projectile_id", object.get("target_id"))])
		active[key] = true
		if not entities.has(key):
			entities[key] = sprites.part(self, "projectile" if projectile else "target", Vector2.ONE)
		var sprite: Sprite2D = entities[key]
		sprite.z_index = int(tools.rendering.draw_order.entities)
		sprite.self_modulate = entity_color()
		var extent: Vector2
		if projectile:
			extent = Vector2.ONE * max(float(sprites.options.projectile_min_diameter_px), 2.0 * float(object.radius_m) * scale_m)
			sprite.position = project(point(object))
		else:
			var body: Dictionary = profile.target_geometry.body
			extent = Vector2(body.length_m, body.width_m) * scale_m
			sprite.position = project(point(object.pose))
			sprite.rotation = -float(object.pose.yaw_rad)
		sprite.scale = extent / sprite.texture.get_size()
	# Despawn, visibility changes and run resets cannot leave an old entity visible.
	for key in entities.keys():
		if not active.has(key):
			entities[key].free()
			entities.erase(key)

func project(point: Vector2) -> Vector2:
	return size * 0.5 + Vector2(point.x - camera.x, camera.y - point.y) * scale_m

func vector(data: Array) -> Vector2:
	return Vector2(data[0], data[1])

func point(pose: Dictionary) -> Vector2:
	return Vector2(pose.x_m, pose.y_m)

func plate(center: Vector2, length: float, width: float, yaw: float, color: Color) -> void:
	var vertices = PackedVector2Array()
	for corner in [Vector2(-1, -1), Vector2(1, -1), Vector2(1, 1), Vector2(-1, 1)]:
		vertices.append(project(center + Vector2(corner.x * length * 0.5, corner.y * width * 0.5).rotated(yaw)))
	draw_colored_polygon(vertices, color)

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("101b29"))
	if profile.is_empty():
		return
	var grid = float(profile.rendering.grid_spacing_m)
	var radius = max(size.x, size.y) / scale_m
	for axis in [0, 1]:
		var offset = camera.x if axis == 0 else camera.y
		for i in range(int(floor((offset-radius) / grid)), int(ceil((offset+radius) / grid)) + 1):
			var a = Vector2(i * grid, camera.y-radius) if axis == 0 else Vector2(camera.x-radius, i * grid)
			var b = Vector2(i * grid, camera.y+radius) if axis == 0 else Vector2(camera.x+radius, i * grid)
			draw_line(project(a), project(b), Color("1c3040"))
	if policy.enabled("map"):
		for wall in profile.walls:
			plate(vector(wall.center), wall.size[0], wall.size[1], 0.0, Color("65788e"))

func draw_observations(canvas: Node2D) -> void:
	if timeline.latest.is_empty():
		return
	if policy.enabled("target_estimates"):
		for message in timeline.latest.payload.get("target_estimates", []):
			var estimate = message.payload
			canvas.draw_arc(project(point(estimate)), profile.body.width_m * scale_m * 0.5, 0, TAU, 24, Color("e8ad58"), 2, true)
	# Body-frame observations remain available without a global pose. No truth projection.
	if policy.enabled("radar"):
		var style: Dictionary = tools.rendering
		var origin = Vector2(style.observation_origin_px[0], size.y-style.observation_origin_px[1])
		for observation in timeline.latest.payload.local_observations:
			if observation.schema in ["radar@1", "armor_detections@1"]:
				var observation_radius = float(style.observation_radius_px)
				canvas.draw_arc(origin, observation_radius, 0, TAU, int(style.observation_ring_segments), Color(style.scan), float(style.line_width_px), true)
				var calibration = profile.armor_calibration if observation.schema == "armor_detections@1" else profile.radar_calibration
				for hit in polar_hits(observation):
					var delta = Vector2(cos(hit[1]), -sin(hit[1])) * float(hit[0]) / float(calibration.range_m) * observation_radius
					canvas.draw_circle(origin + delta, float(style.point_radius_px), Color(style.gps))

func polar_hits(message: Dictionary) -> Array:
	if message.schema == "armor_detections@1":
		return message.payload.measurements_rt
	var hits: Array = []
	for detection in message.payload.detections:
		hits.append([detection.range_m, detection.bearing_rad])
	return hits

func arrow(canvas: Node2D, origin: Vector2, delta: Vector2, color: Color) -> void:
	var a = project(origin)
	var b = project(origin + delta)
	canvas.draw_line(a, b, color, float(tools.rendering.line_width_px), true)
	canvas.draw_circle(b, float(tools.rendering.point_radius_px), color)

func sensor_summary() -> String:
	var result = ""
	for message in data.latest.get("payload", {}).get("local_observations", []):
		var key = "encoders" if message.channel == "/robot/sensors/joint_states" else "imu" if message.schema == "imu@1" else "turret" if message.channel.begins_with("/robot/turret/") or message.schema == "weapon_state@1" else ""
		if not key.is_empty() and policy.enabled(key):
			result += "\n" + str(tools.layers[key]) + " [tick=" + str(message.simulation_tick) + "]\n" + JSON.stringify(message.payload)
	if policy.enabled("scan"):
		var scan = data.scan()
		result += "\n扫描："
		if scan == null:
			result += "缺失或过期"
		else:
			var nearest = INF
			for i in range(scan.payload.ranges_m.size()):
				if scan.payload.hit_mask[i]:
					nearest = min(nearest, float(scan.payload.ranges_m[i]))
			result += "sample tick %s，带噪最近回波 %s；%s" % [scan.simulation_tick, "无回波" if nearest == INF else "%.3f m" % nearest, "同 tick 玩家位姿投影" if data.scan_pose() != null else "无同 tick 玩家位姿，仅车体系"]
	return result
