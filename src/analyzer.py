"""
Analyzer — extracts a keyframe from each clip and sends it to Claude Vision
for content analysis. Returns structured metadata per clip.
"""

import base64
import json
import os
import subprocess
from pathlib import Path

import anthropic
from tqdm import tqdm

from src.config import ANTHROPIC_API_KEY, TEMP_DIR


def _extract_frame(video_path: str, timestamp: float = 2.0) -> str:
    """
    Extract a single frame from a video at `timestamp` seconds.
    Returns path to the extracted JPEG.
    Falls back to frame 0 if the video is shorter than the timestamp.
    """
    stem = Path(video_path).stem
    frame_path = os.path.join(TEMP_DIR, f"{stem}_frame.jpg")

    if os.path.exists(frame_path):
        return frame_path

    # Get video duration first
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    try:
        duration = float(probe.stdout.strip())
        ts = min(timestamp, duration * 0.3)  # use 30% in if video is short
    except ValueError:
        ts = 0

    subprocess.run(
        ["ffmpeg", "-ss", str(ts), "-i", video_path,
         "-frames:v", "1", "-q:v", "2", frame_path, "-y"],
        capture_output=True, check=True
    )
    return frame_path


def _get_video_duration(video_path: str) -> float:
    """Return video duration in seconds using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _load_prompt() -> str:
    prompt_path = Path(__file__).parent.parent / "prompts" / "analyze_clip.md"
    return prompt_path.read_text()


def analyze_clips(clip_paths: list[str]) -> list[dict]:
    """
    Analyze each clip using Claude Vision.
    Returns a list of analysis dicts, one per clip.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _load_prompt()
    results = []

    print(f"\n🔍 Analyzing {len(clip_paths)} clips with Claude Vision...")

    for clip_path in tqdm(clip_paths, desc="Analyzing clips"):
        filename = Path(clip_path).name
        duration = _get_video_duration(clip_path)

        try:
            frame_path = _extract_frame(clip_path)

            with open(frame_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")

            response = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_data,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            raw = response.content[0].text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            analysis = json.loads(raw)

        except Exception as e:
            print(f"  ⚠ Failed to analyze {filename}: {e}")
            analysis = {
                "description": "Analysis failed",
                "content_type": "other",
                "energy": "medium",
                "lighting": "mixed",
                "hook_score": 3,
                "hook_reason": "Could not analyze",
                "tags": [],
            }

        results.append({
            "filename": filename,
            "local_path": clip_path,
            "duration_seconds": round(duration, 2),
            **analysis,
        })

    print(f"✅ Analysis complete for {len(results)} clips")
    return results
