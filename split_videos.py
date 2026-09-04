#!/usr/bin/env python3
"""
Video Splitter — Automatically convert videos to vertical (9:16) format
with centered framing, black letterboxing, and part text overlays,
then split into fixed-length clips using direct single-pass FFmpeg encoding.

Supports videos of any length without temporary files or disk limits.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — edit these values to customise behaviour
# ─────────────────────────────────────────────────────────────────────────────

# Duration of each clip in seconds (e.g. 60 = 1 minute)
CLIP_DURATION: int = 60

# Folder containing source videos (relative to this script)
VIDEOS_DIR: str = "videos"

# Folder where clips will be written (relative to this script)
OUTPUT_DIR: str = "output"

# Supported video file extensions
SUPPORTED_EXTENSIONS: set[str] = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# Vertical frame output resolution (width x height)
VERTICAL_WIDTH: int = 1080
VERTICAL_HEIGHT: int = 1920

# Video encoding quality (CRF: 0 = lossless, 23 = default, 51 = worst)
CRF_QUALITY: int = 18

# Encoding preset (ultrafast, superfast, veryfast, faster, fast, medium, slow)
# Note: veryfast guarantees H.264 High Profile with B-frames for full Instagram web compatibility
ENCODING_PRESET: str = "veryfast"

# Add text overlay to clips (e.g. "Part 1", "Part 2")
ADD_PART_TEXT: bool = True
TEXT_FONT: str = "/System/Library/Fonts/Avenir Next.ttc"
TEXT_COLOR: str = "white"
TEXT_SIZE: int = 72

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _log(message: str, *, indent: int = 0) -> None:
    """Print a timestamped, optionally indented log line."""
    prefix = "  " * indent
    print(f"{prefix}{message}", flush=True)


def _log_separator() -> None:
    """Print a visual separator."""
    print("─" * 60, flush=True)


def check_ffmpeg() -> bool:
    """Return True if ffmpeg and ffprobe are available on PATH."""
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            _log(f"✖  '{tool}' was not found on your PATH.")
            _log(f"   Please install FFmpeg: https://ffmpeg.org/download.html")
            return False
    return True


def get_video_info(video_path: Path) -> dict | None:
    """Use ffprobe to get duration, width, and height of a video file."""
    cmd: list[str] = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            _log(f"⚠  ffprobe returned non-zero exit code for '{video_path.name}'", indent=1)
            return None

        data: dict = json.loads(result.stdout)
        duration_str: str | None = data.get("format", {}).get("duration")
        if duration_str is None:
            _log(f"⚠  Could not read duration from '{video_path.name}'", indent=1)
            return None

        width: int | None = None
        height: int | None = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = int(stream.get("width", 0))
                height = int(stream.get("height", 0))
                break

        if not width or not height:
            _log(f"⚠  Could not read dimensions from '{video_path.name}'", indent=1)
            return None

        return {
            "duration": float(duration_str),
            "width": width,
            "height": height,
        }
    except Exception as exc:
        _log(f"⚠  Error probing video '{video_path.name}': {exc}", indent=1)
        return None


def format_duration(seconds: float) -> str:
    """Format a duration in seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def discover_videos(videos_dir: Path) -> list[Path]:
    """Scan videos_dir for supported video files."""
    if not videos_dir.is_dir():
        _log(f"✖  Videos directory not found: {videos_dir}")
        return []
    return [
        entry for entry in sorted(videos_dir.iterdir())
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def build_filtergraph(
    part_number: int,
    out_width: int = VERTICAL_WIDTH,
    out_height: int = VERTICAL_HEIGHT,
) -> str:
    """Build single-pass vertical scaling, padding, and text overlay filter with strict SAR 1:1."""
    filters = [
        "setpts=PTS-STARTPTS",
        f"scale={out_width}:-2",
        "setsar=1",
        f"pad={out_width}:{out_height}:(ow-iw)/2:(oh-ih)/2:black",
        "format=yuv420p",
    ]

    if ADD_PART_TEXT and Path(TEXT_FONT).exists():
        part_text = f"Part {part_number}"
        text_filter = (
            f"drawtext=fontfile='{TEXT_FONT}':text='{part_text}':"
            f"fontcolor={TEXT_COLOR}:fontsize={TEXT_SIZE}:"
            f"x=(w-text_w)/2:y=520:"
            f"shadowcolor=black:shadowx=4:shadowy=4"
        )
        filters.append(text_filter)

    return ",".join(filters)


def is_valid_clip(clip_path: Path) -> bool:
    """Check if clip exists, is healthy, has standard SAR 1:1, and High/Main profile."""
    if not clip_path.exists() or clip_path.stat().st_size < 50000:
        return False
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=sample_aspect_ratio,profile",
            "-of", "default=noprint_wrappers=1",
            str(clip_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            return False
        
        sar_ok = False
        profile_ok = False
        for line in res.stdout.strip().splitlines():
            if line.startswith("sample_aspect_ratio="):
                sar = line.split("=", 1)[1].strip()
                sar_ok = sar in ("1:1", "")
            elif line.startswith("profile="):
                prof = line.split("=", 1)[1].strip().lower()
                profile_ok = ("high" in prof or "main" in prof)
        return sar_ok and profile_ok
    except Exception:
        return False


def process_video(
    video_path: Path,
    output_folder: Path,
    clip_duration: int = CLIP_DURATION,
) -> int:
    """
    Split video_path into 9:16 vertical clips of clip_duration seconds.
    Direct single-pass encoding: scalable to any length with fast seek and resume.
    """
    video_info = get_video_info(video_path)
    if video_info is None or video_info["duration"] <= 0:
        _log(f"⚠ Skipping — could not determine video duration.", indent=1)
        return 0

    duration = video_info["duration"]
    expected_clips: int = math.ceil(duration / clip_duration)

    _log(f"Source   : {video_info['width']}x{video_info['height']} | Duration: {format_duration(duration)} ({duration:.1f}s)", indent=1)
    _log(f"Target   : {expected_clips} vertical clip(s) @ {clip_duration}s each", indent=1)
    _log(f"Output   : {output_folder}", indent=1)

    output_folder.mkdir(parents=True, exist_ok=True)
    clips_done = 0
    start_time = time.monotonic()

    for i in range(expected_clips):
        part_num = i + 1
        clip_name = f"clip_{part_num:03d}.mp4"
        clip_path = output_folder / clip_name
        start_sec = i * clip_duration

        # Resume support: skip if clip already exists and has valid SAR 1:1
        if is_valid_clip(clip_path):
            clips_done += 1
            print(f"\r  [{part_num}/{expected_clips}] {clip_name} (already verified 1:1) ✓", end="", flush=True)
            continue

        filtergraph = build_filtergraph(part_num)

        cmd: list[str] = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(start_sec),
            "-i", str(video_path),
            "-t", str(clip_duration),
            "-vf", filtergraph,
            "-af", "asetpts=PTS-STARTPTS",
            "-c:v", "libx264",
            "-preset", ENCODING_PRESET,
            "-profile:v", "high",
            "-level", "4.1",
            "-crf", str(CRF_QUALITY),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-avoid_negative_ts", "make_zero",
            "-y",
            str(clip_path),
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0 and clip_path.exists() and clip_path.stat().st_size > 50000:
                clips_done += 1
                print(f"\r  [{part_num}/{expected_clips}] {clip_name} ✓", end="", flush=True)
            else:
                print()
                _log(f"⚠ Failed to create {clip_name}", indent=1)
                if res.stderr.strip():
                    _log(f"  FFmpeg: {res.stderr.strip()[:200]}", indent=2)
        except Exception as exc:
            print()
            _log(f"⚠ Error creating {clip_name}: {exc}", indent=1)

    print()
    elapsed = time.monotonic() - start_time
    _log(f"Generated: {clips_done}/{expected_clips} clip(s) in {elapsed:.1f}s", indent=1)
    return clips_done


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    _log_separator()
    _log("🎬  Video Splitter — Direct Single-Pass Vertical Engine")
    _log(f"    Clip duration   : {CLIP_DURATION}s")
    _log(f"    Vertical frame  : {VERTICAL_WIDTH}x{VERTICAL_HEIGHT} (9:16)")
    _log(f"    Preset/CRF      : {ENCODING_PRESET} (CRF {CRF_QUALITY})")
    _log(f"    Output format   : yuv420p + faststart (Instagram web compatible)")
    _log_separator()

    if not check_ffmpeg():
        sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    videos_dir = script_dir / VIDEOS_DIR
    output_dir = script_dir / OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    videos = discover_videos(videos_dir)
    if not videos:
        _log(f"✖ No video files found in {videos_dir}/")
        sys.exit(0)

    _log(f"Found {len(videos)} video(s) to process\n")

    total_clips = 0
    for idx, video_path in enumerate(videos, start=1):
        video_output = output_dir / video_path.stem
        _log_separator()
        _log(f"[{idx}/{len(videos)}] Processing: {video_path.name}")
        clips = process_video(video_path, video_output)
        total_clips += clips

    _log_separator()
    _log(f"✅ Finished! Total clips ready across all videos: {total_clips}")
    _log_separator()


if __name__ == "__main__":
    main()
