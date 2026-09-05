# Chess TMA — Telegram Mini App Chess Tournament Bot

Full rebuild: single-language stack (Python), FastAPI backend + aiogram 3.x bot +
PostgreSQL + WebSocket + python-chess as the single source of truth for game rules.

## Why this structure

The previous version broke because chess rules were hand-written and duplicated
between frontend/backend. This version validates **every** move server-side with
`python-chess`, so checkmate/stalemate/illegal-move bugs from before are structurally
impossible — the library is battle-tested.

## Folder layout

```
chess-tma/
├── bot/                  # aiogram 3.x Telegram bot
│   ├── main.py           # bot entrypoint, dispatcher setup
│   └── handlers/
│       ├── user.py       # /start, join tournament via invite link
│       └── admin.py      # /create_tournament, /start_tournament, /share_match, payment confirm
├── api/                  # FastAPI backend (serves the WebApp + WebSocket)
│   ├── main.py           # FastAPI app entrypoint
│   ├── routes/
│   │   ├── tournaments.py
│   │   ├── games.py
│   │   └── websocket.py  # real-time board sync, spectator rooms
│   ├── core/
│   │   ├── chess_engine.py     # python-chess wrapper: single source of truth
│   │   ├── tournament_logic.py # bracket generation, prize calculation
│   │   └── security.py         # Telegram initData validation
│   └── db/
│       ├── database.py  # async SQLAlchemy engine/session
│       ├── models.py    # ORM models matching schema.sql
│       └── schema.sql   # raw SQL reference (matches models.py)
├── webapp/               # placeholder static WebApp (replace with your React build)
│   └── index.html
├── requirements.txt
├── Procfile              # Railway process definition
├── railway.json          # Railway build/deploy config
├── .env.example
└── README.md
```

## Setup

1. Create a Railway project, add a **PostgreSQL** plugin — Railway will inject
   `DATABASE_URL` automatically.
2. Copy `.env.example` to `.env` and fill in `BOT_TOKEN` (from @BotFather) and
   `WEBAPP_URL` (your Railway public URL, e.g. `https://your-app.up.railway.app`).
3. In @BotFather, set the Mini App URL to `WEBAPP_URL` and enable it via
   `/setmenubutton` or `/newapp`.
4. Push this repo to Railway (GitHub repo or `railway up`). Railway reads
   `railway.json` / `Procfile` and starts both processes.

## Running locally

```bash
pip install -r requirements.txt
export $(cat .env | xargs)          # or use python-dotenv
python -m api.main &                # FastAPI + WebSocket on :8000
python -m bot.main                  # aiogram bot (polling)
```

## What's implemented vs. what's a stub

**Implemented (working logic):**
- `chess_engine.py` — full legal-move validation, checkmate/stalemate/draw
  detection, move history, FEN state — via `python-chess`.
- `tournament_logic.py` — single-elimination bracket generation (handles
  non-power-of-2 participant counts with byes), prize-pool distribution math.
- WebSocket game rooms with player + read-only spectator roles.
- SQLAlchemy models + schema matching the design we discussed (tournaments,
  participants, payments, matches, games, moves).
- Admin-only command guard, invite-token joining, manual payment confirmation.

**Stubs you need to fill in for production:**
- `webapp/index.html` is a minimal placeholder board — swap in your real
  React/Tailwind frontend (talks to the same REST + WebSocket endpoints).
- Telegram `initData` validation in `security.py` has the correct HMAC
  algorithm but you must set `BOT_TOKEN` for it to verify real requests.
- No automated payment gateway (Click/Payme) — by design, per our
  discussion, payments are admin-confirmed manually via `/confirm_payment`.

## Restart bug — how this version avoids it

Every "restart" creates a **new** `games` row instead of mutating an old one.
Old game state is never reused, so there's no half-reset state to go stale.
