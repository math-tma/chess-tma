"""
Ensures a `users` row exists for a given Telegram user before any table that
has a foreign key to `users.telegram_id` (tournaments.created_by,
participants.user_id, payments.confirmed_by, etc.) tries to reference it.

Without this, the first action a brand-new Telegram user takes (e.g. an
admin creating a tournament) fails with a ForeignKeyViolationError, because
nothing had ever inserted that user into `users` yet.
"""
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import User


async def ensure_user(session: AsyncSession, telegram_id: int, full_name: str = "Foydalanuvchi") -> None:
    stmt = (
        insert(User)
        .values(telegram_id=telegram_id, full_name=full_name)
        .on_conflict_do_nothing(index_elements=[User.telegram_id])
    )
    await session.execute(stmt)
