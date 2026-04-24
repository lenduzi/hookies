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

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
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
    {"id": "FGY2WhTYpPnrIDTdsKH5", "label": "Laura",   "description": "Warm, natural — great for UGC"},
    {"id": "Xb7hH8MSUJpSbSDYk0k2", "label": "Alice",   "description": "Confident, expressive, female"},
    {"id": "pFZP5JQG7iQjIQuC4Bku", "label": "Lily",    "description": "Warm, conversational, female"},
    {"id": "CwhRBWXzGAHq8TQ4Fs17", "label": "Roger",   "description": "Confident, American male"},
    {"id": "JBFqnCBsd6RMkjVDRZzb", "label": "George",  "description": "Deep, warm, British male"},
    {"id": "IKne3meq5aSn9XLyUdCD", "label": "Charlie", "description": "Natural, Australian male"},
    {"id": "onwK4e9ZLuTAKqWW03F9", "label": "Daniel",  "description": "Authoritative, British male"},
    {"id": "N2lVS1w4EtoT3dr4eOWO", "label": "Callum",  "description": "Intense, male"},
    {"id": "bIHbv24MWmeRgasZH58o", "label": "Will",    "description": "Friendly, conversational male"},
]


# ── Pydantic models ───────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str
    brief: str = ""
    angle: str = ""       # content angle / hook type (e.g. "hidden gem", "date night idea")
    drive_url: str = ""

class ScriptEntry(BaseModel):
    cut_id: str
    script: str

class SaveScriptsRequest(BaseModel):
    scripts: list[ScriptEntry]

class GenerateRequest(BaseModel):
    cut_id: str          # e.g. "cut_1"
    tone_hint: str = ""  # optional extra nudge
    cta: str = ""        # override CTA for this regenerate; falls back to meta.cta

class GenerateAnglesRequest(BaseModel):
    platform: str = ""          # e.g. "TikTok / Reels"
    cta: str = ""               # e.g. "Link in bio"
    angles: list[str] = []      # up to 3 angles, one per cut (new multi-select)
    angle: str = ""             # single angle — backward compat fallback
    language: str = "auto"      # "auto" | "en" | "de"
    extra: str = ""             # free-text extra notes

class RunRequest(BaseModel):
    voice: str = "FGY2WhTYpPnrIDTdsKH5"  # Laura (ElevenLabs default)
    skip_assembly: bool = False
    skip_vo: bool = False
    skip_captions: bool = False
    skip_download: bool = False
    caption_style: str = "classic"        # "classic" or "pill"

class ScrapeUrlRequest(BaseModel):
    url: str


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
            "assigned_angle": cut.get("assigned_angle", ""),
            "has_clips": len(cut.get("clips", [])) > 0,
            "script": _read_script(project_id, f"{cut['id']}_{cut['name']}"),
        }
        for cut in cuts
    ]


# ── Routes: meta ─────────────────────────────────────────────────────────────

@app.get("/api/voices")
def get_voices():
    return {"voices": VOICES}


def _html_to_text(html: str) -> str:
    import re as _re
    text = _re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=_re.S | _re.I)
    text = _re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=_re.S | _re.I)
    text = _re.sub(r"<noscript[^>]*>.*?</noscript>", " ", text, flags=_re.S | _re.I)
    text = _re.sub(r"<[^>]+>", " ", text)
    # HTML entities — good enough for the common ones
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#x27;", "'")
    text = text.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
    return _re.sub(r"\s+", " ", text).strip()


# Subpaths we'll try in addition to the root; common "about us" locations in EN/DE
_ABOUT_PATHS = ("", "/about", "/about-us", "/ueber-uns", "/uber-uns", "/story", "/who-we-are")


