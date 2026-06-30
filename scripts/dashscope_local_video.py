import json
import sys


def main():
    try:
        payload = json.load(sys.stdin)
        result = call_dashscope(payload)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


def call_dashscope(payload):
    try:
        import dashscope
        from dashscope import MultiModalConversation
    except ImportError as exc:
        raise RuntimeError(
            "缺少 Python 包 dashscope。请运行：py -m pip install dashscope"
        ) from exc

    api_key = payload.get("apiKey") or ""
    model = payload.get("model") or "qwen3.6-plus"
    file_uri = payload.get("fileUri") or ""
    fps = payload.get("fps")
    prompt = payload.get("prompt") or ""
    base_http_api_url = payload.get("baseHttpApiUrl") or ""

    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置。")
    if not file_uri.startswith("file://"):
        raise RuntimeError("本地路径模式需要 file:// URI。")

    if base_http_api_url:
        dashscope.base_http_api_url = base_http_api_url

    video_item = {"video": file_uri}
    if fps:
        video_item["fps"] = float(fps)

    messages = [
        {
            "role": "user",
            "content": [
                video_item,
                {"text": prompt},
            ],
        }
    ]

    response = MultiModalConversation.call(
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=0.2,
        enable_thinking=False,
    )

    raw = response_to_dict(response)
    strip_reasoning(raw)
    status_code = raw.get("status_code") or raw.get("statusCode")
    if status_code and int(status_code) >= 400:
        message = raw.get("message") or raw.get("code") or json.dumps(raw, ensure_ascii=False)
        raise RuntimeError(str(message))

    return {
        "content": extract_content(raw),
        "usage": raw.get("usage") or raw.get("output", {}).get("usage"),
        "raw": raw,
    }


def response_to_dict(response):
    if isinstance(response, dict):
        return response

    raw = {}
    for attr in ("status_code", "code", "message", "request_id", "usage"):
        if hasattr(response, attr):
            raw[attr] = to_jsonable(getattr(response, attr))
    if hasattr(response, "output"):
        raw["output"] = to_jsonable(getattr(response, "output"))

    if raw:
        return raw

    if hasattr(response, "to_dict"):
        try:
            return response.to_dict()
        except Exception:
            pass
    if hasattr(response, "__dict__"):
        return to_jsonable(dict(response.__dict__))
    try:
        return json.loads(str(response))
    except Exception:
        return {"rawText": str(response)}


def to_jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return {str(key): to_jsonable(item) for key, item in vars(value).items() if not key.startswith("_")}
    return str(value)


def extract_content(raw):
    choices = raw.get("output", {}).get("choices") or raw.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict) and item.get("text"):
                    texts.append(str(item["text"]))
            return "".join(texts)
    return raw.get("rawText") or json.dumps(raw, ensure_ascii=False)


def strip_reasoning(value):
    if isinstance(value, dict):
        value.pop("reasoning_content", None)
        value.pop("reasoning", None)
        for item in value.values():
            strip_reasoning(item)
    elif isinstance(value, list):
        for item in value:
            strip_reasoning(item)


if __name__ == "__main__":
    main()
