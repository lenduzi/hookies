"""
Captioner — transcribes VO audio with word-level timestamps (OpenAI Whisper),
renders caption frames with Pillow, and burns them into the video with moviepy.
No libass or libfreetype required.
Style: bold uppercase body text, key words in golden italic at larger size.
"""

import os
from pathlib import Path


# ── Style config — tweak freely ──────────────────────────────────────────────
WORDS_PER_CHUNK = 3            # words shown at once
FONT_SIZE = 88                 # px for regular words (1080x1920)
KEY_FONT_SCALE = 1.18          # key words rendered this much larger
FONT_PATH = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_INDEX_REGULAR = 1         # Helvetica Neue Bold
FONT_INDEX_KEY = 3             # Helvetica Neue Bold Italic
TEXT_COLOR = (255, 255, 255)   # white
KEY_COLOR = (255, 210, 0)      # golden yellow for key words
OUTLINE_COLOR = (0, 0, 0)      # black stroke
OUTLINE_WIDTH = 5
H_PADDING = 60                 # min px gap from left/right frame edge
Y_FROM_BOTTOM = 260            # px up from bottom of frame
WORD_GAP = 14                  # px between words
UPPERCASE = True

# Words that get the key-word treatment
KEY_WORDS = {
    "TURMBAR", "HAMBURG", "BARTENDER", "BARTENDING", "COCKTAIL", "COCKTAILS",
    "SKILLS", "SKILL", "TEACHER", "TECHNIQUE", "HISTORY", "DATE-NIGHT",
    "STUNNING", "TIPSY", "INCREDIBLE", "UNDERRATED", "MISSING", "ZERO",
    "TEN", "10/10", "HIGHLY", "HONESTLY", "LITERALLY", "ACTUALLY",
    "NUMBER", "ONE", "TWO", "THREE", "SPILL", "SCROLLING", "STOP",
}
# ─────────────────────────────────────────────────────────────────────────────


def transcribe_audio(mp3_path: str) -> list[dict]:
    """
    Transcribe an MP3 using OpenAI Whisper API.
    Returns a list of word dicts: {"word": str, "start": float, "end": float}
    """
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)

    with open(mp3_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )

    return [
        {"word": w.word.strip(), "start": w.start, "end": w.end}
        for w in response.words
    ]


def _group_into_chunks(words: list[dict]) -> list[dict]:
    chunks = []
    for i in range(0, len(words), WORDS_PER_CHUNK):
        group = words[i:i + WORDS_PER_CHUNK]
        text = " ".join(w["word"] for w in group)
        if UPPERCASE:
            text = text.upper()
        chunks.append({
            "text": text,
            "start": round(group[0]["start"], 3),
            "end": round(group[-1]["end"], 3),
        })
    return chunks


def _is_key(word: str) -> bool:
    clean = word.strip(".,!?…—-'\u2019")
    return clean in KEY_WORDS


def _draw_outlined_text(draw, pos, text, font, color, outline_color, outline_width):
    """Draw text with a solid outline by rendering offset copies first."""
    x, y = pos
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=(*outline_color, 255))
    draw.text((x, y), text, font=font, fill=(*color, 255))


def burn_captions(video_path: str, words: list[dict], output_path: str) -> str:
    """
    Burn captions into a video using moviepy + Pillow text rendering.
    Returns the output path.
    """
    import numpy as np
    from moviepy import VideoFileClip, CompositeVideoClip, ImageClip
    from PIL import Image, ImageDraw, ImageFont

    chunks = _group_into_chunks(words)

    video = VideoFileClip(video_path)
    W, H = video.size
    max_text_width = W - H_PADDING * 2

    # Load fonts
    font_regular = ImageFont.truetype(FONT_PATH, FONT_SIZE, index=FONT_INDEX_REGULAR)
    key_size = int(FONT_SIZE * KEY_FONT_SCALE)
    font_key = ImageFont.truetype(FONT_PATH, key_size, index=FONT_INDEX_KEY)

    def measure_word(word, font):
        dummy = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(dummy)
        bb = draw.textbbox((0, 0), word, font=font)
        return bb[2] - bb[0], bb[3] - bb[1]

    def make_caption_clip(chunk: dict):
        raw_words = chunk["text"].split()
        word_fonts = [font_key if _is_key(w) else font_regular for w in raw_words]
        word_colors = [KEY_COLOR if _is_key(w) else TEXT_COLOR for w in raw_words]

        # Measure each word
        sizes = [measure_word(w, f) for w, f in zip(raw_words, word_fonts)]
        total_w = sum(s[0] for s in sizes) + WORD_GAP * (len(raw_words) - 1)
        max_h = max(s[1] for s in sizes)

        # Scale down font sizes if text is too wide to fit with padding
        scale = 1.0
        if total_w > max_text_width:
            scale = max_text_width / total_w
            font_regular_scaled = ImageFont.truetype(
                FONT_PATH, int(FONT_SIZE * scale), index=FONT_INDEX_REGULAR
            )
            font_key_scaled = ImageFont.truetype(
                FONT_PATH, int(key_size * scale), index=FONT_INDEX_KEY
            )
            word_fonts = [font_key_scaled if _is_key(w) else font_regular_scaled for w in raw_words]
            sizes = [measure_word(w, f) for w, f in zip(raw_words, word_fonts)]
            total_w = sum(s[0] for s in sizes) + WORD_GAP * (len(raw_words) - 1)
            max_h = max(s[1] for s in sizes)

        pad = OUTLINE_WIDTH + 4
        img_w = total_w + pad * 2
        img_h = max_h + pad * 2 + int(key_size * KEY_FONT_SCALE * 0.15)  # extra for descenders

        img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Render word by word, left to right
        x = pad
        for word, font, color, (ww, wh) in zip(raw_words, word_fonts, word_colors, sizes):
            # Vertically center each word relative to the tallest word
            y = pad + (max_h - wh) // 2
            _draw_outlined_text(draw, (x, y), word, font, color, OUTLINE_COLOR, OUTLINE_WIDTH)
            x += ww + WORD_GAP

        # Center horizontally, position from bottom
        x_pos = (W - img_w) // 2
        y_pos = H - Y_FROM_BOTTOM - img_h

        clip = (
            ImageClip(np.array(img))
            .with_start(chunk["start"])
            .with_end(chunk["end"])
            .with_position((x_pos, y_pos))
        )
        return clip

    caption_clips = [make_caption_clip(c) for c in chunks]
    final = CompositeVideoClip([video] + caption_clips)

    final.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )

    video.close()
    return output_path
