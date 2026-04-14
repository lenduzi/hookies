"""
Planner — sends all clip analyses to Claude and gets back
3–4 structured edit plans with distinct vibes and viral hooks.
"""

import json
from pathlib import Path

import anthropic

from src.config import ANTHROPIC_API_KEY, NUM_CUTS, TARGET_DURATIONS


def _load_prompt(clip_analyses: list[dict]) -> str:
    prompt_path = Path(__file__).parent.parent / "prompts" / "plan_edits.md"
    template = prompt_path.read_text()

    durations_str = ", ".join(str(d) for d in TARGET_DURATIONS)

    return (
        template
        .replace("{NUM_CUTS}", str(NUM_CUTS))
        .replace("{TARGET_DURATIONS}", durations_str)
        .replace("{CLIP_ANALYSES}", json.dumps(clip_analyses, indent=2))
    )


def plan_edits(clip_analyses: list[dict]) -> dict:
    """
    Ask Claude to generate NUM_CUTS distinct edit plans.
    Returns a dict with a 'cuts' list.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _load_prompt(clip_analyses)

    print(f"\n🎬 Planning {NUM_CUTS} distinct edits with Claude...")

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]

    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON for edit plan: {e}\n\nRaw response:\n{raw}")

    cuts = plan.get("cuts", [])
    print(f"✅ Got {len(cuts)} edit plans:")
    for cut in cuts:
        print(f"   • {cut['name']}: {cut['hook']}")

    return plan
