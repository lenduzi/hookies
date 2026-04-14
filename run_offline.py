#!/usr/bin/env python3
"""
Offline assembler — bypasses Claude API entirely.
Uses a hand-crafted edit plan based on visual inspection of all 25 clips.
Run: .venv/bin/python run_offline.py
Run (skip assembly, just VO): .venv/bin/python run_offline.py --vo-only
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from src.config import TEMP_DIR, OUTPUT_DIR
from src.assembler import assemble_cuts
from src.voiceover import generate_voiceover, mix_voiceover
from src.captioner import transcribe_audio, burn_captions

VO_ONLY = "--vo-only" in sys.argv
SKIP_VO = "--skip-vo" in sys.argv
CAPTIONS_ONLY = "--captions-only" in sys.argv
SKIP_CAPTIONS = "--skip-captions" in sys.argv
SCRIPTS_DIR = Path("voiceover_scripts")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

CLIPS_DIR = TEMP_DIR  # all clips are in ./tmp

def clip(filename):
    return {"filename": filename, "local_path": os.path.join(CLIPS_DIR, filename)}

# Minimal clip_analyses — assembler only needs filename + local_path
clip_analyses = [
    clip("IMG_6626.MOV"),  # Turmbar exterior sign
    clip("IMG_6636.MOV"),  # Bitters bottles + "Gute Zeit gehabt?" sign
    clip("IMG_6637.MOV"),  # Guests watching instructor
    clip("IMG_6638.MOV"),  # Instructor explaining (13s)
    clip("IMG_6639.MOV"),  # Moody bar setup low angle
    clip("IMG_6640.MOV"),  # Bar setup different angle
    clip("IMG_6642.MOV"),  # Instructor expressive/surprised face
    clip("IMG_6650.MOV"),  # Close-up hand pouring into glass
    clip("IMG_6655.MOV"),  # Beautiful finished cocktail
    clip("IMG_6656.MOV"),  # Same cocktail slightly different angle
    clip("IMG_6657.MOV"),  # Wide shot cocktail + bar
    clip("IMG_6661.MOV"),  # Multiple cocktails on table
    clip("IMG_6665.MOV"),  # Instructor pouring dynamically (8.6s)
    clip("IMG_6666.MOV"),  # BLOWTORCH moment (11.8s)
    clip("IMG_6668.MOV"),  # Two coupe glasses on bar
    clip("IMG_6682.MOV"),  # Main class footage (166s)
    clip("IMG_6683.MOV"),  # Green-lit circular venue interior
    clip("IMG_6685.MOV"),  # Green-lit venue, wider angle
    clip("IMG_6686.MOV"),  # Backlit spirits bottle shelf
    clip("IMG_6693.MOV"),  # Woman concentrating, pouring
    clip("IMG_6699.MOV"),  # Woman holding beautiful finished cocktail (9.8s)
    clip("IMG_6706.MOV"),  # Bartender mixing, atmospheric
    clip("IMG_6712.MOV"),  # Multiple cocktails, venue in background (16s)
    clip("IMG_6717.MOV"),  # Elegant garnished cocktail held, long nails (5.8s)
    clip("IMG_6722.MOV"),  # Table spread of finished cocktails (7.9s)
]

plan = {
    "cuts": [
        {
            "id": "cut_1",
            "name": "i_didnt_know_i_could_do_this",
            "hook": "Close-up of hands pouring, uncertain and focused — builds to the beautiful finished result",
            "vibe": "Soft, personal, aspirational — the surprise of discovering you can do this",
            "target_duration": 30,
            "transition": "fade",
            "clips": [
                "IMG_6650.MOV",  # Hand pouring into glass — intimate opener
                "IMG_6693.MOV",  # Woman concentrating while pouring — relatable
                "IMG_6682.MOV",  # Main class footage — the learning moment
                "IMG_6699.MOV",  # Woman holding her finished cocktail — the payoff
                "IMG_6717.MOV",  # Elegant garnished cocktail — money shot close
            ],
            "trim": {
                "IMG_6650.MOV": {"start": 0, "end": 2.8},
                "IMG_6693.MOV": {"start": 0, "end": 4},
                "IMG_6682.MOV": {"start": 50, "end": 60},
                "IMG_6699.MOV": {"start": 0, "end": 8},
                "IMG_6717.MOV": {"start": 0, "end": 5},
            },
        },
        {
            "id": "cut_2",
            "name": "hamburgs_most_underrated_evening",
            "hook": "Stunning green-lit circular venue interior — immediate FOMO — then moody bar, action, blowtorch",
            "vibe": "High energy FOMO — this venue is unreal and you're missing it",
            "target_duration": 30,
            "transition": "cut",
            "clips": [
                "IMG_6683.MOV",  # Green-lit venue interior — jaw-drop opener
                "IMG_6626.MOV",  # Exterior Turmbar sign — context
                "IMG_6686.MOV",  # Backlit bottles — atmosphere
                "IMG_6666.MOV",  # BLOWTORCH — dramatic, high energy
                "IMG_6665.MOV",  # Instructor pouring — action
                "IMG_6642.MOV",  # Instructor expressive face — personality
                "IMG_6661.MOV",  # Multiple cocktails — result
            ],
            "trim": {
                "IMG_6683.MOV": {"start": 0, "end": 2.1},
                "IMG_6626.MOV": {"start": 0, "end": 3.7},
                "IMG_6686.MOV": {"start": 0, "end": 2.6},
                "IMG_6666.MOV": {"start": 0, "end": 8},
                "IMG_6665.MOV": {"start": 0, "end": 6},
                "IMG_6642.MOV": {"start": 0, "end": 4},
                "IMG_6661.MOV": {"start": 0, "end": 1.8},
            },
        },
        {
            "id": "cut_3",
            "name": "what_they_dont_tell_you",
            "hook": "Guests watching the instructor — immediately relatable 'student' energy",
            "vibe": "Conversational, curious, self-deprecating — list format with a delicious payoff",
            "target_duration": 30,
            "transition": "cut",
            "clips": [
                "IMG_6637.MOV",  # Guests watching — 'we're all students here'
                "IMG_6638.MOV",  # Instructor explaining — the knowledge drop
                "IMG_6636.MOV",  # Bitters + "Gute Zeit gehabt?" sign — quirky
                "IMG_6640.MOV",  # Moody bar setup — atmosphere
                "IMG_6655.MOV",  # Beautiful finished cocktail — 'number three'
                "IMG_6656.MOV",  # Same cocktail, different angle
                "IMG_6722.MOV",  # Table full of drinks — the happy ending
            ],
            "trim": {
                "IMG_6637.MOV": {"start": 0, "end": 2},
                "IMG_6638.MOV": {"start": 2, "end": 10},
                "IMG_6636.MOV": {"start": 0, "end": 3.2},
                "IMG_6640.MOV": {"start": 0, "end": 2.9},
                "IMG_6655.MOV": {"start": 0, "end": 2.9},
                "IMG_6656.MOV": {"start": 0, "end": 2.4},
                "IMG_6722.MOV": {"start": 0, "end": 6},
            },
        },
    ]
}

print("\n🎬 Offline Assembly — Turmbar Hamburg")
print("=" * 40)

# Step 1: Assemble video cuts
if not VO_ONLY:
    print("Skipping Claude API — using hand-crafted plan from visual clip review\n")
    output_paths = assemble_cuts(plan, clip_analyses)
else:
    # Re-use already assembled videos
    output_paths = sorted([
        str(p) for p in Path(OUTPUT_DIR).glob("cut_*.mp4")
        if "_vo" not in p.name
    ])
    print(f"↩ Skipping assembly — using {len(output_paths)} existing cuts\n")

if not output_paths:
    print("❌ No assembled cuts found. Run without --vo-only first.")
    sys.exit(1)

# Step 2: Generate voiceovers + mix
if not SKIP_VO:
    print("\n🎙 Generating voiceovers with ElevenLabs...")

    # Map cut name → script file
    script_map = {p.stem: p for p in SCRIPTS_DIR.glob("*.txt")}

    final_paths = []
    for video_path in output_paths:
        cut_name = Path(video_path).stem  # e.g. cut_1_i_didnt_know_i_could_do_this

        # Find matching script
        script_file = script_map.get(cut_name)
        if not script_file:
            print(f"  ⚠ No script found for {cut_name} — skipping VO")
            final_paths.append(video_path)
            continue

        script_text = script_file.read_text().strip()
        vo_path = os.path.join(OUTPUT_DIR, f"{cut_name}_vo.mp3")
        final_path = os.path.join(OUTPUT_DIR, f"{cut_name}_vo.mp4")

        print(f"\n  🎙 {cut_name}")
        print(f"     Generating VO...")
        generate_voiceover(script_text, vo_path)
        vo_size = os.path.getsize(vo_path) / 1024
        print(f"     VO saved ({vo_size:.0f} KB) — mixing onto video...")
        mix_voiceover(video_path, vo_path, final_path)
        size_mb = os.path.getsize(final_path) / (1024 * 1024)
        print(f"     ✅ {os.path.basename(final_path)} ({size_mb:.1f} MB)")
        final_paths.append(final_path)
else:
    final_paths = output_paths

# Step 3: Captions
if not SKIP_CAPTIONS:
    print("\n📝 Generating captions with Whisper...")

    captioned_paths = []
    for video_path in final_paths:
        stem = Path(video_path).stem  # e.g. cut_1_..._vo
        # Find the matching VO mp3
        vo_mp3 = os.path.join(OUTPUT_DIR, f"{stem.replace('_vo', '')}_vo.mp3")

        if not os.path.exists(vo_mp3):
            print(f"  ⚠ No VO audio found for {stem} — skipping captions")
            captioned_paths.append(video_path)
            continue

        final_captioned = os.path.join(OUTPUT_DIR, f"{stem}_cap.mp4")

        print(f"\n  📝 {stem}")
        print(f"     Transcribing VO with Whisper...")
        words = transcribe_audio(vo_mp3)
        print(f"     Got {len(words)} words — burning captions into video...")
        burn_captions(video_path, words, final_captioned)
        size_mb = os.path.getsize(final_captioned) / (1024 * 1024)
        print(f"     ✅ {os.path.basename(final_captioned)} ({size_mb:.1f} MB)")
        captioned_paths.append(final_captioned)
else:
    captioned_paths = final_paths

print(f"\n{'=' * 40}")
print(f"✅ Done — {len(captioned_paths)} cuts ready in ./{OUTPUT_DIR}/")
for path in captioned_paths:
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"   • {os.path.basename(path)} ({size_mb:.1f} MB)")
print()
