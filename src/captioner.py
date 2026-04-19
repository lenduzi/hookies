"""
Captioner — transcribes VO audio with word-level timestamps (OpenAI Whisper),
renders caption frames with Pillow, and burns them into the video with moviepy.
No libass or libfreetype required.

Styles:
  highlight — karaoke word-by-word: solid yellow box behind active word, dark text on box,
              inactive words in light grey. Dark pill background. (default)
  word      — one word at a time, large bold, black outline. No background. Maximum drama.
  classic   — three words at once, bold, black outline. Key words yellow, others white.
              No background. Documentary / podcast-clip style.
"""

import os
from pathlib import Path


# ── Style config — tweak freely ──────────────────────────────────────────────
WORDS_PER_CHUNK = 3            # words shown at once (highlight + classic)
FONT_SIZE      = 88            # px — body text at 1080×1920
WORD_FONT_SIZE = 130           # px — single-word style
FONT_PATH = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_INDEX_REGULAR = 1         # Helvetica Neue Bold
TEXT_COLOR    = (255, 255, 255)
KEY_COLOR     = (255, 210, 0)  # golden yellow
OUTLINE_COLOR = (0, 0, 0)
OUTLINE_WIDTH = 5
H_PADDING     = 60             # px from left/right frame edge
Y_FROM_BOTTOM = 520            # px up from bottom of frame
WORD_GAP      = 14             # px between words
UPPERCASE     = True

# Highlight style — pill background
PILL_BG     = (15, 15, 15)
PILL_ALPHA  = 220
PILL_RADIUS = 18
PILL_H_PAD  = 30
PILL_V_PAD  = 16
# Highlight box drawn behind active word
BOX_PAD_X   = 8
BOX_PAD_Y   = 5
BOX_RADIUS  = 7

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

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
        text  = " ".join(w["word"] for w in group)
        if UPPERCASE:
            text = text.upper()
        word_items = [
            {
                "word":  w["word"].upper() if UPPERCASE else w["word"],
                "start": round(w["start"], 3),
                "end":   round(w["end"],   3),
            }
            for w in group
        ]
        chunks.append({
            "text":  text,
            "start": round(group[0]["start"], 3),
            "end":   round(group[-1]["end"],  3),
            "words": word_items,
        })
    return chunks


def _is_key(word: str, key_words_set: set) -> bool:
    clean = word.strip(".,!?…—-'\u2019")
    return clean in key_words_set


def _draw_outlined_text(draw, pos, text, font, color, outline_color, outline_width):
    x, y = pos
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, font=font, fill=(*outline_color, 255))
    draw.text((x, y), text, font=font, fill=(*color, 255))


