extends Node
## Local management API only. Never accepts World/Core handles or player execution.
var base_url: String
var token: String = ""
var options: Dictionary
var inflight: int = 0

func configure(url: String, config: Dictionary) -> bool:
	var pattern = RegEx.new()
	pattern.compile("^http://127\\.0\\.0\\.1:[0-9]{1,5}$")
	if pattern.search(url) == null or int(url.get_slice(":", 2)) not in range(1, 65536):
		return false
	base_url = url
	options = config
	return true

func call_api(path: String, payload: Variant = null) -> Dictionary:
	if inflight >= int(options.max_inflight):
		return {"error": "客户端请求繁忙，请重试。"}
	if not path.begins_with("/api/") or ".." in path:
		return {"error": "INVALID_API_PATH"}
	inflight += 1
	var request = HTTPRequest.new()
	request.timeout = float(options.request_timeout_s)
	request.body_size_limit = int(options.max_response_bytes)
	add_child(request)
	var headers = PackedStringArray(["Content-Type: application/json", "Origin: " + base_url])
	var method = HTTPClient.METHOD_GET
	var body = ""
	if payload != null:
		method = HTTPClient.METHOD_POST
		headers.append("X-TankBot-Control: " + token)
		body = JSON.stringify(payload)
	var error = request.request(base_url + path, headers, method, body)
	if error != OK:
		request.queue_free()
		inflight -= 1
		return {"error": "HTTP 启动失败: " + str(error)}
	var response = await request.request_completed
	request.queue_free()
	inflight -= 1
	if response[0] != HTTPRequest.RESULT_SUCCESS:
		return {"error": "连接失败/超时: " + str(response[0])}
	var value = JSON.parse_string(response[3].get_string_from_utf8())
	if not value is Dictionary:
		return {"error": "INVALID_API_RESPONSE"}
	if int(response[1]) != 200:
		return {"error": value.get("error", "HTTP " + str(response[1]))}
	return value
