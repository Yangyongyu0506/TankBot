extends Node2D
## Authorized player displays; no private geometry or developer inputs.
var view: Control
var grids: Dictionary = {}
var map_layer: Node2D

func configure(owner_view: Control) -> void:
	view = owner_view
	z_index = int(view.tools.rendering.draw_order.annotations)
	if not is_instance_valid(map_layer):
		map_layer = Node2D.new()
		map_layer.z_as_relative = false
		map_layer.draw.connect(draw_grids)
		add_child(map_layer)
	map_layer.z_index = int(view.tools.rendering.draw_order.map)
	grids.clear()
	var task = view.policy.level.get("global_planning", {})
	if task.has("map"):
		for pair in [["planning_map", task.map.get("grid", []), "occupied"], ["safety_grid", task.get("inflated_grid", []), "safety"]]:
			var grid: Array = pair[1]
			if grid.is_empty() or grid[0].is_empty():
				continue
			var image = Image.create(grid[0].size(), grid.size(), false, Image.FORMAT_RGBA8)
			image.fill(Color.TRANSPARENT)
			for row in range(grid.size()):
				for col in range(grid[row].size()):
					if grid[row][col]:
						image.set_pixel(col, grid.size() - row - 1, Color(view.tools.rendering[pair[2]]))
			grids[pair[0]] = {"texture": ImageTexture.create_from_image(image), "origin": view.vector(task.map.origin_xy), "extent": Vector2(grid[0].size(), grid.size()) * float(task.map.resolution_m)}

func _process(_dt: float) -> void:
	queue_redraw()
	if is_instance_valid(map_layer):
		map_layer.queue_redraw()

func line(points: Array, color: Color) -> void:
	var projected = PackedVector2Array()
	for point in points:
		projected.append(view.project(point))
	if projected.size() > 1:
		draw_polyline(projected, color, float(view.tools.rendering.line_width_px), true)

func draw_grids() -> void:
	if view == null or view.profile.is_empty():
		return
	for key in grids:
		if view.policy.enabled(key):
			var grid: Dictionary = grids[key]
			map_layer.draw_texture_rect(grid.texture, Rect2(view.project(grid.origin + Vector2(0, grid.extent.y)), grid.extent * view.scale_m), false)

func _draw() -> void:
	if view == null or view.profile.is_empty():
		return
	var policy = view.policy
	var style: Dictionary = view.tools.rendering
	var data = view.data
	view.draw_observations(self)
	if policy.enabled("trail"):
		var points: Array = []
		for sample in data.trail:
			points.append(view.point(sample.pose))
		line(points, Color(style.trail))
	if policy.enabled("pose_estimates"):
		for history in data.estimates.values():
			var points: Array = []
			for message in history:
				points.append(view.point(message.payload))
			line(points, Color(style.reference))
	if policy.enabled("gps"):
		for sample in data.gps:
			draw_circle(view.project(view.vector(sample.payload.position_m)), float(style.point_radius_px), Color(style.gps))
	if view.draw_pose:
		var center = view.point(view.draw_pose)
		var yaw = float(view.draw_pose.yaw_rad)
		if policy.enabled("frames"):
			view.arrow(self, center, Vector2(float(style.frame_length_m), 0).rotated(yaw), Color(style.frame_x))
			view.arrow(self, center, Vector2(0, float(style.frame_length_m)).rotated(yaw), Color(style.frame_y))
		if policy.enabled("pose_covariance"):
			var pair = view.timeline.bracket(view.timeline.poses, view.timeline.render_ms)
			if not pair.is_empty():
				ellipse(center, pair[0].get("covariance"))
		if policy.enabled("imu"):
			for message in data.latest.get("payload", {}).get("local_observations", []):
				if message.schema == "imu@1" and message.frame_id == "base_link":
					var payload: Dictionary = message.payload
					view.arrow(self, center, Vector2(payload.linear_acceleration_x_mps2, payload.linear_acceleration_y_mps2).rotated(yaw) * float(style.acceleration_scale_s2), Color(style.frame_y))
	draw_routes()
	draw_scan()

