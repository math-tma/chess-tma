from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.chess_engine import new_game_fen
from api.db.database import get_session
from api.db.models import Game

router = APIRouter()


class CreateGameRequest(BaseModel):
    player_white: int
    player_black: int
    match_id: int | None = None


class GameOut(BaseModel):
    id: int
    fen: str
    status: str
    player_white: int
    player_black: int

    class Config:
        from_attributes = True


@router.post("", response_model=GameOut)
async def create_game(req: CreateGameRequest, session: AsyncSession = Depends(get_session)):
    """
    Creates a brand-new game row with the starting position. This is also
    what a 'restart' does — it never mutates an existing game, it creates a
    fresh one, so there's no half-reset state to go stale (see README).
    """
    game = Game(
        player_white=req.player_white,
        player_black=req.player_black,
        match_id=req.match_id,
        fen=new_game_fen(),
        status="ongoing",
    )
    session.add(game)
    await session.commit()
    await session.refresh(game)
    return game


@router.get("/{game_id}", response_model=GameOut)
async def get_game(game_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Game).where(Game.id == game_id))
    game = result.scalar_one_or_none()
    if game is None:
        raise HTTPException(404, "game not found")
    return game


@router.post("/{game_id}/resign")
async def resign_game(game_id: int, user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Game).where(Game.id == game_id))
    game = result.scalar_one_or_none()
    if game is None:
        raise HTTPException(404, "game not found")
    if user_id not in (game.player_white, game.player_black):
        raise HTTPException(403, "only a player in this game can resign")

    resigning_color = "white" if user_id == game.player_white else "black"
    game.status = "resigned"
    game.winner_id = game.player_black if resigning_color == "white" else game.player_white
    await session.commit()
    return {"ok": True, "winner_id": game.winner_id}
