"""
WebSocket game rooms.

One room per `game_id`. Players can send moves; spectators are connected
read-only — the server silently ignores any move attempt from a connection
that isn't one of the two registered players for that game.
"""
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from api.core.chess_engine import ChessGame, GameStatus
from api.db.database import async_session
from api.db.models import Game, MoveRecord, User

router = APIRouter()


class Room:
    def __init__(self):
        self.connections: dict[WebSocket, dict] = {}  # ws -> {"user_id": int, "role": "player"|"spectator"}

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.pop(ws, None)


class RoomManager:
    def __init__(self):
        self.rooms: dict[int, Room] = {}

    def get_room(self, game_id: int) -> Room:
        if game_id not in self.rooms:
            self.rooms[game_id] = Room()
        return self.rooms[game_id]


rooms = RoomManager()


async def _player_names(session, game_row: Game) -> dict:
    result = await session.execute(
        select(User).where(User.telegram_id.in_([game_row.player_white, game_row.player_black]))
    )
    names = {u.telegram_id: u.full_name for u in result.scalars().all()}
    return {
        "white_name": names.get(game_row.player_white, "Oq"),
        "black_name": names.get(game_row.player_black, "Qora"),
    }


@router.websocket("/ws/game/{game_id}")
async def game_socket(websocket: WebSocket, game_id: int, user_id: int):
    """
    Connect with: /ws/game/123?user_id=456
    (In production, replace the raw `user_id` query param with a validated
    Telegram initData token — see api/core/security.py — passed once at
    connect time and verified before accepting.)
    """
    await websocket.accept()
    room = rooms.get_room(game_id)

    async with async_session() as session:
        result = await session.execute(select(Game).where(Game.id == game_id))
        game_row = result.scalar_one_or_none()
        names = await _player_names(session, game_row) if game_row else {}

    if game_row is None:
        await websocket.send_json({"type": "error", "reason": "game_not_found"})
        await websocket.close()
        return

    if user_id == game_row.player_white:
        role, your_color = "player", "white"
    elif user_id == game_row.player_black:
        role, your_color = "player", "black"
    else:
        role, your_color = "spectator", None

    room.connections[websocket] = {"user_id": user_id, "role": role}

    chess_game = ChessGame(fen=game_row.fen)
    await websocket.send_json({
        "type": "state",
        "fen": game_row.fen,
        "status": game_row.status,
        "role": role,              # frontend disables the board for spectators
        "your_color": your_color,  # "white" | "black" | None (spectator)
        "turn": chess_game.turn,
        **names,
    })

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            if msg_type == "legal_moves_request":
                async with async_session() as session:
                    result = await session.execute(select(Game).where(Game.id == game_id))
                    current = result.scalar_one_or_none()
                if current is None:
                    continue
                cg = ChessGame(fen=current.fen)
                await websocket.send_json({
                    "type": "legal_moves",
                    "from": data.get("square"),
                    "targets": cg.legal_moves_from(data.get("square", "")),
                })
                continue

            if msg_type != "move":
                continue

            if role != "player":
                await websocket.send_json({"type": "error", "reason": "spectators_cannot_move"})
                continue

            async with async_session() as session:
                result = await session.execute(select(Game).where(Game.id == game_id))
                game_row = result.scalar_one_or_none()

                if game_row is None or game_row.status != "ongoing":
                    await websocket.send_json({"type": "error", "reason": "game_not_active"})
                    continue

                chess_game = ChessGame(fen=game_row.fen)

                # Enforce turn order: only the player whose color matches
                # the side to move may submit a move.
                expected_player = (
                    game_row.player_white if chess_game.turn == "white" else game_row.player_black
                )
                if user_id != expected_player:
                    await websocket.send_json({"type": "error", "reason": "not_your_turn"})
                    continue

                move_result = chess_game.push_move(data.get("uci", ""))

                if not move_result.ok:
                    await websocket.send_json({"type": "error", "reason": move_result.reason})
                    continue

                game_row.fen = move_result.fen_after
                game_row.status = move_result.status.value
                if move_result.status != GameStatus.ONGOING:
                    game_row.winner_id = (
                        game_row.player_white if move_result.winner_color == "white"
                        else game_row.player_black if move_result.winner_color == "black"
                        else None
                    )

                move_count_result = await session.execute(
                    select(MoveRecord).where(MoveRecord.game_id == game_id)
                )
                move_number = len(move_count_result.scalars().all()) + 1

                session.add(MoveRecord(
                    game_id=game_id,
                    move_number=move_number,
                    uci=move_result.uci,
                    fen_after=move_result.fen_after,
                ))
                await session.commit()

            next_turn = chess_game.turn  # already reflects the side to move now, after push_move
            await room.broadcast({
                "type": "move",
                "uci": move_result.uci,
                "san": move_result.san,
                "fen": move_result.fen_after,
                "status": move_result.status.value,
                "winner_color": move_result.winner_color,
                "turn": next_turn,
            })

    except WebSocketDisconnect:
        room.connections.pop(websocket, None)
