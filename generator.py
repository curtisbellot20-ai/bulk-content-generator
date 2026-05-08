import base64
import json
import os
import random
import re
import tempfile
import textwrap
import time
from typing import List, Optional

import numpy as np
import requests as _requests
from PIL import Image, ImageDraw, ImageFont

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
]

LIP_SYNC_MODEL = "kling-v1-6"   # best model for lip-sync via API
IMG2VIDEO_MODEL = "kling-v1-6"  # best model for image-to-video via API


def _load_font(size: int = 52) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_text_overlay(frame: np.ndarray, text: str, tw: int, th: int) -> np.ndarray:
    img = Image.fromarray(frame).convert("RGBA")
    font = _load_font(52)
    lines = textwrap.wrap(text, width=28)
    if not lines:
        return frame
    line_h = 68
    pad = 28
    box_h = len(lines) * line_h + pad * 2
    box_y = th - box_h - 80
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rounded_rectangle([40, box_y, tw - 40, box_y + box_h], radius=20, fill=(0, 0, 0, 170))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)
    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (tw - (bbox[2] - bbox[0])) // 2
        y = box_y + pad + idx * line_h
        for dx, dy in [(-3,-3),(3,-3),(-3,3),(3,3),(-3,0),(3,0),(0,-3),(0,3)]:
            draw.text((x+dx, y+dy), line, font=font, fill=(0,0,0,255))
        draw.text((x, y), line, font=font, fill=(255,255,255,255))
    return np.array(img.convert("RGB"))


