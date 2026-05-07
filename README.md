# Bulk Content Generator

Generate dozens of blog posts, social media captions, product descriptions, emails, and ads in one command — powered by Claude AI.

## Supported content types

| Type | Description |
|---|---|
| `blog_post` | 500–700 word structured article |
| `social_media` | LinkedIn + Twitter/X + Instagram posts |
| `product_description` | 150–250 word sales copy |
| `email` | Professional email with subject line |
| `ad_copy` | Headline + body + CTA |
| `seo_article` | 800–1000 word keyword-optimised article |

## Setup

### 1. Install Python 3.8+
Download from https://python.org if you don't have it.

### 2. Install dependencies
```bash
pip3 install -r requirements.txt
```

### 3. Add your API key
```bash
cp .env.example .env
```
Open `.env` and replace `your_api_key_here` with your key from https://console.anthropic.com/

### 4. Add your topics
Edit `topics.csv`. Each row needs three columns:
```
topic,type,tone
"Your topic here",blog_post,professional
```

### 5. Run
```bash
python3 run.py
```

Generated files appear in the `output/` folder, one `.txt` file per topic.

## Options

```bash
python3 run.py --topics my_topics.csv --output my_output --delay 2
```

| Flag | Default | Description |
|---|---|---|
| `--topics` | `topics.csv` | Path to your topics file |
| `--output` | `output` | Folder where results are saved |
| `--delay` | `1.0` | Seconds between API calls |

## Plain text input (alternative to CSV)

You can also pass a plain `.txt` file with one topic per line:
```bash
python3 run.py --topics my_topics.txt
```
Topics loaded this way default to `blog_post` type and `professional` tone.