def burn_captions(video_path: str, words: list, output_path: str,
                  style: str = "highlight", key_words=None) -> str:
    """
    Burn captions into a video using moviepy + Pillow.

    Args:
        video_path:  input video file
        words:       word-level timestamps from transcribe_audio()
        output_path: where to write the captioned video
        style:       "highlight" | "word" | "classic"
        key_words:   strings to highlight in classic style (falls back to DEFAULT_KEY_WORDS)
    Returns:
        output_path
    """
    import numpy as np
    from moviepy import VideoFileClip, CompositeVideoClip, ImageClip
    from PIL import Image, ImageDraw, ImageFont

    if key_words:
        active_key_words = {w.upper().strip(".,!?…—-'\u2019") for w in key_words}
    else:
        active_key_words = DEFAULT_KEY_WORDS

    chunks = _group_into_chunks(words, WORDS_PER_CHUNK)

    video = VideoFileClip(video_path)
    W, H  = video.size
    max_text_width = W - H_PADDING * 2

    # ── Font loading ──────────────────────────────────────────────────────────
    font_regular = ImageFont.truetype(FONT_PATH, FONT_SIZE,      index=FONT_INDEX_REGULAR)
    font_word    = ImageFont.truetype(FONT_PATH, WORD_FONT_SIZE, index=FONT_INDEX_REGULAR)

    def measure(word, font):
        dummy = Image.new("RGBA", (1, 1))
        bb    = ImageDraw.Draw(dummy).textbbox((0, 0), word, font=font)
        return bb[2] - bb[0], bb[3] - bb[1]

    # ── Global scale: one scale factor for the entire video ───────────────────
    # Scan all chunks to find the widest, then scale fonts down uniformly.
    # This eliminates chunk-to-chunk font-size jumps.
    avail_pill    = max_text_width - PILL_H_PAD * 2
    avail_outline = max_text_width

    if chunks:
        max_chunk_w = max(
            sum(measure(w, font_regular)[0] for w in c["text"].split())
            + WORD_GAP * max(len(c["text"].split()) - 1, 0)
            for c in chunks
        )
    else:
        max_chunk_w = 0

    pill_scale    = min(1.0, avail_pill    / max_chunk_w) if max_chunk_w > 0 else 1.0
    outline_scale = min(1.0, avail_outline / max_chunk_w) if max_chunk_w > 0 else 1.0

    gp = (ImageFont.truetype(FONT_PATH, int(FONT_SIZE * pill_scale),    index=FONT_INDEX_REGULAR)
          if pill_scale    < 1.0 else font_regular)
    gc = (ImageFont.truetype(FONT_PATH, int(FONT_SIZE * outline_scale), index=FONT_INDEX_REGULAR)
          if outline_scale < 1.0 else font_regular)

    # ── Highlight style ───────────────────────────────────────────────────────
    def make_highlight_clips(chunk: dict) -> list:
        """One clip per word. Active word: solid yellow box + dark text.
        Inactive words: light grey. Dark pill background throughout."""
        word_items = chunk["words"]
        raw_words  = [w["word"] for w in word_items]

        sizes   = [measure(w, gp) for w in raw_words]
        total_w = sum(s[0] for s in sizes) + WORD_GAP * (len(raw_words) - 1)
        max_h   = max(s[1] for s in sizes)

        img_w = total_w + PILL_H_PAD * 2
        img_h = max_h   + PILL_V_PAD * 2
        x_pos = (W - img_w) // 2
        y_pos = H - Y_FROM_BOTTOM - img_h

        # Pre-compute x position of each word so the pill never shifts
        xs = []
        x  = PILL_H_PAD
        for ww, _ in sizes:
            xs.append(x)
            x += ww + WORD_GAP

        clips = []
        for active_idx, word_item in enumerate(word_items):
            img  = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            draw.rounded_rectangle(
                [0, 0, img_w - 1, img_h - 1],
                radius=PILL_RADIUS,
                fill=(*PILL_BG, PILL_ALPHA),
            )

            for wi, (word, (ww, wh)) in enumerate(zip(raw_words, sizes)):
                wx = xs[wi]
                wy = PILL_V_PAD + (max_h - wh) // 2
                if wi == active_idx:
                    draw.rounded_rectangle(
                        [wx - BOX_PAD_X, wy - BOX_PAD_Y,
                         wx + ww + BOX_PAD_X, wy + wh + BOX_PAD_Y],
                        radius=BOX_RADIUS,
                        fill=(*KEY_COLOR, 255),
                    )
                    draw.text((wx, wy), word, font=gp, fill=(15, 15, 15, 255))
                else:
                    draw.text((wx, wy), word, font=gp, fill=(210, 210, 210, 255))

            t_start = word_item["start"]
            t_end   = (word_items[active_idx + 1]["start"]
                       if active_idx + 1 < len(word_items) else chunk["end"])

            clips.append(
                ImageClip(np.array(img))
                .with_start(t_start)
                .with_end(t_end)
                .with_position((x_pos, y_pos))
            )
        return clips

    # ── Word style ────────────────────────────────────────────────────────────
    def make_word_clips() -> list:
        """One clip per word. Large bold text, thick outline, no background.
        Per-word scaling is intentional — long words are simply slightly smaller."""
        clips = []
        for w in words:
            text   = w["word"].upper() if UPPERCASE else w["word"]
            f      = font_word
            ww, wh = measure(text, f)
            if ww > max_text_width:
                f      = ImageFont.truetype(FONT_PATH,
                                            int(WORD_FONT_SIZE * max_text_width / ww),
                                            index=FONT_INDEX_REGULAR)
                ww, wh = measure(text, f)

            pad   = OUTLINE_WIDTH + 6
            img_w = ww + pad * 2
            img_h = wh + pad * 2

            img  = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
            _draw_outlined_text(ImageDraw.Draw(img), (pad, pad),
                                text, f, TEXT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH + 2)

            x_pos = (W - img_w) // 2
            y_pos = H - Y_FROM_BOTTOM - img_h

            clips.append(
                ImageClip(np.array(img))
                .with_start(round(w["start"], 3))
                .with_end(round(w["end"],   3))
                .with_position((x_pos, y_pos))
            )
        return clips

    # ── Classic style ─────────────────────────────────────────────────────────
    def make_classic_clip(chunk: dict):
        """Three words at once. Key words yellow, others white. Bold + black outline.
        All words the same size — color is the only differentiator."""
        raw_words   = chunk["text"].split()
        word_colors = [KEY_COLOR if _is_key(w, active_key_words) else TEXT_COLOR
                       for w in raw_words]

        sizes   = [measure(w, gc) for w in raw_words]
        total_w = sum(s[0] for s in sizes) + WORD_GAP * (len(raw_words) - 1)
        max_h   = max(s[1] for s in sizes)

        pad   = OUTLINE_WIDTH + 4
        img_w = total_w + pad * 2
        img_h = max_h   + pad * 2

        img  = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        x = pad
        for word, color, (ww, wh) in zip(raw_words, word_colors, sizes):
            y = pad + (max_h - wh) // 2
            _draw_outlined_text(draw, (x, y), word, gc, color, OUTLINE_COLOR, OUTLINE_WIDTH)
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
    if style == "word":
        caption_clips = make_word_clips()
    elif style == "classic":
        caption_clips = [make_classic_clip(c) for c in chunks]
    else:  # highlight (default)
        caption_clips = [c for chunk in chunks for c in make_highlight_clips(chunk)]

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
