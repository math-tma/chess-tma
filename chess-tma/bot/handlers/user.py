import os

import httpx
from aiogram import Router, types
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

router = Router()

WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://your-app.up.railway.app")
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    """
    Handles both plain /start and deep links like:
    - t.me/bot?start=join_<invite_token>   (auto-joins a private tournament)
    - t.me/bot?start=watch_<game_id>       (open as spectator)
    """
    payload = command.args or ""

    if payload.startswith("join_"):
        token = payload.removeprefix("join_")
        await _join_by_token(message, token)
        return

    webapp_url = WEBAPP_URL
    if payload:
        webapp_url = f"{WEBAPP_URL}?startapp={payload}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♟️ Ochish", web_app=WebAppInfo(url=webapp_url))]
    ])

    if payload.startswith("watch_"):
        text = "O'yinni tomosha qilish uchun quyidagi tugmani bosing:"
    else:
        text = "Shaxmat turnirlariga xush kelibsiz! Boshlash uchun tugmani bosing:"

    await message.answer(text, reply_markup=keyboard)


@router.message(Command("join"))
async def cmd_join(message: types.Message, command: CommandObject):
    """Usage: /join <kod> — turnirga taklif kodi orqali qo'shilish."""
    if not command.args:
        await message.answer("Foydalanish: /join <kod>\nKodni admin sizga yuboradi.")
        return
    await _join_by_token(message, command.args.strip())


async def _join_by_token(message: types.Message, token: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{API_BASE}/api/tournaments/join-by-token", json={
            "invite_token": token,
            "user_id": message.from_user.id,
            "user_name": message.from_user.full_name,
        })

    if resp.status_code == 404:
        await message.answer("❌ Bunday kod topilmadi. Kodni tekshirib qayta yuboring.")
        return
    if resp.status_code != 200:
        await message.answer(f"Xatolik: {resp.text}")
        return

    data = resp.json()
    if data["status"] == "pending_payment":
        await message.answer(
            f"✅ <b>{data['tournament_name']}</b> turniriga qo'shildingiz!\n"
            f"Bu pullik turnir — to'lovni amalga oshirgach, admin tasdiqlashini kuting."
        )
    else:
        await message.answer(f"✅ <b>{data['tournament_name']}</b> turniriga muvaffaqiyatli qo'shildingiz!")
