#!/usr/bin/env bash
# ==============================================================================
# autoClipper — Dedicated Instagram Reels Scheduler Runner
#
# Runs schedule_upload.py with automatic retry loop for remaining clips
# Usage:
#   ./run_scheduler.sh              # Schedule all pending clips
#   ./run_scheduler.sh --dry-run    # Preview schedule without uploading
#   ./run_scheduler.sh --limit 5    # Upload & schedule only 5 clips
# ==============================================================================

set -e

BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo -e "${RED}Virtual environment .venv not found. Run ./run_workflow.sh first.${NC}"
    exit 1
fi

echo -e "\n${BOLD}${CYAN}==>${NC} ${BOLD}Starting Instagram Reels Scheduler...${NC}\n"

MAX_RUNS=5
RUN_COUNT=1
while [ $RUN_COUNT -le $MAX_RUNS ]; do
    echo -e "${CYAN}Launching Reels Scheduler (Pass $RUN_COUNT of $MAX_RUNS)...${NC}"
    pkill -f "Chrome-Automation" 2>/dev/null || true
    if python schedule_upload.py "$@"; then
        echo -e "\n${GREEN}✓ All pending reels processed successfully on pass $RUN_COUNT.${NC}\n"
        break
    else
        STATUS=$?
        echo -e "\n${YELLOW}⚠ Scheduler exited with code $STATUS. Re-running in 10 seconds to schedule remaining clips...${NC}\n"
        pkill -f "Chrome-Automation" 2>/dev/null || true
        sleep 10
        RUN_COUNT=$((RUN_COUNT + 1))
    fi
done
