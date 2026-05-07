# Bulk Content Generator

Generate batches of animated short-form vertical videos (1080×1920) from your AI images and scripts, powered by **Kling AI** image-to-video with automatic TTS narration and caption overlays.

## What it does

1. **Upload 1–20 images** of yourself (AI-generated or real photos).
2. **Paste your scripts**, separated by `---` lines.
3. *(Optional)* Add **visual motion prompts** (one per script block) to control how Kling animates each image.
4. **Configure** video count (1–20), image mode, script mode, Kling clip duration (5s/10s), and quality.
5. **Generate** — each script becomes a fully animated MP4 with:
   - Kling AI animation of your image (falls back to Ken Burns zoom if no API key)
   - Google TTS narration of your script
   - Progressive caption overlay at the bottom
6. **Download** individually or as a ZIP.

## Quick Start

```bash
# 1. Install ffmpeg (required by MoviePy)
sudo apt install ffmpeg        # Linux
brew install ffmpeg            # macOS

# 2. Add your Kling credentials
cp .env.example .env
# Edit .env and fill in KLING_ACCESS_KEY + KLING_SECRET_KEY

# 3. Run
bash start.sh
```

Open **http://localhost:8000** in your browser.

## Getting Kling API Keys

1. Sign up at [klingai.com](https://klingai.com)
2. Go to **Developer** → **API Keys**
3. Copy your **Access Key** and **Secret Key** into `.env`

You can also paste keys directly in the web UI (Step 3 → Kling AI Animation section) — useful for testing without touching the `.env` file.

## Script Format

Separate individual scripts with a `---` line:

```
Hey everyone! Today I want to talk about growing your social media...

---

Did you know the algorithm rewards consistency more than virality?

---

Here’s the exact posting schedule I use to stay consistent...
```

**Visual Prompts (optional):** Enter one line per script block in the prompts textarea to control Kling’s animation:
```
walking through golden hour light, slow push in
smiling at camera, bokeh background, dynamic energy
pointing to text on screen, confident posture
```
Leave any line blank to auto-extract a prompt from the script.

**Run-On mode:** paste one long script and it splits evenly across all videos — great for repurposing long-form content.

## Output

- Format: MP4 (H.264 + AAC)
- Resolution: 1080×1920 (9:16 vertical)
- FPS: 30
- Duration: Kling clip length + TTS narration (video loops if TTS is longer)

## Folder Structure

```
bulk-content-generator/
├── app.py          # FastAPI routes
├── generator.py    # KlingClient + VideoGenerator + script/prompt parsers
├── requirements.txt
├── start.sh
├── .env.example    # Copy to .env and fill in Kling credentials
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   └── app.js
├── uploads/        # Temp image storage
└── outputs/        # Generated videos
```
