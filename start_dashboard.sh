#!/bin/bash
echo "--------------------------------------------------------"
echo "🚨 Launching ParkVision AI Production Server..."
echo "Framework: FastAPI (Backend) + SQLite (DB) + Vanilla JS (Frontend)"
echo "Topic: Poor Visibility on Parking-Induced Congestion"
echo "--------------------------------------------------------"
# Resolve the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Run uvicorn pointing to the script's directory as app-dir
python3 -m uvicorn main:app --app-dir "$SCRIPT_DIR" --host 0.0.0.0 --port 8502 --reload
