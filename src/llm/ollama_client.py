import json
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_ENDPOINT = "http://localhost:11434"
LOCAL_OLLAMA_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1"
}


def validate_local_endpoint(endpoint):

    parsed_url = urllib.parse.urlparse(endpoint)

    if parsed_url.scheme != "http":
        raise ValueError("Ollama endpoint must use local http.")

    if parsed_url.hostname not in LOCAL_OLLAMA_HOSTS:
        raise ValueError("Only localhost Ollama endpoints are allowed.")

    return endpoint.rstrip("/")


def read_json_url(url, timeout=2):

    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8")

    return json.loads(body)


def post_json_url(url, payload, timeout=60):

    request_data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=request_data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")

    return json.loads(body)


def is_ollama_running(endpoint=DEFAULT_ENDPOINT):

    try:
        local_endpoint = validate_local_endpoint(endpoint)
        read_json_url(f"{local_endpoint}/api/tags", timeout=2)
        return True
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return False


def list_models(endpoint=DEFAULT_ENDPOINT):

    try:
        local_endpoint = validate_local_endpoint(endpoint)
        response = read_json_url(f"{local_endpoint}/api/tags", timeout=5)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return []

    model_names = []

    for model in response.get("models", []):
        model_name = model.get("name")

        if model_name:
            model_names.append(model_name)

    return model_names


def chat(model, prompt, endpoint=DEFAULT_ENDPOINT):

    if not model:
        raise ValueError("model is required")

    if not prompt:
        raise ValueError("prompt is required")

    local_endpoint = validate_local_endpoint(endpoint)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False
    }

    try:
        response = post_json_url(
            url=f"{local_endpoint}/api/chat",
            payload=payload,
            timeout=120
        )
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Ollama chat failed: {error}") from error

    message = response.get("message", {})

    return message.get("content", "")
