# AI Bulk Video Generator

Upload your photos + scripts → Claude + Kling AI generate 5–20 talking head videos in one batch.

## Workflow

1. **Upload images** — 1–20 photos of yourself or your AI influencer
2. **Add scripts** — paste or upload a `.txt` file, scripts separated by `---`
3. **Choose settings** — image rotation vs random, 5 or 10 second clips
4. **Generate** — all videos render on Kling AI simultaneously
5. **Download** — preview each video or download all as a ZIP

## Write scripts with Claude

Use the **Write Scripts** tab to generate 30-second spoken scripts from topics using Claude AI. One click copies them into the video tab.

## Setup

### 1. Install Python 3.8+

### 2. Install dependencies
```bash
pip3 install -r requirements.txt
```

### 3. Add API keys
```bash
cp .env.example .env
```
Fill in your keys:
- `ANTHROPIC_API_KEY` — https://console.anthropic.com/
- `KLING_API_KEY` — https://klingai.com/dev

### 4. Run
```bash
python3 web_app.py
```
Open **http://localhost:5000**

## Script format

Separate multiple scripts with `---` on its own line:
```
Hey everyone, today I want to share three tips for better sleep...

---

Okay so continuing from last time, the fourth tip is all about your morning routine...

---

And finally, tip number five...
```

Each section becomes one video. Scripts can be completely independent topics or a continuing series.
