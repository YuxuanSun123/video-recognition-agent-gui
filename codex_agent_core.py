import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from video_agent_core import (
    ROOT,
    clamp_float,
    export_csv,
    export_markdown,
    get_config,
    normalize_report,
    parse_model_json,
)


CACHE_DIR = ROOT / ".cache"
JOBS_DIR = CACHE_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

CODEX_TIMEOUT_SECONDS = int(os.environ.get("SHOT_READER_CODEX_TIMEOUT", "1800"))
CODEX_STATUS_TIMEOUT_SECONDS = int(os.environ.get("SHOT_READER_CODEX_STATUS_TIMEOUT", "45"))
CODEX_MAX_FRAMES = int(os.environ.get("SHOT_READER_CODEX_MAX_FRAMES", "24"))


def get_codex_status():
    executable = get_codex_command()
    if not executable:
        return {
            "installed": False,
            "ready": False,
            "authenticated": False,
            "status": "missing",
            "message": "未检测到 Codex CLI。请先安装并登录 Codex。",
        }

    version = read_codex_version()
    doctor = run_codex_doctor()
    if doctor.get("error"):
        return {
            "installed": True,
            "ready": False,
            "authenticated": False,
            "status": "doctor-failed",
            "message": doctor["error"],
            "version": version,
            "executable": executable,
        }

    checks = doctor.get("checks") or {}
    app_config = get_config()
    configured_model = normalize_codex_model(app_config.get("codex_model"))
    configured_effort = normalize_reasoning_effort(app_config.get("codex_reasoning_effort"))
    auth = checks.get("auth.credentials") or {}
    config = checks.get("config.load") or {}
    reachability = checks.get("network.provider_reachability") or {}
    websocket = checks.get("network.websocket_reachability") or {}
    authenticated = auth.get("status") == "ok"
    network_ok = reachability.get("status") in ("ok", None) or websocket.get("status") == "ok"
    ready = bool(authenticated and network_ok and doctor.get("overallStatus") != "error")

    auth_details = auth.get("details") or {}
    config_details = config.get("details") or {}
    auth_mode = auth_details.get("stored auth mode") or "unknown"
    model = configured_model or config_details.get("model") or ""
    reasoning_effort = configured_effort or config_details.get("model_reasoning_effort") or ""
    if not authenticated:
        message = "Codex 尚未登录。请在终端运行 codex login 完成登录。"
    elif not network_ok:
        message = "Codex 已登录，但当前网络无法稳定连接 ChatGPT/Codex 服务。请检查代理、VPN 或防火墙后重试。"
    else:
        message = "Codex 已就绪，可以使用本机登录状态运行分析。" if ready else "Codex 已安装，但运行状态不可用。"

    return {
        "installed": True,
        "ready": ready,
        "authenticated": authenticated,
        "status": "ready" if ready else "unavailable",
        "message": message,
        "version": version,
        "executable": executable,
        "authMode": auth_mode,
        "model": model,
        "reasoningEffort": reasoning_effort,
        "configuredModel": configured_model,
        "configuredReasoningEffort": configured_effort,
        "overallStatus": doctor.get("overallStatus"),
        "doctorSummary": {
            "auth": auth.get("summary"),
            "config": config.get("summary"),
            "reachability": reachability.get("summary") or websocket.get("summary"),
        },
    }


def read_codex_version():
    command = get_codex_command()
    if not command:
        return ""
    try:
        result = run_process([command, "--version"], timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stdout or result.stderr or "").strip()


def run_codex_doctor():
    command = get_codex_command()
    if not command:
        return {"error": "未检测到 Codex CLI。"}
    try:
        result = run_process(
            [command, "doctor", "--json"],
            timeout=CODEX_STATUS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"error": "Codex doctor 检测超时，请稍后重试。"}
    except OSError as exc:
        return {"error": f"无法启动 Codex：{exc}"}
    try:
        data = json.loads(result.stdout or "{}")
        data["_commandReturnCode"] = result.returncode
        return data
    except json.JSONDecodeError:
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return {"error": (detail or "Codex doctor 返回失败。")[:800]}
        return {"error": "Codex doctor 返回内容无法解析。"}


