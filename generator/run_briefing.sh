#!/bin/bash
# Morning Briefing Generator Runner
# Generates briefing, voice files, and pushes to GitHub

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BRIEFING_DIR="$(dirname "$SCRIPT_DIR")"
KOKORO_VENV="$HOME/kokoro-tts/venv"
BRIEFING_VENV="$BRIEFING_DIR/venv"

echo "=== Morning Briefing Generator ==="
echo "Started at: $(date)"

# Activate venvs and run generator
cd "$BRIEFING_DIR"

# Source the briefing venv (has yfinance)
source "$BRIEFING_VENV/bin/activate"

# Add kokoro to PYTHONPATH
export PYTHONPATH="$KOKORO_VENV/lib/python3.11/site-packages:$PYTHONPATH"

# Run the generator
python3 generator/generate_briefing.py

# Get the generated folder
FOLDER=$(cat .current_page)
echo "Generated folder: $FOLDER"

# Git commit and push
git add .
git commit -m "Briefing for $(date +%Y-%m-%d)"
git push origin main

echo "=== Briefing Published ==="
echo "URL: https://copilot-clive.github.io/briefing/$FOLDER/"
echo "Finished at: $(date)"
