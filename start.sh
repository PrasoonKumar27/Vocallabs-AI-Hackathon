#!/bin/bash
PORT="${PORT:-8000}"
echo "Starting Uvicorn on port $PORT..."
exec python3 -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
