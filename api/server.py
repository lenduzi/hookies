"""
Hookies API — FastAPI backend (multi-project).

Projects live in ./projects/{id}/
  meta.json   — name, brief, drive_url, clips_dir, created_at
  plan.json   — cut definitions (clips, trims, labels)
  scripts/    — voiceover .txt files
  output/     — rendered .mp4 files

Endpoints:
  GET  /api/voices
  GET  /api/projects
  POST /api/projects
  GET  /api/projects/{id}
  DELETE /api/projects/{id}
  GET  /api/projects/{id}/scripts
  POST /api/projects/{id}/scripts
  POST /api/projects/{id}/generate   ← Claude script generation
  POST /api/projects/{id}/run        ← SSE pipeline
  GET  /api/projects/{id}/outputs
  GET  /api/download/{project_id}/{filename}
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

PROJECTS_DIR = ROOT / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Hookies API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VOICES = [
    {"id": "alloy",   "label": "Alloy",   "description": "Clear, neutral"},
    {"id": "echo",    "label": "Echo",    "description": "Smooth, male"},
    {"id": "fable",   "label": "Fable",   "description": "Warm, storytelling"},
    {"id": "onyx",    "label": "Onyx",    "description": "Deep, authoritative"},
    {"id": "nova",    "label": "Nova",    "description": "Warm, natural — great for UGC"},
    {"id": "shimmer", "label": "Shimmer", "description": "Bright, upbeat"},
]


# ── Pydantic models ───────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str
    brief: str = ""
    drive_url: str = ""

class ScriptEntry(BaseModel):
    cut_id: str
    script: str

class SaveScriptsRequest(BaseModel):
    scripts: list[ScriptEntry]

class GenerateRequest(BaseModel):
    cut_id: str          # e.g. "cut_1"
    tone_hint: str = ""  # optional extra nudge

class GenerateAnglesRequest(BaseModel):
    emotion: str = ""    # e.g. "FOMO", "Inspiration"
    platform: str = ""   # e.g. "TikTok / Reels"
    cta: str = ""        # e.g. "Link in bio"
    extra: str = ""      # free-text extra notes

class RunRequest(BaseModel):
    voice: str = "nova"
    skip_assembly: bool = False
    skip_vo: bool = False
    skip_captions: bool = False
    skip_download: bool = False


# ── Project helpers ───────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

def _project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id

def _load_meta(project_id: str) -> dict:
    p = _project_dir(project_id) / "meta.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return json.loads(p.read_text())

def _load_plan(project_id: str) -> dict:
    p = _project_dir(project_id) / "plan.json"
    if not p.exists():
        return {"cuts": []}
    return json.loads(p.read_text())

def _scripts_dir(project_id: str) -> Path:
    d = _project_dir(project_id) / "scripts"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _output_dir(project_id: str) -> Path:
    d = _project_dir(project_id) / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _read_script(project_id: str, filename: str) -> str:
    p = _scripts_dir(project_id) / f"{filename}.txt"
    return p.read_text().strip() if p.exists() else ""

def _output_files(project_id: str) -> list[dict]:
    d = _output_dir(project_id)
    files = sorted(d.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [
        {
            "name": f.name,
            "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
            "url": f"/api/download/{project_id}/{f.name}",
        }
        for f in files
    ]

def _cuts_with_scripts(project_id: str) -> list[dict]:
    plan = _load_plan(project_id)
    cuts = plan.get("cuts", [])
    return [
        {
            "id": cut["id"],
            "name": cut["name"],
            "label": cut.get("label", cut["name"]),
            "hook": cut.get("hook", ""),
            "vibe": cut.get("vibe", ""),
            "has_clips": len(cut.get("clips", [])) > 0,
            "script": _read_script(project_id, f"{cut['id']}_{cut['name']}"),
        }
        for cut in cuts
    ]


# ── Routes: meta ─────────────────────────────────────────────────────────────

@app.get("/api/voices")
def get_voices():
    return {"voices": VOICES}


@app.get("/api/projects")
def list_projects():
    projects = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        meta_file = d / "meta.json"
        if d.is_dir() and meta_file.exists():
            meta = json.loads(meta_file.read_text())
            plan = _load_plan(meta["id"])
            output_count = len(list((d / "output").glob("*.mp4"))) if (d / "output").exists() else 0
            projects.append({**meta, "cut_count": len(plan.get("cuts", [])), "output_count": output_count})
    return {"projects": projects}


@app.post("/api/projects", status_code=201)
def create_project(req: CreateProjectRequest):
    project_id = _slug(req.name)
    d = _project_dir(project_id)
    if d.exists():
        raise HTTPException(status_code=409, detail=f"Project '{project_id}' already exists")
    d.mkdir(parents=True)
    (d / "scripts").mkdir()
    (d / "output").mkdir()
    (d / "clips").mkdir()

    meta = {
        "id": project_id,
        "name": req.name,
        "brief": req.brief,
        "drive_url": req.drive_url,
        "clips_dir": str(d / "clips"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=2))

    # Seed a blank 3-cut plan
    plan = {
        "cuts": [
            {"id": "cut_1", "name": "angle_1", "label": "Cut 1", "hook": "", "vibe": "", "clips": [], "trim": {}, "transition": "cut", "target_duration": 30},
            {"id": "cut_2", "name": "angle_2", "label": "Cut 2", "hook": "", "vibe": "", "clips": [], "trim": {}, "transition": "cut", "target_duration": 30},
            {"id": "cut_3", "name": "angle_3", "label": "Cut 3", "hook": "", "vibe": "", "clips": [], "trim": {}, "transition": "cut", "target_duration": 30},
        ]
    }
    (d / "plan.json").write_text(json.dumps(plan, indent=2))

    return {"project": meta}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    meta = _load_meta(project_id)
    plan = _load_plan(project_id)
    return {"project": meta, "plan": plan}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    import shutil
    d = _project_dir(project_id)
    if not d.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    shutil.rmtree(d)
    return {"ok": True}


# ── Routes: scripts ───────────────────────────────────────────────────────────

@app.get("/api/projects/{project_id}/scripts")
def get_scripts(project_id: str):
    _load_meta(project_id)  # 404 guard
    return {"cuts": _cuts_with_scripts(project_id)}


@app.post("/api/projects/{project_id}/scripts")
def save_scripts(project_id: str, req: SaveScriptsRequest):
    plan = _load_plan(project_id)
    cuts_by_id = {c["id"]: c for c in plan.get("cuts", [])}
    for entry in req.scripts:
        cut = cuts_by_id.get(entry.cut_id)
        if not cut:
            raise HTTPException(status_code=400, detail=f"Unknown cut_id: {entry.cut_id}")
        filename = f"{entry.cut_id}_{cut['name']}.txt"
        (_scripts_dir(project_id) / filename).write_text(entry.script.strip())
    return {"ok": True}


# ── Routes: AI generation ─────────────────────────────────────────────────────

GENERATION_PROMPT = """You are a social media video scriptwriter specialising in UGC (user-generated content) for Instagram Reels and TikTok.