@app.post("/api/scrape-brief")
async def scrape_brief(req: ScrapeUrlRequest):
    import httpx
    import anthropic
    from urllib.parse import urljoin, urlparse

    raw_url = req.url.strip()
    if not raw_url.startswith(("http://", "https://")):
        raw_url = "https://" + raw_url

    parsed = urlparse(raw_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
    }

    pages: list[tuple[str, str]] = []  # (url, text)
    errors: list[str] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=15, headers=headers) as client:
        # Always try the user-supplied URL first, then common about-page paths off its origin.
        candidates = [raw_url] + [urljoin(base, p) for p in _ABOUT_PATHS if urljoin(base, p) != raw_url]
        seen = set()
        for url in candidates:
            if url in seen or len(pages) >= 3:
                continue
            seen.add(url)
            try:
                resp = await client.get(url)
                if resp.status_code >= 400:
                    errors.append(f"{url} → HTTP {resp.status_code}")
                    continue
                text = _html_to_text(resp.text)
                if len(text) < 200:
                    errors.append(f"{url} → only {len(text)} chars of text (likely JS-rendered)")
                    continue
                pages.append((str(resp.url), text))
            except Exception as e:
                errors.append(f"{url} → {type(e).__name__}: {e}")

    if not pages:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not extract any readable text from the site. "
                "This often happens with single-page apps that render content via JavaScript. "
                "Tried: " + "; ".join(errors[:4])
            ),
        )

    combined = "\n\n---\n\n".join(f"# {url}\n{text[:4000]}" for url, text in pages)
    combined = combined[:12000]  # cap total context

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                f"Below is raw text from up to 3 pages of a brand/venue's website (origin: {base}).\n\n"
                f"{combined}\n\n"
                "Distill this into a short project brief for short-form UGC video scripts.\n\n"
                "Target: 2–3 sentences, max ~60 words. Capture:\n"
                "• what the place actually IS, in plain words (not marketing copy)\n"
                "• what someone DOES there — the sensory/experiential core (what you see, taste, touch)\n"
                "• the tone and who it's for\n\n"
                "Hard rules — these kill the output if violated:\n"
                "• Do NOT list cities or locations. \"A wine-and-paint bar\" beats \"with locations in Frankfurt, Munich, Hamburg, and Berlin.\"\n"
                "• Do NOT enumerate products, services, or event formats. \"You drink wine while you paint\" beats \"formats like Techno & Paint, Blind Tasting, Aktmalerei, Aquarellkurs.\"\n"
                "• Do NOT include founding year, founder names, or company history unless it's essential to the vibe.\n"
                "• Do NOT write like a press release or an elevator pitch. Write like you're describing the place to a friend over a drink.\n\n"
                "Write in the same language as the source content. Plain text, no preamble, no markdown."
            ),
        }],
    )
    brief = msg.content[0].text.strip()
    return {"brief": brief, "pages_used": [u for u, _ in pages]}


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
        "angle": req.angle,
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


def _extract_and_save_key_words(project_id: str) -> None:
    """Background task: read all scripts, ask Claude for highlight words, save to meta.json."""
    import anthropic

    script_files = list(_scripts_dir(project_id).glob("*.txt"))
    if not script_files:
        return

    combined = "\n\n---\n\n".join(f.read_text().strip() for f in script_files if f.read_text().strip())
    if not combined:
        return

    prompt = (
        "Extract caption highlight words from these short-form video scripts.\n\n"
        f"SCRIPTS:\n{combined}\n\n"
        "Return 8-12 uppercase words worth highlighting in captions: brand/venue names, "
        "locations, power words (STUNNING, INCREDIBLE, etc.), numbers, strong verbs. "
        "Skip filler words.\n\n"
        'Return ONLY valid JSON, no markdown fences: {"key_words": ["WORD1", "WORD2", ...]}'
    )

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = re.sub(r"```(?:json)?\s*|\s*```", "", msg.content[0].text).strip()
        key_words = json.loads(raw).get("key_words", [])
        if key_words:
            meta = _load_meta(project_id)
            meta["key_words"] = [w.upper() for w in key_words]
            (_project_dir(project_id) / "meta.json").write_text(json.dumps(meta, indent=2))
    except Exception as exc:
        print(f"  ⚠ key_words extraction failed for {project_id}: {exc}", file=sys.stderr)


