import os

import httpx
from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from api.core.security import is_admin

router = Router()

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


# =========================================================================
# Admin panel — tugmali menyu, admin buyruqlarni qo'lda yozmasligi uchun.
# Matn buyruqlar (/create_tournament, /start_tournament, ...) pastda ham
# saqlangan — kimdir eskicha ishlatmoqchi bo'lsa ishlayveradi.
# =========================================================================

class CreateTournament(StatesGroup):
    waiting_name = State()
    waiting_max_participants = State()
    waiting_entry_fee = State()


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Yangi turnir", callback_data="admin:create")],
        [InlineKeyboardButton(text="▶️ Turnirni boshlash", callback_data="admin:start:list")],
        [InlineKeyboardButton(text="💰 To'lovlarni tasdiqlash", callback_data="admin:pay:list")],
        [InlineKeyboardButton(text="🎥 O'yinni ulashish", callback_data="admin:share:list")],
    ])


@router.message(Command("admin"))
async def cmd_admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Bu buyruq faqat adminlar uchun.")
        return
    await message.answer("🎛 Admin panel:", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "admin:menu")
async def cb_back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🎛 Admin panel:", reply_markup=main_menu_keyboard())
    await callback.answer()


# ---------- 1) Yangi turnir yaratish (FSM: nomi -> max o'rin -> kirish narxi) ----------

@router.callback_query(F.data == "admin:create")
async def cb_create_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Faqat adminlar uchun.", show_alert=True)
        return
    await state.set_state(CreateTournament.waiting_name)
    await callback.message.edit_text("Turnir nomini yozing:")
    await callback.answer()


@router.message(CreateTournament.waiting_name)
async def fsm_create_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(CreateTournament.waiting_max_participants)
    await message.answer("Maksimal ishtirokchilar sonini yozing (masalan: 16):")


@router.message(CreateTournament.waiting_max_participants)
async def fsm_create_max_participants(message: types.Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("Iltimos, faqat raqam yozing (masalan: 16):")
        return
    await state.update_data(max_participants=int(message.text.strip()))
    await state.set_state(CreateTournament.waiting_entry_fee)
    await message.answer(
        "Kirish narxini yozing (so'mda). Bepul turnir bo'lsa 0 deb yozing:"
    )


@router.message(CreateTournament.waiting_entry_fee)
async def fsm_create_entry_fee(message: types.Message, state: FSMContext):
    raw = message.text.strip().replace(" ", "")
    if not raw.replace(".", "", 1).isdigit():
        await message.answer("Iltimos, faqat raqam yozing (bepul bo'lsa 0):")
        return

    entry_fee = float(raw)
    data = await state.get_data()
    await state.clear()

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{API_BASE}/api/tournaments", json={
            "created_by": message.from_user.id,
            "created_by_name": message.from_user.full_name,
            "name": data["name"],
            "max_participants": data["max_participants"],
            "is_paid": entry_fee > 0,
            "entry_fee": entry_fee,
            "is_private": True,
        })

    if resp.status_code != 200:
        await message.answer(f"Xatolik: {resp.text}")
        return

    result = resp.json()
    bot_username = (await message.bot.get_me()).username
    invite_link = f"https://t.me/{bot_username}?start=join_{result['invite_token']}"
    join_code = result["invite_token"]

    await message.answer(
        f"✅ Turnir yaratildi: <b>{result['name']}</b>\n"
        f"ID: {result['id']}\n\n"
        f"Ishtirokchilar uchun havola:\n{invite_link}\n\n"
        f"Yoki botga shu buyruqni yuborishsin:\n<code>/join {join_code}</code>",
        reply_markup=main_menu_keyboard(),
    )


# ---------- 2) Turnirni boshlash — ro'yxatdan tanlab bosish ----------

@router.callback_query(F.data == "admin:start:list")
async def cb_start_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Faqat adminlar uchun.", show_alert=True)
        return

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/api/tournaments", params={
            "created_by": callback.from_user.id, "status": "registration",
        })

    tournaments = resp.json() if resp.status_code == 200 else []
    if not tournaments:
        await callback.message.edit_text(
            "Boshlanishi mumkin bo'lgan turnir yo'q (barchasi allaqachon boshlangan yoki hali yaratilmagan).",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")]
            ]),
        )
        await callback.answer()
        return

    buttons = [
        [InlineKeyboardButton(text=f"{t['name']} (ID {t['id']})", callback_data=f"admin:start:sel:{t['id']}")]
        for t in tournaments
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")])
    await callback.message.edit_text("Qaysi turnirni boshlaymiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:start:sel:"))
async def cb_start_selected(callback: types.CallbackQuery):
    tournament_id = int(callback.data.rsplit(":", 1)[-1])

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE}/api/tournaments/{tournament_id}/start",
            params={"admin_id": callback.from_user.id},
        )

    if resp.status_code != 200:
        await callback.answer(f"Xatolik: {resp.text}", show_alert=True)
        return

    data = resp.json()
    await callback.message.edit_text(
        f"🏁 Turnir boshlandi! {data['matches_created']} ta o'yin yaratildi, "
        f"{data['byes']} ta ishtirokchi bye orqali avtomatik o'tdi.",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


# ---------- 3) To'lovlarni tasdiqlash — turnir tanlash -> foydalanuvchi tanlash ----------

@router.callback_query(F.data == "admin:pay:list")
async def cb_pay_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Faqat adminlar uchun.", show_alert=True)
        return

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/api/tournaments", params={"created_by": callback.from_user.id})

    tournaments = [t for t in (resp.json() if resp.status_code == 200 else []) if t["is_paid"]]
    if not tournaments:
        await callback.message.edit_text(
            "Pullik turnirlaringiz yo'q.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")]
            ]),
        )
        await callback.answer()
        return

    buttons = [
        [InlineKeyboardButton(text=t["name"], callback_data=f"admin:pay:tour:{t['id']}")]
        for t in tournaments
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")])
    await callback.message.edit_text("Qaysi turnir uchun to'lovlarni ko'ramiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:pay:tour:"))
