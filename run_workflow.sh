#!/usr/bin/env bash
# ==============================================================================
# autoClipper — End-to-End Reels Automation Pipeline
#
# Runs the entire workflow line-by-line:
#   1. Environment & dependency verification (Python venv, FFmpeg)
#   2. Video preparation (standardizing raw filenames in videos/)
#   3. Video Splitting (landscape to vertical 9:16 + Part overlays + 60s clips)
#   4. Schedule Calculation (auto-detects last reel + starts 3h after)
#   5. Instagram Web Automation (uploads & schedules Reels)
#
# Usage:
#   ./run_workflow.sh              # Run complete workflow
#   ./run_workflow.sh --dry-run    # Preview schedule without uploading
#   ./run_workflow.sh --limit 5    # Upload & schedule only 5 clips
# ==============================================================================

set -e

# Terminal colors
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_step() {
    echo -e "\n${BOLD}${CYAN}==>${NC} ${BOLD}$1${NC}"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_info() {
    echo -e "  $1"
}

log_warn() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

log_error() {
    echo -e "${RED}✖ $1${NC}"
}

echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          🎬 autoClipper Automation Workflow              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ------------------------------------------------------------------------------
# STEP 1: Check System Dependencies
# ------------------------------------------------------------------------------
log_step "[1/5] Checking Dependencies..."

if ! command -v ffmpeg &>/dev/null; then
    log_error "FFmpeg is not installed or not on PATH."
    log_info "Install with: brew install ffmpeg"
    exit 1
fi
log_success "FFmpeg found: $(ffmpeg -version | head -n 1 | cut -d' ' -f1-3)"

if ! command -v ffprobe &>/dev/null; then
    log_error "ffprobe is not installed."
    exit 1
fi
log_success "ffprobe found"

# ------------------------------------------------------------------------------
# STEP 2: Activate / Setup Python Virtual Environment
# ------------------------------------------------------------------------------
log_step "[2/5] Setting Up Python Environment..."

if [ ! -d ".venv" ]; then
    log_info "Creating virtual environment in .venv..."
    python3 -m venv .venv
fi

source .venv/bin/activate
log_success "Python virtual environment activated: $(python -V)"

# Ensure requirements are installed
if [ -f "requirements.txt" ]; then
    log_info "Verifying Python package dependencies..."
    pip install -q -r requirements.txt
    log_success "Dependencies verified (selenium, webdriver-manager)"
fi

# ------------------------------------------------------------------------------
# STEP 3: Video File Preparation
# ------------------------------------------------------------------------------
log_step "[3/5] Checking Source Videos in videos/..."

mkdir -p videos output

# Clean up raw YouTube download filename if present
RAW_BHOOTNI="videos/Bhootni Story | FULL EPISODE |  Part 1 | Taarak Mehta Ka Ooltah Chashmah | तारक मेहता का उल्टा चश्मा_480p.mp4"
CLEAN_BHOOTNI="videos/TMKOC_Bhootni_Story.mp4"

if [ -f "$RAW_BHOOTNI" ]; then
    log_info "Standardizing video name to clean format..."
    mv "$RAW_BHOOTNI" "$CLEAN_BHOOTNI"
    log_success "Renamed: $RAW_BHOOTNI -> $CLEAN_BHOOTNI"
fi

VIDEO_COUNT=$(find videos -type f \( -name "*.mp4" -o -name "*.mov" -o -name "*.mkv" \) | wc -l | tr -d ' ')
if [ "$VIDEO_COUNT" -eq 0 ]; then
    # Check if we already have clips in output
    CLIP_COUNT=$(find output -type f \( -name "*.mp4" -o -name "*.mov" \) ! -path "*/_vertical_temp/*" | wc -l | tr -d ' ')
    if [ "$CLIP_COUNT" -eq 0 ]; then
        log_error "No videos found in videos/ and no clips in output/."
        log_info "Please place a video in videos/ or run python download.py first."
        exit 1
    else
        log_info "No source videos in videos/, but found $CLIP_COUNT clip(s) ready in output/."
    fi
else
    log_success "Found $VIDEO_COUNT source video(s) in videos/"
fi

# ------------------------------------------------------------------------------
# STEP 4: Convert to Vertical (9:16) and Split into Clips
# ------------------------------------------------------------------------------
log_step "[4/5] Running Video Processing (split_videos.py)..."

python split_videos.py

log_success "Video processing complete. Clips ready in output/ folder."

# ------------------------------------------------------------------------------
# STEP 5: Schedule & Upload to Instagram
# ------------------------------------------------------------------------------
log_step "[5/5] Running Instagram Reels Scheduler (schedule_upload.py)..."

# Ensure any previous automation Chrome is terminated cleanly to release profile lock
# Run scheduler with automatic retry if any reels fail to schedule
MAX_RUNS=5
RUN_COUNT=1
while [ $RUN_COUNT -le $MAX_RUNS ]; do
    log_info "Launching Reels Scheduler (Pass $RUN_COUNT of $MAX_RUNS)..."
    pkill -f "Chrome-Automation" 2>/dev/null || true
    if python schedule_upload.py "$@"; then
        log_success "All pending reels processed successfully on pass $RUN_COUNT."
        break
    else
        STATUS=$?
        log_warn "Scheduler exited with code $STATUS. Re-running in 10 seconds to schedule remaining clips..."
        pkill -f "Chrome-Automation" 2>/dev/null || true
        sleep 10
        RUN_COUNT=$((RUN_COUNT + 1))
    fi
done

echo -e "\n${BOLD}${GREEN}🎉 Workflow finished!${NC}\n"
