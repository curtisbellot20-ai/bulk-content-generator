import os
import uuid
import zipfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

load_dotenv()

app = FastAPI(title="Bulk Content Generator")

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
for _d in [UPLOAD_DIR, OUTPUT_DIR, Path("static"), Path("templates")]:
    _d.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

jobs: dict = {}
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/session")
async def create_session():
    sid = str(uuid.uuid4())
    (UPLOAD_DIR / sid).mkdir(parents=True, exist_ok=True)
    return {"session_id": sid}


@app.post("/api/upload-image/{session_id}")
async def upload_image(session_id: str, image: UploadFile = File(...)):
    session_dir = UPLOAD_DIR / session_id
    if not session_dir.exists():
        return JSONResponse({"error": "Invalid session"}, status_code=400)
    existing = [f for f in session_dir.iterdir() if f.suffix.lower() in ALLOWED_EXTS]
    if len(existing) >= 20:
        return JSONResponse({"error": "Maximum 20 images allowed"}, status_code=400)
    suffix = Path(image.filename or "img.jpg").suffix.lower()
    if suffix not in ALLOWED_EXTS:
        return JSONResponse({"error": f"Unsupported type: {suffix}"}, status_code=400)
    filename = f"{uuid.uuid4()}{suffix}"
    (session_dir / filename).write_bytes(await image.read())
    return {"filename": filename, "original": image.filename}


@app.delete("/api/upload-image/{session_id}/{filename}")
async def delete_image(session_id: str, filename: str):
    path = UPLOAD_DIR / session_id / Path(filename).name
    if path.exists():
        path.unlink()
    return {"ok": True}


# ---------------------------------------------------------------------------
# AI script generation
# ---------------------------------------------------------------------------

@app.post("/api/generate-scripts")
async def generate_scripts(
    description: str = Form(...),
    count: int = Form(default=5),
    anthropic_key: str = Form(default=""),
):
    """Generate scripts + Kling motion prompts via Claude and return them."""
    api_key = anthropic_key.strip() or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return JSONResponse(
            {"error": "Anthropic API key required. Add to .env or enter in the UI."},
            status_code=400,
        )
    count = max(1, min(20, count))
    try:
        from generator import generate_scripts_and_prompts
        items = generate_scripts_and_prompts(description, count, api_key)
        return {"items": items}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# Video generation
# ---------------------------------------------------------------------------

@app.post("/api/generate")
async def generate_videos(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    scripts: str = Form(...),
    prompts: str = Form(default=""),
    video_count: int = Form(default=5),
    image_mode: str = Form(default="rotation"),
    script_mode: str = Form(default="separate"),
    clip_duration: str = Form(default="5"),
    kling_mode: str = Form(default="std"),
    piapi_key: str = Form(default=""),
    kling_access_key: str = Form(default=""),
    kling_secret_key: str = Form(default=""),
):
    video_count = max(1, min(20, video_count))
    session_dir = UPLOAD_DIR / session_id
    if not session_dir.exists():
        return JSONResponse({"error": "Invalid session"}, status_code=400)
    image_paths = sorted(str(p) for p in session_dir.iterdir() if p.suffix.lower() in ALLOWED_EXTS)
    if not image_paths:
        return JSONResponse({"error": "No images uploaded"}, status_code=400)
    if not scripts.strip():
        return JSONResponse({"error": "No scripts provided"}, status_code=400)

    # PiAPI key takes priority over direct Kling keys
    piapi_key_val = piapi_key.strip() or os.getenv("PIAPI_KEY", "")
    access_key = kling_access_key.strip() or os.getenv("KLING_ACCESS_KEY", "")
    secret_key = kling_secret_key.strip() or os.getenv("KLING_SECRET_KEY", "")
    using_kling = bool(piapi_key_val or (access_key and secret_key))

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "queued", "progress": 0, "total": video_count,
        "videos": [], "error": None, "using_kling": using_kling,
    }
    background_tasks.add_task(
        _run_generation,
        job_id=job_id, image_paths=image_paths,
        scripts_text=scripts, prompts_text=prompts,
        video_count=video_count, image_mode=image_mode,
        script_mode=script_mode, clip_duration=clip_duration,
        kling_mode=kling_mode, piapi_key=piapi_key_val,
        access_key=access_key, secret_key=secret_key,
    )
    return {"job_id": job_id}


def _run_generation(job_id, image_paths, scripts_text, prompts_text, video_count,
                   image_mode, script_mode, clip_duration, kling_mode,
                   piapi_key, access_key, secret_key):
    from generator import (
        KlingClient, PiAPIKlingClient, VideoGenerator, parse_prompts, parse_scripts,
    )
    output_dir = OUTPUT_DIR / job_id
    output_dir.mkdir(exist_ok=True)
    jobs[job_id]["status"] = "running"
    try:
        if piapi_key:
            kling = PiAPIKlingClient(piapi_key)
        elif access_key and secret_key:
            kling = KlingClient(access_key, secret_key)
        else:
            kling = None

        scripts = parse_scripts(scripts_text, video_count, script_mode)
        prompt_list = parse_prompts(prompts_text, scripts)
        gen = VideoGenerator(image_paths, image_mode=image_mode, kling_client=kling,
                             clip_duration=clip_duration, kling_mode=kling_mode)
        done = []
        for i, (script, prompt) in enumerate(zip(scripts[:video_count], prompt_list)):
            jobs[job_id]["progress"] = i
            out = str(output_dir / f"video_{i+1:02d}.mp4")
            gen.create_video(script, prompt, out, video_index=i)
            done.append(f"video_{i+1:02d}.mp4")
            jobs[job_id]["videos"] = done.copy()
        jobs[job_id]["status"] = "complete"
        jobs[job_id]["progress"] = video_count
    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(exc)
        raise


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return jobs[job_id]


@app.get("/api/download/{job_id}/{filename}")
async def download_video(job_id: str, filename: str):
    filename = Path(filename).name
    path = OUTPUT_DIR / job_id / filename
    if not path.exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(str(path), media_type="video/mp4", filename=filename)


@app.get("/api/download-all/{job_id}")
async def download_all(job_id: str):
    output_dir = OUTPUT_DIR / job_id
    if not output_dir.exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    zip_path = OUTPUT_DIR / f"{job_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for mp4 in sorted(output_dir.glob("*.mp4")):
            zf.write(mp4, mp4.name)
    return FileResponse(str(zip_path), media_type="application/zip", filename="bulk_videos.zip")
