# Bulk Content Generator

Generate batches of short-form vertical videos (1080×1920) from your images and scripts — powered by Python, FastAPI, MoviePy, and Google TTS.

## What it does

1. **Upload 1–20 images** of yourself (AI-generated or real photos).
2. **Paste your scripts**, separated by `---` lines.
3. **Configure** video count (5–20), image selection (rotation or random), and script mode (separate or run-on).
4. **Generate** — each script becomes an MP4 with:
   - Ken Burns slow-zoom effect on your image
   - Google TTS narration of your script
   - Progressive caption overlay at the bottom
5. **Download** videos individually or as a ZIP.

## Quick Start

```bash
bash start.sh
```

Then open **http://localhost:8000** in your browser.

## Requirements

- Python 3.9+
- `ffmpeg` installed and on your PATH (`sudo apt install ffmpeg` or `brew install ffmpeg`)
- Internet connection for Google TTS (videos will be silent if offline)

## Script Format

Separate individual scripts with a `---` line:

```
Hey everyone! Today I want to talk about growing your social media...

---

Did you know the algorithm rewards consistency more than virality?

---

Here's the exact posting schedule I use to stay consistent...
```

**Run-On mode**: paste one long script and it will be split evenly across all videos — great for series content or long-form repurposed to short clips.

## Output

- Format: MP4 (H.264 + AAC)
- Resolution: 1080×1920 (9:16 vertical)
- FPS: 30
- Duration: matches TTS narration length

## Folder Structure

```
bulk-content-generator/
├── app.py          # FastAPI application & routes
├── generator.py    # VideoGenerator class (Ken Burns + TTS + captions)
├── requirements.txt
├── start.sh
├── templates/
│   └── index.html  # Step-wizard web UI
├── static/
│   ├── style.css
│   └── app.js
├── uploads/        # Temp image storage (auto-created)
└── outputs/        # Generated videos (auto-created)
```