func ellipse(center: Vector2, covariance: Variant) -> void:
	if not covariance is Array or covariance.size() != 9:
		return
	var a = float(covariance[0])
	var b = (float(covariance[1]) + float(covariance[3])) * 0.5
	var d = float(covariance[4])
	var delta = sqrt((a - d) * (a - d) + 4 * b * b)
	var major = (a + d + delta) * 0.5
	var minor = (a + d - delta) * 0.5
	if major < 0 or minor < 0:
		return
	var angle = 0.5 * atan2(2 * b, a - d)
	var points: Array = []
	var count = int(view.tools.rendering.ellipse_segments)
	for i in range(count + 1):
		var phase = TAU * i / count
		points.append(center + Vector2(sqrt(major) * cos(phase), sqrt(minor) * sin(phase)).rotated(angle))
	line(points, Color(view.tools.rendering.reference))

func draw_routes() -> void:
	var level = view.policy.level
	var style: Dictionary = view.tools.rendering
	if view.policy.enabled("waypoints") and level.has("navigation"):
		var points: Array = []
		for point in level.navigation.points_m:
			points.append(view.vector(point))
			circle(view.vector(point), level.navigation.position_tolerance_m, Color(style.checkpoint))
		line(points, Color(style.checkpoint))
	var reference: Dictionary = level.get("path_tracking", {})
	var planning: Dictionary = level.get("global_planning", {})
	var route: Dictionary = view.task.get("global_planning", {}).get("route", reference)
	if view.policy.enabled("path"):
		var points: Array = []
		for point in route.get("points_m", []):
			points.append(view.vector(point))
		line(points, Color(style.scan))
		if not points.is_empty():
			draw_circle(view.project(points[0]), float(style.point_radius_px), Color(style.trail))
			draw_circle(view.project(points[-1]), float(style.point_radius_px), Color(style.goal))
	if view.policy.enabled("checkpoints"):
		var reached = int(view.task.get("path_tracking", {}).get("reached_count", 0))
		for i in range(reference.get("checkpoints_m", []).size()):
			circle(view.vector(reference.checkpoints_m[i]), float(reference.checkpoint_radius_m), Color(style.trail if i < reached else style.checkpoint))
	if view.policy.enabled("planning_map") or view.policy.enabled("safety_grid"):
		for field in ["start_xy", "goal_xy"]:
			if planning.has(field):
				draw_circle(view.project(view.vector(planning[field])), float(style.point_radius_px), Color(style.goal))

func circle(center: Vector2, radius_m: float, color: Color) -> void:
	draw_arc(view.project(center), radius_m * view.scale_m, 0, TAU, int(view.tools.rendering.observation_ring_segments), color, float(view.tools.rendering.line_width_px), true)

func draw_scan() -> void:
	var scan = view.data.scan()
	if scan == null:
		return
	var payload: Dictionary = scan.payload
	var style: Dictionary = view.tools.rendering
	var origin = Vector2(style.observation_origin_px[0], view.size.y - style.observation_origin_px[1])
	var radius = float(style.observation_radius_px)
	var pose = view.data.scan_pose() if view.policy.enabled("scan_points") else null
	if view.policy.enabled("scan"):
		draw_arc(origin, radius, 0, TAU, int(style.observation_ring_segments), Color(style.scan), float(style.line_width_px), true)
	for i in range(payload.ranges_m.size()):
		if not payload.hit_mask[i]:
			continue
		var angle = float(payload.angle_min_rad) + i * float(payload.angle_increment_rad)
		var ray = Vector2(cos(angle), sin(angle)) * float(payload.ranges_m[i])
		if view.policy.enabled("scan"):
			var hit = origin + Vector2(ray.x, -ray.y) * radius / float(payload.range_max_m)
			draw_circle(hit, float(style.point_radius_px), Color(style.scan))
		if pose != null:
			draw_circle(view.project(view.point(pose) + ray.rotated(float(pose.yaw_rad))), float(style.point_radius_px), Color(style.scan))
