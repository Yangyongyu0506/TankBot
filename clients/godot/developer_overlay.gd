extends Node2D
## Independent developer grant. Never feeds the public timeline or robot runtime.
const Timeline = preload("res://timeline.gd")
const VehicleSprite = preload("res://vehicle_sprite.gd")
var view: Control
var timeline = Timeline.new()
var latest: Dictionary = {}
var enabled: bool = false
var vehicle: Node2D
var targets: Dictionary = {}
var projectile_sprites: Dictionary = {}
var frame: Dictionary = {}
var received_ms: float = 0.0
var annotations: Node2D

func configure(owner_view: Control) -> void:
	clear()
	view = owner_view
	timeline.configure(view.profile)
	annotations = Node2D.new()
	annotations.z_index = int(view.tools.rendering.draw_order.annotations)
	annotations.draw.connect(draw_annotations)
	add_child(annotations)
	vehicle = VehicleSprite.new()
	vehicle.z_index = int(view.tools.rendering.draw_order.entities)
	vehicle.configure(view.sprites, view.profile.chassis_visual, view.profile.body, view.profile.wheel_calibration, view.profile.weapons_enabled)
	vehicle.mount_barrel(view.sprites, view.vector(view.profile.turret_muzzle_offset_m), view.profile.rendering.barrel_width_m, Color(view.profile.chassis_visual.colors.barrel))
	vehicle.self_modulate = view.entity_color(Color(view.tools.rendering.truth_tint))
	vehicle.visible = false
	add_child(vehicle)

func clear() -> void:
	latest = {}
	frame = {}
	timeline.clear()
	for child in get_children():
		child.free()
	targets.clear()
	projectile_sprites.clear()
	vehicle = null
	annotations = null
	queue_redraw()

func revoke() -> void:
	enabled = false
	clear()
	visible = false

func accept(snapshot: Dictionary) -> void:
	if not enabled or snapshot.get("run_id") != view.profile.run_id:
		return
	if not is_instance_valid(vehicle):
		configure(view)
	if not latest.is_empty() and snapshot.simulation_tick <= latest.simulation_tick:
		return
	latest = snapshot.duplicate(true)
	received_ms = Time.get_ticks_msec()
	var truth: Dictionary = latest.truth
	var pose: Array = truth.truth_pose
	var objects: Array = []
	for target in truth.targets:
		if target.alive:
			objects.append({"kind": "target", "target_id": target.target_id, "pose": {"x_m": target.pose[0], "y_m": target.pose[1], "yaw_rad": target.pose[2]}})
	for projectile in truth.projectiles:
		objects.append({"kind": "projectile", "projectile_id": projectile.projectile_id, "x_m": projectile.position[0], "y_m": projectile.position[1], "radius_m": view.profile.projectile_radius_m})
	var observations: Array = []
	for message in latest.sensors.values():
		if message.channel == "/robot/turret/joint_states":
			observations.append(message)
	timeline.push({"run_id": latest.run_id, "sequence_number": latest.simulation_tick, "simulation_tick": latest.simulation_tick,
		"payload": {"view_revision": 0, "selected_pose": {"source_id": "system", "frame_id": "map", "simulation_tick": latest.simulation_tick, "pose": {"x_m": pose[0], "y_m": pose[1], "yaw_rad": pose[2]}} if truth.get("player_alive", true) else null,
		"objects": objects, "local_observations": observations}}, received_ms)

