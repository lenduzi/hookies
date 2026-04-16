"""
Captioner — transcribes VO audio with word-level timestamps (OpenAI Whisper),
renders caption frames with Pillow, and burns them into the video with moviepy.
No libass or libfreetype required.

Styles:
  highlight — karaoke word-by-word: active word bold+yellow, others thin+grey, dark pill bg
  keywords  — show full chunk; key words yellow+bold italic+larger, others thin white, dark pill bg
  classic   — bold uppercase, key words golden+italic+larger, black outline (no background)
"""

import os
from pathlib import Path


# ── Style config — tweak freely ──────────────────────────────────────────────
WORDS_PER_CHUNK = 3            # words shown at once
FONT_SIZE = 88                 # px for regular words (1080x1920)
KEY_FONT_SCALE = 1.18          # key words rendered this much larger
FONT_PATH = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_INDEX_THIN    = 0         # Helvetica Neue Regular   — inactive words
FONT_INDEX_REGULAR = 1         # Helvetica Neue Bold      — active / body
FONT_INDEX_KEY     = 3         # Helvetica Neue Bold Italic — key words
TEXT_COLOR = (255, 255, 255)   # white
KEY_COLOR = (255, 210, 0)      # golden yellow for key words
OUTLINE_COLOR = (0, 0, 0)      # black stroke (classic only)
OUTLINE_WIDTH = 5
H_PADDING = 60                 # min px gap from left/right frame edge
Y_FROM_BOTTOM = 520            # px up from bottom of frame
WORD_GAP = 14                  # px between words
UPPERCASE = True

# Shared pill/highlight background config
PILL_BG        = (15, 15, 15)
PILL_BG_ALPHA  = 220
PILL_RADIUS    = 18
PILL_H_PAD     = 30
PILL_V_PAD     = 16

# Default key words — used when no project-specific list is provided
DEFAULT_KEY_WORDS = {
    "TURMBAR", "HAMBURG", "BARTENDER", "BARTENDING", "COCKTAIL", "COCKTAILS",
    "SKILLS", "SKILL", "TEACHER", "TECHNIQUE", "HISTORY", "DATE-NIGHT",
    "STUNNING", "TIPSY", "INCREDIBLE", "UNDERRATED", "MISSING", "ZERO",
    "TEN", "10/10", "HIGHLY", "HONESTLY", "LITERALLY", "ACTUALLY",
    "NUMBER", "ONE", "TWO", "THREE", "SPILL", "SCROLLING", "STOP",
}
# ─────────────────────────────────────────────────────────────────────────────


def transcribe_audio(mp3_path: str) -> list:
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


def _group_into_chunks(words: list, words_per_chunk: int = WORDS_PER_CHUNK) -> list:
    chunks = []
    for i in range(0, len(words), words_per_chunk):
        group = words[i:i + words_per_chunk]
        text = " ".join(w["word"] for w in group)
        if UPPERCASE:
            text = text.upper()
        # Preserve per-word timestamps for karaoke-style highlight rendering
        word_items = [
            {
                "word": w["word"].upper() if UPPERCASE else w["word"],
                "start": round(w["start"], 3),
                "end": round(w["end"], 3),
            }
            for w in group
        ]
        chunks.append({
            "text": text,
            "start": round(group[0]["start"], 3),
            "end": round(group[-1]["end"], 3),
            "words": word_items,
        })
    return chunks


def _is_key(word: str, key_words_set: set) -> bool:
    clean = word.strip(".,!?…—-'\u2019")
    return clean in key_words_set


def _draw_outlined_text(draw, pos, text, font, color, outline_color, outline_width):
    """Draw text with a solid outline by rendering offset copies first."""
    x, y = pos
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=(*outline_color, 255))
    draw.text((x, y), text, font=font, fill=(*color, 255))


