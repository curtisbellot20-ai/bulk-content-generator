import os
import json
import zipfile
import tempfile
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from generator import generate_content

app = Flask(__name__)

CONTENT_TYPES = [
    ("blog_post", "Blog Post"),
    ("social_media", "Social Media Posts"),
    ("product_description", "Product Description"),
    ("email", "Email"),
    ("ad_copy", "Ad Copy"),
    ("seo_article", "SEO Article"),
]

TONES = [
    "professional",
    "friendly",
    "excited",
    "helpful",
    "urgent",
    "casual",
    "formal",
    "humorous",
]


@app.route("/")
def index():
    return render_template("index.html", content_types=CONTENT_TYPES, tones=TONES)


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
                filename = f"{i:03d}_{safe}.txt"
                zf.writestr(filename, f"Topic: {item['topic']}\n{'='*60}\n\n{item['content']}")

    return send_file(tmp.name, as_attachment=True, download_name="generated_content.zip", mimetype="application/zip")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set in .env file.")
    else:
        print("Starting Bulk Content Generator...")
        print("Open your browser and go to: http://localhost:5000")
        app.run(debug=False, port=5000)