func update_frame(now_ms: float, display_ms: float) -> void:
	visible = enabled and not latest.is_empty() and now_ms - received_ms <= float(view.profile.rendering.history_ms)
	if not visible:
		return
	if not is_instance_valid(vehicle):
		configure(view)
		return
	frame = timeline.sample(now_ms, display_ms)
	vehicle.self_modulate = view.entity_color(Color(view.tools.rendering.truth_tint))
	vehicle.visible = view.policy.enabled("truth_robot") and frame.pose != null
	if vehicle.visible:
		vehicle.present(view.project(view.point(frame.pose)), frame.pose.yaw_rad, view.scale_m, frame.turret)
	var active_targets: Dictionary = {}
	var active_projectiles: Dictionary = {}
	for object in frame.objects:
		if object.kind == "target" and view.policy.enabled("truth_targets"):
			var key = str(object.target_id)
			active_targets[key] = true
			var visual = latest.target_visuals.get(key)
			if not targets.has(key):
				if visual:
					var node = VehicleSprite.new()
					node.configure(view.sprites, visual.chassis_visual, visual.body, visual.wheel_calibration, view.profile.weapons_enabled)
					node.mount_barrel(view.sprites, view.vector(view.profile.turret_muzzle_offset_m), view.profile.rendering.barrel_width_m, Color(visual.chassis_visual.colors.barrel))
					add_child(node)
					targets[key] = node
				else:
					targets[key] = view.sprites.part(self, "target", Vector2.ONE)
			targets[key].z_index = int(view.tools.rendering.draw_order.entities)
			targets[key].self_modulate = view.entity_color(Color(view.tools.rendering.truth_target_tint))
			var position = view.project(view.point(object.pose))
			if visual:
				targets[key].present(position, object.pose.yaw_rad, view.scale_m, 0.0)
			else:
				var body: Dictionary = view.profile.target_geometry.body
				targets[key].position = position
				targets[key].rotation = -float(object.pose.yaw_rad)
				targets[key].scale = Vector2(body.length_m, body.width_m) * view.scale_m / targets[key].texture.get_size()
		if object.kind == "projectile" and view.policy.enabled("projectiles"):
			var key = str(object.projectile_id)
			active_projectiles[key] = true
			if not projectile_sprites.has(key):
				projectile_sprites[key] = view.sprites.part(self, "projectile", Vector2.ONE)
			var sprite: Sprite2D = projectile_sprites[key]
			sprite.z_index = int(view.tools.rendering.draw_order.entities)
			sprite.self_modulate = view.entity_color()
			sprite.position = view.project(view.point(object))
			sprite.scale = Vector2.ONE * max(float(view.sprites.options.projectile_min_diameter_px), 2.0 * object.radius_m * view.scale_m) / sprite.texture.get_size()
	for pair in [[targets, active_targets], [projectile_sprites, active_projectiles]]:
		for key in pair[0].keys():
			if not pair[1].has(key):
				pair[0][key].free()
				pair[0].erase(key)
	queue_redraw()
	annotations.queue_redraw()

func _draw() -> void:
	if not enabled or latest.is_empty() or frame.is_empty():
		return
	var style: Dictionary = view.tools.rendering
	if view.policy.enabled("private_obstacles"):
		for wall in latest.private_obstacles:
			polygon(self, view.vector(wall.center), wall.size[0], wall.size[1], 0.0, Color(style.private_obstacle), true)

func draw_annotations() -> void:
	if not enabled or latest.is_empty() or frame.is_empty():
		return
	var style: Dictionary = view.tools.rendering
	if frame.pose:
		var pose: Dictionary = frame.pose
		var center = view.point(pose)
		if view.policy.enabled("colliders"):
			polygon(annotations, center, view.profile.body.length_m, view.profile.body.width_m, pose.yaw_rad, Color(style.collider), false, view.profile.body.corner_radius_m)
		if view.policy.enabled("velocities"):
			var velocity: Array = latest.truth.truth_velocity
			view.arrow(annotations, center, Vector2(velocity[0], velocity[1]).rotated(pose.yaw_rad) * float(style.velocity_scale_s), Color(style.velocity))
		# Global radar projection is available only through this explicit grant.
		if view.policy.enabled("radar"):
			for message in latest.sensors.values():
				if message.frame_id == "base_link" and message.schema in ["radar@1", "armor_detections@1"]:
					for hit in view.polar_hits(message):
						var delta = Vector2(cos(hit[1]), sin(hit[1])) * hit[0]
						annotations.draw_circle(view.project(center + delta.rotated(pose.yaw_rad)), float(style.point_radius_px), Color(style.gps))
	for target in latest.truth.targets:
		if not target.alive:
			continue
		var visual = latest.target_visuals.get(str(target.target_id))
		var body: Dictionary = visual.body if visual else view.profile.target_geometry.body
		var center = Vector2(target.pose[0], target.pose[1])
		if view.policy.enabled("colliders"):
			polygon(annotations, center, body.length_m, body.width_m, target.pose[2], Color(style.collider), false, body.corner_radius_m)
		if view.policy.enabled("velocities"):
			view.arrow(annotations, center, Vector2(target.velocity[0], target.velocity[1]).rotated(target.pose[2]) * float(style.velocity_scale_s), Color(style.velocity))

func polygon(canvas: Node2D, center: Vector2, length_m: float, width_m: float, yaw: float, color: Color, filled: bool = false, radius_m: float = 0.0) -> void:
	var vertices = PackedVector2Array()
	var signs = [Vector2(1, 1), Vector2(-1, 1), Vector2(-1, -1), Vector2(1, -1)]
	var segments = int(view.tools.rendering.ellipse_segments) / 4
	for corner in range(4):
		var pivot: Vector2 = signs[corner] * (Vector2(length_m, width_m) * 0.5 - Vector2.ONE * radius_m)
		if radius_m == 0:
			vertices.append(view.project(center + pivot.rotated(yaw)))
		else:
			for i in range(segments + 1):
				var angle = (corner + float(i) / segments) * PI * 0.5
				vertices.append(view.project(center + (pivot + Vector2(cos(angle), sin(angle)) * radius_m).rotated(yaw)))
	if filled:
		canvas.draw_colored_polygon(vertices, color)
	else:
		vertices.append(vertices[0])
		canvas.draw_polyline(vertices, color, float(view.tools.rendering.line_width_px), true)
