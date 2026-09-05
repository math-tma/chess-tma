import os

import httpx
from aiogram import F, Router, types
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from api.core.security import get_admin_ids

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
        instructions = data.get("payment_instructions") or "To'lov ma'lumotini admin sizga alohida yuboradi."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ To'ladim",
                callback_data=f"paid:{data['tournament_id']}",
            )]
        ])
        await message.answer(
            f"✅ <b>{data['tournament_name']}</b> turniriga qo'shildingiz!\n\n"
            f"💰 Kirish narxi: {data['entry_fee']:.0f} so'm\n"
            f"📋 To'lov: {instructions}\n\n"
            f"To'lovni amalga oshirgach, pastdagi tugmani bosing — admin xabardor bo'ladi.",
            reply_markup=keyboard,
        )
    else:
        await message.answer(f"✅ <b>{data['tournament_name']}</b> turniriga muvaffaqiyatli qo'shildingiz!")


@router.callback_query(F.data.startswith("paid:"))
async def cb_user_claims_paid(callback: types.CallbackQuery):
    """
    User taps "✅ To'ladim" — this doesn't confirm payment itself (only an
    admin can, via the admin panel), it just notifies every admin so they
    know to go check and confirm. Reuses the existing admin:pay:user
    callback so admins can confirm with one tap right from the notification.
    """
    tournament_id = callback.data.split(":", 1)[1]
    user = callback.from_user

    notify_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Tasdiqlash",
            callback_data=f"admin:pay:user:{tournament_id}:{user.id}",
        )]
    ])

    admin_ids = get_admin_ids()
    sent_to_anyone = False
    for admin_id in admin_ids:
        try:
            await callback.bot.send_message(
                admin_id,
                f"💰 <b>{user.full_name}</b> (ID: {user.id}) to'lov qildim deb belgiladi.\n"
                f"Turnir ID: {tournament_id}\n\n"
                f"Tekshirib, tasdiqlang:",
                reply_markup=notify_keyboard,
            )
            sent_to_anyone = True
        except Exception:
            continue  # admin hali botga /start bosmagan bo'lishi mumkin

    if sent_to_anyone:
        await callback.answer("Admin xabardor qilindi. Tasdiqlashini kuting.", show_alert=True)
    else:
        await callback.answer(
            "Adminlarga xabar yubora olmadim — ular hali botni ishga tushirmagan bo'lishi mumkin.",
            show_alert=True,
        )
