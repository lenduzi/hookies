#!/usr/bin/env python3
"""
UGC Cut Generator
-----------------
Transform a folder of raw UGC clips into multiple distinct, ready-to-post video edits.

Usage:
  python main.py --source drive --folder-url "https://drive.google.com/drive/folders/ABC123"
  python main.py --source local --folder-path ./my_clips
"""

import argparse
import json
import os
import shutil
import sys
import time

from src import config
from src.config import TEMP_DIR, OUTPUT_DIR
from src.drive_client import download_folder, get_local_clips
from src.analyzer import analyze_clips
from src.planner import plan_edits
from src.assembler import assemble_cuts


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate multiple viral video cuts from raw UGC clips."
    )
    parser.add_argument(
        "--source",
        choices=["drive", "local"],
        required=True,
        help="Where to load clips from: 'drive' or 'local'",
    )
    parser.add_argument(
        "--folder-url",
        help="Google Drive folder URL (required if --source=drive)",
    )
    parser.add_argument(
        "--folder-path",
        help="Local folder path (required if --source=local)",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip downloading and reuse clips already in TEMP_DIR",
    )
    parser.add_argument(
        "--save-plan",
        action="store_true",
        help="Save the Claude edit plan to output/edit_plan.json",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temp files after run (useful for debugging)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    start_time = time.time()

    print("\n🎬 UGC Cut Generator")
    print("=" * 40)

    # Validate config
    try:
        config.validate()
    except EnvironmentError as e:
        print(f"\n❌ Config error: {e}")
        sys.exit(1)

    # Step 1: Get clips
    if args.source == "drive":
        if not args.folder_url:
            print("❌ --folder-url is required when --source=drive")
            sys.exit(1)
        if args.skip_download:
            from pathlib import Path
            from src.config import SUPPORTED_EXTENSIONS
            clip_paths = [
                str(f) for f in Path(TEMP_DIR).iterdir()
                if f.suffix.lower() in SUPPORTED_EXTENSIONS
            ]
            print(f"↩ Skipping download, using {len(clip_paths)} cached clips from {TEMP_DIR}")
        else:
            clip_paths = download_folder(args.folder_url)
    else:
        if not args.folder_path:
            print("❌ --folder-path is required when --source=local")
            sys.exit(1)
        clip_paths = get_local_clips(args.folder_path)

    if not clip_paths:
        print("❌ No clips found. Exiting.")
        sys.exit(1)

    # Step 2: Analyze clips with Claude Vision
    clip_analyses = analyze_clips(clip_paths)

    # Step 3: Plan edits with Claude
    plan = plan_edits(clip_analyses)

    # Optionally save the plan
    if args.save_plan:
        plan_path = os.path.join(OUTPUT_DIR, "edit_plan.json")
        with open(plan_path, "w") as f:
            json.dump({"analyses": clip_analyses, "plan": plan}, f, indent=2)
        print(f"\n💾 Edit plan saved to {plan_path}")

    # Step 4: Assemble cuts with FFmpeg
    output_paths = assemble_cuts(plan, clip_analyses)

    # Cleanup temp files
    if not args.keep_temp:
        # Only remove extracted frames and segments, not downloaded clips
        for f in os.listdir(TEMP_DIR):
            if f.endswith("_frame.jpg") or "_seg" in f or f == "concat_list.txt":
                os.remove(os.path.join(TEMP_DIR, f))

    elapsed = time.time() - start_time
    print(f"\n{'=' * 40}")
    print(f"✅ Done in {elapsed:.0f}s — {len(output_paths)} cuts ready in ./{OUTPUT_DIR}/")
    for path in output_paths:
        print(f"   • {os.path.basename(path)}")
    print()


if __name__ == "__main__":
    main()
