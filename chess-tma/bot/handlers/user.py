import os

from aiogram import Router, types
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

router = Router()

WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://your-app.up.railway.app")


@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    """
    Handles both plain /start and deep links like:
    - t.me/bot?start=join_<invite_token>   (join a private tournament)
    - t.me/bot?start=watch_<game_id>       (open as spectator)

    Telegram passes the WebApp startapp payload through here as
    command.args, so we just forward it into the WebApp URL's query string
    and let the frontend route accordingly.
    """
    payload = command.args or ""

    webapp_url = WEBAPP_URL
    if payload:
        webapp_url = f"{WEBAPP_URL}?startapp={payload}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♟️ Ochish", web_app=WebAppInfo(url=webapp_url))]
    ])

    if payload.startswith("join_"):
        text = "Turnirga qo'shilish uchun quyidagi tugmani bosing:"
    elif payload.startswith("watch_"):
        text = "O'yinni tomosha qilish uchun quyidagi tugmani bosing:"
    else:
        text = "Shaxmat turnirlariga xush kelibsiz! Boshlash uchun tugmani bosing:"

    await message.answer(text, reply_markup=keyboard)
