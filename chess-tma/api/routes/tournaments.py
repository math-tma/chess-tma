import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.security import is_admin
from api.core.tournament_logic import calculate_prizes, generate_first_round, resolve_byes
from api.core.users import ensure_user
from api.db.database import get_session
from api.db.models import Match, Participant, Payment, Tournament, User

router = APIRouter()


# ---------- request/response models ----------

class CreateTournamentRequest(BaseModel):
    created_by: int
    created_by_name: str = "Admin"
    name: str
    max_participants: int
    is_private: bool = False
    is_paid: bool = False
    entry_fee: float = 0
    payment_instructions: str | None = None  # e.g. "Karta: 8600 xxxx xxxx xxxx (Ism Familiya)"
    prize_distribution: dict | None = None  # e.g. {"1": 50, "2": 30, "3": 20}


class JoinByTokenRequest(BaseModel):
    invite_token: str
    user_id: int
    user_name: str = "Foydalanuvchi"


class TournamentOut(BaseModel):
    id: int
    name: str
    status: str
    is_private: bool
    is_paid: bool
    entry_fee: float
    invite_token: str | None
    max_participants: int

    class Config:
        from_attributes = True


# ---------- routes ----------

@router.get("", response_model=list[TournamentOut])
async def list_tournaments(
    created_by: int | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """
    Lists tournaments, optionally filtered by creator and/or status.
    Used by the bot's admin panel to build inline-button menus instead of
    the admin having to type tournament IDs from memory.
    """
    query = select(Tournament)
    if created_by is not None:
        query = query.where(Tournament.created_by == created_by)
    if status is not None:
        query = query.where(Tournament.status == status)
    query = query.order_by(Tournament.id.desc())

    result = await session.execute(query)
    return result.scalars().all()


@router.post("", response_model=TournamentOut)
async def create_tournament(req: CreateTournamentRequest, session: AsyncSession = Depends(get_session)):
    if not is_admin(req.created_by):
        raise HTTPException(403, "only admins can create tournaments")

    if req.prize_distribution:
        # validates the percentages sum to 100 — raises ValueError -> 400 below
        try:
            calculate_prizes(100, req.prize_distribution)  # dry run with a dummy pool
        except ValueError as e:
            raise HTTPException(400, str(e))

    await ensure_user(session, req.created_by, req.created_by_name)

    tournament = Tournament(
        created_by=req.created_by,
        name=req.name,
        max_participants=req.max_participants,
        is_private=req.is_private,
        invite_token=secrets.token_urlsafe(12) if req.is_private else None,
        is_paid=req.is_paid,
        entry_fee=req.entry_fee,
        payment_instructions=req.payment_instructions,
        prize_distribution=req.prize_distribution,
    )
    session.add(tournament)
    await session.commit()
    await session.refresh(tournament)
    return tournament


@router.post("/join-by-token")
async def join_by_token(req: JoinByTokenRequest, session: AsyncSession = Depends(get_session)):
    """
    Used by the bot's /join <token> command — the user only needs the short
    invite code, not the tournament's numeric ID.
    """
    await ensure_user(session, req.user_id, req.user_name)

    result = await session.execute(
        select(Tournament).where(Tournament.invite_token == req.invite_token)
    )
    tournament = result.scalar_one_or_none()
    if tournament is None:
        raise HTTPException(404, "kod noto'g'ri yoki turnir topilmadi")

    return await _do_join(session, tournament, req.user_id)


@router.post("/{tournament_id}/join")
async def join_tournament(
    tournament_id: int,
    user_id: int,
    invite_token: str | None = None,
    user_name: str = "Foydalanuvchi",
    session: AsyncSession = Depends(get_session),
):
    await ensure_user(session, user_id, user_name)

    result = await session.execute(select(Tournament).where(Tournament.id == tournament_id))
    tournament = result.scalar_one_or_none()
    if tournament is None:
        raise HTTPException(404, "tournament not found")

    if tournament.is_private and invite_token != tournament.invite_token:
        raise HTTPException(403, "invalid or missing invite token for a private tournament")

    return await _do_join(session, tournament, user_id)


async def _do_join(session: AsyncSession, tournament: Tournament, user_id: int) -> dict:
    if tournament.status != "registration":
        raise HTTPException(400, "tournament is not open for registration")

    existing = await session.execute(
        select(Participant).where(
            Participant.tournament_id == tournament.id, Participant.user_id == user_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "already joined")

    status = "pending_payment" if tournament.is_paid else "joined"
    participant = Participant(tournament_id=tournament.id, user_id=user_id, status=status)
    session.add(participant)

    if tournament.is_paid:
        session.add(Payment(
            tournament_id=tournament.id,
            user_id=user_id,
            amount=tournament.entry_fee,
            status="pending",
        ))

    await session.commit()
    return {
        "ok": True,
        "status": status,
        "tournament_id": tournament.id,
        "tournament_name": tournament.name,
        "entry_fee": float(tournament.entry_fee) if tournament.is_paid else 0,
        "payment_instructions": tournament.payment_instructions if tournament.is_paid else None,
    }


@router.get("/{tournament_id}/pending-payments")
async def list_pending_payments(tournament_id: int, session: AsyncSession = Depends(get_session)):
    """Lists users with an unconfirmed payment for this tournament, so the
    admin panel can show a tap-to-confirm button per user instead of the
    admin typing user IDs from memory."""
    result = await session.execute(
        select(Payment, User)
        .join(User, User.telegram_id == Payment.user_id)
        .where(Payment.tournament_id == tournament_id, Payment.status == "pending")
    )
    return [
        {"user_id": payment.user_id, "user_name": user.full_name, "amount": float(payment.amount)}
        for payment, user in result.all()
    ]


@router.post("/{tournament_id}/confirm-payment")
async def confirm_payment(
    tournament_id: int,
    user_id: int,
    admin_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Admin manually confirms a payment was received (see README — no
    automated payment gateway by design)."""
    if not is_admin(admin_id):
        raise HTTPException(403, "only admins can confirm payments")

    await ensure_user(session, admin_id)

    payment_result = await session.execute(
        select(Payment).where(
            Payment.tournament_id == tournament_id,
            Payment.user_id == user_id,
            Payment.status == "pending",
        )
    )
    payment = payment_result.scalar_one_or_none()
    if payment is None:
        raise HTTPException(404, "no pending payment found for this user")

    payment.status = "confirmed"
    payment.confirmed_by = admin_id
    payment.confirmed_at = datetime.now(timezone.utc)

    participant_result = await session.execute(
        select(Participant).where(
            Participant.tournament_id == tournament_id, Participant.user_id == user_id
        )
    )
    participant = participant_result.scalar_one_or_none()
    if participant:
        participant.status = "joined"
        participant.joined_at = datetime.now(timezone.utc)

    await session.commit()
    return {"ok": True}


@router.post("/{tournament_id}/start")
async def start_tournament(tournament_id: int, admin_id: int, session: AsyncSession = Depends(get_session)):
    if not is_admin(admin_id):
        raise HTTPException(403, "only admins can start tournaments")

    result = await session.execute(select(Tournament).where(Tournament.id == tournament_id))
    tournament = result.scalar_one_or_none()
    if tournament is None:
        raise HTTPException(404, "tournament not found")

    participants_result = await session.execute(
        select(Participant).where(
            Participant.tournament_id == tournament_id, Participant.status == "joined"
        )
    )
    joined_ids = [p.user_id for p in participants_result.scalars().all()]

    if len(joined_ids) < 2:
        raise HTTPException(400, "need at least 2 fully-joined (paid, if applicable) participants")

    pairings = generate_first_round(joined_ids)
    playable, auto_advanced = resolve_byes(pairings)

    for p in playable:
        session.add(Match(
            tournament_id=tournament_id,
            round=1,
            player1_id=p.player1_id,
            player2_id=p.player2_id,
            status="pending",
        ))

    # Byes auto-advance: recorded as finished matches with no opponent, so
    # the bracket UI can show "bye" and next_round logic picks them up.
    for winner_id in auto_advanced:
        session.add(Match(
            tournament_id=tournament_id,
            round=1,
            player1_id=winner_id,
            player2_id=None,
            winner_id=winner_id,
            status="finished",
        ))

    tournament.status = "ongoing"
    await session.commit()
    return {"ok": True, "matches_created": len(playable), "byes": len(auto_advanced)}


@router.get("/{tournament_id}/matches")
async def list_matches(tournament_id: int, session: AsyncSession = Depends(get_session)):
    """Lists matches for a tournament, for the admin panel's 'share match'
    button list."""
    result = await session.execute(
        select(Match).where(Match.tournament_id == tournament_id).order_by(Match.round, Match.id)
    )
    matches = result.scalars().all()
    return [
        {
            "id": m.id,
            "round": m.round,
            "player1_id": m.player1_id,
            "player2_id": m.player2_id,
            "game_id": m.game_id,
            "status": m.status,
        }
        for m in matches
    ]


@router.get("/{tournament_id}/share-link/{match_id}")
async def get_spectator_link(tournament_id: int, match_id: int, session: AsyncSession = Depends(get_session)):
    """
    Returns the spectator WebApp deep link for a match's game, for the admin
    to post via /share_match in the bot. Requires the match to already have
    a game_id (i.e. both players have started playing).
    """
    result = await session.execute(select(Match).where(Match.id == match_id, Match.tournament_id == tournament_id))
    match = result.scalar_one_or_none()
    if match is None:
        raise HTTPException(404, "match not found")
    if match.game_id is None:
        raise HTTPException(400, "match hasn't started yet — no game to watch")

    bot_username = os.environ.get("BOT_USERNAME", "your_bot")
    link = f"https://t.me/{bot_username}/app?startapp=watch_{match.game_id}"
    return {"link": link}
