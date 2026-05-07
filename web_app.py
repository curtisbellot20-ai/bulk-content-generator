import os
import uuid
import random
import tempfile
import zipfile
import threading
import time
import requests
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from generator import generate_scripts_and_prompts
from video_generator import start_video, check_video

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

UPLOAD_DIR = Path(tempfile.gettempdir()) / "bcg_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

sessions = {}    # session_id -> {images: [path, ...]}
video_tasks = {} # task_id -> {status, index, script, motion, url, error}


@app.route("/")
def index():
    return render_template("index.html", session_id=str(uuid.uuid4()))


@app.route("/session/images", methods=["POST"])
def upload_images():
    session_id = request.form.get("session_id", "")
    files = request.files.getlist("images")
    if not files:
        return jsonify({"error": "No images received."}), 400
    if len(files) > 20:
        return jsonify({"error": "Maximum 20 images."}), 400

    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(exist_ok=True)

    saved = []
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        fpath = session_dir / f"{uuid.uuid4()}{ext}"
        f.save(fpath)
        saved.append(str(fpath))

    if not saved:
        return jsonify({"error": "No valid images (JPG, PNG, WebP)."}), 400

    sessions.setdefault(session_id, {})["images"] = saved
    return jsonify({"count": len(saved)})


@app.route("/generate", methods=["POST"])
def generate():
    """Generate scripts+prompts with Claude, then immediately kick off Kling videos."""
    data = request.get_json()
    session_id = data.get("session_id", "")
    theme = data.get("theme", "").strip()
    count = max(1, min(int(data.get("count", 5)), 20))
    image_mode = data.get("image_mode", "rotation")
    duration = int(data.get("duration", 5))

    if not theme:
        return jsonify({"error": "Enter a content idea."}), 400

    images = sessions.get(session_id, {}).get("images", [])
    if not images:
        return jsonify({"error": "Upload at least one photo first."}), 400

    # Step 1 — Claude generates scripts + motion prompts
    try:
        items = generate_scripts_and_prompts(theme, count)
    except Exception as e:
        return jsonify({"error": f"Script generation failed: {e}"}), 500

    # Step 2 — Build tasks and start Kling in background
    tasks = []
    for i, item in enumerate(items):
        img = images[i % len(images)] if image_mode == "rotation" else random.choice(images)
        tid = str(uuid.uuid4())
        video_tasks[tid] = {
            "status": "queued",
            "index": i + 1,
            "script": item.get("script", ""),
            "motion": item.get("motion", ""),
            "url": None,
            "error": None,
        }
        tasks.append({"task_id": tid, "image": img,
                      "motion": item.get("motion", ""), "duration": duration})

    threading.Thread(target=_run_batch, args=(tasks,), daemon=True).start()

    return jsonify({"tasks": [
        {"task_id": t["task_id"],
         "script": video_tasks[t["task_id"]]["script"],
         "motion": video_tasks[t["task_id"]]["motion"]}
        for t in tasks
    ]})


def _run_batch(tasks):
    for task in tasks:
        tid = task["task_id"]
        try:
            kling_id = start_video(task["image"], task["motion"], task["duration"])
            video_tasks[tid]["kling_id"] = kling_id
            video_tasks[tid]["status"] = "processing"
        except Exception as e:
            video_tasks[tid]["status"] = "failed"
            video_tasks[tid]["error"] = str(e)
        time.sleep(1.5)

    for _ in range(180):
        time.sleep(5)
        pending = [t for t in tasks if video_tasks[t["task_id"]]["status"] == "processing"]
        if not pending:
            break
        for task in pending:
            tid = task["task_id"]
            kling_id = video_tasks[tid].get("kling_id")
            if not kling_id:
                continue
            try:
                result = check_video(kling_id)
                if result["status"] == "done":
                    video_tasks[tid]["status"] = "done"
                    video_tasks[tid]["url"] = result["url"]
                elif result["status"] == "failed":
                    video_tasks[tid]["status"] = "failed"
                    video_tasks[tid]["error"] = result.get("error", "Unknown")
            except Exception:
                pass


@app.route("/status/videos", methods=["POST"])
def videos_status():
    task_ids = request.get_json().get("task_ids", [])
    return jsonify({tid: video_tasks.get(tid, {"status": "unknown"}) for tid in task_ids})


@app.route("/download/videos", methods=["POST"])
def download_videos():
    task_ids = request.get_json().get("task_ids", [])
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    with zipfile.ZipFile(tmp.name, "w") as zf:
        for tid in task_ids:
            task = video_tasks.get(tid, {})
            if task.get("status") == "done" and task.get("url"):
                try:
                    resp = requests.get(task["url"], timeout=60)
                    resp.raise_for_status()
                    zf.writestr(f"video_{task['index']:02d}.mp4", resp.content)
                except Exception:
                    pass
    return send_file(tmp.name, as_attachment=True,
                     download_name="videos.zip", mimetype="application/zip")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    missing = [k for k in ("ANTHROPIC_API_KEY", "KLING_API_KEY") if not os.getenv(k)]
    if missing:
        for k in missing:
            print(f"WARNING: {k} not set in .env")
    print("Starting... open http://localhost:5000")
    app.run(debug=False, port=5000)