PROJECT BRIEF:
{brief}

CUT TO SCRIPT:
ID: {cut_id}
Label: {label}
Hook concept: {hook}
Vibe: {vibe}

Write exactly 3 alternative voiceover scripts for this cut. Each should:
- Be 40–60 words (fits a ~30 second clip at natural speaking pace)
- Feel authentic and conversational, not like an ad
- Match the vibe described above
- Vary meaningfully — different openers, different structures, different emotional angles
- End with a soft CTA (link in bio, details in bio, etc.)

Return ONLY valid JSON in this exact shape, no markdown fences:
{{
  "variants": [
    {{"label": "Variant A", "script": "..."}},
    {{"label": "Variant B", "script": "..."}},
    {{"label": "Variant C", "script": "..."}}
  ]
}}"""

@app.post("/api/projects/{project_id}/generate")
def generate_scripts(project_id: str, req: GenerateRequest):
    import anthropic

    meta = _load_meta(project_id)
    plan = _load_plan(project_id)
    cut = next((c for c in plan.get("cuts", []) if c["id"] == req.cut_id), None)
    if not cut:
        raise HTTPException(status_code=400, detail=f"Unknown cut_id: {req.cut_id}")

    brief = meta.get("brief", "")
    if req.tone_hint:
        brief += f"\n\nExtra tone note: {req.tone_hint}"

    prompt = GENERATION_PROMPT.format(
        brief=brief,
        cut_id=cut["id"],
        label=cut.get("label", cut["name"]),
        hook=cut.get("hook", ""),
        vibe=cut.get("vibe", ""),
    )

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown fences if Claude wraps anyway
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Claude returned non-JSON: {raw[:300]}")

    return result  # {"variants": [...]}


ANGLES_PROMPT = """You are a social media video strategist and UGC scriptwriter specialising in Instagram Reels and TikTok.

PROJECT BRIEF:
{brief}

PARAMETERS:
- Target emotion: {emotion}
- Platform: {platform}
- CTA style: {cta}
{extra_line}

Generate exactly 3 distinct video angle concepts for this project. Each angle should have a different hook strategy, emotional approach, and narrative structure — they should feel like genuinely different videos, not variations on the same idea.

For each angle provide:
- name: a short slug (snake_case, 3-5 words)
- label: a human-readable title (e.g. "Cut 1 — The Sceptic's Journey")
- hook: one sentence describing the visual/verbal opening hook
- vibe: 1-2 sentence tone description
- script: a ready-to-use voiceover script (40-60 words, conversational, authentic UGC tone, ends with a soft CTA)

