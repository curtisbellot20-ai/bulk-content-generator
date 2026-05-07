import os
import csv
import time
import argparse
from pathlib import Path
from datetime import datetime
from generator import generate_content


def load_topics(filepath):
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Topics file not found: {filepath}")

    topics = []
    if path.suffix == ".csv":
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                topics.append(row)
    else:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    topics.append({"topic": line, "type": "blog_post", "tone": "professional"})
    return topics


def save_result(output_dir, index, topic, content):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = topic[:50].replace(" ", "_").replace("/", "-")
    filename = f"{index:03d}_{safe_name}.txt"
    filepath = output_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Topic: {topic}\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")
        f.write(content)
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Bulk Content Generator powered by Claude AI")
    parser.add_argument("--topics", default="topics.csv", help="Path to topics file (CSV or TXT)")
    parser.add_argument("--output", default="output", help="Output directory for generated content")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between API calls (default: 1.0)")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found in environment.")
        print("Please copy .env.example to .env and add your API key.")
        return

    print(f"Loading topics from: {args.topics}")
    try:
        topics = load_topics(args.topics)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return

    print(f"Found {len(topics)} topics. Generating content...\n")
    success, failed = 0, 0

    for i, row in enumerate(topics, start=1):
        topic = row.get("topic", "").strip()
        content_type = row.get("type", "blog_post").strip()
        tone = row.get("tone", "professional").strip()

        if not topic:
            continue

        print(f"[{i}/{len(topics)}] Generating: {topic[:60]}")
        try:
            content = generate_content(topic, content_type, tone)
            filepath = save_result(args.output, i, topic, content)
            print(f"  Saved → {filepath}")
            success += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

        if i < len(topics):
            time.sleep(args.delay)

    print(f"\nDone! {success} succeeded, {failed} failed.")
    print(f"Output saved to: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
