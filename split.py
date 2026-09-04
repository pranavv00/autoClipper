#!/usr/bin/env python3
"""
Video Splitter — Automatically split videos into fixed-length clips using FFmpeg.

===================================================================================
SETUP INSTRUCTIONS
===================================================================================

1. Install Python 3.11 or later:
       https://www.python.org/downloads/

2. Install FFmpeg:

   macOS (Homebrew):
       brew install ffmpeg

   Ubuntu / Debian:
       sudo apt update && sudo apt install ffmpeg

   Windows (Chocolatey):
       choco install ffmpeg

   Or download from: https://ffmpeg.org/download.html

3. Place your video files into the "videos/" folder (next to this script).
   Supported formats: .mp4, .mov, .mkv, .avi, .webm

4. (Optional) Edit CLIP_DURATION below to change the clip length in seconds.

5. Run the script:
       python split_videos.py

6. Clips appear in the "output/<video_name>/" folders.

===================================================================================
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

# Duration of each clip in seconds (e.g. 60 = 1 minute, 30 = 30 seconds)
CLIP_DURATION: int = 60

# Folder containing source videos (relative to this script)
VIDEOS_DIR: str = "videos"

# Folder where clips will be written (relative to this script)
OUTPUT_DIR: str = "output"

# Supported video file extensions
SUPPORTED_EXTENSIONS: set[str] = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# Add text overlay to clips (e.g. "Part 1", "Part 2")
ADD_PART_TEXT: bool = True
TEXT_FONT: str = "/System/Library/Fonts/Avenir Next.ttc"
TEXT_COLOR: str = "white"
TEXT_SIZE: int = 72
CRF_QUALITY: int = 18
ENCODING_PRESET: str = "ultrafast"

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _log(message: str, *, indent: int = 0) -> None:
    """Print a timestamped, optionally indented log line."""
    prefix = "  " * indent
    print(f"{prefix}{message}")


def _log_separator() -> None:
    """Print a visual separator."""
    print("─" * 60)


def check_ffmpeg() -> bool:
    """Return True if ffmpeg and ffprobe are available on PATH."""
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            _log(f"✖  '{tool}' was not found on your PATH.")
            _log(f"   Please install FFmpeg: https://ffmpeg.org/download.html")
            return False
    return True


def get_video_duration(video_path: Path) -> float | None:
    """
    Use ffprobe to get the duration of a video file in seconds.

    Returns None if the duration cannot be determined.
    """
    cmd: list[str] = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(video_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            _log(f"⚠  ffprobe returned non-zero exit code for '{video_path.name}'", indent=1)
            return None

        data: dict = json.loads(result.stdout)
        duration_str: str | None = data.get("format", {}).get("duration")

        if duration_str is None:
            _log(f"⚠  Could not read duration from '{video_path.name}'", indent=1)
            return None

        return float(duration_str)

    except subprocess.TimeoutExpired:
        _log(f"⚠  ffprobe timed out for '{video_path.name}'", indent=1)
        return None
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        _log(f"⚠  Error parsing ffprobe output for '{video_path.name}': {exc}", indent=1)
        return None


def format_duration(seconds: float) -> str:
    """Format a duration in seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def discover_videos(videos_dir: Path) -> list[Path]:
    """
    Scan *videos_dir* for files with supported extensions.

    Returns a sorted list of Paths.
    """
    found: list[Path] = []

    if not videos_dir.is_dir():
        _log(f"✖  Videos directory not found: {videos_dir}")
        return found

    for entry in sorted(videos_dir.iterdir()):
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
            found.append(entry)

    return found


def is_already_processed(output_folder: Path) -> bool:
    """
    Return True if *output_folder* exists and already contains at least one
    clip file, indicating that this video has been processed previously.
    """
    if not output_folder.is_dir():
        return False

    # Check for any video files inside
    for child in output_folder.iterdir():
        if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
            return True

    return False