def extract_visual_prompt(script: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", script.strip())
    return " ".join(sentences[:2])[:200]


# ---------------------------------------------------------------------------
# AI Script + Prompt Generator
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a short-form video content writer for AI influencer accounts.
You write punchy, scroll-stopping scripts and Kling AI motion prompts.

Script rules:
- Spoken words ONLY. No stage directions, no emojis, no hashtags.
- STRICT structure: Hook (3-5 words) + Body + CTA.
- STRICT length: 20-25 words MAXIMUM. Every word must earn its place.
  At 2.5 words/second, 25 words = exactly 10 seconds. Do NOT exceed this.
- Conversational and direct. Write how people actually talk.
- Example (22 words): "Nobody tells you this. The algorithm punishes you until you do one thing. Start today or stay invisible."

Prompt rules:
- Body movement + camera movement ONLY.
- Examples: "slow confident head turn to camera, arms crossed",
  "pointing finger forward, walking toward camera with attitude",
  "dramatic pause mid-sentence, slow push-in zoom".
- NEVER describe scene, background, clothing, lighting, or setting.
"""


def _extract_json(text: str) -> list:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        return json.loads(m.group(0))
    raise ValueError("Could not parse JSON from Claude response")


def generate_scripts_and_prompts(description: str, count: int, api_key: str) -> list:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    user_msg = (
        f"Content style: {description}\n"
        f"Number of videos: {count}\n\n"
        "Return ONLY a JSON array with no extra text:\n"
        '[{"script": "...", "prompt": "..."}, ...]'
    )
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = message.content[0].text
    items = _extract_json(raw)
    result = []
    for item in items[:count]:
        result.append({
            "script": str(item.get("script", "")).strip(),
            "prompt": str(item.get("prompt", "")).strip(),
        })
    return result


# ---------------------------------------------------------------------------
# Kling AI direct client (JWT auth)
# ---------------------------------------------------------------------------

class KlingClient:
    BASE_URL = "https://api.klingai.com"

    def __init__(self, access_key: str, secret_key: str):
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip()

    def _jwt(self) -> str:
        import jwt as pyjwt
        now = int(time.time())
        payload = {"iss": self.access_key, "exp": now + 1800, "nbf": now - 5}
        return pyjwt.encode(payload, self.secret_key, algorithm="HS256")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._jwt()}", "Content-Type": "application/json"}

    def submit_lip_sync(self, image_path: str, audio_path: str, mode: str = "std") -> str:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        with open(audio_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        payload = {
            "model_name": LIP_SYNC_MODEL,
            "input": {
                "input_type": "image",
                "image": img_b64,
                "audio_type": "file",
                "audio_file": audio_b64,
            },
            "mode": mode,
        }
        print(f"[lip-sync] Submitting to Kling direct API, model={LIP_SYNC_MODEL}, mode={mode}")
        resp = _requests.post(
            f"{self.BASE_URL}/v1/videos/lip-sync",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        print(f"[lip-sync] Response status: {resp.status_code}")
        try:
            print(f"[lip-sync] Response body: {resp.text[:500]}")
        except Exception:
            pass
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Kling lip-sync submit error: {data.get('message')} | full: {data}")
        return data["data"]["task_id"]

    def poll_lip_sync(self, task_id: str, timeout: int = 420) -> str:
        print(f"[lip-sync] Polling task {task_id}...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = _requests.get(
                f"{self.BASE_URL}/v1/videos/lip-sync/{task_id}",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Kling lip-sync poll error: {data.get('message')}")
            status = data["data"]["task_status"]
            print(f"[lip-sync] Task status: {status}")
            if status == "succeed":
                return data["data"]["task_result"]["videos"][0]["url"]
            if status in ("failed", "expired"):
                msg = data['data'].get('task_status_msg', '')
                raise RuntimeError(f"Kling lip-sync task {status}: {msg}")
            time.sleep(8)
        raise TimeoutError(f"Kling lip-sync task {task_id} timed out")

    def submit_image2video(self, image_path: str, prompt: str, duration: str = "5", mode: str = "std") -> str:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        resp = _requests.post(
            f"{self.BASE_URL}/v1/videos/image2video",
            headers=self._headers(),
            json={
                "model_name": IMG2VIDEO_MODEL,
                "image": img_b64,
                "prompt": prompt,
                "negative_prompt": "blurry, low quality, distorted, watermark",
                "cfg_scale": 0.5,
                "mode": mode,
                "aspect_ratio": "9:16",
                "duration": duration,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Kling submit error: {data.get('message')}")
        return data["data"]["task_id"]

    def poll_result(self, task_id: str, timeout: int = 420) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = _requests.get(
                f"{self.BASE_URL}/v1/videos/image2video/{task_id}",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Kling poll error: {data.get('message')}")
            status = data["data"]["task_status"]
            if status == "succeed":
                return data["data"]["task_result"]["videos"][0]["url"]
            if status in ("failed", "expired"):
                raise RuntimeError(f"Kling task {status}: {data['data'].get('task_status_msg', '')}")
            time.sleep(8)
        raise TimeoutError(f"Kling task {task_id} timed out after {timeout}s")


# ---------------------------------------------------------------------------
# PiAPI Kling client (X-API-KEY auth)
# ---------------------------------------------------------------------------

class PiAPIKlingClient:
    """Kling via PiAPI proxy — uses X-API-KEY header, no JWT required."""
    BASE_URL = "https://api.piapi.ai"

    def __init__(self, api_key: str):
        self.api_key = api_key.strip()

    def _headers(self) -> dict:
        return {"X-API-KEY": self.api_key, "Content-Type": "application/json"}

    def submit_lip_sync(self, image_path: str, audio_path: str, mode: str = "std") -> str:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        with open(audio_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        payload = {
            "model_name": LIP_SYNC_MODEL,
            "input": {
                "input_type": "image",
                "image": img_b64,
                "audio_type": "file",
                "audio_file": audio_b64,
            },
            "mode": mode,
        }
        print(f"[lip-sync] Submitting to PiAPI, model={LIP_SYNC_MODEL}, mode={mode}")
        resp = _requests.post(
            f"{self.BASE_URL}/api/kling/v1/videos/lip-sync",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        print(f"[lip-sync] Response status: {resp.status_code}")
        try:
            print(f"[lip-sync] Response body: {resp.text[:500]}")
        except Exception:
            pass
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"PiAPI lip-sync submit error: {data.get('message')} | full: {data}")
        return data["data"]["task_id"]

    def poll_lip_sync(self, task_id: str, timeout: int = 420) -> str:
        print(f"[lip-sync] Polling PiAPI task {task_id}...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = _requests.get(
                f"{self.BASE_URL}/api/kling/v1/videos/lip-sync/{task_id}",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 200:
                raise RuntimeError(f"PiAPI lip-sync poll error: {data.get('message')}")
            status = data["data"]["task_status"]
            print(f"[lip-sync] Task status: {status}")
            if status == "succeed":
                return data["data"]["task_result"]["videos"][0]["url"]
            if status in ("failed", "expired"):
                raise RuntimeError(f"PiAPI lip-sync task {status}: {data['data'].get('task_status_msg', '')}")
            time.sleep(8)
        raise TimeoutError(f"PiAPI lip-sync task {task_id} timed out")

    def submit_image2video(self, image_path: str, prompt: str, duration: str = "5", mode: str = "std") -> str:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        resp = _requests.post(
            f"{self.BASE_URL}/api/kling/v1/videos/image2video",
            headers=self._headers(),
            json={
                "model_name": IMG2VIDEO_MODEL,
                "image": img_b64,
                "prompt": prompt,
                "negative_prompt": "blurry, low quality, distorted, watermark",
                "cfg_scale": 0.5,
                "mode": mode,
                "aspect_ratio": "9:16",
                "duration": duration,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"PiAPI Kling submit error: {data.get('message')}")
        return data["data"]["task_id"]

    def poll_result(self, task_id: str, timeout: int = 420) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = _requests.get(
                f"{self.BASE_URL}/api/kling/v1/videos/image2video/{task_id}",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 200:
                raise RuntimeError(f"PiAPI Kling poll error: {data.get('message')}")
            status = data["data"]["task_status"]
            if status == "succeed":
                return data["data"]["task_result"]["videos"][0]["url"]
            if status in ("failed", "expired"):
                raise RuntimeError(f"PiAPI Kling task {status}: {data['data'].get('task_status_msg', '')}")
            time.sleep(8)
        raise TimeoutError(f"PiAPI Kling task {task_id} timed out after {timeout}s")


# ---------------------------------------------------------------------------
# Video generator
# ---------------------------------------------------------------------------

class VideoGenerator:
    TARGET_W = 1080
    TARGET_H = 1920

    def __init__(self, image_paths: List[str], image_mode: str = "rotation",
                 kling_client=None, clip_duration: str = "5",
                 kling_mode: str = "std", use_lip_sync: bool = True):
        self.image_paths = image_paths
        self.image_mode = image_mode
        self._index = 0
        self.kling = kling_client
        self.clip_duration = clip_duration
        self.kling_mode = kling_mode
        self.use_lip_sync = use_lip_sync

    def _next_image(self) -> str:
        if self.image_mode == "random":
            return random.choice(self.image_paths)
        path = self.image_paths[self._index % len(self.image_paths)]
        self._index += 1
        return path

    def _prepare_image(self, path: str) -> np.ndarray:
        img = Image.open(path).convert("RGB")
        tw, th = self.TARGET_W, self.TARGET_H
        ir, tr = img.width / img.height, tw / th
        margin = 1.12
        if ir > tr:
            new_h, new_w = int(th * margin), int(th * margin * ir)
        else:
            new_w, new_h = int(tw * margin), int(tw * margin / ir)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        x1, y1 = (new_w - tw) // 2, (new_h - th) // 2
        return np.array(img.crop((x1, y1, x1 + tw, y1 + th)))

    def _tts(self, text: str, path: str) -> bool:
        try:
            from gtts import gTTS
            gTTS(text=text, lang="en", slow=False).save(path)
            return True
        except Exception as e:
            print(f"[TTS] Failed: {e}")
            return False

    def _caption_clip(self, clip, script: str):
        tw, th = self.TARGET_W, self.TARGET_H
        words = script.split()
        chunks = [" ".join(words[i:i+6]) for i in range(0, len(words), 6)]
        chunk_dur = clip.duration / max(len(chunks), 1)
        def add_captions(get_frame, t):
            frame = get_frame(t)
            idx = min(int(t / chunk_dur), len(chunks) - 1)
            return _draw_text_overlay(frame, chunks[idx], tw, th) if chunks else frame
        return clip.fl(add_captions)

    def _create_lip_sync_video(self, script: str, img_path: str, output_path: str):
        from moviepy.editor import VideoFileClip
        print(f"[lip-sync] Generating TTS audio for: {script[:60]}...")
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "speech.mp3")
            if not self._tts(script, audio_path):
                raise RuntimeError("TTS failed — cannot generate lip-sync without audio")
            print(f"[lip-sync] TTS done. Submitting lip-sync job...")
            task_id = self.kling.submit_lip_sync(img_path, audio_path, mode=self.kling_mode)
            print(f"[lip-sync] Task ID: {task_id}. Polling for result...")
            video_url = self.kling.poll_lip_sync(task_id)
            print(f"[lip-sync] Done! Downloading video from {video_url[:80]}...")
            video_bytes = _requests.get(video_url, timeout=120).content
            raw_path = os.path.join(tmp, "lipsync_raw.mp4")
            with open(raw_path, "wb") as f:
                f.write(video_bytes)
            tw, th = self.TARGET_W, self.TARGET_H
            clip = VideoFileClip(raw_path).resize((tw, th))
            clip = self._caption_clip(clip, script)
            clip.write_videofile(output_path, fps=30, codec="libx264", audio_codec="aac",
                                 temp_audiofile=os.path.join(tmp, "tmp_audio.m4a"),
                                 remove_temp=True, logger=None, threads=4, preset="medium")
            print(f"[lip-sync] Video saved: {output_path}")

    def _create_kling_video(self, script: str, prompt: str, img_path: str, output_path: str):
        from moviepy.editor import AudioFileClip, VideoFileClip
        task_id = self.kling.submit_image2video(img_path, prompt, duration=self.clip_duration, mode=self.kling_mode)
        video_url = self.kling.poll_result(task_id)
        video_bytes = _requests.get(video_url, timeout=120).content
        tw, th = self.TARGET_W, self.TARGET_H
        with tempfile.TemporaryDirectory() as tmp:
            kling_path = os.path.join(tmp, "kling_raw.mp4")
            with open(kling_path, "wb") as f:
                f.write(video_bytes)
            audio_path = os.path.join(tmp, "narration.mp3")
            has_audio = self._tts(script, audio_path)
            clip = VideoFileClip(kling_path).resize((tw, th))
            if has_audio:
                audio = AudioFileClip(audio_path)
                if audio.duration > clip.duration:
                    clip = clip.loop(duration=audio.duration)
                clip = clip.set_audio(audio.set_duration(clip.duration))
            clip = self._caption_clip(clip, script)
            clip.write_videofile(output_path, fps=30, codec="libx264", audio_codec="aac",
                                 temp_audiofile=os.path.join(tmp, "tmp_audio.m4a"),
                                 remove_temp=True, logger=None, threads=4, preset="medium")

    def _create_static_video(self, script: str, img_path: str, output_path: str):
        from moviepy.editor import AudioFileClip
        from moviepy.video.VideoClip import VideoClip
        img_array = self._prepare_image(img_path)
        tw, th = self.TARGET_W, self.TARGET_H
        h, w = img_array.shape[:2]
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "narration.mp3")
            has_audio = self._tts(script, audio_path)
            if has_audio:
                audio = AudioFileClip(audio_path)
                duration = min(audio.duration + 0.4, 10.0)
            else:
                audio, duration = None, min(len(script.split()) / 2.5, 10.0)
            words = script.split()
            chunks = [" ".join(words[i:i+6]) for i in range(0, len(words), 6)]
            chunk_dur = duration / max(len(chunks), 1)
            def make_frame(t):
                scale = max(1.0, 1.08 - 0.08 * (t / duration))
                cw, ch = min(int(tw/scale), w), min(int(th/scale), h)
                x1, y1 = max(0,(w-cw)//2), max(0,(h-ch)//2)
                frame = np.array(Image.fromarray(img_array[y1:y1+ch, x1:x1+cw]).resize((tw, th), Image.LANCZOS))
                idx = min(int(t/chunk_dur), len(chunks)-1)
                return _draw_text_overlay(frame, chunks[idx], tw, th) if chunks else frame
            clip = VideoClip(make_frame, duration=duration).set_fps(30)
            if audio:
                clip = clip.set_audio(audio)
            clip.write_videofile(output_path, fps=30, codec="libx264", audio_codec="aac",
                                 temp_audiofile=os.path.join(tmp, "tmp_audio.m4a"),
                                 remove_temp=True, logger=None, threads=4, preset="medium")

    def create_video(self, script: str, prompt: str, output_path: str, video_index: int = 0):
        img_path = self._next_image()
        if self.kling:
            print(f"[VIDEO] Kling client available, use_lip_sync={self.use_lip_sync}")
            if self.use_lip_sync:
                try:
                    self._create_lip_sync_video(script, img_path, output_path)
                    return
                except Exception as exc:
                    print(f"[Kling lip-sync] video {video_index+1} FAILED: {exc}")
                    print(f"[Kling lip-sync] Falling back to img2video...")
            try:
                self._create_kling_video(script, prompt, img_path, output_path)
                return
            except Exception as exc:
                print(f"[Kling img2video] video {video_index+1} FAILED: {exc}")
                print(f"[Kling img2video] Falling back to static video...")
        else:
            print(f"[VIDEO] No Kling client — using static fallback")
        self._create_static_video(script, img_path, output_path)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_scripts(text: str, video_count: int, mode: str) -> List[str]:
    parts = re.split(r"\n\s*[-=]{3,}\s*\n|\n{3,}", text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return []
    if mode == "runon":
        words = " ".join(parts).split()
        per = max(1, len(words) // video_count)
        chunks = []
        for i in range(video_count):
            start = i * per
            end = start + per if i < video_count - 1 else len(words)
            if start < len(words):
                chunks.append(" ".join(words[start:end]))
        return chunks
    return [parts[i % len(parts)] for i in range(video_count)]


def parse_prompts(prompt_text: str, scripts: List[str]) -> List[str]:
    lines = prompt_text.strip().splitlines() if prompt_text.strip() else []
    result = []
    for i, script in enumerate(scripts):
        raw = lines[i].strip() if i < len(lines) else ""
        result.append(raw if raw else extract_visual_prompt(script))
    return result