def create_codex_job(*, title, video_url="", local_path="", fps=1, subtitle_text="", custom_prompt=""):
    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "id": job_id,
        "mode": "codex",
        "status": "queued",
        "stage": "queued",
        "message": "Codex 分析任务已创建。",
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "progress": 0,
        "paths": {
            "jobDir": str(job_dir),
            "localPath": str(local_path or ""),
            "videoUrl": video_url or "",
        },
        "request": {
            "title": title,
            "videoUrl": video_url,
            "localPath": str(local_path or ""),
            "fps": str(fps),
            "subtitleText": subtitle_text,
            "customPrompt": custom_prompt,
        },
    }
    write_json(job_dir / "job.json", state)
    write_json(job_dir / "request.json", state["request"])
    return state


def get_codex_job(job_id):
    path = JOBS_DIR / safe_job_id(job_id) / "job.json"
    if not path.exists():
        raise KeyError(job_id)
    return json.loads(path.read_text(encoding="utf-8"))


def run_codex_job(job_id):
    job_id = safe_job_id(job_id)
    job_dir = JOBS_DIR / job_id
    state = get_codex_job(job_id)
    request = state.get("request") or {}
    title = request.get("title") or "逐镜拉片报告"
    video_url = request.get("videoUrl") or ""
    local_path = request.get("localPath") or ""
    fps = clamp_float(request.get("fps") or 1, 0.1, 10)

    try:
        update_job(job_id, status="running", stage="preparing", progress=8, message="正在准备 Codex 工作目录。")
        schema_path = write_output_schema(job_dir)

        update_job(job_id, stage="extracting", progress=22, message="正在抽取视频关键帧与音频素材。")
        assets = extract_video_assets(job_dir, local_path=local_path, video_url=video_url, fps=fps)
        write_json(job_dir / "asset_manifest.json", assets)

        update_job(job_id, stage="codex", progress=48, message="正在调用 Codex Agent 生成逐镜结构化报告。")
        raw_text, raw_meta = run_codex_exec(
            job_dir=job_dir,
            schema_path=schema_path,
            prompt=build_codex_prompt(
                title=title,
                fps=fps,
                video_url=video_url,
                local_path=local_path,
                subtitle_text=request.get("subtitleText") or "",
                custom_prompt=request.get("customPrompt") or "",
                assets=assets,
            ),
            images=[frame["path"] for frame in assets.get("frames", [])],
        )
        write_json(job_dir / "codex_run.json", raw_meta)

        update_job(job_id, stage="normalizing", progress=78, message="正在解析 Codex 输出并生成报告文件。")
        parsed = parse_model_json(raw_text)
        report = normalize_report(parsed, title=title, video_url=video_url, fps=fps)
        attach_frame_thumbnails(report, assets.get("frames", []), job_id)
        report.setdefault("meta", {})
        report["meta"]["provider"] = "Codex Agent"
        report["meta"]["basis"] = report["meta"].get("basis") or f"Codex Agent 基于 {len(assets.get('frames', []))} 张关键帧、用户字幕/转写与本地素材清单生成。"

        shots_path = job_dir / "shots.json"
        md_path = job_dir / "report.md"
        csv_path = job_dir / "report.csv"
        write_json(shots_path, report)
        export_markdown(report, md_path)
        export_csv(report, csv_path)

        update_job(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            message=f"Codex 分析完成：{len(report.get('shots', []))} 镜。",
            report=report,
            outputs={
                "shotsJson": str(shots_path),
                "markdown": str(md_path),
                "csv": str(csv_path),
                "rawResponse": str(job_dir / "raw_response.txt"),
            },
        )
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            message="Codex 分析失败。",
            error=str(exc),
        )