Return ONLY valid JSON, no markdown fences:
{{
  "cuts": [
    {{
      "id": "cut_1",
      "name": "slug_name_here",
      "label": "Cut 1 — Human Title",
      "hook": "Opening hook description",
      "vibe": "Tone and energy description",
      "script": "Full voiceover script..."
    }},
    {{
      "id": "cut_2",
      "name": "...",
      "label": "Cut 2 — ...",
      "hook": "...",
      "vibe": "...",
      "script": "..."
    }},
    {{
      "id": "cut_3",
      "name": "...",
      "label": "Cut 3 — ...",
      "hook": "...",
      "vibe": "...",
      "script": "..."
    }}
  ]
}}"""

@app.post("/api/projects/{project_id}/generate-angles")
def generate_angles(project_id: str, req: GenerateAnglesRequest):
    import anthropic

    meta = _load_meta(project_id)
    brief = meta.get("brief", "")
    if not brief:
        raise HTTPException(status_code=400, detail="Project has no brief — add one before generating angles")

    extra_line = f"- Extra notes: {req.extra}" if req.extra else ""

    prompt = ANGLES_PROMPT.format(
        brief=brief,
        emotion=req.emotion or "any",
        platform=req.platform or "TikTok / Instagram Reels",
        cta=req.cta or "Link in bio",
        extra_line=extra_line,
    )

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Claude returned non-JSON: {raw[:300]}")

    cuts = result.get("cuts", [])
    if len(cuts) != 3:
        raise HTTPException(status_code=500, detail=f"Expected 3 cuts, got {len(cuts)}")

    # Load existing plan to preserve clips/trim data
    plan = _load_plan(project_id)
    existing_by_id = {c["id"]: c for c in plan.get("cuts", [])}

    new_cuts = []
    for cut in cuts:
        existing = existing_by_id.get(cut["id"], {})
        new_cuts.append({
            "id": cut["id"],
            "name": cut["name"],
            "label": cut["label"],
            "hook": cut["hook"],
            "vibe": cut["vibe"],
            "clips": existing.get("clips", []),
            "trim": existing.get("trim", {}),
            "transition": existing.get("transition", "cut"),
            "target_duration": existing.get("target_duration", 30),
        })

    # Save updated plan
    plan["cuts"] = new_cuts
    (_project_dir(project_id) / "plan.json").write_text(json.dumps(plan, indent=2))

    # Save generated scripts
    for cut in cuts:
        filename = f"{cut['id']}_{cut['name']}.txt"
        (_scripts_dir(project_id) / filename).write_text(cut["script"].strip())

    return {"cuts": _cuts_with_scripts(project_id)}


# ── Routes: pipeline ──────────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/run")
async def run_pipeline(project_id: str, req: RunRequest, request: Request):
    _load_meta(project_id)  # 404 guard

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        def emit(event: str, data: dict):
            payload = json.dumps({"event": event, **data})
            queue.put_nowait(f"data: {payload}\n\n")

        async def run():
            try:
                cmd = [sys.executable, "run_offline.py", "--project", project_id]
                if req.skip_assembly:
                    cmd.append("--vo-only")
                if req.skip_vo:
                    cmd.append("--skip-vo")
                if req.skip_captions:
                    cmd.append("--skip-captions")
                if req.skip_download:
                    cmd.append("--skip-download")

                env = os.environ.copy()
                env["OPENAI_TTS_VOICE"] = req.voice

                emit("start", {"message": f"Starting pipeline for {project_id}..."})

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                    cwd=str(ROOT),
                )

                async for raw_line in proc.stdout:
                    line = raw_line.decode("utf-8", errors="replace").rstrip()
                    if line:
                        emit("log", {"message": line})

                await proc.wait()

                if proc.returncode == 0:
                    emit("done", {"message": "Pipeline complete!", "files": _output_files(project_id)})
                else:
                    emit("error", {"message": f"Pipeline exited with code {proc.returncode}"})

            except Exception as exc:
                emit("error", {"message": str(exc)})
            finally:
                queue.put_nowait(None)

        asyncio.create_task(run())

        while True:
            if await request.is_disconnected():
                break
            try:
                item = await asyncio.wait_for(queue.get(), timeout=30)
            except asyncio.TimeoutError:
                yield "data: {\"event\":\"ping\"}\n\n"
                continue
            if item is None:
                break
            yield item

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/projects/{project_id}/outputs")
def get_outputs(project_id: str):
    _load_meta(project_id)
    return {"files": _output_files(project_id)}


@app.get("/api/download/{project_id}/{filename}")
def download_file(project_id: str, filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = _output_dir(project_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path), media_type="video/mp4", filename=filename)