@app.post("/api/projects/{project_id}/scripts")
def save_scripts(project_id: str, req: SaveScriptsRequest, background_tasks: BackgroundTasks):
    plan = _load_plan(project_id)
    cuts_by_id = {c["id"]: c for c in plan.get("cuts", [])}
    for entry in req.scripts:
        cut = cuts_by_id.get(entry.cut_id)
        if not cut:
            raise HTTPException(status_code=400, detail=f"Unknown cut_id: {entry.cut_id}")
        filename = f"{entry.cut_id}_{cut['name']}.txt"
        (_scripts_dir(project_id) / filename).write_text(entry.script.strip())
    background_tasks.add_task(_extract_and_save_key_words, project_id)
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
- Feel like a real person talking to a friend, not an ad — contractions, hedges, sentence fragments are all fine
- Match the vibe and hook concept described above (don't drift to a different angle)
- Vary meaningfully — different openers, different structures, different emotional angles
- Open a LOOP in the first line (curiosity, contrast, bold claim, POV, number, question, or direct address) — a reason to keep watching
- Reference ONE sensory/experiential detail from the brief (what you see, taste, do) — not a factoid
- End with this call to action — use the exact words or a close natural paraphrase: "{cta}"

NEVER do these — instant rejection:
✗ List cities or locations (e.g. "in Frankfurt, München, Hamburg und Berlin")
✗ Enumerate products, formats, or services (e.g. "Formate wie X, Y und Z")
✗ Include founding year, founders' names, or company history
✗ Marketing speak ("einzigartig", "eine Mischung aus", "unvergesslich")
✗ Anything that sounds like a website About page

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

    cta = req.cta or meta.get("cta") or "Link in bio"

    prompt = GENERATION_PROMPT.format(
        brief=brief,
        cut_id=cut["id"],
        label=cut.get("label", cut["name"]),
        hook=cut.get("hook", ""),
        vibe=cut.get("vibe", ""),
        cta=cta,
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


ANGLES_PROMPT = """You are writing voiceover scripts for short-form social media videos (Instagram Reels / TikTok) about a specific venue or experience.

━━━ VENUE / PROJECT BRIEF ━━━
{brief}

━━━ HOOK PATTERNS — every hook MUST use one of these structures ━━━
The first line of each script is the hook. It has ~3 seconds to stop the scroll. Pick a DIFFERENT pattern for each cut.

• Curiosity gap     — "Das Weirdeste an diesem Ort ist..." / "The weirdest thing about this place is..."
• Negation / secret — "Niemand spricht darüber, aber..." / "Nobody tells you that..."
• Specific number   — "3 Gründe, warum ich hier jedes Wochenende hingehe..." / "3 things I wish I knew before..."
• POV framing       — "POV: Du entdeckst gerade..." / "POV: you just found..."
• Personal contrast — "Ich war skeptisch, bis..." / "I thought X until..."  (before/after builds a loop)
• Direct address    — "Wenn du in [stadt] wohnst und das nicht kennst..." / "If you live in X and haven't tried this..."
• Bold claim        — "Das ist der unterschätzteste Abend in [stadt]." / "This is the most underrated spot in X."
• Question          — "Warum redet niemand über..." / "Why isn't anyone talking about..."

Rules for hooks:
• Must open a LOOP — a reason to keep watching to get the payoff.
• Must be SPECIFIC — a sensory or personal detail, not a generic pitch. "ein Glas Wein in der Hand" beats "creative experiences."
• No throat-clearing ("Also..." / "So..."). First word matters.

━━━ OUTPUT RULES — follow every rule, no exceptions ━━━
1. LANGUAGE: Write every script in {language}.
2. VENUE: Every script must name the venue once. Use ONE sensory/experiential detail from the brief (what you see, taste, do) — not a factoid. NEVER list cities, formats, events, or services. NEVER use phrases like "mit Standorten in..." or "they have locations in..." or "Formate wie X, Y und Z." One venue, one vivid detail, that's it.
3. CTA: Every script must end with this call to action — use the exact words or a close natural paraphrase: "{cta}"
4. LENGTH: 40–60 words per script. Conversational UGC — sounds like a real person talking to a friend, not an ad. Contractions, hedges ("ich mein", "ehrlich", "also"), sentence fragments and half-thoughts are all fine. When in doubt, make it SHORTER and more casual.
5. PLATFORM: {platform}
{extra_line}
━━━ ANTI-PATTERNS — instant rejection ━━━
✗ "X hat Standorte in Frankfurt, München, Hamburg und Berlin"  (enumeration)
✗ "Formate wie Techno & Paint, Blind Tasting oder Aktmalerei"   (list of services)
✗ "Gegründet 2018 von..."                                        (press-release)
✗ "bietet eine einzigartige Mischung aus..."                     (marketing speak)
✗ Anything that sounds like a website "About" page.

━━━ ANGLE ASSIGNMENTS ━━━
{angle_assignments}

━━━ OUTPUT FORMAT ━━━
Return ONLY valid JSON, no markdown fences. Include assigned_angle verbatim for each cut — this is how we verify you followed the assignment.

{{
  "key_words": ["WORD1", ...],
  "cuts": [
    {{
      "id": "cut_1",
      "assigned_angle": "exact angle text from assignment",
      "name": "snake_case_slug",
      "label": "Cut 1 — Human Title",
      "hook": "One sentence — the verbal/visual opening that immediately signals the angle",
      "vibe": "1-2 sentences on tone and energy",
      "script": "Full 40-60 word voiceover. Names the venue. Ends with the specified CTA."
    }},
    {{
      "id": "cut_2",
      "assigned_angle": "...",
      "name": "...",
      "label": "Cut 2 — ...",
      "hook": "...",
      "vibe": "...",
      "script": "..."
    }},
    {{
      "id": "cut_3",
      "assigned_angle": "...",
      "name": "...",
      "label": "Cut 3 — ...",
      "hook": "...",
      "vibe": "...",
      "script": "..."
    }}
  ]
}}

key_words: 6-12 uppercase words across all 3 scripts worth highlighting in captions — venue name, location, event names, power words."""


def _build_angle_assignments(angles: list[str]) -> str:
    """Return the angle-assignment block for ANGLES_PROMPT based on selection count."""
    if len(angles) == 3:
        return (
            f"ANGLE ASSIGNMENTS — each cut must be built entirely around its assigned angle.\n"
            f"The brief provides context about the venue; the angle tells you WHAT the video is about.\n\n"
            f'CUT 1 ANGLE: "{angles[0]}"\n'
            f"  → Hook, vibe, and script must frame the venue specifically through this lens.\n\n"
            f'CUT 2 ANGLE: "{angles[1]}"\n'
            f"  → Hook, vibe, and script must frame the venue specifically through this lens.\n\n"
            f'CUT 3 ANGLE: "{angles[2]}"\n'
            f"  → Hook, vibe, and script must frame the venue specifically through this lens.\n\n"
            f"These are three completely different videos targeting three different search intents. "
            f"Someone watching Cut 1 should immediately know it's about '{angles[0]}', not '{angles[1]}'."
        )
    if len(angles) == 2:
        return (
            f"ANGLE ASSIGNMENTS — two angles are specified; invent a third that complements them:\n\n"
            f'CUT 1 ANGLE: "{angles[0]}"\n'
            f"  → Hook, vibe, and script must frame the venue through this lens.\n\n"
            f'CUT 2 ANGLE: "{angles[1]}"\n'
            f"  → Hook, vibe, and script must frame the venue through this lens.\n\n"
            f"CUT 3 ANGLE: Invent a third angle complementary to the above two.\n"
            f"  → Choose an angle that targets a different audience or search intent."
        )
    if len(angles) == 1:
        return (
            f'ANGLE FOR ALL 3 CUTS: "{angles[0]}"\n\n'
            f"Generate 3 distinct takes on this single angle. Each cut must have:\n"
            f"- A completely different hook strategy (e.g. question, bold statement, POV opening)\n"
            f"- A different emotional frame (e.g. FOMO, curiosity, inspiration)\n"
            f"- A different narrative structure\n"
            f"They must feel like meaningfully different videos, not minor variations."
        )
    # 0 angles — Claude decides
    return (
        "ANGLES: You decide. Generate 3 distinct content angles that work well for this venue/project.\n"
        "Each must target a different search intent or emotional trigger — "
        "they should feel like genuinely different videos, not variations on the same idea."
    )

@app.post("/api/projects/{project_id}/generate-angles")
def generate_angles(project_id: str, req: GenerateAnglesRequest):
    import anthropic

    meta = _load_meta(project_id)
    brief = meta.get("brief", "")
    if not brief:
        raise HTTPException(status_code=400, detail="Project has no brief — add one before generating angles")

    # Resolve angles: multi-select takes precedence, fall back to single angle, then meta
    angles = req.angles or ([req.angle] if req.angle else []) or meta.get("angles", []) or ([meta.get("angle")] if meta.get("angle") else [])

    # Resolve language
    lang_map = {"en": "English", "de": "German / Deutsch"}
    language = lang_map.get(req.language, "the same language as the brief above (auto-detect)")

    extra_line = f"Extra notes: {req.extra}" if req.extra else ""

    prompt = ANGLES_PROMPT.format(
        brief=brief,
        language=language,
        angle_assignments=_build_angle_assignments(angles),
        platform=req.platform or "TikTok / Instagram Reels",
        cta=req.cta or "Link in bio",
        extra_line=extra_line,
    )

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=(
            "You are a precise UGC video scriptwriter. "
            "When angle assignments are provided you follow them exactly — "
            "each cut's hook, vibe, and script must be built around its assigned angle. "
            "You never blend angles or let background context override explicit assignments. "
            "You always return valid JSON and nothing else."
        ),
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

    # Warn if assigned_angle fields don't match requested angles (helps catch prompt drift)
    if len(angles) == 3:
        for i, cut in enumerate(cuts):
            returned = cut.get("assigned_angle", "")
            if returned and returned.lower() != angles[i].lower():
                import sys
                print(f"  ⚠ angle mismatch cut_{i+1}: expected '{angles[i]}' got '{returned}'", file=sys.stderr)

    # Persist key_words + angles + cta back to meta so per-cut regenerates inherit them
    key_words = result.get("key_words", [])
    if key_words:
        meta["key_words"] = key_words
    if angles:
        meta["angles"] = angles
        meta["angle"] = angles[0]  # backward compat
    if req.cta:
        meta["cta"] = req.cta
    if req.platform:
        meta["platform"] = req.platform
    if req.language and req.language != "auto":
        meta["language"] = req.language
    if req.extra:
        meta["extra"] = req.extra
    (_project_dir(project_id) / "meta.json").write_text(json.dumps(meta, indent=2))

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
            "assigned_angle": cut.get("assigned_angle", ""),
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
                if req.caption_style and req.caption_style != "classic":
                    cmd += ["--caption-style", req.caption_style]

                env = os.environ.copy()
                env["ELEVENLABS_VOICE_ID"] = req.voice

                emit("start", {"message": f"Starting pipeline for {project_id}..."})

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                    cwd=str(ROOT),
                )

                _progress_re = re.compile(r"^PROGRESS:(\d+)/(\d+):(.+)$")
                async for raw_line in proc.stdout:
                    line = raw_line.decode("utf-8", errors="replace").rstrip()
                    if not line:
                        continue
                    m = _progress_re.match(line)
                    if m:
                        emit("progress", {"done": int(m.group(1)), "total": int(m.group(2)), "label": m.group(3)})
                    else:
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


# ── Routes: clip library ──────────────────────────────────────────────────────

def _thumbs_dir(project_id: str) -> Path:
    d = _project_dir(project_id) / ".thumbs"
    d.mkdir(exist_ok=True)
    return d


def _clip_duration(clip_path: str) -> float:
    import subprocess
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", clip_path],
        capture_output=True, text=True,
    )
    try:
        return round(float(r.stdout.strip()), 1)
    except ValueError:
        return 0.0


