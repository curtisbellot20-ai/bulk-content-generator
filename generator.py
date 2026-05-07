import base64
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


def _load_font(size: int = 52) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_text_overlay(frame: np.ndarray, text: str, tw: int, th: int) -> np.ndarray:
    """Render wrapped caption at the bottom of frame with a dark rounded background."""
    img = Image.fromarray(frame).convert("RGBA")
    font = _load_font(52)
    draw_measure = ImageDraw.Draw(img)

    lines = textwrap.wrap(text, width=28)
    if not lines:
        return frame

    line_h = 68
    pad = 28
    box_h = len(lines) * line_h + pad * 2
    box_y = th - box_h - 80

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rounded_rectangle(
        [40, box_y, tw - 40, box_y + box_h],
        radius=20,
        fill=(0, 0, 0, 170),
    )
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (tw - text_w) // 2
        y = box_y + pad + idx * line_h
        for dx, dy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (-3, 0), (3, 0), (0, -3), (0, 3)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    return np.array(img.convert("RGB"))


def extract_visual_prompt(script: str) -> str:
    """Use the first two sentences of a script as a visual motion prompt."""
    sentences = re.split(r"(?<=[.!?])\s+", script.strip())
    text = " ".join(sentences[:2]).strip()
    return text[:200]


# ---------------------------------------------------------------------------
# Kling AI client
# ---------------------------------------------------------------------------

