import os
import uuid
import tempfile
import zipfile
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from generator import generate_content
from video_generator import start_video, check_video

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

CONTENT_TYPES = [
    ("blog_post", "Blog Post"),
    ("social_media", "Social Media Posts"),
    ("product_description", "Product Description"),
    ("email", "Email"),
    ("ad_copy", "Ad Copy"),
    ("seo_article", "SEO Article"),
]

TONES = ["professional", "friendly", "excited", "helpful", "urgent", "casual", "formal", "humorous"]

# In-memory store for video tasks
video_tasks = {}
UPLOAD_DIR = Path(tempfile.gettempdir()) / "bcg_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@app.route("/")
def index():
    return render_template("index.html", content_types=CONTENT_TYPES, tones=TONES)


# ── Content generation ──────────────────────────────────────────

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    topics_raw = data.get("topics", "").strip()
    content_type = data.get("content_type", "blog_post")
    tone = data.get("tone", "professional")

    if not topics_raw:
        return jsonify({"error": "Please enter at least one topic."}), 400

    topics = [t.strip() for t in topics_raw.splitlines() if t.strip()]
    results = []
    for topic in topics:
        try:
            content = generate_content(topic, content_type, tone)
            results.append({"topic": topic, "content": content, "error": None})
        except Exception as e:
            results.append({"topic": topic, "content": None, "error": str(e)})

    return jsonify({"results": results})


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    results = data.get("results", [])
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    with zipfile.ZipFile(tmp.name, "w") as zf:
        for i, item in enumerate(results, start=1):
            if item.get("content"):
                safe = item["topic"][:50].replace(" ", "_").replace("/", "-")
                zf.writestr(f"{i:03d}_{safe}.txt",
                            f"Topic: {item['topic']}\n{'='*60}\n\n{item['content']}")
    return send_file(tmp.name, as_attachment=True,
                     download_name="generated_content.zip", mimetype="application/zip")


# ── Video generation ────────────────────────────────────────────

@app.route("/video/script", methods=["POST"])
def video_script():
    """Generate a short spoken script from a topic."""
    data = request.get_json()
    topic = data.get("topic", "").strip()
    tone = data.get("tone", "friendly")
    if not topic:
        return jsonify({"error": "Please enter a topic."}), 400
    try:
        # Generate a short 30-second spoken script
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": (
                f"Write a short 30-second spoken video script (around 80 words) about: {topic}.\n"
                f"Tone: {tone}. Write it as natural speech — no stage directions, no headers, "
                "just the words the person will say directly to camera."
            )}],
        )
        return jsonify({"script": msg.content[0].text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/video/start", methods=["POST"])
def video_start():
    topic = request.form.get("topic", "").strip()
    script = request.form.get("script", "").strip()
    duration = int(request.form.get("duration", 5))
    image_file = request.files.get("image")

    if not script:
        return jsonify({"error": "Script is required."}), 400
    if not image_file:
        return jsonify({"error": "Please upload a photo."}), 400

    ext = Path(image_file.filename).suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        return jsonify({"error": "Photo must be JPG, PNG, or WebP."}), 400

    image_path = UPLOAD_DIR / f"{uuid.uuid4()}{ext}"
    image_file.save(image_path)

    task_id = str(uuid.uuid4())
    video_tasks[task_id] = {"status": "starting", "url": None, "error": None}

    def run():
        try:
            kling_task_id = start_video(str(image_path), script, duration)
            video_tasks[task_id]["kling_id"] = kling_task_id
            video_tasks[task_id]["status"] = "processing"
            # Poll until done (max 10 minutes)
            for _ in range(120):
                import time; time.sleep(5)
                result = check_video(kling_task_id)
                if result["status"] == "done":
                    video_tasks[task_id]["status"] = "done"
                    video_tasks[task_id]["url"] = result["url"]
                    return
                elif result["status"] == "failed":
                    video_tasks[task_id]["status"] = "failed"
                    video_tasks[task_id]["error"] = result.get("error", "Failed")
                    return
            video_tasks[task_id]["status"] = "failed"
            video_tasks[task_id]["error"] = "Timed out after 10 minutes."
        except Exception as e:
            video_tasks[task_id]["status"] = "failed"
            video_tasks[task_id]["error"] = str(e)
        finally:
            if image_path.exists():
                image_path.unlink()

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/video/status/<task_id>")
def video_status(task_id):
    task = video_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found."}), 404
    return jsonify(task)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    missing = [k for k in ("ANTHROPIC_API_KEY", "KLING_API_KEY") if not os.getenv(k)]
    if missing:
        print(f"ERROR: Missing in .env: {', '.join(missing)}")
    else:
        print("Starting Bulk Content Generator...")
        print("Open your browser and go to: http://localhost:5000")
        app.run(debug=False, port=5000)