def extract_video_assets(job_dir, *, local_path="", video_url="", fps=1):
    frames_dir = job_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    source = Path(local_path) if local_path else None
    assets = {
        "source": {
            "localPath": str(source) if source else "",
            "videoUrl": video_url or "",
        },
        "ffmpeg": bool(ffmpeg),
        "ffprobe": bool(ffprobe),
        "duration": None,
        "frames": [],
        "audio": "",
        "warnings": [],
    }

    if not source or not source.exists():
        if video_url:
            assets["warnings"].append("当前只拿到了公网 URL，没有本地文件，Codex 将主要依据 URL、字幕和补充说明分析。")
        else:
            assets["warnings"].append("未提供可抽帧的本地视频。")
        return assets

    assets["source"]["sizeBytes"] = source.stat().st_size
    if not ffmpeg:
        assets["warnings"].append("未检测到 ffmpeg，无法自动抽帧。")
        return assets

    duration = probe_duration(source, ffprobe)
    assets["duration"] = duration
    sample_fps = clamp_float(fps, 0.1, 10)
    if duration and duration > 0:
        sample_fps = min(sample_fps, max(0.05, CODEX_MAX_FRAMES / duration))

    frame_pattern = frames_dir / "frame_%04d.jpg"
    args = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vf",
        f"fps={sample_fps:.4f},scale=1280:-2",
        "-frames:v",
        str(CODEX_MAX_FRAMES),
        str(frame_pattern),
    ]
    result = run_process(args, timeout=180)
    if result.returncode != 0:
        assets["warnings"].append((result.stderr or "ffmpeg 抽帧失败。").strip())
    frames = sorted(frames_dir.glob("frame_*.jpg"))
    for index, frame in enumerate(frames):
        assets["frames"].append(
            {
                "index": index + 1,
                "name": frame.name,
                "path": str(frame),
                "approxSecond": round(index / sample_fps, 3) if sample_fps else 0,
            }
        )

    audio_path = job_dir / "audio.wav"
    audio_args = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-t",
        "600",
        str(audio_path),
    ]
    audio_result = run_process(audio_args, timeout=180)
    if audio_result.returncode == 0 and audio_path.exists() and audio_path.stat().st_size:
        assets["audio"] = str(audio_path)
    elif audio_result.stderr:
        assets["warnings"].append("音频提取未完成：" + audio_result.stderr.strip()[:500])
    return assets


def probe_duration(source, ffprobe):
    if not ffprobe:
        return None
    result = run_process(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source),
        ],
        timeout=30,
    )
    try:
        return float((result.stdout or "").strip())
    except (TypeError, ValueError):
        return None


def run_codex_exec(*, job_dir, schema_path, prompt, images):
    command = get_codex_command()
    if not command:
        raise RuntimeError("未检测到 Codex CLI。")
    config = get_config()
    codex_model = normalize_codex_model(config.get("codex_model"))
    reasoning_effort = normalize_reasoning_effort(config.get("codex_reasoning_effort"))
    raw_path = job_dir / "raw_response.txt"
    stdout_path = job_dir / "codex_stdout.log"
    stderr_path = job_dir / "codex_stderr.log"
    args = [
        command,
        "exec",
        "--skip-git-repo-check",
        "--cd",
        str(job_dir),
        "--sandbox",
        "workspace-write",
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(raw_path),
        "--color",
        "never",
    ]
    if codex_model:
        args.extend(["--model", codex_model])
    if reasoning_effort:
        args.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    for image in images[:CODEX_MAX_FRAMES]:
        args.extend(["--image", image])
    args.append("-")

    result = run_process(args, timeout=CODEX_TIMEOUT_SECONDS, input_text=prompt, cwd=job_dir)
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    if result.returncode != 0:
        detail = summarize_codex_error(result.stderr or result.stdout or "")
        raise RuntimeError(detail or "Codex exec 返回失败。")

    raw_text = raw_path.read_text(encoding="utf-8") if raw_path.exists() else (result.stdout or "")
    if not raw_text.strip():
        raise RuntimeError("Codex 没有返回可解析的最终消息。")
    return raw_text, {
        "returnCode": result.returncode,
        "stdoutPath": str(stdout_path),
        "stderrPath": str(stderr_path),
        "rawPath": str(raw_path),
        "imageCount": min(len(images), CODEX_MAX_FRAMES),
        "model": codex_model or "codex-default",
        "reasoningEffort": reasoning_effort or "codex-default",
    }


