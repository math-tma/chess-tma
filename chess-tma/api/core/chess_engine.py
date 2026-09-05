"""
Single source of truth for chess rules.

Everything about legality, check, checkmate, stalemate, draws, promotion,
castling, en passant is delegated to `python-chess`. Nothing here re-implements
chess rules by hand — that's exactly what caused the bugs in the previous
version ("mot bo'lmayotgan edi", pieces moving incorrectly).

The backend is the only place that decides whether a move is legal. The
frontend only ever displays state and sends move attempts; it never decides
legality itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import chess


class GameStatus(str, Enum):
    ONGOING = "ongoing"
    CHECKMATE = "checkmate"
    STALEMATE = "stalemate"
    DRAW = "draw"          # insufficient material / 75-move / fivefold repetition
    RESIGNED = "resigned"


@dataclass
class MoveResult:
    ok: bool
    reason: str | None = None          # set when ok=False, e.g. "illegal_move"
    fen_after: str | None = None
    san: str | None = None             # e.g. "Nf3", "Qxe7+"
    uci: str | None = None             # e.g. "g1f3"
    status: GameStatus = GameStatus.ONGOING
    winner_color: str | None = None    # "white" | "black" | None


class ChessGame:
    """Thin wrapper around a python-chess Board tied to one `games` row."""

    def __init__(self, fen: str | None = None):
        self.board = chess.Board(fen) if fen else chess.Board()

    @property
    def fen(self) -> str:
        return self.board.fen()

    @property
    def turn(self) -> str:
        return "white" if self.board.turn == chess.WHITE else "black"

    def legal_moves_uci(self) -> list[str]:
        """All legal moves from the current position, for the frontend to
        highlight — the frontend should never compute this itself."""
        return [m.uci() for m in self.board.legal_moves]

    def legal_moves_from(self, square_uci: str) -> list[str]:
        """Legal destination squares for a piece on `square_uci` (e.g. 'e2').
        Used to highlight valid targets when a player taps a piece."""
        try:
            from_sq = chess.parse_square(square_uci)
        except ValueError:
            return []
        return [
            chess.square_name(m.to_square)
            for m in self.board.legal_moves
            if m.from_square == from_sq
        ]

    def push_move(self, uci: str) -> MoveResult:
        """Attempt to apply a move given in UCI form (e.g. 'e2e4', 'e7e8q'
        for promotion). Returns a MoveResult describing what happened."""
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return MoveResult(ok=False, reason="malformed_move")

        if move not in self.board.legal_moves:
            return MoveResult(ok=False, reason="illegal_move")

        san = self.board.san(move)
        self.board.push(move)

        status, winner = self._evaluate_status()

        return MoveResult(
            ok=True,
            fen_after=self.board.fen(),
            san=san,
            uci=uci,
            status=status,
            winner_color=winner,
        )

    def _evaluate_status(self) -> tuple[GameStatus, str | None]:
        if self.board.is_checkmate():
            # side to move is the side that got mated -> other side wins
            winner = "black" if self.board.turn == chess.WHITE else "white"
            return GameStatus.CHECKMATE, winner
        if self.board.is_stalemate():
            return GameStatus.STALEMATE, None
        if (
            self.board.is_insufficient_material()
            or self.board.is_seventyfive_moves()
            or self.board.is_fivefold_repetition()
        ):
            return GameStatus.DRAW, None
        return GameStatus.ONGOING, None

    def resign(self, resigning_color: str) -> MoveResult:
        winner = "black" if resigning_color == "white" else "white"
        return MoveResult(
            ok=True,
            fen_after=self.board.fen(),
            status=GameStatus.RESIGNED,
            winner_color=winner,
        )


def new_game_fen() -> str:
    """FEN for a fresh starting position — used whenever a game or a
    restart happens. Restart always creates a brand new `games` row with
    this FEN rather than mutating an existing one (see README)."""
    return chess.Board().fen()
