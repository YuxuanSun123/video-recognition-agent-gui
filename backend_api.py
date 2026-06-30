import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from video_agent_core import (
    ROOT as DATA_ROOT,
    analyze_video,
    get_config,
    mask_secret,
    save_config,
    upload_to_github_release,
)


ROOT = DATA_ROOT
CACHE_DIR = ROOT / ".cache"
UPLOAD_DIR = CACHE_DIR / "uploads"
THUMB_DIR = CACHE_DIR / "thumbnails"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Shot Reader Local API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5177",
        "http://localhost:5177",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media/thumbnails", StaticFiles(directory=str(THUMB_DIR)), name="thumbnails")


@app.get("/api/health")
def health():
    config = get_config()
    return {
        "ok": True,
        "dashscope": bool(config.get("dashscope_api_key")),
        "visionModel": config.get("vision_model"),
        "omniModel": config.get("omni_model"),
    }


@app.get("/api/config")
def read_config():
    config = get_config()
    safe = dict(config)
    safe["dashscope_api_key"] = ""
    safe["github_token"] = ""
    safe["dashscope_api_key_masked"] = mask_secret(config.get("dashscope_api_key"))
    safe["github_token_masked"] = mask_secret(config.get("github_token"))
    return safe


@app.post("/api/config")
async def write_config(payload: dict):
    save_config(payload)
    return read_config()


@app.post("/api/upload/github")
async def github_upload(file: UploadFile = File(...)):
    path = await persist_upload(file)
    try:
        url = upload_to_github_release(str(path))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"url": url, "localPath": str(path)}


@app.post("/api/analyze")
async def analyze(
    mode: str = Form("local"),
    title: str = Form("逐镜拉片报告"),
    video_url: str = Form(""),
    analysis_mode: str = Form("vision"),
    fps: str = Form("1"),
    subtitle_text: str = Form(""),
    custom_prompt: str = Form(""),
    file: UploadFile | None = File(None),
):
    local_path = ""
    if file and file.filename:
        local_path = str(await persist_upload(file))
    if mode == "github":
        if not local_path:
            raise HTTPException(status_code=400, detail="请先选择本地视频文件。")
        try:
            video_url = upload_to_github_release(local_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        local_for_analysis = ""
    else:
        local_for_analysis = local_path if mode == "local" else ""

    try:
        result = analyze_video(
            title=title,
            video_url=video_url,
            local_path=local_for_analysis,
            analysis_mode=analysis_mode,
            fps=fps,
            subtitle_text=subtitle_text,
            custom_prompt=custom_prompt,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if local_path:
        attach_thumbnails(result["report"], local_path)
    return JSONResponse(result)


async def persist_upload(file: UploadFile) -> Path:
    suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    path = UPLOAD_DIR / safe_name
    with path.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    return path


def attach_thumbnails(report, video_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return
    video = Path(video_path)
    if not video.exists():
        return
    batch = THUMB_DIR / uuid.uuid4().hex
    batch.mkdir(parents=True, exist_ok=True)
    for index, shot in enumerate(report.get("shots", [])):
        start = shot_start_seconds(shot, index)
        output = batch / f"shot-{index + 1:03d}.png"
        args = [
            ffmpeg,
            "-y",
            "-ss",
            f"{max(start, 0):.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=160:90:force_original_aspect_ratio=decrease,pad=160:90:(ow-iw)/2:(oh-ih)/2:color=0x151b20",
            "-f",
            "image2",
            str(output),
        ]
        try:
            subprocess.run(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (subprocess.SubprocessError, OSError):
            continue
        if output.exists():
            shot["thumbnailUrl"] = f"/media/thumbnails/{batch.name}/{output.name}"


def shot_start_seconds(shot, index):
    try:
        return float(shot.get("start"))
    except (TypeError, ValueError):
        pass
    timecode = str(shot.get("timecode") or "")
    for separator in ("-", "–", "—", "~", "至"):
        if separator in timecode:
            timecode = timecode.split(separator, 1)[0]
            break
    return time_string_to_seconds(timecode.strip(), index * 10)


def time_string_to_seconds(value, fallback=0):
    if not value:
        return fallback
    parts = [part.strip() for part in value.replace("：", ":").split(":") if part.strip()]
    try:
        nums = [float(part) for part in parts]
    except ValueError:
        return fallback
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 1:
        return nums[0]
    return fallback


def main():
    import uvicorn

    host = os.environ.get("VIDEO_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("VIDEO_AGENT_PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level=os.environ.get("VIDEO_AGENT_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
