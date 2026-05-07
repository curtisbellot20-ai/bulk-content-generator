# Bulk Content Generator + AI Video

Generate blog posts, social media captions, product descriptions, and more — then turn them into talking head videos featuring you or your AI influencer. Powered by Claude AI and Kling AI.

## What it does

| Feature | Description |
|---|---|
| Bulk content | Generate dozens of pieces of written content from a topic list |
| AI Video | Upload your photo → Claude writes a script → Kling AI animates you speaking it |
| Download | Export all content as ZIP, or download your video |

## Setup

### 1. Install Python 3.8+
Download from https://python.org if needed.

### 2. Install dependencies
```bash
pip3 install -r requirements.txt
```

### 3. Add your API keys
```bash
cp .env.example .env
```
Open `.env` and fill in:
- `ANTHROPIC_API_KEY` — from https://console.anthropic.com/
- `KLING_API_KEY` — from https://klingai.com/dev

### 4. Run
```bash
python3 web_app.py
```

Open your browser to **http://localhost:5000**

## Content tab
- Type topics (one per line)
- Pick content type and tone
- Click **Generate Content**
- Copy individual results or download all as ZIP

## AI Video tab
1. Upload a clear photo of yourself or your AI influencer
2. Enter what the video is about and click **Write Script** (Claude generates a 30-second script)
3. Edit the script if needed
4. Pick duration (5 or 10 seconds)
5. Click **Generate Video** — Kling AI will render it in 2–4 minutes
6. Preview and download the finished video
