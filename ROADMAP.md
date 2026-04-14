# Hookies — Roadmap

## Current state (v0.1.0 + post-MVP work)

### What works end-to-end
- Multi-project support — create a project with a name, brief, and Drive URL
- Google Drive download — clips pulled into `projects/{id}/clips/` before assembly
- **Visual Clip Plan Editor** — thumbnail grid of all clips, click to assign to cuts, inline trim (in/out seconds), reorder (↑↓), transition selector (cut/fade), save to `plan.json`
- FFmpeg assembly — trims, reframes to 9:16, concatenates with cut/fade transitions
- OpenAI TTS voiceover (tts-1-hd, 6 voice options)
- Whisper caption burn-in — word-grouped, bold white + golden italic key words, auto-scaled
- AI script generation — per-cut variants (3 options, click to use)
- AI angle generation — Claude proposes 3 full angle concepts (name, hook, vibe, script) from project brief + emotion/platform/CTA chips
- FastAPI backend with SSE streaming pipeline log
- Next.js dark UI (ElevenLabs-style) at localhost:3000

### Project structure
```
projects/{id}/
  meta.json      ← name, brief, drive_url, clips_dir
  plan.json      ← cut definitions (clips, trims, labels, hooks, vibes)
  scripts/       ← voiceover .txt files
  output/        ← rendered .mp4 files (gitignored)
  clips/         ← downloaded footage (gitignored)
  .thumbs/       ← cached JPEG thumbnails (gitignored)
```

---

## Next session — immediate priority

### Feature: AI Edit Plan (the big one)

**What it does:** User clicks "✦ AI Edit Plan" → Claude Vision analyzes every clip → Claude generates the full clip plan (which clips go in each cut, in what order, with trim points) → Clip Plan editor populates automatically.

This is the original core promise of the app. The building blocks already exist:
- `src/analyzer.py` — sends a keyframe from each clip to `claude-sonnet-4-6` Vision, returns structured JSON description per clip
- `src/planner.py` — takes clip analyses + editorial briefs, returns a full edit plan JSON

They just need to be called with project-aware paths and exposed via a streaming API endpoint.

**What to build:**

1. **Backend — `POST /api/projects/{id}/analyze-and-plan`** (SSE stream)
   - Scan `clips_dir` for video files
   - For each clip: extract a keyframe with ffmpeg, send to Claude Vision (`src/analyzer.py` logic), emit `{"event":"progress","message":"Analysed IMG_6650.MOV (3/25)"}` 
   - Once all clips analysed: call Claude text planner with clip analyses + the angle hooks/vibes already in `plan.json`
   - Parse result, write to `plan.json` (preserving existing labels/hooks/vibes, only updating `clips` and `trim`)
   - Emit `{"event":"done","plan":...}`

2. **Frontend — "✦ AI Edit Plan" button** in the Clip Plan section header
   - Opens an SSE stream to the endpoint above
   - Shows a progress bar / log while Claude works
   - When done: re-fetches project plan, Clip Plan editor populates with AI-chosen clips + trims
   - User can then tweak manually before running pipeline

**Key files to touch:**
- `api/server.py` — add the new SSE endpoint
- `src/analyzer.py` — already works, just needs `clips_dir` param instead of hardcoded paths
- `src/planner.py` — already works, needs to accept pre-existing angle hooks/vibes as briefs
- `frontend/app/page.tsx` — add button + progress UI to ClipPlanEditor component

**Prompt engineering note:** The planner prompt should be seeded with the angle concepts already generated (hook, vibe, label from `plan.json`) so Claude selects clips that match each specific angle rather than inventing new ones.

---

## Backlog (in priority order)

### Caption style presets
A style picker in the UI with 3-4 presets:
- **Current** — bold white + golden italic key words
- **Pill** — word chunk gets a solid rounded background box (very 2024 TikTok)
- **Minimal** — smaller, centered, no outline
- **Big single word** — one word at a time, full screen drama

Each preset is a named config dict in `src/captioner.py`. UI adds a selector row above the run button.

### Music bed
Optional background track ducked under VO. Implementation:
- Upload/select a music file per project (or a small built-in library)
- FFmpeg `-filter_complex` to mix: original video audio (if any) + VO + music at -18dB
- Toggle in pipeline options

### In-browser video preview
Show output videos directly in the UI without downloading. Next.js `<video>` tag pointing at a streaming endpoint. Needs `Range` header support in FastAPI (use `FileResponse` with range support or `StreamingResponse`).

### Clip scrubber
Click a clip thumbnail in the library to preview it at a specific second. Could be a simple HTML5 `<video>` in a modal — the clip file is local so it can be served directly by FastAPI.
