extends Control
## Drawing consumes only public profile and ViewGateway messages.
const Timeline = preload("res://timeline.gd")
const SpriteLibrary = preload("res://sprite_library.gd")
const VehicleSprite = preload("res://vehicle_sprite.gd")
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

func load_assets(value: Dictionary) -> bool:
	return sprites.configure(value)

func configure(value: Dictionary) -> void:
	clear_entities()
	profile = value
	timeline.configure(value)
	camera = Vector2(value.rendering.camera_origin_m[0], value.rendering.camera_origin_m[1])
	vehicle = VehicleSprite.new()
	vehicle.name = "player_vehicle"
	vehicle.configure(sprites, value.chassis_visual, value.body, value.wheel_calibration, value.weapons_enabled)
	vehicle.mount_barrel(sprites, vector(value.turret_muzzle_offset_m), value.rendering.barrel_width_m, Color(value.chassis_visual.colors.barrel))
	vehicle.visible = false
	add_child(vehicle)
	draw_pose = null
	scene = {"pose": null, "objects": [], "turret": 0.0}

func clear_entities() -> void:
	if is_instance_valid(vehicle):
		vehicle.free()
	for entity in entities.values():
		entity.free()
	entities.clear()

func accept(message: Dictionary) -> void:
	if timeline.push(message, Time.get_ticks_msec()):
		camera = Vector2(profile.rendering.camera_origin_m[0], profile.rendering.camera_origin_m[1])

func _process(_dt: float) -> void:
	if not profile.is_empty() and size.x > 0:
		scale_m = size.x / float(profile.rendering.viewport_width_m)
		scene = timeline.sample(Time.get_ticks_msec())
		draw_pose = scene.pose
		if draw_pose:
			camera = point(draw_pose)
		vehicle.visible = draw_pose != null and layers.robot
		if vehicle.visible:
			vehicle.present(project(point(draw_pose)), float(draw_pose.yaw_rad), scale_m, float(scene.turret))
		sync_entities()
	queue_redraw()

func sync_entities() -> void:
	var active: Dictionary = {}
	for object in scene.objects:
		var projectile: bool = object.kind == "projectile"
		if (projectile and not layers.projectiles) or (not projectile and not layers.robot):
			continue
		var key = str([object.kind, object.get("projectile_id", object.get("target_id"))])
		active[key] = true
		if not entities.has(key):
			entities[key] = sprites.part(self, "projectile" if projectile else "target", Vector2.ONE)
		var sprite: Sprite2D = entities[key]
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
	if layers.map:
		for wall in profile.walls:
			plate(vector(wall.center), wall.size[0], wall.size[1], 0.0, Color("65788e"))
	if layers.path:
		for level in profile.campaign.levels:
			if level.level_id == profile.campaign.active_level and level.has("path_tracking"):
				var path = level.path_tracking.get("points_m", [])
				for i in range(1, path.size()):
					draw_line(project(vector(path[i-1])), project(vector(path[i])), Color("4ac8df"), 2, true)
	if timeline.latest.is_empty():
		return
	if layers.target_estimates:
		for message in timeline.latest.payload.get("target_estimates", []):
			var estimate = message.payload
			draw_arc(project(point(estimate)), profile.body.width_m * scale_m * 0.5, 0, TAU, 24, Color("e8ad58"), 2, true)
	# Body-frame observations remain available without a global pose. No truth projection.
	if layers.radar:
		var origin = Vector2(90, size.y-95)
		for observation in timeline.latest.payload.local_observations:
			if observation.schema == "radar@1":
				draw_arc(origin, 70, 0, TAU, 48, Color("6b91a9"))
				for detection in observation.payload.detections:
					var delta = Vector2(cos(detection.bearing_rad), -sin(detection.bearing_rad)) * detection.range_m / profile.radar_calibration.range_m * 70
					draw_circle(origin + delta, 3, Color("e8ad58"))
