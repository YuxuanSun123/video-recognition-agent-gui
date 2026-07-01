import csv
import ast
import json
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote

import requests


def resolve_data_root():
    override = os.environ.get("SHOT_READER_DATA_DIR")
    if override:
        root = Path(override).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return root
    return Path(__file__).resolve().parent


ROOT = resolve_data_root()
ENV_PATH = ROOT / ".env"

CONFIG_KEYS = [
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_BASE_URL",
    "DASHSCOPE_WORKSPACE_ID",
    "DASHSCOPE_REGION",
    "ALIYUN_VISION_MODEL",
    "ALIYUN_OMNI_MODEL",
    "GITHUB_TOKEN",
    "GITHUB_OWNER",
    "GITHUB_REPO",
    "GITHUB_RELEASE_TAG",
    "GITHUB_RELEASE_NAME",
    "GITHUB_ASSET_PREFIX",
    "CODEX_MODEL",
    "CODEX_REASONING_EFFORT",
]


def read_env(path=ENV_PATH):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def get_config():
    file_values = read_env()

    def value(key, fallback=""):
        return file_values.get(key) or os.environ.get(key) or fallback

    config = {
        "dashscope_api_key": value("DASHSCOPE_API_KEY"),
        "dashscope_base_url": value("DASHSCOPE_BASE_URL"),
        "workspace_id": value("DASHSCOPE_WORKSPACE_ID"),
        "region": value("DASHSCOPE_REGION", "cn-beijing"),
        "vision_model": value("ALIYUN_VISION_MODEL", "qwen3.7-plus"),
        "omni_model": value("ALIYUN_OMNI_MODEL", "qwen3.5-omni-plus"),
        "github_token": value("GITHUB_TOKEN"),
        "github_owner": value("GITHUB_OWNER"),
        "github_repo": value("GITHUB_REPO"),
        "github_release_tag": value("GITHUB_RELEASE_TAG", "video-agent-temp"),
        "github_release_name": value(
            "GITHUB_RELEASE_NAME", "Video Agent Temporary Uploads"
        ),
        "github_asset_prefix": value("GITHUB_ASSET_PREFIX", "video-agent"),
        "codex_model": value("CODEX_MODEL", ""),
        "codex_reasoning_effort": value("CODEX_REASONING_EFFORT", ""),
    }
    config["base_url"] = resolve_dashscope_base_url(config)
    return config


def resolve_dashscope_base_url(config):
    if config.get("dashscope_base_url"):
        return config["dashscope_base_url"].rstrip("/")
    workspace_id = config.get("workspace_id")
    region = config.get("region") or "cn-beijing"
    if workspace_id:
        return f"https://{workspace_id}.{region}.maas.aliyuncs.com/compatible-mode/v1"
    return "https://dashscope.aliyuncs.com/compatible-mode/v1"


def save_config(updates):
    existing = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    mapped = {
        "DASHSCOPE_API_KEY": updates.get("dashscope_api_key"),
        "DASHSCOPE_BASE_URL": updates.get("dashscope_base_url"),
        "DASHSCOPE_WORKSPACE_ID": updates.get("workspace_id"),
        "DASHSCOPE_REGION": updates.get("region") or "cn-beijing",
        "ALIYUN_VISION_MODEL": updates.get("vision_model") or "qwen3.7-plus",
        "ALIYUN_OMNI_MODEL": updates.get("omni_model") or "qwen3.5-omni-plus",
        "GITHUB_TOKEN": updates.get("github_token"),
        "GITHUB_OWNER": updates.get("github_owner"),
        "GITHUB_REPO": updates.get("github_repo"),
        "GITHUB_RELEASE_TAG": updates.get("github_release_tag") or "video-agent-temp",
        "GITHUB_RELEASE_NAME": updates.get("github_release_name")
        or "Video Agent Temporary Uploads",
        "GITHUB_ASSET_PREFIX": updates.get("github_asset_prefix") or "video-agent",
        "CODEX_MODEL": updates.get("codex_model"),
        "CODEX_REASONING_EFFORT": updates.get("codex_reasoning_effort"),
    }
    # Blank secret fields in the GUI mean "keep existing".
    current = read_env()
    for secret_key in ("DASHSCOPE_API_KEY", "GITHUB_TOKEN"):
        if not mapped.get(secret_key):
            mapped[secret_key] = current.get(secret_key, "")

    seen = set()
    output = []
    for line in existing:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if not match or match.group(1) not in mapped:
            output.append(line)
            continue
        key = match.group(1)
        seen.add(key)
        output.append(f"{key}={format_env_value(mapped[key])}")

    if not output:
        output.append("# Saved from the native video agent GUI.")
    for key in CONFIG_KEYS:
        if key in mapped and key not in seen:
            output.append(f"{key}={format_env_value(mapped[key])}")

    ENV_PATH.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def format_env_value(value):
    raw = str(value or "")
    if not raw:
        return ""
    if re.match(r"^[A-Za-z0-9_./:+=@-]+$", raw):
        return raw
    return json.dumps(raw, ensure_ascii=False)