def _extract_thumb(clip_path: str, thumb_path: str) -> bool:
    import subprocess
    r = subprocess.run(
        ["ffmpeg", "-y", "-ss", "0.5", "-i", clip_path,
         "-vframes", "1", "-vf", "scale=200:-1", thumb_path],
        capture_output=True,
    )
    return r.returncode == 0


@app.get("/api/projects/{project_id}/clips")
def get_clips(project_id: str):
    meta = _load_meta(project_id)
    clips_dir = Path(meta.get("clips_dir", str(_project_dir(project_id) / "clips")))
    if not clips_dir.exists():
        return {"clips": []}

    from src.config import SUPPORTED_EXTENSIONS
    clip_files = sorted(
        [f for f in clips_dir.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS],
        key=lambda f: f.name,
    )

    thumbs = _thumbs_dir(project_id)
    result = []
    for f in clip_files:
        thumb_file = thumbs / f"{f.stem}.jpg"
        if not thumb_file.exists():
            _extract_thumb(str(f), str(thumb_file))
        result.append({
            "filename": f.name,
            "duration": _clip_duration(str(f)),
            "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
            "thumbnail_url": f"/api/projects/{project_id}/thumbnails/{f.stem}.jpg",
        })
    return {"clips": result}


@app.get("/api/projects/{project_id}/thumbnails/{filename}")
def get_thumbnail(project_id: str, filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    thumb = _thumbs_dir(project_id) / filename
    if not thumb.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(str(thumb), media_type="image/jpeg")


class SavePlanRequest(BaseModel):
    cuts: list[dict]


# ── Routes: AI Edit Plan ──────────────────────────────────────────────────────

def _build_plan_prompt(clip_analyses: list[dict], cuts: list[dict]) -> str:
    """Build a dynamic planning prompt seeded with the project's existing angle briefs."""
    cuts_section = ""
    for i, cut in enumerate(cuts, 1):
        label = cut.get("label", cut.get("name", f"Cut {i}"))
        hook = cut.get("hook", "")
        vibe = cut.get("vibe", "")
        transition = cut.get("transition", "cut")
        cuts_section += f"""
### Cut {i} — "{label}"
- **Hook concept:** {hook or "Select the most compelling opener"}
- **Vibe:** {vibe or "Energetic, authentic, social-media ready"}
- **Transition:** {transition}
"""

    n = len(cuts)
    cut_ids = ", ".join(f'"{c["id"]}"' for c in cuts)
    example_cut = cuts[0] if cuts else {"id": "cut_1", "name": "angle_1"}
    example_clips = []
    if clip_analyses:
        example_clips = [clip_analyses[0]["filename"]]
        if len(clip_analyses) > 1:
            example_clips.append(clip_analyses[1]["filename"])

    return f"""You are an expert UGC video editor specialising in viral social media content for venues, restaurants, and nightlife.

You have analysed a folder of raw clips. Below is a JSON array of clip analysis results. Your job is to plan exactly **{n} distinct video edits**, each approximately 30 seconds long, each matching one of the creative briefs below.

## Clip analyses:
{json.dumps(clip_analyses, indent=2)}

---

## The {n} required edits:
{cuts_section}

---

## Your task:

Return a JSON object with exactly {n} cuts, one per brief above. Each cut must:
- Start with the best available hook clip for that brief (highest hook_score that matches the vibe)
- Use a different subset and ordering of clips from the others
- Have tight trims — keep clips punchy, no dead air
- Total trimmed duration should approximately equal 30 seconds

Return a JSON object in exactly this format:

```json
{{
  "cuts": [
    {{
      "id": "{example_cut['id']}",
      "clips": {json.dumps(example_clips)},
      "trim": {{
        {json.dumps(example_clips[0]) if example_clips else '"clip.MOV"'}: {{"start": 0, "end": 8}}
      }},
      "transition": "cut"
    }}
  ]
}}
```

Rules:
- `clips` must be ordered — first clip is the hook/opener
- `trim.start` and `trim.end` are in seconds, keep cuts tight and energetic
- `transition` is one of: `cut` | `fade` — use the transition specified in the brief
- Only use filenames that exist in the clip analyses provided
- The `id` values for the {n} cuts must be exactly: {cut_ids}
- Return ONLY the JSON object, no preamble or explanation
"""


@app.post("/api/projects/{project_id}/sync-drive")
async def sync_drive(project_id: str, request: Request):
    """SSE endpoint: download clips from the project's Google Drive URL into clips_dir."""
    meta = _load_meta(project_id)
    drive_url = meta.get("drive_url", "").strip()
    if not drive_url:
        raise HTTPException(status_code=400, detail="No Drive URL configured for this project")

    dest_dir = str(_project_dir(project_id) / "clips")

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        def emit(event: str, data: dict):
            payload = json.dumps({"event": event, **data})
            queue.put_nowait(f"data: {payload}\n\n")

        async def run():
            try:
                emit("progress", {"message": "Connecting to Google Drive…"})
                await asyncio.sleep(0)

                import pathlib
                pathlib.Path(dest_dir).mkdir(parents=True, exist_ok=True)

                from src.drive_client import download_folder
                loop = asyncio.get_event_loop()
                paths = await loop.run_in_executor(None, download_folder, drive_url, dest_dir)

                # Update meta.json clips_dir to point at the downloaded clips
                meta["clips_dir"] = dest_dir
                (_project_dir(project_id) / "meta.json").write_text(json.dumps(meta, indent=2))

                emit("done", {"message": f"Downloaded {len(paths)} clips.", "count": len(paths)})
            except Exception as exc:
                emit("error", {"message": str(exc)})
            finally:
                queue.put_nowait(None)

        asyncio.create_task(run())

        while True:
            if await request.is_disconnected():
                break
            try:
                item = await asyncio.wait_for(queue.get(), timeout=300)
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


@app.post("/api/projects/{project_id}/analyze-and-plan")
async def analyze_and_plan(project_id: str, request: Request):
    """SSE endpoint: analyse every clip with Claude Vision, then generate the full edit plan."""
    import base64
    import anthropic

    meta = _load_meta(project_id)
    plan = _load_plan(project_id)
    cuts = plan.get("cuts", [])

    clips_dir = Path(meta.get("clips_dir", str(_project_dir(project_id) / "clips")))
    thumbs = _thumbs_dir(project_id)

    prompt_path = ROOT / "prompts" / "analyze_clip.md"
    analyze_prompt = prompt_path.read_text()

    from src.config import SUPPORTED_EXTENSIONS
    clip_files = sorted(
        [f for f in clips_dir.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS],
        key=lambda f: f.name,
    ) if clips_dir.exists() else []

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        def emit(event: str, data: dict):
            payload = json.dumps({"event": event, **data})
            queue.put_nowait(f"data: {payload}\n\n")

        async def run():
            try:
                if not clip_files:
                    emit("error", {"message": "No video clips found in clips directory"})
                    return

                client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                clip_analyses = []
                total = len(clip_files)

                emit("progress", {"message": f"Found {total} clips — starting analysis…"})
                await asyncio.sleep(0)  # yield so the first event flushes

                for idx, clip_file in enumerate(clip_files, 1):
                    filename = clip_file.name
                    stem = clip_file.stem

                    # Reuse cached thumbnail, or extract a new one (async subprocess)
                    thumb_path = thumbs / f"{stem}.jpg"
                    if not thumb_path.exists():
                        proc = await asyncio.create_subprocess_exec(
                            "ffmpeg", "-y", "-ss", "2", "-i", str(clip_file),
                            "-frames:v", "1", "-q:v", "2", str(thumb_path),
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        await proc.wait()

                    # Get duration (async subprocess)
                    probe = await asyncio.create_subprocess_exec(
                        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(clip_file),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    stdout, _ = await probe.communicate()
                    try:
                        duration = round(float(stdout.decode().strip()), 2)
                    except ValueError:
                        duration = 0.0

                    # Send to Claude Vision (awaited — non-blocking)
                    analysis = {
                        "description": "Analysis failed",
                        "content_type": "other",
                        "energy": "medium",
                        "lighting": "mixed",
                        "hook_score": 3,
                        "hook_reason": "Could not analyze",
                        "tags": [],
                    }
                    if thumb_path.exists():
                        try:
                            with open(str(thumb_path), "rb") as f:
                                image_data = base64.standard_b64encode(f.read()).decode("utf-8")
                            response = await client.messages.create(
                                model="claude-sonnet-4-6",
                                max_tokens=500,
                                messages=[{
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "image",
                                            "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data},
                                        },
                                        {"type": "text", "text": analyze_prompt},
                                    ],
                                }],
                            )
                            raw = response.content[0].text.strip()
                            if raw.startswith("```"):
                                raw = raw.split("```")[1]
                                if raw.startswith("json"):
                                    raw = raw[4:]
                                raw = raw.rsplit("```", 1)[0]
                            analysis = json.loads(raw)
                        except Exception as e:
                            emit("progress", {"message": f"  ⚠ Failed to analyse {filename}: {e}"})

                    clip_analyses.append({
                        "filename": filename,
                        "local_path": str(clip_file),
                        "duration_seconds": duration,
                        **analysis,
                    })
                    emit("progress", {"message": f"Analysed {filename} ({idx}/{total})"})

                # Build dynamic prompt and call planner (awaited)
                emit("progress", {"message": f"All {total} clips analysed — generating edit plan…"})
                await asyncio.sleep(0)
                planner_prompt = _build_plan_prompt(clip_analyses, cuts)

                response = await client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4000,
                    messages=[{"role": "user", "content": planner_prompt}],
                )
                raw = response.content[0].text.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.rsplit("```", 1)[0]

                try:
                    ai_plan = json.loads(raw)
                except json.JSONDecodeError as e:
                    emit("error", {"message": f"Claude returned invalid JSON for edit plan: {e}"})
                    return

                ai_cuts_by_id = {c["id"]: c for c in ai_plan.get("cuts", [])}

                updated_cuts = []
                for cut in cuts:
                    cid = cut["id"]
                    ai = ai_cuts_by_id.get(cid, {})
                    updated_cuts.append({
                        **cut,  # preserve label, hook, vibe, target_duration, transition
                        "clips": ai.get("clips", cut.get("clips", [])),
                        "trim":  ai.get("trim",  cut.get("trim",  {})),
                        # Only override transition if AI specified one and original is default
                        "transition": ai.get("transition", cut.get("transition", "cut")),
                    })

                plan["cuts"] = updated_cuts
                plan_path = _project_dir(project_id) / "plan.json"
                plan_path.write_text(json.dumps(plan, indent=2))

                emit("done", {"message": "Edit plan ready!", "plan": plan})

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


@app.post("/api/projects/{project_id}/plan")
def save_plan(project_id: str, req: SavePlanRequest):
    plan = _load_plan(project_id)
    existing_by_id = {c["id"]: c for c in plan.get("cuts", [])}

    updated = []
    for incoming in req.cuts:
        cut_id = incoming.get("id")
        base = existing_by_id.get(cut_id, {})
        updated.append({
            **base,
            "clips": incoming.get("clips", base.get("clips", [])),
            "trim":  incoming.get("trim",  base.get("trim",  {})),
            "transition": incoming.get("transition", base.get("transition", "cut")),
        })

    plan["cuts"] = updated
    (_project_dir(project_id) / "plan.json").write_text(json.dumps(plan, indent=2))
    # Return refreshed cuts so has_clips updates immediately
    return {"ok": True, "cuts": _cuts_with_scripts(project_id)}
