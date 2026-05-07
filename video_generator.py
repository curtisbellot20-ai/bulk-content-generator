import os
import base64
import requests

PIAPI_BASE = "https://api.piapi.ai/api/kling/v1"


def _headers():
    api_key = os.getenv("KLING_API_KEY")
    if not api_key:
        raise ValueError("KLING_API_KEY not set in .env")
    return {"x-api-key": api_key, "Content-Type": "application/json"}


def start_video(image_path: str, script: str, duration: int = 5) -> str:
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model_name": "kling-v1-5",
        "image": image_b64,
        "prompt": script,
        "duration": str(duration),
        "mode": "std",
        "aspect_ratio": "9:16",
    }
    resp = requests.post(f"{PIAPI_BASE}/videos/image2video",
                         json=payload, headers=_headers(), timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") not in (0, 200, None):
        raise Exception(result.get("message", "PiAPI error"))
    # PiAPI wraps in data or returns task_id directly
    data = result.get("data", result)
    task_id = data.get("task_id") or data.get("id")
    if not task_id:
        raise Exception(f"No task_id in response: {result}")
    return task_id


def check_video(task_id: str) -> dict:
    resp = requests.get(f"{PIAPI_BASE}/videos/image2video/{task_id}",
                        headers=_headers(), timeout=30)
    resp.raise_for_status()
    result = resp.json()
    data = result.get("data", result)
    status = data.get("task_status") or data.get("status", "")

    if status in ("succeed", "completed", "done", "success"):
        videos = (data.get("task_result") or {}).get("videos") or data.get("videos", [])
        url = videos[0].get("url") if videos else data.get("video_url") or data.get("url")
        return {"status": "done", "url": url}
    if status in ("failed", "error"):
        return {"status": "failed", "error": data.get("task_status_msg") or data.get("error", "Unknown")}
    return {"status": "processing"}
