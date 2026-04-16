#!/usr/bin/env python3
"""
Project-aware pipeline runner.
Usage:
  .venv/bin/python run_offline.py --project turmbar-hamburg
  .venv/bin/python run_offline.py --project fairgrapes-wein --skip-download
  .venv/bin/python run_offline.py --project turmbar-hamburg --vo-only
  .venv/bin/python run_offline.py --project turmbar-hamburg --skip-vo
  .venv/bin/python run_offline.py --project turmbar-hamburg --skip-captions
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from src.assembler import assemble_cuts
from src.voiceover import generate_voiceover, mix_voiceover
from src.captioner import transcribe_audio, burn_captions

# ── Args ──────────────────────────────────────────────────────────────────────
def _arg(flag):
    try:
        return sys.argv[sys.argv.index(flag) + 1]
    except (ValueError, IndexError):
        return None

PROJECT_ID     = _arg("--project") or "turmbar-hamburg"
VO_ONLY        = "--vo-only"        in sys.argv
SKIP_VO        = "--skip-vo"        in sys.argv
SKIP_CAPTIONS  = "--skip-captions"  in sys.argv
SKIP_DOWNLOAD  = "--skip-download"  in sys.argv
CAPTION_STYLE  = _arg("--caption-style") or "classic"

# ── Project paths ─────────────────────────────────────────────────────────────
PROJECT_DIR = Path("projects") / PROJECT_ID

if not PROJECT_DIR.exists():
    print(f"❌ Project '{PROJECT_ID}' not found in ./projects/")
    sys.exit(1)

meta      = json.loads((PROJECT_DIR / "meta.json").read_text())
plan_data = json.loads((PROJECT_DIR / "plan.json").read_text())

CLIPS_DIR   = Path(meta.get("clips_dir", str(PROJECT_DIR / "clips")))
SCRIPTS_DIR = PROJECT_DIR / "scripts"
OUTPUT_DIR  = PROJECT_DIR / "output"

CLIPS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"\n🎬 Hookies — {meta['name']}")
print("=" * 40)

# ── Step 0: Download from Google Drive if configured ─────────────────────────
drive_url = meta.get("drive_url", "").strip()

if drive_url and not VO_ONLY:
    # Drive projects always download into projects/{id}/clips/
    drive_clips_dir = PROJECT_DIR / "clips"
    drive_clips_dir.mkdir(exist_ok=True)
    CLIPS_DIR = drive_clips_dir  # override so assembler uses the right folder

    if SKIP_DOWNLOAD:
        existing = list(CLIPS_DIR.iterdir())
        print(f"↩ Skipping download — {len(existing)} clips already in {CLIPS_DIR}")
    else:
        print(f"☁️  Downloading clips from Google Drive...")
        try:
            from src.drive_client import download_folder
            download_folder(drive_url, dest_dir=str(CLIPS_DIR))
        except Exception as e:
            print(f"❌ Drive download failed: {e}")
            sys.exit(1)

# ── Build clip_analyses from plan ─────────────────────────────────────────────
seen = {}
for cut in plan_data["cuts"]:
    for filename in cut.get("clips", []):
        if filename not in seen:
            seen[filename] = {
                "filename": filename,
                "local_path": str(CLIPS_DIR / filename),
            }

clip_analyses = list(seen.values())

# ── Step 1: Assemble ──────────────────────────────────────────────────────────
if not VO_ONLY:
    print(f"\nAssembling cuts from plan.json...")
    output_paths = assemble_cuts(plan_data, clip_analyses, output_dir=str(OUTPUT_DIR))
else:
    output_paths = sorted([
        str(p) for p in OUTPUT_DIR.glob("cut_*.mp4")
        if "_vo" not in p.name
    ])
    print(f"↩ Skipping assembly — using {len(output_paths)} existing cuts")

if not output_paths:
    if not VO_ONLY:
        print("❌ No cuts assembled — check that your plan.json has clips configured.")
    else:
        print("❌ No assembled cuts found. Run without --vo-only first.")
    sys.exit(1)

# ── Step 2: Voiceover ─────────────────────────────────────────────────────────
if not SKIP_VO:
    print("\n🎙 Generating voiceovers...")
    script_map = {p.stem: p for p in SCRIPTS_DIR.glob("*.txt")}
    final_paths = []

    for video_path in output_paths:
        cut_name = Path(video_path).stem
        script_file = script_map.get(cut_name)
        if not script_file:
            print(f"  ⚠ No script for {cut_name} — skipping VO")
            final_paths.append(video_path)
            continue

        script_text = script_file.read_text().strip()
        vo_path    = str(OUTPUT_DIR / f"{cut_name}_vo.mp3")
        final_path = str(OUTPUT_DIR / f"{cut_name}_vo.mp4")

        print(f"\n  🎙 {cut_name}")
        generate_voiceover(script_text, vo_path)
        print(f"     VO saved — mixing onto video...")
        mix_voiceover(video_path, vo_path, final_path)
        size_mb = os.path.getsize(final_path) / (1024 * 1024)
        print(f"     ✅ {Path(final_path).name} ({size_mb:.1f} MB)")
        final_paths.append(final_path)
else:
    final_paths = output_paths

# ── Step 3: Captions ──────────────────────────────────────────────────────────
if not SKIP_CAPTIONS:
    print("\n📝 Generating captions with Whisper...")
    captioned_paths = []

    for video_path in final_paths:
        stem = Path(video_path).stem
        vo_mp3 = str(OUTPUT_DIR / f"{stem.replace('_vo', '')}_vo.mp3")

        if not os.path.exists(vo_mp3):
            print(f"  ⚠ No VO audio for {stem} — skipping captions")
            captioned_paths.append(video_path)
            continue

        final_captioned = str(OUTPUT_DIR / f"{stem}_cap.mp4")

        print(f"\n  📝 {stem}")
        words = transcribe_audio(vo_mp3)
        print(f"     {len(words)} words — burning captions ({CAPTION_STYLE} style)...")
        project_key_words = meta.get("key_words") or None
        burn_captions(video_path, words, final_captioned,
                      style=CAPTION_STYLE, key_words=project_key_words)
        size_mb = os.path.getsize(final_captioned) / (1024 * 1024)
        print(f"     ✅ {Path(final_captioned).name} ({size_mb:.1f} MB)")
        captioned_paths.append(final_captioned)
else:
    captioned_paths = final_paths

# ── Done ──────────────────────────────────────────────────────────────────────
print(f"\n{'=' * 40}")
print(f"✅ Done — {len(captioned_paths)} cuts ready in {OUTPUT_DIR}/")
for path in captioned_paths:
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"   • {Path(path).name} ({size_mb:.1f} MB)")
print()
