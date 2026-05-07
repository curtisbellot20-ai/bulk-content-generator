import os
import time
import base64
import requests

KLING_BASE = "https://api.klingai.com"


def _headers():
    api_key = os.getenv("KLING_API_KEY")
    if not api_key:
        raise ValueError("KLING_API_KEY not set in .env file")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def start_video(image_path: str, script: str, duration: int = 5) -> str:
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model_name": "kling-v1-5",
        "image": image_b64,
        "prompt": f"Person speaking naturally and confidently to camera: {script[:500]}",
        "duration": str(duration),
        "mode": "std",
        "cfg_scale": 0.5,
    }

    resp = requests.post(
        f"{KLING_BASE}/v1/videos/image2video",
        json=payload,
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") != 0:
        raise Exception(result.get("message", "Kling API error"))
    return result["data"]["task_id"]


def check_video(task_id: str) -> dict:
    resp = requests.get(
        f"{KLING_BASE}/v1/videos/image2video/{task_id}",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    status = data["task_status"]

    if status == "succeed":
        url = data["task_result"]["videos"][0]["url"]
        return {"status": "done", "url": url}
    elif status == "failed":
        return {"status": "failed", "error": data.get("task_status_msg", "Unknown error")}
    return {"status": "processing"}