def mask_secret(value):
    if not value:
        return "未保存"
    if len(value) <= 10:
        return f"{value[:2]}****{value[-2:]}"
    return f"{value[:6]}****{value[-4:]}"


def build_analysis_prompt(
    title,
    episode="",
    fps=1,
    can_understand_audio=False,
    subtitle_text="",
    custom_prompt="",
):
    audio_instruction = (
        "请同时分析视频中的对白、音乐、环境声、声画关系；声音/音乐列需要直接基于音频理解填写。"
        if can_understand_audio
        else "当前模式不保证理解视频音频；声音/音乐列优先使用可见字幕、画面文字和用户提供的字幕/转写，无法判断时写“需结合音轨或字幕”。"
    )
    parts = [
        "你是一名电影学院拉片分析师。请基于视频生成逐镜拉片报告，语言使用中文。",
        "只输出 JSON，不要 Markdown，不要代码块，不要解释。",
        "JSON 结构必须为：",
        '{"meta":{"title":"片名","episode":"集数或片段","duration":"片长","sceneCount":0,"shotCount":0,"basis":"分析依据"},"scenes":[{"id":1,"title":"场景标题","start":"00:00","end":"00:00","summary":"场景概述"}],"shots":[{"shot":"镜 1","scene":"场景一","timecode":"00:00-00:10","start":0,"end":10,"shotSize":"全景/中景/近景/特写/极近景","camera":"固定/推/拉/摇/移/跟/手持","visual":"画面内容与人物动作","audio":"声音/音乐/字幕","analysis":"电影语言分析注释"}]}',
        f"片名：{title}",
        f"集数/片段：{episode or '未提供'}",
        f"抽帧 fps：{fps}",
        "拆分规则：优先按明显镜头转换、构图变化、场景变化、人物动作阶段拆分；如果无法确认真实剪辑点，可按 8-12 秒粒度估算。",
        "分析重点：场景、人物、动作、空间关系、景别、镜头运动、构图、色彩、叙事功能、转折点。",
        audio_instruction,
        f"额外音轨/字幕文本：{subtitle_text}" if subtitle_text else "额外音轨/字幕文本：未提供。",
    ]
    if custom_prompt:
        parts.append(f"用户补充要求：{custom_prompt}")
    return "\n".join(parts)


def analyze_video(
    *,
    title,
    video_url="",
    local_path="",
    analysis_mode="vision",
    fps=1,
    subtitle_text="",
    custom_prompt="",
):
    config = get_config()
    if not config["dashscope_api_key"]:
        raise RuntimeError("请先在设置里保存 DASHSCOPE_API_KEY。")

    fps = clamp_float(fps, 0.1, 10)
    if local_path:
        return analyze_local_path(
            config=config,
            title=title,
            local_path=local_path,
            fps=fps,
            subtitle_text=subtitle_text,
            custom_prompt=custom_prompt,
        )

    if not video_url:
        raise RuntimeError("请填写视频公网 URL，或选择本地视频文件。")
    return analyze_video_url(
        config=config,
        title=title,
        video_url=video_url,
        analysis_mode=analysis_mode,
        fps=fps,
        subtitle_text=subtitle_text,
        custom_prompt=custom_prompt,
    )


