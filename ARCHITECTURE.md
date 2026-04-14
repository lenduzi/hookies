# Architecture

## Pipeline Overview

```
Google Drive / Local Folder
         │
         ▼
  ┌─────────────┐
  │ drive_client │  Downloads all MOV/MP4 clips to a local temp dir
  └─────────────┘
         │
         ▼
  ┌─────────────┐
  │   analyzer  │  FFmpeg extracts 1 keyframe per clip
  └─────────────┘  Claude Vision describes: content, energy, hook potential
         │
         ▼
  ┌─────────────┐
  │   planner   │  Claude receives all clip descriptions
  └─────────────┘  Returns 3–4 edit plans as structured JSON
         │          Each plan: hook clip, ordered clip list, vibe, target duration
         ▼
  ┌─────────────┐
  │  assembler  │  FFmpeg concatenates clips per plan
  └─────────────┘  Applies reframe (9:16 / 1:1 / 16:9), fade transitions
         │
         ▼
   output/*.mp4
```

## Key Design Decisions

### Why frame extraction vs full video analysis?
Sending full video files to Claude is expensive and slow. Extracting a single representative keyframe per clip gives Claude enough visual context to understand content type, energy, and composition — at a fraction of the cost.

### Why structured JSON from Claude?
The planner prompt instructs Claude to return a strict JSON schema. This makes the assembler deterministic and easy to debug. If Claude returns malformed JSON, the pipeline retries with a stricter prompt.

### Why FFmpeg for assembly?
FFmpeg is the most reliable, format-agnostic tool for video concatenation and reframing. It handles MOV, MP4, variable frame rates, and codec differences transparently — exactly what you get from raw iPhone UGC footage.

## Claude API Usage

| Step | Model | Input | Approx cost per run |
|---|---|---|---|
| Clip analysis | claude-opus-4-5 | 1 frame image per clip | ~$0.02 per clip |
| Edit planning | claude-opus-4-5 | All clip descriptions (text) | ~$0.05 total |

For 25 clips: estimated **$0.55–$0.75 per full run**.

## Data Flow

```python
# analyzer output (per clip)
{
  "filename": "IMG_6682.MOV",
  "local_path": "/tmp/ugc_clips/IMG_6682.MOV",
  "duration_seconds": 165,
  "description": "Wide shot of a dimly lit cocktail bar interior. Warm amber lighting, bottles visible behind bar. Low energy, cinematic feel. Strong opener candidate.",
  "tags": ["wide", "bar", "atmospheric", "low-energy", "interior"],
  "hook_score": 8  # 1-10, Claude's rating of viral hook potential
}

# planner output
{
  "cuts": [
    {
      "id": "cut_1",
      "name": "moody_atmospheric",
      "hook": "Slow reveal of bar interior builds anticipation",
      "vibe": "Cinematic, moody, aspirational",
      "target_duration": 30,
      "clips": ["IMG_6682.MOV", "IMG_6699.MOV", "IMG_6642.MOV"],
      "trim": {
        "IMG_6682.MOV": {"start": 0, "end": 8},
        "IMG_6699.MOV": {"start": 2, "end": 7},
        "IMG_6642.MOV": {"start": 0, "end": 5}
      },
      "transition": "fade"
    }
  ]
}
```

## Extending the Tool

- **Add captions**: pipe assembler output through Whisper + ffmpeg subtitles filter
- **Add music**: assembler can mix in a background audio track with ffmpeg
- **Add platform presets**: define output profiles (TikTok, Reels, Shorts) in config
- **Web UI**: wrap main.py in a FastAPI app + simple HTML frontend
