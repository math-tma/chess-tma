from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.database import Base


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255))
    coins: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[int] = mapped_column(Integer, default=1200)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    name: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(20), default="single_elimination")
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    entry_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    prize_distribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"1": 50, "2": 30, "3": 20}
    max_participants: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="registration")  # registration, ongoing, finished
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    participants: Mapped[list["Participant"]] = relationship(back_populates="tournament")
    matches: Mapped[list["Match"]] = relationship(back_populates="tournament")


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_payment")  # pending_payment, joined, eliminated
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tournament: Mapped["Tournament"] = relationship(back_populates="participants")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, confirmed, rejected
    confirmed_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    round: Mapped[int] = mapped_column(Integer)
    player1_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    player2_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    game_id: Mapped[int | None] = mapped_column(ForeignKey("games.id"), nullable=True)
    winner_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, ongoing, finished

    tournament: Mapped["Tournament"] = relationship(back_populates="matches")


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    player_white: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    player_black: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    fen: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="ongoing")  # ongoing, checkmate, stalemate, draw, resigned
    winner_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    moves: Mapped[list["MoveRecord"]] = relationship(back_populates="game")


class MoveRecord(Base):
    __tablename__ = "moves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    move_number: Mapped[int] = mapped_column(Integer)
    uci: Mapped[str] = mapped_column(String(10))
    fen_after: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    game: Mapped["Game"] = relationship(back_populates="moves")
