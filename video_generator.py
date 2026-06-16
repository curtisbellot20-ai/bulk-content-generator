import os
import requests

PIAPI_BASE = "https://api.piapi.ai/api/kling/v1"


def _headers():
    api_key = os.getenv("KLING_API_KEY")
    if not api_key:
        raise ValueError("KLING_API_KEY not set in .env")
    return {"X-API-Key": api_key, "Content-Type": "application/json"}


def _upload_image_get_url(image_path: str) -> str:
    """PiAPI requires a public image URL, so host the local file first."""
    with open(image_path, "rb") as f:
        resp = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": f},
            timeout=30,
        )
    resp.raise_for_status()
    url = resp.text.strip()
    if not url.startswith("http"):
        raise Exception(f"Image upload failed: {url}")
    return url


def start_video(image_path: str, script: str, duration: int = 5) -> str:
    image_url = _upload_image_get_url(image_path)

    payload = {
        "model_name": "kling-v1-5",
        "image": image_url,
        "prompt": script,
        "duration": str(duration),
        "mode": "std",
        "aspect_ratio": "9:16",
    }
    resp = requests.post(f"{PIAPI_BASE}/videos/image2video",
                         json=payload, headers=_headers(), timeout=30)
    resp.raise_for_status()
    result = resp.json()
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
