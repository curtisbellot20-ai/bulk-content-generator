import json
import anthropic


def generate_scripts_and_prompts(theme: str, count: int) -> list:
    """Returns list of {script, motion} dicts."""
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": (
            f'Generate {count} short-form social media video ideas for an AI influencer. Theme: "{theme}".\n\n'
            'For EACH video return exactly two things:\n'
            '- "script": The exact words spoken to camera. Natural, punchy, 20-30 words max. No stage directions or labels.\n'
            '- "motion": ONLY physical movement and facial expression of the person. 8-12 words. '
            'Body language, gestures, head movement, expression only. '
            'No backgrounds, settings, lighting, cameras, or props.\n\n'
            'Return a raw JSON array only. No markdown, no explanation:\n'
            '[{"script": "...", "motion": "..."}, ...]'
        )}],
    )
    text = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
