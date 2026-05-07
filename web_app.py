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
from video_generator import start_video, check_video

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

UPLOAD_DIR = Path(tempfile.gettempdir()) / "bcg_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory stores (reset on server restart)
sessions = {}   # session_id -> {images: [path, ...]}
video_tasks = {}  # task_id -> {status, index, script_preview, url, error}


@app.route("/")
def index():
    return render_template("index.html", session_id=str(uuid.uuid4()))


# ── Image upload ────────────────────────────────────────────────────────────

@app.route("/session/images", methods=["POST"])
def upload_images():
    session_id = request.form.get("session_id", "")
    files = request.files.getlist("images")
    if not files:
        return jsonify({"error": "No images received."}), 400
    if len(files) > 20:
        return jsonify({"error": "Maximum 20 images allowed."}), 400

    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(exist_ok=True)

    saved = []
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        fname = f"{uuid.uuid4()}{ext}"
        fpath = session_dir / fname
        f.save(fpath)
        saved.append(str(fpath))

    if not saved:
        return jsonify({"error": "No valid images. Use JPG, PNG, or WebP."}), 400

    sessions.setdefault(session_id, {})["images"] = saved
    return jsonify({"count": len(saved)})


# ── Batch video generation ───────────────────────────────────────────────────

@app.route("/generate/videos", methods=["POST"])
def generate_videos():
    data = request.get_json()
    session_id = data.get("session_id", "")
    scripts = [s.strip() for s in data.get("scripts", []) if s.strip()]
    image_mode = data.get("image_mode", "rotation")  # "rotation" or "random"
    duration = int(data.get("duration", 5))

    if not scripts:
        return jsonify({"error": "No scripts provided."}), 400
    if len(scripts) > 20:
        return jsonify({"error": "Maximum 20 videos per batch."}), 400

    images = sessions.get(session_id, {}).get("images", [])
    if not images:
        return jsonify({"error": "No images uploaded. Upload your photos first."}), 400

    # Build task list
    tasks = []
    for i, script in enumerate(scripts):
        img = images[i % len(images)] if image_mode == "rotation" else random.choice(images)
        tid = str(uuid.uuid4())
        video_tasks[tid] = {
            "status": "queued",
            "index": i + 1,
            "script_preview": script[:80],
            "url": None,
            "error": None,
        }
        tasks.append({"task_id": tid, "image": img, "script": script, "duration": duration})

    threading.Thread(target=_run_batch, args=(tasks,), daemon=True).start()
    return jsonify({"tasks": [{"task_id": t["task_id"], "preview": t["script"][:80]} for t in tasks]})


def _run_batch(tasks):
    # Submit all to Kling in parallel (stagger slightly to avoid rate limits)
    for task in tasks:
        tid = task["task_id"]
        try:
            kling_id = start_video(task["image"], task["script"], task["duration"])
            video_tasks[tid]["kling_id"] = kling_id
            video_tasks[tid]["status"] = "processing"
        except Exception as e:
            video_tasks[tid]["status"] = "failed"
            video_tasks[tid]["error"] = str(e)
        time.sleep(1.5)  # small gap between submissions

    # Poll all pending tasks until complete (max 15 minutes)
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
                    video_tasks[tid]["error"] = result.get("error", "Unknown error")
            except Exception as e:
                pass  # keep polling


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
                    filename = f"video_{task['index']:02d}.mp4"
                    zf.writestr(filename, resp.content)
                except Exception:
                    pass
    return send_file(tmp.name, as_attachment=True,
                     download_name="videos.zip", mimetype="application/zip")


# ── Content generator (Claude) ───────────────────────────────────────────────

@app.route("/generate/scripts", methods=["POST"])
def generate_scripts():
    data = request.get_json()
    topics_raw = data.get("topics", "").strip()
    tone = data.get("tone", "friendly")
    if not topics_raw:
        return jsonify({"error": "Enter at least one topic."}), 400

    topics = [t.strip() for t in topics_raw.splitlines() if t.strip()]
    import anthropic
    client = anthropic.Anthropic()
    scripts = []
    for topic in topics:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": (
                f"Write a 30-second spoken video script (around 80 words) about: {topic}.\n"
                f"Tone: {tone}. Natural speech only — no stage directions, no headers."
            )}],
        )
        scripts.append(msg.content[0].text.strip())

    return jsonify({"scripts": scripts})


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    missing = [k for k in ("ANTHROPIC_API_KEY", "KLING_API_KEY") if not os.getenv(k)]
    if missing:
        for k in missing:
            print(f"WARNING: {k} not set in .env")
    print("Starting... open http://localhost:5000")
    app.run(debug=False, port=5000)