def build_codex_prompt(*, title, fps, video_url, local_path, subtitle_text, custom_prompt, assets):
    frame_lines = "\n".join(
        f"- {frame['name']}：约 {frame.get('approxSecond', 0)} 秒"
        for frame in assets.get("frames", [])
    ) or "- 未能抽取关键帧。"
    warning_lines = "\n".join(f"- {item}" for item in assets.get("warnings", [])) or "- 无。"
    return f"""你是 Shot Reader 的本地 Codex Agent，任务是把视频素材整理成电影学院风格的逐镜拉片报告。

重要边界：
- 你不是原生视频接口；请依据本次 prompt 附加的关键帧图片、asset_manifest.json、用户提供的字幕/音轨转写和补充要求进行分析。
- 如果无法确认声音、对白或真实剪辑点，请明确写“需结合音轨/原片确认”，不要编造。
- 只输出符合 schema 的 JSON，不要输出 Markdown，不要输出解释文字，不要使用代码块。

片名/报告标题：{title}
抽帧 fps 设置：{fps}
本地视频路径：{local_path or "未提供"}
公网 URL：{video_url or "未提供"}
音频文件：{assets.get("audio") or "未提取"}
素材清单：asset_manifest.json

关键帧列表：
{frame_lines}

素材警告：
{warning_lines}

用户提供的字幕/音轨转写：
{subtitle_text or "未提供"}

用户补充要求：
{custom_prompt or "无"}

请生成 JSON：
- meta.title 使用报告标题。
- meta.duration 可以依据素材时长估计；未知时写“待确认”。
- scenes 至少按主要场景段落拆分。
- shots 要尽量逐镜拆分，字段必须包含 shot、scene、timecode、start、end、shotSize、camera、visual、audio、analysis。
- visual 写画面内容/人物动作；analysis 写镜头语言、叙事功能、构图、色彩或剪辑注释；audio 写可判断的声音/音乐/字幕依据。
"""


def write_output_schema(job_dir):
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["meta", "scenes", "shots"],
        "properties": {
            "meta": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "episode", "duration", "sceneCount", "shotCount", "basis"],
                "properties": {
                    "title": {"type": "string"},
                    "episode": {"type": "string"},
                    "duration": {"type": "string"},
                    "sceneCount": {"type": "integer"},
                    "shotCount": {"type": "integer"},
                    "basis": {"type": "string"},
                },
            },
            "scenes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "title", "start", "end", "summary"],
                    "properties": {
                        "id": {"type": "integer"},
                        "title": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                },
            },
            "shots": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["shot", "scene", "timecode", "start", "end", "shotSize", "camera", "visual", "audio", "analysis"],
                    "properties": {
                        "shot": {"type": "string"},
                        "scene": {"type": "string"},
                        "timecode": {"type": "string"},
                        "start": {"type": "number"},
                        "end": {"type": "number"},
                        "shotSize": {"type": "string"},
                        "camera": {"type": "string"},
                        "visual": {"type": "string"},
                        "audio": {"type": "string"},
                        "analysis": {"type": "string"},
                    },
                },
            },
        },
    }
    path = job_dir / "codex_report_schema.json"
    write_json(path, schema)
    return path


def attach_frame_thumbnails(report, frames, job_id):
    shots = report.get("shots") or []
    if not shots or not frames:
        return
    for index, shot in enumerate(shots):
        if len(shots) == 1:
            frame_index = 0
        else:
            frame_index = round(index * (len(frames) - 1) / (len(shots) - 1))
        frame = frames[max(0, min(frame_index, len(frames) - 1))]
        shot["thumbnailUrl"] = f"/media/jobs/{job_id}/frames/{Path(frame['path']).name}"


def update_job(job_id, **updates):
    path = JOBS_DIR / safe_job_id(job_id) / "job.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state.update(updates)
    state["updatedAt"] = now_iso()
    write_json(path, state)
    return state


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_process(args, *, timeout, input_text=None, cwd=None):
    return subprocess.run(
        args,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def summarize_codex_error(text):
    text = str(text or "").strip()
    if not text:
        return ""
    try:
        marker = '"message":'
        if marker in text:
            after = text.split(marker, 1)[1].strip()
            if after.startswith('"'):
                end = after.find('",', 1)
                if end != -1:
                    return json.loads(after[: end + 1])
    except (json.JSONDecodeError, ValueError):
        pass
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        if "ERROR:" in stripped or "error:" in stripped.lower():
            return stripped[-1000:]
    return text[-1000:]


def get_codex_command():
    names = ("codex.cmd", "codex.exe", "codex") if os.name == "nt" else ("codex",)
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return ""


def normalize_codex_model(value):
    return str(value or "").strip()


def normalize_reasoning_effort(value):
    value = str(value or "").strip().lower()
    allowed = {"", "minimal", "low", "medium", "high", "xhigh"}
    if value not in allowed:
        return ""
    return value


def safe_job_id(job_id):
    value = str(job_id or "")
    if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in value):
        raise KeyError(job_id)
    return value


def now_iso():
    return datetime.now(timezone.utc).isoformat()
