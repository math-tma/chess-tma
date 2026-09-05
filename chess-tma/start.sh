#!/usr/bin/env bash
set -e

# Railway runs one container per service. This script starts the FastAPI
# WebApp/WebSocket server in the background and the Telegram bot (polling)
# in the foreground, so both run inside a single Railway service.
#
# If you'd rather run them as two separate Railway services (recommended once
# traffic grows), split this into two services each with its own start
# command: "uvicorn api.main:app --host 0.0.0.0 --port $PORT" and
# "python -m bot.main".

uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
API_PID=$!

python -m bot.main &
BOT_PID=$!

trap "kill $API_PID $BOT_PID" SIGINT SIGTERM
wait -n $API_PID $BOT_PID
