extends Node2D
## Local geometry is in metres; the view alone supplies authorized pose and scale.
var weapon = Node2D.new()
var model_kind: String = ""
var wheel_sprites: Array[Sprite2D] = []

func configure(library: RefCounted, model: Dictionary, body: Dictionary, calibration: Variant, weapons_enabled: bool) -> void:
	model_kind = model.kind
	if model_kind == "tracked":
		library.part(self, "tracked_base", Vector2(model.track.length_m, 2.0 * model.track.center_y_m + model.track.width_m))
	elif model_kind == "radial_omni":
		# The hull fits the existing body; wheel centres/orientations use calibration.
		library.part(self, "omni_hull", Vector2(body.length_m, body.width_m))
		for mount in calibration.wheels:
			var angle = deg_to_rad(float(mount.azimuth_deg))
			var center = Vector2(cos(angle), sin(angle)) * float(calibration.center_radius_m)
			wheel_sprites.append(library.part(self, "omni_wheel", Vector2(2.0 * calibration.radius_m, model.wheel.width_m), center, angle + PI * 0.5))
		# Compiled shell centres share the actual armor mounting planes.
		var armor: Dictionary = model.armor
		for side in [-1, 1]:
			library.part(self, "armor", Vector2(armor.front_width_m, armor.front_length_m), Vector2(side * armor.front_center_x_m, 0), PI * 0.5)
			library.part(self, "armor", Vector2(armor.side_length_m, armor.side_width_m), Vector2(0, side * armor.side_center_y_m))
	var marker = PackedVector2Array()
	for vertex in model.forward_marker_m:
		marker.append(Vector2(vertex[0], vertex[1]))
	var marker_bounds = Rect2(marker[0], Vector2.ZERO)
	for vertex in marker:
		marker_bounds = marker_bounds.expand(vertex)
	library.part(self, "forward_marker", marker_bounds.size, marker_bounds.get_center(), 0.0, Color(model.colors.mark))
	weapon.name = "weapon"
	add_child(weapon)
	weapon.visible = weapons_enabled
	library.part(weapon, "turret", Vector2.ONE * float(model.turret_radius_m) * 2.0, Vector2.ZERO, 0.0, Color(model.colors.shell))

func mount_barrel(library: RefCounted, muzzle: Vector2, width_m: float, tint: Color) -> void:
	var barrel = library.part(weapon, "barrel", Vector2(muzzle.length(), width_m), muzzle * 0.5, muzzle.angle(), tint)
	# The tube enters beneath the cap, rotating about the same physical turret axis.
	weapon.move_child(barrel, 0)

func present(screen_position: Vector2, yaw: float, pixels_per_metre: float, turret_angle: float) -> void:
	position = screen_position
	rotation = -yaw
	scale = Vector2.ONE * pixels_per_metre
	weapon.rotation = -turret_angle
