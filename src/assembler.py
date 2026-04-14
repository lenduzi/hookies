"""
Assembler — takes edit plans and uses FFmpeg to stitch clips into final MP4s.
Handles reframing, trimming, and transitions.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from src.config import OUTPUT_DIR, OUTPUT_FORMAT, FORMAT_FILTERS, TEMP_DIR


def _get_clip_path(filename: str, clip_analyses: list[dict]) -> str:
    """Look up the local path for a clip by filename."""
    for clip in clip_analyses:
        if clip["filename"] == filename:
            return clip["local_path"]
    raise FileNotFoundError(f"Clip not found in analyses: {filename}")


def _prepare_clip(clip_path: str, start: float, end: float, index: int, cut_name: str) -> str:
    """
    Trim and reframe a single clip. Returns path to the prepared segment.
    """
    out_path = os.path.join(TEMP_DIR, f"{cut_name}_seg{index:02d}.mp4")
    vf_filter = FORMAT_FILTERS[OUTPUT_FORMAT]
    duration = end - start

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", clip_path,
            "-t", str(duration),
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-an",  # drop audio for now — add music layer separately if desired
            "-r", "30",
            out_path,
        ],
        capture_output=True,
        check=True,
    )
    return out_path


def _concatenate_clips(segment_paths: list[str], output_path: str, transition: str) -> None:
    """
    Concatenate prepared segments into a single MP4.
    Supports 'cut' (hard cut) and 'fade' transitions.
    """
    if transition == "cut":
        # Simple concat demuxer — fastest
        list_file = os.path.join(TEMP_DIR, "concat_list.txt")
        with open(list_file, "w") as f:
            for seg in segment_paths:
                f.write(f"file '{os.path.abspath(seg)}'\n")

        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", list_file, "-c", "copy", output_path],
            capture_output=True,
            check=True,
        )
    else:
        # Fade transition using xfade filter
        # Build a chain: [0][1]xfade, [result][2]xfade, etc.
        n = len(segment_paths)
        if n == 1:
            subprocess.run(
                ["ffmpeg", "-y", "-i", segment_paths[0], "-c", "copy", output_path],
                capture_output=True, check=True
            )
            return

        inputs = []
        for seg in segment_paths:
            inputs += ["-i", seg]

        # Build xfade filter chain
        fade_dur = 0.5
        filter_parts = []
        prev = "0:v"
        offset = 0.0

        for i in range(1, n):
            # Get duration of previous segment to calculate offset
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", segment_paths[i - 1]],
                capture_output=True, text=True
            )
            try:
                seg_dur = float(probe.stdout.strip())
            except ValueError:
                seg_dur = 3.0
            offset += seg_dur - fade_dur

            out_label = f"v{i}" if i < n - 1 else "vout"
            filter_parts.append(
                f"[{prev}][{i}:v]xfade=transition=fade:duration={fade_dur}:offset={offset:.2f}[{out_label}]"
            )
            prev = out_label
            offset -= fade_dur  # account for overlap

        filter_complex = ";".join(filter_parts)

        subprocess.run(
            ["ffmpeg", "-y"] + inputs + [
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                output_path,
            ],
            capture_output=True,
            check=True,
        )


def assemble_cuts(plan: dict, clip_analyses: list[dict]) -> list[str]:
    """
    Assemble all cuts from the plan. Returns list of output file paths.
    """
    output_paths = []
    cuts = plan.get("cuts", [])

    print(f"\n✂️  Assembling {len(cuts)} cuts with FFmpeg...")

    for cut in cuts:
        cut_name = cut["name"]
        transition = cut.get("transition", "cut")
        clips_order = cut["clips"]
        trim_map = cut.get("trim", {})

        print(f"\n  📹 Building: {cut_name}")
        print(f"     Hook: {cut['hook']}")
        print(f"     Vibe: {cut['vibe']}")
        print(f"     Clips: {' → '.join(clips_order)}")

        segment_paths = []
        for i, filename in enumerate(clips_order):
            clip_path = _get_clip_path(filename, clip_analyses)
            trim = trim_map.get(filename, {})
            start = trim.get("start", 0)

            # Default end: use full clip if not specified
            if "end" not in trim:
                probe = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", clip_path],
                    capture_output=True, text=True
                )
                try:
                    end = float(probe.stdout.strip())
                except ValueError:
                    end = start + 5
            else:
                end = trim["end"]

            seg_path = _prepare_clip(clip_path, start, end, i, cut_name)
            segment_paths.append(seg_path)

        output_filename = f"{cut['id']}_{cut_name}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        _concatenate_clips(segment_paths, output_path, transition)

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"     ✅ Saved: {output_filename} ({size_mb:.1f} MB)")
        output_paths.append(output_path)

    return output_paths
