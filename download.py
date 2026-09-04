#!/usr/bin/env python3
"""
YouTube Video Downloader

This script uses `yt-dlp` to download a YouTube video in the best possible quality (MP4).
The video will be saved directly into your `videos/` folder, ready for splitting!

Prerequisites:
    pip install yt-dlp
"""

import sys
import subprocess
import shutil
from pathlib import Path

# The video URL you provided
VIDEO_URL = "https://youtu.be/HmnG35THPeA?si=QMWBrO3Swg-Z0AM9"

# Directory where the video should be saved
OUTPUT_DIR = "videos"

def main():
    # Check if yt-dlp is installed
    if not shutil.which("yt-dlp"):
        print("yt-dlp CLI is not installed. Installing it via Homebrew...")
        try:
            subprocess.check_call(["brew", "install", "yt-dlp"])
        except subprocess.CalledProcessError:
            print("Failed to install yt-dlp. Please try installing manually: brew install yt-dlp")
            sys.exit(1)

    # Ensure the output directory exists
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    print(f"Starting download for: {VIDEO_URL}")
    print("This might take a few moments depending on the video length and your internet connection...")

    # Build the command for yt-dlp
    cmd = [
        "yt-dlp",
        "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--output", f"{OUTPUT_DIR}/%(title)s.%(ext)s",
        VIDEO_URL
    ]

    try:
        subprocess.check_call(cmd)
        print(f"\n✅ Download complete! The video has been saved to the '{OUTPUT_DIR}' folder.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ An error occurred during the download: {e}")

if __name__ == "__main__":
    main()
