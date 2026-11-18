extends RefCounted
## Trusted, client-only files; decoded once, shared by every Sprite2D instance.
var textures: Dictionary = {}
var options: Dictionary = {}

func configure(spec: Dictionary) -> bool:
	options = spec
	for key in spec.assets:
		var definition: Dictionary = spec.assets[key]
		var image = Image.load_from_file(definition.path)
		if image == null or image.is_empty():
			push_error("SPRITE_IMAGE_INVALID: " + str(definition.path))
			return false
		if max(image.get_width(), image.get_height()) > int(spec.limits.max_dimension_px):
			push_error("SPRITE_IMAGE_TOO_LARGE: " + str(definition.path))
			return false
		var region = image.get_used_rect()
		if definition.has("region_px"):
			var r: Array = definition.region_px
			region = Rect2i(r[0], r[1], r[2], r[3])
		if not region.has_area() or not Rect2i(Vector2i.ZERO, image.get_size()).encloses(region):
			push_error("SPRITE_REGION_INVALID: " + str(definition.path))
			return false
		image.generate_mipmaps()
		var texture = AtlasTexture.new()
		texture.atlas = ImageTexture.create_from_image(image)
		# Ignore transparent padding without editing or baking the original art.
		texture.region = Rect2(region)
		texture.filter_clip = true
		textures[key] = texture
	return true

func part(parent: Node, key: String, extent_m: Vector2, center_m: Vector2 = Vector2.ZERO, yaw: float = 0.0, tint: Color = Color.WHITE) -> Sprite2D:
	var sprite = Sprite2D.new()
	sprite.name = key
	sprite.texture = textures[key]
	sprite.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	sprite.scale = extent_m / sprite.texture.get_size()
	sprite.position = Vector2(center_m.x, -center_m.y)
	sprite.rotation = -yaw
	sprite.modulate = tint
	parent.add_child(sprite)
	return sprite
