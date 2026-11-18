extends Control
## Drawing consumes only public profile and ViewGateway messages.
const Timeline = preload("res://timeline.gd")
var timeline = Timeline.new()
var profile: Dictionary = {}
var camera = Vector2.ZERO
var layers = {"map": true, "robot": true, "projectiles": true, "target_estimates": true, "path": true, "radar": true}
var scale_m: float = 1.0
var draw_pose: Variant = null

func configure(value: Dictionary) -> void:
	profile = value
	timeline.configure(value)
	camera = Vector2(value.rendering.camera_origin_m[0], value.rendering.camera_origin_m[1])

func accept(message: Dictionary) -> void:
	if timeline.push(message, Time.get_ticks_msec()):
		camera = Vector2(profile.rendering.camera_origin_m[0], profile.rendering.camera_origin_m[1])

func _process(_dt: float) -> void:
	queue_redraw()

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

func chassis(pose: Dictionary, model: Dictionary, calibration: Variant, turret: float = 0.0) -> void:
	var center = point(pose)
	var yaw = float(pose.yaw_rad)
	if model.kind == "tracked":
		for side in [-1, 1]:
			plate(center + Vector2(0, side * model.track.center_y_m).rotated(yaw), model.track.length_m, model.track.width_m, yaw, Color(model.colors.rubber))
	elif model.kind == "radial_omni" and calibration:
		for mount in calibration.wheels:
			var angle = deg_to_rad(float(mount.azimuth_deg))
			var position = Vector2(cos(angle), sin(angle)) * float(calibration.center_radius_m)
			plate(center + position.rotated(yaw), float(calibration.radius_m) * 2, float(model.wheel.width_m), yaw + angle + PI * 0.5, Color(model.colors.rubber))
	plate(center, model.hull.length_m, model.hull.width_m, yaw, Color(model.colors.shell))
	var marker = PackedVector2Array()
	for vertex in model.forward_marker_m:
		marker.append(project(center + vector(vertex).rotated(yaw)))
	draw_colored_polygon(marker, Color(model.colors.mark))
	if profile.weapons_enabled:
		draw_circle(project(center), model.turret_radius_m * scale_m, Color(model.colors.turret))
		var muzzle = vector(profile.turret_muzzle_offset_m).rotated(yaw + turret)
		draw_line(project(center), project(center + muzzle), Color(model.colors.barrel), max(1.0, profile.rendering.barrel_width_m * scale_m), true)

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("101b29"))
	if profile.is_empty():
		return
	scale_m = size.x / float(profile.rendering.viewport_width_m)
	var scene = timeline.sample(Time.get_ticks_msec())
	draw_pose = scene.pose
	if draw_pose:
		camera = point(draw_pose)
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
	for object in scene.objects:
		if object.kind == "projectile" and layers.projectiles:
			draw_circle(project(point(object)), max(2.0, object.radius_m * scale_m), Color("ffe1a6"))
		elif object.kind == "target" and layers.robot:
			var geometry = profile.target_geometry.body
			plate(point(object.pose), geometry.length_m, geometry.width_m, object.pose.yaw_rad, Color("dc8073"))
	if draw_pose and layers.robot:
		chassis(draw_pose, profile.chassis_visual, profile.wheel_calibration, scene.turret)
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