def burn_captions(video_path: str, words: list, output_path: str,
                  style: str = "classic", key_words=None) -> str:
    """
    Burn captions into a video using moviepy + Pillow text rendering.

    Args:
        video_path:  input video file
        words:       word-level timestamps from transcribe_audio()
        output_path: where to write the captioned video
        style:       "highlight" | "keywords" | "classic"
        key_words:   optional list of strings to highlight in keywords/classic styles;
                     if None, falls back to DEFAULT_KEY_WORDS
    Returns:
        output_path
    """
    import numpy as np
    from moviepy import VideoFileClip, CompositeVideoClip, ImageClip
    from PIL import Image, ImageDraw, ImageFont

    # Build the active key-word set
    if key_words:
        active_key_words = {w.upper().strip(".,!?…—-'\u2019") for w in key_words}
    else:
        active_key_words = DEFAULT_KEY_WORDS

    chunks = _group_into_chunks(words, WORDS_PER_CHUNK)

    video = VideoFileClip(video_path)
    W, H = video.size
    max_text_width = W - H_PADDING * 2

    # ── Font loading ──────────────────────────────────────────────────────────
    font_regular = ImageFont.truetype(FONT_PATH, FONT_SIZE, index=FONT_INDEX_REGULAR)
    key_size     = int(FONT_SIZE * KEY_FONT_SCALE)
    font_key     = ImageFont.truetype(FONT_PATH, key_size,  index=FONT_INDEX_KEY)

    def measure_word(word, font):
        dummy = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(dummy)
        bb = draw.textbbox((0, 0), word, font=font)
        return bb[2] - bb[0], bb[3] - bb[1]

    # ── Global scale: scan all chunks, compute ONE scale factor ───────────────
    # This guarantees font size is identical across every chunk in the video.
    available_pill    = max_text_width - PILL_H_PAD * 2
    available_classic = max_text_width

    max_pill_w    = 0
    max_classic_w = 0
    for _c in chunks:
        _ws = _c["text"].split()
        _tw_pill = (
            sum(measure_word(w, font_regular)[0] for w in _ws)
            + WORD_GAP * (len(_ws) - 1)
        )
        _tw_classic = (
            sum(measure_word(w, font_key if _is_key(w, active_key_words) else font_regular)[0] for w in _ws)
            + WORD_GAP * (len(_ws) - 1)
        )
        max_pill_w    = max(max_pill_w,    _tw_pill)
        max_classic_w = max(max_classic_w, _tw_classic)

    pill_scale    = min(1.0, available_pill    / max_pill_w)    if max_pill_w    > 0 else 1.0
    classic_scale = min(1.0, available_classic / max_classic_w) if max_classic_w > 0 else 1.0

    # Globally-scaled fonts — used by every render function (no per-chunk rescaling)
    if pill_scale < 1.0:
        gp_regular = ImageFont.truetype(FONT_PATH, int(FONT_SIZE * pill_scale), index=FONT_INDEX_REGULAR)
        gp_key     = ImageFont.truetype(FONT_PATH, int(key_size  * pill_scale), index=FONT_INDEX_KEY)
    else:
        gp_regular, gp_key = font_regular, font_key

    if classic_scale < 1.0:
        gc_regular = ImageFont.truetype(FONT_PATH, int(FONT_SIZE * classic_scale), index=FONT_INDEX_REGULAR)
        gc_key     = ImageFont.truetype(FONT_PATH, int(key_size  * classic_scale), index=FONT_INDEX_KEY)
    else:
        gc_regular, gc_key = font_regular, font_key

    # ── Classic style ─────────────────────────────────────────────────────────
    def make_classic_clip(chunk: dict):
        raw_words   = chunk["text"].split()
        word_fonts  = [gc_key if _is_key(w, active_key_words) else gc_regular for w in raw_words]
        word_colors = [KEY_COLOR if _is_key(w, active_key_words) else TEXT_COLOR for w in raw_words]

        sizes   = [measure_word(w, f) for w, f in zip(raw_words, word_fonts)]
        total_w = sum(s[0] for s in sizes) + WORD_GAP * (len(raw_words) - 1)
        max_h   = max(s[1] for s in sizes)

        pad   = OUTLINE_WIDTH + 4
        img_w = total_w + pad * 2
        img_h = max_h + pad * 2 + int(gc_key.size * 0.15)

        img  = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        x = pad
        for word, font, color, (ww, wh) in zip(raw_words, word_fonts, word_colors, sizes):
            y = pad + (max_h - wh) // 2
            _draw_outlined_text(draw, (x, y), word, font, color, OUTLINE_COLOR, OUTLINE_WIDTH)
            x += ww + WORD_GAP

        x_pos = (W - img_w) // 2
        y_pos = H - Y_FROM_BOTTOM - img_h

        return (
            ImageClip(np.array(img))
            .with_start(chunk["start"])
            .with_end(chunk["end"])
            .with_position((x_pos, y_pos))
        )

    # ── Highlight (karaoke) style ─────────────────────────────────────────────
    def make_highlight_clips(chunk: dict) -> list:
        """One ImageClip per word. Active word: yellow. Inactive: dim white.
        Same font (gp_regular) for all — color-only differentiation prevents
        perceived size jumps between active/inactive words."""
        word_items = chunk["words"]
        raw_words  = [w["word"] for w in word_items]

        sizes   = [measure_word(w, gp_regular) for w in raw_words]
        total_w = sum(s[0] for s in sizes) + WORD_GAP * (len(raw_words) - 1)
        max_h   = max(s[1] for s in sizes)

        img_w = total_w + PILL_H_PAD * 2
        img_h = max_h   + PILL_V_PAD * 2
        x_pos = (W - img_w) // 2
        y_pos = H - Y_FROM_BOTTOM - img_h

        clips = []
        for active_idx, word_item in enumerate(word_items):
            img  = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle(
                [0, 0, img_w - 1, img_h - 1],
                radius=PILL_RADIUS,
                fill=(*PILL_BG, PILL_BG_ALPHA),
            )
            x = PILL_H_PAD
            for wi, (word, (ww, wh)) in enumerate(zip(raw_words, sizes)):
                y     = PILL_V_PAD + (max_h - wh) // 2
                color = KEY_COLOR if wi == active_idx else (150, 150, 150)
                draw.text((x, y), word, font=gp_regular, fill=(*color, 255))
                x += ww + WORD_GAP

            t_start = word_item["start"]
            t_end   = word_items[active_idx + 1]["start"] if active_idx + 1 < len(word_items) else chunk["end"]

            clips.append(
                ImageClip(np.array(img))
                .with_start(t_start)
                .with_end(t_end)
                .with_position((x_pos, y_pos))
            )
        return clips

    # ── Keywords style ────────────────────────────────────────────────────────
    def make_keywords_clip(chunk: dict):
        """Full chunk at once. Key words: gp_key (Bold Italic) + yellow.
        Other words: gp_regular + dim white. Dark pill background."""
        raw_words   = chunk["text"].split()
        word_fonts  = [gp_key     if _is_key(w, active_key_words) else gp_regular for w in raw_words]
        word_colors = [KEY_COLOR  if _is_key(w, active_key_words) else (200, 200, 200) for w in raw_words]

        sizes   = [measure_word(w, f) for w, f in zip(raw_words, word_fonts)]
        total_w = sum(s[0] for s in sizes) + WORD_GAP * (len(raw_words) - 1)
        max_h   = max(s[1] for s in sizes)

        img_w = total_w + PILL_H_PAD * 2
        img_h = max_h   + PILL_V_PAD * 2
        img   = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        draw  = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [0, 0, img_w - 1, img_h - 1],
            radius=PILL_RADIUS,
            fill=(*PILL_BG, PILL_BG_ALPHA),
        )
        x = PILL_H_PAD
        for word, font, color, (ww, wh) in zip(raw_words, word_fonts, word_colors, sizes):
            y = PILL_V_PAD + (max_h - wh) // 2
            draw.text((x, y), word, font=font, fill=(*color, 255))
            x += ww + WORD_GAP

        x_pos = (W - img_w) // 2
        y_pos = H - Y_FROM_BOTTOM - img_h

        return (
            ImageClip(np.array(img))
            .with_start(chunk["start"])
            .with_end(chunk["end"])
            .with_position((x_pos, y_pos))
        )

    # ── Dispatch ──────────────────────────────────────────────────────────────
    if style == "highlight":
        caption_clips = [c for chunk in chunks for c in make_highlight_clips(chunk)]
    elif style == "keywords":
        caption_clips = [make_keywords_clip(c) for c in chunks]
    else:  # classic
        caption_clips = [make_classic_clip(c) for c in chunks]
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