async def cb_pay_tournament_selected(callback: types.CallbackQuery):
    tournament_id = int(callback.data.rsplit(":", 1)[-1])

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/api/tournaments/{tournament_id}/pending-payments")

    pending = resp.json() if resp.status_code == 200 else []
    if not pending:
        await callback.message.edit_text(
            "Kutilayotgan to'lovlar yo'q.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:pay:list")]
            ]),
        )
        await callback.answer()
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"{p['user_name']} — {p['amount']:.0f} so'm",
            callback_data=f"admin:pay:user:{tournament_id}:{p['user_id']}",
        )]
        for p in pending
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:pay:list")])
    await callback.message.edit_text("Kimning to'lovini tasdiqlaymiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:pay:user:"))
async def cb_pay_confirm(callback: types.CallbackQuery):
    _, _, _, tournament_id, user_id = callback.data.split(":")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE}/api/tournaments/{tournament_id}/confirm-payment",
            params={"user_id": user_id, "admin_id": callback.from_user.id},
        )

    if resp.status_code != 200:
        await callback.answer(f"Xatolik: {resp.text}", show_alert=True)
        return

    await callback.message.edit_text("✅ To'lov tasdiqlandi.", reply_markup=main_menu_keyboard())
    await callback.answer()


# ---------- 4) O'yinni ulashish — turnir tanlash -> o'yin tanlash ----------

@router.callback_query(F.data == "admin:share:list")
async def cb_share_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Faqat adminlar uchun.", show_alert=True)
        return

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/api/tournaments", params={
            "created_by": callback.from_user.id, "status": "ongoing",
        })

    tournaments = resp.json() if resp.status_code == 200 else []
    if not tournaments:
        await callback.message.edit_text(
            "Hozir ketayotgan turnir yo'q.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")]
            ]),
        )
        await callback.answer()
        return

    buttons = [
        [InlineKeyboardButton(text=t["name"], callback_data=f"admin:share:tour:{t['id']}")]
        for t in tournaments
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:menu")])
    await callback.message.edit_text("Qaysi turnirdagi o'yinni ulashamiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:share:tour:"))
async def cb_share_tournament_selected(callback: types.CallbackQuery):
    tournament_id = int(callback.data.rsplit(":", 1)[-1])

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/api/tournaments/{tournament_id}/matches")

    matches = [m for m in (resp.json() if resp.status_code == 200 else []) if m["game_id"]]
    if not matches:
        await callback.message.edit_text(
            "Hali boshlangan (tomosha qilsa bo'ladigan) o'yin yo'q.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:share:list")]
            ]),
        )
        await callback.answer()
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"{m['round']}-raund: #{m['player1_id']} vs #{m['player2_id']}",
            callback_data=f"admin:share:match:{tournament_id}:{m['id']}",
        )]
        for m in matches
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin:share:list")])
    await callback.message.edit_text("Qaysi o'yinni ulashamiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:share:match:"))
async def cb_share_match_selected(callback: types.CallbackQuery):
    _, _, _, tournament_id, match_id = callback.data.split(":")

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/api/tournaments/{tournament_id}/share-link/{match_id}")

    if resp.status_code != 200:
        await callback.answer(f"Xatolik: {resp.text}", show_alert=True)
        return

    link = resp.json()["link"]
    await callback.message.edit_text(f"🎥 O'yinni tomosha qilish:\n{link}", reply_markup=main_menu_keyboard())
    await callback.answer()


# =========================================================================
# Eski matn buyruqlar — kerak bo'lganda hali ham ishlaydi.
# =========================================================================

@router.message(Command("create_tournament"))
async def cmd_create_tournament(message: types.Message, command: CommandObject):
    """Usage: /create_tournament <name> <max_participants> [entry_fee]"""
    if not is_admin(message.from_user.id):
        await message.answer("Bu buyruq faqat adminlar uchun.")
        return

    if not command.args:
        await message.answer(
            "Foydalanish: /create_tournament <nomi> <max_ishtirokchi> [kirish_narxi]\n"
            "Yoki tugmali panel uchun: /admin"
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
            "created_by_name": message.from_user.full_name,
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
async def cmd_start_tournament(message: types.Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("Bu buyruq faqat adminlar uchun.")
        return

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
async def cmd_confirm_payment(message: types.Message, command: CommandObject):
    """Usage: /confirm_payment <tournament_id> <user_id>"""
    if not is_admin(message.from_user.id):
        await message.answer("Bu buyruq faqat adminlar uchun.")
        return

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
async def cmd_share_match(message: types.Message, command: CommandObject):
    """Usage: /share_match <tournament_id> <match_id>"""
    if not is_admin(message.from_user.id):
        await message.answer("Bu buyruq faqat adminlar uchun.")
        return

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
