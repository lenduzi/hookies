# Hookies — Roadmap

## Current state (as of 2026-04-19)

### What works end-to-end
- Multi-project CRUD — name, brief, Drive URL, per-project clips
- Google Drive download — clips pulled into `projects/{id}/clips/` before assembly
- **Visual Clip Plan Editor** — thumbnail grid, click-to-assign, inline trim, reorder, transition selector, save
- FFmpeg assembly — trims, reframes to 9:16, cut/fade transitions
- AI angle generation — Claude proposes 3 full angle concepts from brief + chips
- AI script generation — per-cut variants (3 options, click to use)
- AI Edit Plan — Claude Vision analyses every clip, auto-populates the cut plan
- ElevenLabs voiceover (6 voice options, tts-1-hd quality)
- Whisper caption burn-in — 3 styles: Highlight (yellow box), Word (single large), Classic (outline)
- SSE streaming pipeline log + animated progress bar
- Output files grouped by cut with angle label headers
- Dark ElevenLabs-style UI at localhost:3000

### Project structure
```
projects/{id}/
  meta.json      ← name, brief, drive_url, clips_dir, key_words
  plan.json      ← cut definitions (clips, trims, labels, hooks, vibes)
  scripts/       ← voiceover .txt files
  output/        ← rendered .mp4 files (gitignored)
  clips/         ← downloaded footage (gitignored)
  .thumbs/       ← cached JPEG thumbnails (gitignored)
```

---

## Phase 1 — Standalone production (Hookies as a live tool)

**Goal:** Hookies running at a real URL, usable by anyone with an account.

### 1a — Infrastructure

| Component | Choice | Notes |
|-----------|--------|-------|
| Frontend  | **Vercel** | Push to main → auto-deploy. Free tier covers it. |
| Backend   | **Render.com** (web service + background worker) | Supports Python + FFmpeg, persistent disk ($7/mo), native env var management. |
| Storage   | **Cloudflare R2** | S3-compatible, free egress, cheap. Videos uploaded here after render; frontend streams from R2. |
| Queue     | **rq + Redis** (via Render Redis add-on) | Pipeline can't be a blocking HTTP request. SSE endpoint enqueues a job, worker runs it, progress events pushed via Redis pub/sub. |

**Key files to add:**
- `worker.py` — rq worker entry point, imports and runs the pipeline
- `src/storage.py` — upload/download helpers for R2 (`boto3` with custom endpoint)
- `Dockerfile` (or `render.yaml`) — reproducible build with FFmpeg

**Environment variables to extract:**
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`
- `R2_BUCKET`, `R2_ENDPOINT`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`
- `REDIS_URL`

### 1b — Auth

Simple API-key auth for now (no OAuth complexity):
- `POST /api/auth/login` returns a JWT
- All project endpoints require `Authorization: Bearer <token>`
- Hardcode 1-2 users in env vars initially, move to DB when needed

### 1c — Database

Currently: everything in `projects/{id}/` JSON files on disk.  
For prod: keep JSON files on disk (Render persistent disk is fine), add a lightweight SQLite DB for user → project mapping and job status tracking. No Postgres needed yet.

**Estimated effort:** 3–4 sessions

---

## Phase 2 — Quality of life before launch

Small things that matter for real users:

- **In-browser video preview** — `<video>` tag pointing at a streaming endpoint. Needs `Range` header support in FastAPI (`FileResponse` already handles it).
- **Auto-generate key_words from script** — after script is saved, call Claude to extract 8–12 key words for the caption highlight. Saves having to maintain `meta.json.key_words` manually.
- **Music bed** — optional background track at -18dB ducked under VO. FFmpeg `-filter_complex` mix. Small library of royalty-free tracks bundled.
- **Clip scrubber** — click a clip thumbnail in the editor to preview it in a modal. HTML5 `<video>` served from FastAPI.

**Estimated effort:** 1–2 sessions

---

## Phase 3 — getwhisper.de integration

**Goal:** Hookies embedded in the Whisper creator platform. Creators log in to Whisper, upload clips, get polished cuts in one click. No voiceover or captions from Hookies — creators add their own in CapCut/similar.

### Integration model

```
Whisper platform
  └── POST /api/projects           ← create project (API token auth)
  └── POST /api/projects/{id}/clips/upload ← push clips directly (no Drive)
  └── POST /api/projects/{id}/run  ← trigger pipeline (assembly only, no VO/captions)
  └── GET  /api/projects/{id}/outputs ← poll or webhook for results
  └── GET  /api/projects/{id}/outputs/{file}/download ← stream high-res MP4
```

**What to build:**
1. **Direct clip upload endpoint** — `POST /api/projects/{id}/clips/upload` accepts multipart video, saves to clips dir (or R2). Replaces the Drive download flow for the embedded use case.
2. **API token auth** — project-scoped tokens created by the Whisper backend and passed as a header. No login UI needed for the embedded flow.
3. **Webhook callback** — when pipeline completes, POST to a configurable `webhook_url` stored in `meta.json` with the list of output file URLs.
4. **"Assembly only" as first-class mode** — currently a skip flag. Make it a named pipeline preset (`mode: "assembly"`) for the Whisper use case.

**What stays the same:**  
All the AI (angle gen, script gen, AI Edit Plan) still runs. Whisper sends a brief; Hookies generates angles, assembles cuts, returns clean MP4s. Creators do final VO + captions in their preferred tool.

**Estimated effort:** 2 sessions

---

## Phase 4 — Scale and polish

Once Phase 3 is live and creators are using it:

- **Voice cloning** — ElevenLabs instant clone from a 30-second sample. Creator records themselves once; all future VO uses their voice. Changes the standalone value prop dramatically.
- **Thumbnail export** — best frame per cut, exported as cover image (needed for every platform upload).
- **Hook A/B** — export 2 versions of each cut with different first 3 seconds for split testing.
- **Template library** — save a successful cut pattern (clip order + hook formula) as a reusable template across projects.
- **Analytics webhook** — when a Whisper creator posts a Hookies-generated video, track views/engagement back to the template/angle that generated it. Closes the feedback loop on what works.

---

## Immediate next actions

1. ✅ Caption styles — Highlight box, Word, Classic (done)
2. ☐ Set up Render + Vercel + R2 accounts
3. ☐ Extract all env vars, write `render.yaml`
4. ☐ Add `rq` worker + Redis for background pipeline jobs
5. ☐ Add basic JWT auth
6. ☐ Deploy and smoke-test end-to-end
7. ☐ Build direct clip upload endpoint for Whisper integration
8. ☐ Build webhook callback
