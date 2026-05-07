import os
import random
import re
import tempfile
import textwrap
from typing import List

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Ordered list of bold font paths to try across Linux / macOS / Windows
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Arial Bold.ttf",
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
    """Render wrapped caption text at the bottom of frame with a dark pill background."""
    img = Image.fromarray(frame).convert("RGBA")
    font = _load_font(52)

    lines = textwrap.wrap(text, width=28)
    if not lines:
        return frame

    line_h = 68
    pad = 28
    box_h = len(lines) * line_h + pad * 2
    box_y = th - box_h - 80

    # Semi-transparent dark background
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
        # Outline
        for dx, dy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (-3, 0), (3, 0), (0, -3), (0, 3)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    return np.array(img.convert("RGB"))


class VideoGenerator:
    TARGET_W = 1080
    TARGET_H = 1920

    def __init__(self, image_paths: List[str], image_mode: str = "rotation"):
        self.image_paths = image_paths
        self.image_mode = image_mode
        self._index = 0

    def _next_image(self) -> str:
        if self.image_mode == "random":
            return random.choice(self.image_paths)
        path = self.image_paths[self._index % len(self.image_paths)]
        self._index += 1
        return path

    def _prepare_image(self, path: str) -> np.ndarray:
        """Resize + center-crop image to fill TARGET with 12% margin for Ken Burns."""
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
        img = img.crop((x1, y1, x1 + tw, y1 + th))
        return np.array(img)

    def _tts(self, text: str, path: str) -> bool:
        try:
            from gtts import gTTS
            gTTS(text=text, lang="en", slow=False).save(path)
            return True
        except Exception:
            return False

    def create_video(self, script: str, output_path: str, video_index: int = 0):
        from moviepy.editor import AudioFileClip
        from moviepy.video.VideoClip import VideoClip

        img_array = self._prepare_image(self._next_image())
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
                # Estimate reading pace: ~2.5 words/sec
                duration = max(5.0, len(script.split()) / 2.5)

            # Split script into timed caption chunks (10 words each)
            words = script.split()
            chunk_size = 10
            chunks = [" ".join(words[i: i + chunk_size]) for i in range(0, len(words), chunk_size)]
            chunk_dur = duration / max(len(chunks), 1)

            def make_frame(t):
                # Ken Burns: slow zoom-out from 1.08× to 1.0× over duration
                scale = max(1.0, 1.08 - 0.08 * (t / duration))
                cw = min(int(tw / scale), w)
                ch = min(int(th / scale), h)
                x1 = max(0, (w - cw) // 2)
                y1 = max(0, (h - ch) // 2)
                cropped = img_array[y1: y1 + ch, x1: x1 + cw]
                frame = np.array(Image.fromarray(cropped).resize((tw, th), Image.LANCZOS))

                # Progressive caption
                idx = min(int(t / chunk_dur), len(chunks) - 1)
                if chunks:
                    frame = _draw_text_overlay(frame, chunks[idx], tw, th)
                return frame

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


def parse_scripts(text: str, video_count: int, mode: str) -> List[str]:
    """Split raw text into per-video script strings."""
    # Delimiters: lines of --- or === (3+ chars), or 3+ consecutive blank lines
    parts = re.split(r"\n\s*[-=]{3,}\s*\n|\n{3,}", text.strip())
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        return []

    if mode == "runon":
        # Merge all text, split evenly across video_count
        words = " ".join(parts).split()
        per = max(1, len(words) // video_count)
        chunks = []
        for i in range(video_count):
            start = i * per
            end = start + per if i < video_count - 1 else len(words)
            if start < len(words):
                chunks.append(" ".join(words[start:end]))
        return chunks

    # separate mode: cycle through scripts if fewer than requested
    return [parts[i % len(parts)] for i in range(video_count)]
