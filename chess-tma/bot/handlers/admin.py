import os

import httpx
from aiogram import Router, types
from aiogram.filters import Command, CommandObject

from api.core.security import is_admin

router = Router()

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


def admin_only(handler):
    async def wrapper(message: types.Message, *args, **kwargs):
        if not is_admin(message.from_user.id):
            await message.answer("Bu buyruq faqat adminlar uchun.")
            return
        return await handler(message, *args, **kwargs)
    return wrapper


@router.message(Command("create_tournament"))
@admin_only
async def cmd_create_tournament(message: types.Message, command: CommandObject):
    """
    Usage: /create_tournament <name> <max_participants> [entry_fee]
    Example: /create_tournament "Yozgi turnir" 16 20000
    A fuller version would open a WebApp form instead of parsing raw text —
    this is the minimal command-line path to get a tournament created.
    """
    if not command.args:
        await message.answer(
            "Foydalanish: /create_tournament <nomi> <max_ishtirokchi> [kirish_narxi]"
        )
        return

    parts = command.args.rsplit(maxsplit=2)
    try:
        if len(parts) == 3 and parts[-1].isdigit() and parts[-2].isdigit():
            name, max_participants, entry_fee = parts[0], int(parts[1]), float(parts[2])
            is_paid = entry_fee > 0
        elif len(parts) >= 2 and parts[-1].isdigit():
            name = " ".join(parts[:-1])
            max_participants = int(parts[-1])
            entry_fee, is_paid = 0, False
        else:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("Format noto'g'ri. Masalan: /create_tournament Yozgi_turnir 16 20000")
        return

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{API_BASE}/api/tournaments", json={
            "created_by": message.from_user.id,
            "name": name,
            "max_participants": max_participants,
            "is_paid": is_paid,
            "entry_fee": entry_fee,
            "is_private": True,
        })

    if resp.status_code != 200:
        await message.answer(f"Xatolik: {resp.text}")
        return

    data = resp.json()
    bot_username = (await message.bot.get_me()).username
    invite_link = f"https://t.me/{bot_username}?start=join_{data['invite_token']}"

    await message.answer(
        f"✅ Turnir yaratildi: <b>{data['name']}</b>\n"
        f"ID: {data['id']}\n"
        f"Taklif havolasi (ishtirokchilarga yuboring):\n{invite_link}\n\n"
        f"Ro'yxatdan o'tish tugagach: /start_tournament {data['id']}"
    )


@router.message(Command("start_tournament"))
@admin_only
async def cmd_start_tournament(message: types.Message, command: CommandObject):
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Foydalanish: /start_tournament <tournament_id>")
        return

    tournament_id = int(command.args.strip())

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE}/api/tournaments/{tournament_id}/start",
            params={"admin_id": message.from_user.id},
        )

    if resp.status_code != 200:
        await message.answer(f"Xatolik: {resp.text}")
        return

    data = resp.json()
    await message.answer(
        f"🏁 Turnir boshlandi! {data['matches_created']} ta o'yin yaratildi, "
        f"{data['byes']} ta ishtirokchi bye orqali avtomatik o'tdi."
    )


@router.message(Command("confirm_payment"))
@admin_only
async def cmd_confirm_payment(message: types.Message, command: CommandObject):
    """Usage: /confirm_payment <tournament_id> <user_id>"""
    args = (command.args or "").split()
    if len(args) != 2 or not all(a.isdigit() for a in args):
        await message.answer("Foydalanish: /confirm_payment <tournament_id> <user_id>")
        return

    tournament_id, user_id = int(args[0]), int(args[1])

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE}/api/tournaments/{tournament_id}/confirm-payment",
            params={"user_id": user_id, "admin_id": message.from_user.id},
        )

    if resp.status_code != 200:
        await message.answer(f"Xatolik: {resp.text}")
        return

    await message.answer(f"✅ To'lov tasdiqlandi, foydalanuvchi {user_id} turnirga qo'shildi.")


@router.message(Command("share_match"))
@admin_only
async def cmd_share_match(message: types.Message, command: CommandObject):
    """Usage: /share_match <tournament_id> <match_id> — posts a spectator
    link. Send this command in the group/channel you want the link posted to."""
    args = (command.args or "").split()
    if len(args) != 2 or not all(a.isdigit() for a in args):
        await message.answer("Foydalanish: /share_match <tournament_id> <match_id>")
        return

    tournament_id, match_id = int(args[0]), int(args[1])

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/api/tournaments/{tournament_id}/share-link/{match_id}"
        )

    if resp.status_code != 200:
        await message.answer(f"Xatolik: {resp.text}")
        return

    link = resp.json()["link"]
    await message.answer(f"🎥 O'yinni tomosha qilish:\n{link}")