def split_video(
    video_path: Path,
    output_folder: Path,
    clip_duration: int,
) -> int:
    """
    Split *video_path* into clips of *clip_duration* seconds using FFmpeg
    stream-copy (no re-encoding) for maximum speed and quality preservation.

    Clips are written to *output_folder* as clip_001.mp4, clip_002.mp4, …

    Returns the number of clips successfully created.
    """
    # Determine duration
    duration = get_video_duration(video_path)
    if duration is None or duration <= 0:
        _log(f"⚠  Skipping '{video_path.name}' — could not determine duration.", indent=1)
        return 0

    expected_clips: int = math.ceil(duration / clip_duration)

    _log(f"Duration : {format_duration(duration)} ({duration:.1f}s)", indent=1)
    _log(f"Expected : {expected_clips} clip(s) @ {clip_duration}s each", indent=1)

    # Ensure output folder exists
    output_folder.mkdir(parents=True, exist_ok=True)
    _log(f"Output   : {output_folder}", indent=1)

    clips_created: int = 0
    start_time = time.monotonic()

    for i in range(expected_clips):
        start_sec: float = i * clip_duration
        clip_name: str = f"clip_{i + 1:03d}.mp4"
        clip_path: Path = output_folder / clip_name

        # Build the FFmpeg command:
        cmd: list[str] = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(start_sec),
            "-i", str(video_path),
            "-t", str(clip_duration),
        ]

        if ADD_PART_TEXT:
            part_text = f"Part {i + 1}"
            vf_filter = (
                f"drawtext=fontfile='{TEXT_FONT}':text='{part_text}':"
                f"fontcolor={TEXT_COLOR}:fontsize={TEXT_SIZE}:"
                f"x=(w-text_w)/2:y=520:"
                f"shadowcolor=black:shadowx=4:shadowy=4"
            )
            cmd.extend([
                "-vf", vf_filter,
                "-c:v", "libx264",
                "-preset", ENCODING_PRESET,
                "-crf", str(CRF_QUALITY),
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-c:a", "copy",
            ])
        else:
            cmd.extend([
                "-c", "copy",
                "-map", "0",
            ])

        cmd.extend([
            "-avoid_negative_ts", "1",
            "-y",
            str(clip_path),
        ])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # generous timeout per clip
            )

            if result.returncode == 0 and clip_path.exists():
                clips_created += 1
                # Progress indicator (inline)
                print(f"\r  Clip {clips_created}/{expected_clips} ✓", end="", flush=True)
            else:
                print()  # newline after progress
                _log(f"⚠  Failed to create {clip_name}", indent=1)
                if result.stderr.strip():
                    _log(f"   FFmpeg: {result.stderr.strip()[:200]}", indent=2)

        except subprocess.TimeoutExpired:
            print()
            _log(f"⚠  FFmpeg timed out while creating {clip_name}", indent=1)
        except OSError as exc:
            print()
            _log(f"⚠  OS error creating {clip_name}: {exc}", indent=1)

    # Final newline after progress indicator
    print()

    elapsed = time.monotonic() - start_time
    _log(f"Generated: {clips_created}/{expected_clips} clip(s) in {elapsed:.1f}s", indent=1)

    return clips_created


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """Entry-point: discover videos, split each one into clips."""
    _log_separator()
    _log("🎬  Video Splitter")
    _log(f"    Clip duration : {CLIP_DURATION}s")
    _log(f"    Videos folder : {VIDEOS_DIR}/")
    _log(f"    Output folder : {OUTPUT_DIR}/")
    _log_separator()

    # 1. Check FFmpeg availability
    if not check_ffmpeg():
        sys.exit(1)

    # 2. Resolve paths relative to this script's location
    script_dir: Path = Path(__file__).resolve().parent
    videos_dir: Path = script_dir / VIDEOS_DIR
    output_dir: Path = script_dir / OUTPUT_DIR

    # 3. Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # 4. Discover videos
    videos: list[Path] = discover_videos(videos_dir)

    if not videos:
        _log("No supported video files found in the videos/ folder.")
        _log(f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        sys.exit(0)

    _log(f"Found {len(videos)} video(s)\n")

    # 5. Process each video
    total_clips: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0

    for idx, video_path in enumerate(videos, start=1):
        video_stem: str = video_path.stem  # filename without extension
        video_output: Path = output_dir / video_stem

        _log_separator()
        _log(f"[{idx}/{len(videos)}] Processing: {video_path.name}")

        # Check if already processed
        if is_already_processed(video_output):
            _log(f"⏩  Already processed — skipping (folder exists with clips)", indent=1)
            skipped += 1
            continue

        try:
            clips = split_video(video_path, video_output, CLIP_DURATION)
            total_clips += clips
            if clips > 0:
                processed += 1
            else:
                failed += 1
        except Exception as exc:
            _log(f"✖  Unexpected error: {exc}", indent=1)
            failed += 1
            continue

    # 6. Summary
    print()
    _log_separator()
    _log("✅  Finished processing all videos")
    _log(f"    Processed : {processed} video(s)")
    _log(f"    Skipped   : {skipped} video(s) (already done)")
    _log(f"    Failed    : {failed} video(s)")
    _log(f"    Total clips generated: {total_clips}")
    _log_separator()


if __name__ == "__main__":
    main()
