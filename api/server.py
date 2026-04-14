"""
Hookies API — FastAPI backend.
Endpoints:
  GET  /api/voices          → list available TTS voices
  GET  /api/scripts         → get current voiceover scripts
  POST /api/scripts         → save voiceover scripts
  POST /api/run             → SSE stream: run full pipeline
  GET  /api/outputs         → list output files
  GET  /api/download/{name} → stream-download an output file
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path("./output")
SCRIPTS_DIR = Path("./voiceover_scripts")
OUTPUT_DIR.mkdir(exist_ok=True)
SCRIPTS_DIR.mkdir(exist_ok=True)

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

CUT_DEFAULTS = [
    {
        "id": "cut_1",
        "name": "i_didnt_know_i_could_do_this",
        "label": "Cut 1 — I didn't know I could do this",
    },
    {
        "id": "cut_2",
        "name": "hamburgs_most_underrated_evening",
        "label": "Cut 2 — Hamburg's most underrated evening",
    },
    {
        "id": "cut_3",
        "name": "what_they_dont_tell_you",
        "label": "Cut 3 — What they don't tell you",
    },
]


# ── Models ────────────────────────────────────────────────────────────────────

class ScriptEntry(BaseModel):
    cut_id: str
    script: str

class SaveScriptsRequest(BaseModel):
    scripts: list[ScriptEntry]

class RunRequest(BaseModel):
    voice: str = "nova"
    drive_url: str = ""
    skip_assembly: bool = False
    skip_vo: bool = False
    skip_captions: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _script_path(cut_name: str) -> Path:
    return SCRIPTS_DIR / f"{cut_name}.txt"


def _read_script(cut_name: str) -> str:
    p = _script_path(cut_name)
    return p.read_text().strip() if p.exists() else ""


def _output_files() -> list[dict]:
    if not OUTPUT_DIR.exists():
        return []
    files = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [
        {
            "name": f.name,
            "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
            "url": f"/api/download/{f.name}",
        }
        for f in files
    ]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/voices")
def get_voices():
    return {"voices": VOICES}


@app.get("/api/scripts")
def get_scripts():
    return {
        "cuts": [
            {**cut, "script": _read_script(f"cut_{i+1}_{cut['name']}")}
            for i, cut in enumerate(CUT_DEFAULTS)
        ]
    }


@app.post("/api/scripts")
def save_scripts(req: SaveScriptsRequest):
    for entry in req.scripts:
        # Find the cut name from id
        cut = next((c for c in CUT_DEFAULTS if c["id"] == entry.cut_id), None)
        if not cut:
            raise HTTPException(status_code=400, detail=f"Unknown cut_id: {entry.cut_id}")
        filename = f"{entry.cut_id}_{cut['name']}"
        _script_path(filename).write_text(entry.script.strip())
    return {"ok": True}


@app.get("/api/outputs")
def get_outputs():
    return {"files": _output_files()}


@app.get("/api/download/{filename}")
def download_file(filename: str):
    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = OUTPUT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path), media_type="video/mp4", filename=filename)


@app.post("/api/run")
async def run_pipeline(req: RunRequest, request: Request):
    """SSE endpoint — streams progress events while running the pipeline."""

    async def event_stream():
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def emit(event: str, data: dict):
            payload = json.dumps({"event": event, **data})
            queue.put_nowait(f"data: {payload}\n\n")

        async def run():
            try:
                import subprocess
                cmd = [
                    sys.executable, "run_offline.py",
                ]
                if req.skip_assembly:
                    cmd.append("--vo-only")
                if req.skip_vo:
                    cmd.append("--skip-vo")
                if req.skip_captions:
                    cmd.append("--skip-captions")

                # Set voice via env
                env = os.environ.copy()
                env["OPENAI_TTS_VOICE"] = req.voice

                emit("start", {"message": "Starting pipeline..."})

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                    cwd=str(Path(__file__).parent.parent),
                )

                async for raw_line in proc.stdout:
                    line = raw_line.decode("utf-8", errors="replace").rstrip()
                    if line:
                        emit("log", {"message": line})

                await proc.wait()

                if proc.returncode == 0:
                    emit("done", {"message": "Pipeline complete!", "files": _output_files()})
                else:
                    emit("error", {"message": f"Pipeline exited with code {proc.returncode}"})

            except Exception as exc:
                emit("error", {"message": str(exc)})
            finally:
                queue.put_nowait(None)  # sentinel

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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