class KlingClient:
    """Thin wrapper around the Kling AI image-to-video REST API."""

    BASE_URL = "https://api.klingai.com"

    def __init__(self, access_key: str, secret_key: str):
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip()

    def _jwt(self) -> str:
        import jwt as pyjwt  # PyJWT
        now = int(time.time())
        payload = {"iss": self.access_key, "exp": now + 1800, "nbf": now - 5}
        return pyjwt.encode(payload, self.secret_key, algorithm="HS256")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._jwt()}",
            "Content-Type": "application/json",
        }

    def submit_image2video(
        self,
        image_path: str,
        prompt: str,
        duration: str = "5",
        mode: str = "std",
    ) -> str:
        """Submit an image-to-video task and return the task_id."""
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        resp = _requests.post(
            f"{self.BASE_URL}/v1/videos/image2video",
            headers=self._headers(),
            json={
                "model_name": "kling-v1",
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
        """Poll until task succeeds and return the video URL."""
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
                msg = data["data"].get("task_status_msg", "")
                raise RuntimeError(f"Kling task {status}: {msg}")
            time.sleep(8)

        raise TimeoutError(f"Kling task {task_id} timed out after {timeout}s")


# ---------------------------------------------------------------------------
# Video generator
# ---------------------------------------------------------------------------

class VideoGenerator:
    TARGET_W = 1080
    TARGET_H = 1920

    def __init__(
        self,
        image_paths: List[str],
        image_mode: str = "rotation",
        kling_client: Optional[KlingClient] = None,
        clip_duration: str = "5",
        kling_mode: str = "std",
    ):
        self.image_paths = image_paths
        self.image_mode = image_mode
        self._index = 0
        self.kling = kling_client
        self.clip_duration = clip_duration
        self.kling_mode = kling_mode

    def _next_image(self) -> str:
        if self.image_mode == "random":
            return random.choice(self.image_paths)
        path = self.image_paths[self._index % len(self.image_paths)]
        self._index += 1
        return path

    def _prepare_image(self, path: str) -> np.ndarray:
        img = Image.open(path).convert("RGB")
        tw, th = self.TARGET_W, self.TARGET_H
        ir = img.width / img.height
        tr = tw / th
        margin = 1.12
        if ir > tr:
            new_h = int(th * margin)
            new_w = int(new_h * ir)
        else:
            new_w = int(tw * margin)
            new_h = int(new_w / ir)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        x1 = (new_w - tw) // 2
        y1 = (new_h - th) // 2
        return np.array(img.crop((x1, y1, x1 + tw, y1 + th)))

    def _tts(self, text: str, path: str) -> bool:
        try:
            from gtts import gTTS
            gTTS(text=text, lang="en", slow=False).save(path)
            return True
        except Exception:
            return False

    def _caption_clip(self, clip, script: str):
        """Wrap a MoviePy clip with progressive PIL caption overlay."""
        tw, th = self.TARGET_W, self.TARGET_H
        words = script.split()
        chunks = [" ".join(words[i: i + 10]) for i in range(0, len(words), 10)]
        chunk_dur = clip.duration / max(len(chunks), 1)

        def add_captions(get_frame, t):
            frame = get_frame(t)
            idx = min(int(t / chunk_dur), len(chunks) - 1)
            return _draw_text_overlay(frame, chunks[idx], tw, th) if chunks else frame

        return clip.fl(add_captions)

    # -- Kling path ----------------------------------------------------------

    def _create_kling_video(self, script: str, prompt: str, img_path: str, output_path: str):
        from moviepy.editor import AudioFileClip, VideoFileClip

        task_id = self.kling.submit_image2video(
            img_path, prompt, duration=self.clip_duration, mode=self.kling_mode
        )
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

            # If TTS is longer than the Kling clip, loop the video
            if has_audio:
                audio = AudioFileClip(audio_path)
                if audio.duration > clip.duration:
                    clip = clip.loop(duration=audio.duration)
                clip = clip.set_audio(audio.set_duration(clip.duration))

            clip = self._caption_clip(clip, script)

            clip.write_videofile(
                output_path,
                fps=30,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile=os.path.join(tmp, "tmp_audio.m4a"),
                remove_temp=True,
                logger=None,
                threads=4,
                preset="medium",
            )

    # -- Static (fallback) path ----------------------------------------------

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
                duration = audio.duration + 0.4
            else:
                audio = None
                duration = max(5.0, len(script.split()) / 2.5)

            words = script.split()
            chunks = [" ".join(words[i: i + 10]) for i in range(0, len(words), 10)]
            chunk_dur = duration / max(len(chunks), 1)

            def make_frame(t):
                scale = max(1.0, 1.08 - 0.08 * (t / duration))
                cw = min(int(tw / scale), w)
                ch = min(int(th / scale), h)
                x1 = max(0, (w - cw) // 2)
                y1 = max(0, (h - ch) // 2)
                frame = np.array(
                    Image.fromarray(img_array[y1: y1 + ch, x1: x1 + cw]).resize((tw, th), Image.LANCZOS)
                )
                idx = min(int(t / chunk_dur), len(chunks) - 1)
                return _draw_text_overlay(frame, chunks[idx], tw, th) if chunks else frame

            clip = VideoClip(make_frame, duration=duration).set_fps(30)
            if audio:
                clip = clip.set_audio(audio)

            clip.write_videofile(
                output_path,
                fps=30,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile=os.path.join(tmp, "tmp_audio.m4a"),
                remove_temp=True,
                logger=None,
                threads=4,
                preset="medium",
            )

    # -- Public entry point --------------------------------------------------

    def create_video(self, script: str, prompt: str, output_path: str, video_index: int = 0):
        img_path = self._next_image()
        if self.kling:
            try:
                self._create_kling_video(script, prompt, img_path, output_path)
                return
            except Exception as exc:
                print(f"[Kling] video {video_index + 1} failed ({exc}) — using static fallback")
        self._create_static_video(script, img_path, output_path)


# ---------------------------------------------------------------------------
# Script / prompt parsing helpers
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
    """
    Return one visual prompt per script.
    Blank lines in prompt_text fall back to auto-extraction from the script.
    """
    lines = prompt_text.strip().splitlines() if prompt_text.strip() else []
    result = []
    for i, script in enumerate(scripts):
        raw = lines[i].strip() if i < len(lines) else ""
        result.append(raw if raw else extract_visual_prompt(script))
    return result