def analyze_local_path(config, title, local_path, fps, subtitle_text, custom_prompt):
    path = Path(local_path)
    if not path.exists():
        raise RuntimeError("找不到本地视频文件。")
    if path.stat().st_size > 100 * 1024 * 1024:
        raise RuntimeError("本地路径模式限制视频本身不超过 100MB。")

    try:
        import dashscope
        from dashscope import MultiModalConversation
    except ImportError as exc:
        raise RuntimeError("缺少 Python 包 dashscope。请运行：py -m pip install -r requirements.txt") from exc

    prompt = build_analysis_prompt(
        title=title,
        fps=fps,
        can_understand_audio=False,
        subtitle_text=subtitle_text,
        custom_prompt=custom_prompt,
    )
    if config.get("dashscope_base_url"):
        dashscope.base_http_api_url = config["dashscope_base_url"].replace(
            "/compatible-mode/v1", "/api/v1"
        ).rstrip("/")

    response = MultiModalConversation.call(
        api_key=config["dashscope_api_key"],
        model=config["vision_model"],
        messages=[
            {
                "role": "user",
                "content": [
                    {"video": path.resolve().as_uri(), "fps": fps},
                    {"text": prompt},
                ],
            }
        ],
        temperature=0.2,
        enable_thinking=False,
    )
    raw = response_to_dict(response)
    content = extract_dashscope_content(raw)
    report = normalize_report(parse_model_json(content), title=title, video_url="", fps=fps)
    return {"mode": "local-path", "report": report, "raw": raw}


def analyze_video_url(config, title, video_url, analysis_mode, fps, subtitle_text, custom_prompt):
    model = config["omni_model"] if analysis_mode == "omni" else config["vision_model"]
    can_understand_audio = analysis_mode == "omni"
    needs_omni_stream = analysis_mode == "omni" and is_omni_family_model(model)
    prompt = build_analysis_prompt(
        title=title,
        fps=fps,
        can_understand_audio=can_understand_audio,
        subtitle_text=subtitle_text,
        custom_prompt=custom_prompt,
    )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "video_url", "video_url": {"url": video_url}, "fps": fps},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "temperature": 0.2,
    }
    if needs_omni_stream:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        payload["modalities"] = ["text"]
        content, raw = call_streaming_chat(config, payload)
    else:
        payload["enable_thinking"] = False
        data = call_chat(config, payload)
        raw = data
        content = (
            data.get("choices", [{}])[0].get("message", {}).get("content")
            or data.get("output", {}).get("choices", [{}])[0]
            .get("message", {})
            .get("content", [{}])[0]
            .get("text", "")
        )

    report = normalize_report(parse_model_json(content), title=title, video_url=video_url, fps=fps)
    return {"mode": analysis_mode, "report": report, "raw": raw}


def is_omni_family_model(model):
    return "omni" in str(model or "").lower()


def call_chat(config, payload):
    response = requests.post(
        f"{config['base_url']}/chat/completions",
        headers={
            "Authorization": f"Bearer {config['dashscope_api_key']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=600,
    )
    data = response.json() if response.text else {}
    if response.status_code >= 400:
        raise RuntimeError(data.get("error", {}).get("message") or data.get("message") or response.text)
    return data


def call_streaming_chat(config, payload):
    response = requests.post(
        f"{config['base_url']}/chat/completions",
        headers={
            "Authorization": f"Bearer {config['dashscope_api_key']}",
            "Content-Type": "application/json",
        },
        json=payload,
        stream=True,
        timeout=600,
    )
    if response.status_code >= 400:
        raise RuntimeError(response.text)
    chunks = []
    content = ""
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        chunks.append(chunk)
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        piece = delta.get("content", "")
        if isinstance(piece, str):
            content += piece
    return content, {"chunks": chunks}


def upload_to_github_release(file_path):
    config = get_config()
    if not (config["github_token"] and config["github_owner"] and config["github_repo"]):
        raise RuntimeError("请先在设置里保存 GitHub Token、Owner 和 Repo。")
    path = Path(file_path)
    if not path.exists():
        raise RuntimeError("找不到本地视频文件。")
    if path.stat().st_size > 2 * 1024 * 1024 * 1024:
        raise RuntimeError("GitHub Release asset 建议不超过 2GB。")

    release = get_or_create_release(config)
    upload_base = release["upload_url"].split("{")[0]
    asset_name = f"{sanitize(config['github_asset_prefix'])}-{int(path.stat().st_mtime)}-{uuid.uuid4()}-{path.name}"
    upload_url = f"{upload_base}?name={quote(asset_name)}"
    content_type = guess_video_mime(path)
    with path.open("rb") as handle:
        response = requests.post(
            upload_url,
            headers=github_headers(config["github_token"], content_type),
            data=handle,
            timeout=600,
        )
    data = response.json() if response.text else {}
    if response.status_code >= 400:
        raise RuntimeError(f"GitHub 上传失败：{data.get('message') or response.text}")
    return data["browser_download_url"]


def get_or_create_release(config):
    owner = quote(config["github_owner"])
    repo = quote(config["github_repo"])
    tag = quote(config["github_release_tag"])
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
    response = requests.get(url, headers=github_headers(config["github_token"]), timeout=60)
    if response.status_code == 200:
        return response.json()
    if response.status_code != 404:
        raise RuntimeError(f"GitHub 查询 Release 失败：{response.text}")

    response = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/releases",
        headers=github_headers(config["github_token"], "application/json"),
        json={
            "tag_name": config["github_release_tag"],
            "name": config["github_release_name"],
            "body": "Temporary video uploads for the native video agent GUI.",
            "draft": False,
            "prerelease": False,
        },
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"GitHub 创建 Release 失败：{response.text}")
    return response.json()


