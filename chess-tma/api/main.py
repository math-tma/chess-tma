from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.db.database import init_models
from api.routes import games, tournaments, websocket


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    yield


app = FastAPI(title="Chess TMA API", lifespan=lifespan)

# Telegram WebApp is served from the same origin in production, but during
# local dev the WebApp may be opened from a different port — allow it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tournaments.router, prefix="/api/tournaments", tags=["tournaments"])
app.include_router(games.router, prefix="/api/games", tags=["games"])
app.include_router(websocket.router, tags=["websocket"])

# Serve the placeholder WebApp static files — replace webapp/ with your real build.
app.mount("/", StaticFiles(directory="webapp", html=True), name="webapp")