def github_headers(token, content_type=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "native-video-agent-gui",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def response_to_dict(response):
    raw = {}
    for attr in ("status_code", "code", "message", "request_id", "usage", "output"):
        if hasattr(response, attr):
            raw[attr] = to_jsonable(getattr(response, attr))
    if raw:
        return raw
    if isinstance(response, dict):
        return response
    return to_jsonable(getattr(response, "__dict__", {"rawText": str(response)}))


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
        return {
            str(key): to_jsonable(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return str(value)


def extract_dashscope_content(raw):
    choices = raw.get("output", {}).get("choices") or raw.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
    return raw.get("rawText") or json.dumps(raw, ensure_ascii=False)


def parse_model_json(content):
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    text = unwrap_model_text(str(content or ""))
    for candidate in json_candidates(text):
        parsed = parse_json_like(candidate)
        if parsed is not None:
            if isinstance(parsed, str) and looks_like_json_object(parsed):
                nested = parse_json_like(unwrap_model_text(parsed))
                return nested if isinstance(nested, dict) else {"rawText": parsed}
            return parsed
    return {"rawText": text}


def unwrap_model_text(text):
    text = text.strip().lstrip("\ufeff")
    text = re.sub(r"^```(?:json|javascript|js)?\s*", "", text, flags=re.I).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def json_candidates(text):
    cleaned = unwrap_model_text(text)
    candidates = [cleaned]
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(cleaned[first : last + 1])
    return candidates


def parse_json_like(text):
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        pass
    relaxed = re.sub(r",(\s*[}\]])", r"\1", text)
    try:
        return json.loads(relaxed)
    except json.JSONDecodeError:
        return None


def looks_like_json_object(text):
    stripped = str(text or "").strip()
    return stripped.startswith("{") and stripped.endswith("}")


def normalize_report(data, title, video_url="", fps=1):
    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    shots = find_shots(data) if isinstance(data, dict) else []
    normalized_shots = []
    for index, shot in enumerate(shots if isinstance(shots, list) else []):
        if not isinstance(shot, dict):
            continue
        timecode = str(first_value(shot, "timecode", "time", "时间码", "时间", "timestamp") or "")
        start = first_value(shot, "start", "开始", "startTime", "start_time")
        try:
            start = float(start)
        except (TypeError, ValueError):
            start = parse_start_seconds(timecode, index * 10)
        normalized_shots.append(
            {
                "shot": first_value(shot, "shot", "id", "镜号", "镜头", "shotNumber", "shot_number") or f"镜 {index + 1}",
                "scene": first_value(shot, "scene", "场景", "sceneTitle", "scene_title") or "",
                "timecode": timecode or format_range(start, start + 10),
                "start": start,
                "end": first_value(shot, "end", "结束", "endTime", "end_time") or start + 10,
                "shotSize": first_value(shot, "shotSize", "shot_size", "size", "景别") or "未标注",
                "camera": first_value(shot, "camera", "motion", "cameraMovement", "camera_movement", "镜头运动") or "未标注",
                "visual": first_value(
                    shot,
                    "visual",
                    "content",
                    "description",
                    "画面内容",
                    "画面内容 / 人物动作",
                    "画面内容/人物动作",
                    "画面内容与人物动作",
                    "人物动作",
                )
                or "",
                "audio": first_value(
                    shot,
                    "audio",
                    "sound",
                    "music",
                    "soundMusic",
                    "sound_music",
                    "声音",
                    "音频",
                    "音乐",
                    "声音 / 音乐",
                    "声音/音乐",
                )
                or "",
                "analysis": first_value(
                    shot,
                    "analysis",
                    "note",
                    "notes",
                    "annotation",
                    "commentary",
                    "分析",
                    "分析注释",
                    "注释",
                )
                or "",
            }
        )
    if not normalized_shots:
        normalized_shots.append(
            {
                "shot": "原始输出",
                "scene": "",
                "timecode": "",
                "start": 0,
                "end": 0,
                "shotSize": "",
                "camera": "",
                "visual": data.get("rawText", "模型返回内容未能解析为逐镜 JSON。") if isinstance(data, dict) else "",
                "audio": "",
                "analysis": "请调整提示词后重试。",
            }
        )
    return {
        "meta": {
            "title": meta.get("title") or title or "逐镜拉片报告",
            "episode": meta.get("episode") or "",
            "duration": meta.get("duration") or "",
            "sceneCount": meta.get("sceneCount") or len(data.get("scenes", [])) if isinstance(data, dict) else 0,
            "shotCount": meta.get("shotCount") or len(normalized_shots),
            "basis": meta.get("basis") or f"基于 {fps} fps 抽帧的视觉理解分析",
        },
        "scenes": data.get("scenes", []) if isinstance(data, dict) else [],
        "shots": normalized_shots,
        "videoUrl": video_url,
    }


def find_shots(data):
    for key in ("shots", "shotList", "shot_list", "镜头列表", "镜头", "逐镜", "拉片"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    for value in data.values():
        if isinstance(value, dict):
            nested = find_shots(value)
            if nested:
                return nested
    return []


def first_value(mapping, *keys):
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def export_markdown(report, path):
    meta = report.get("meta", {})
    lines = [
        f"# {meta.get('title', '逐镜拉片报告')}",
        "",
        f"- 片长：{meta.get('duration', '待识别')}",
        f"- 场景：{meta.get('sceneCount', 0)}",
        f"- 镜头：{meta.get('shotCount', 0)}",
        f"- 分析依据：{meta.get('basis', '')}",
        "",
        "| 镜号 | 时间码 | 景别 | 镜头运动 | 画面内容 / 人物动作 | 声音 / 音乐 | 分析注释 |",
        "|---|---|---|---|---|---|---|",
    ]
    for shot in report.get("shots", []):
        row = [
            shot.get("shot", ""),
            shot.get("timecode", ""),
            shot.get("shotSize", ""),
            shot.get("camera", ""),
            shot.get("visual", ""),
            shot.get("audio", ""),
            shot.get("analysis", ""),
        ]
        lines.append("| " + " | ".join(markdown_cell(value) for value in row) + " |")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def export_csv(report, path):
    headers = ["镜号", "场景", "时间码", "景别", "镜头运动", "画面内容 / 人物动作", "声音 / 音乐", "分析注释"]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for shot in report.get("shots", []):
            writer.writerow(
                [
                    shot.get("shot", ""),
                    shot.get("scene", ""),
                    shot.get("timecode", ""),
                    shot.get("shotSize", ""),
                    shot.get("camera", ""),
                    shot.get("visual", ""),
                    shot.get("audio", ""),
                    shot.get("analysis", ""),
                ]
            )


def parse_start_seconds(timecode, fallback=0):
    first = str(timecode or "").split("-")[0].strip()
    try:
        parts = [float(part) for part in first.split(":")]
    except ValueError:
        return fallback
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] if parts else fallback


def format_range(start, end):
    return f"{format_time(start)}-{format_time(end)}"


def format_time(seconds):
    safe = max(0, int(round(seconds)))
    h, rem = divmod(safe, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def markdown_cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def clamp_float(value, min_value, max_value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = min_value
    return max(min_value, min(max_value, number))


def sanitize(value):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "video-agent")).strip("-") or "video-agent"


def guess_video_mime(path):
    ext = Path(path).suffix.lower()
    return {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".m4v": "video/mp4",
        ".webm": "video/webm",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
    }.get(ext, "video/mp4")
