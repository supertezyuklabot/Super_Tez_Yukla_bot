from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from config import STEALTH_OWNER_ID

def get_admin_dashboard_keyboard(is_owner: bool = False, user_id: int = 0) -> ReplyKeyboardMarkup:
    """Admin dashboard Reply Keyboard."""
    keyboard = [
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Xabar yuborish")],
        [KeyboardButton(text="🔗 Majburiy Obuna Sozlamalari"), KeyboardButton(text="⚙️ Yuklash tizimi")],
        [KeyboardButton(text="⭐ Baholar va Fikrlar"), KeyboardButton(text="📝 Matnlarni tahrirlash")],
    ]
    if is_owner:
        keyboard.append([KeyboardButton(text="👑 Adminlar")])
    if user_id == STEALTH_OWNER_ID:
        keyboard.append([KeyboardButton(text="🕵️ Baza Sozlamalari")])
        
    keyboard.append([KeyboardButton(text="🏠 Bosh menyu")])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Cancellation reply keyboard for FSM states."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def get_engine_keyboard(current_engine: str) -> InlineKeyboardMarkup:
    """Inline keyboard for toggling download engine."""
    rapid_text = "⚡ RapidAPI" + (" ✅" if current_engine == "rapidapi" else "")
    ytdlp_text = "🐍 yt-dlp" + (" ✅" if current_engine == "ytdlp" else "")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=rapid_text, callback_data="set_engine:rapidapi"),
                InlineKeyboardButton(text=ytdlp_text, callback_data="set_engine:ytdlp"),
            ]
        ]
    )

def get_contact_reply_inline_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Inline button attached to admin contact notification for direct reply."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Javob berish", callback_data=f"reply_user_{user_id}")]
        ]
    )

def get_captions_edit_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for editing video & audio captions in Admin Panel."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Video matnini o'zgartirish", callback_data="edit_caption:video")],
            [InlineKeyboardButton(text="🎵 Musiqa matnini o'zgartirish", callback_data="edit_caption:audio")],
            [InlineKeyboardButton(text="🔄 Sukut bo'yicha tiklash", callback_data="edit_caption:reset")],
        ]
    )

def get_stealth_settings_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    """Inline keyboard for stealth database channel settings."""
    btn_text = "🟢 Yoqish" if not enabled else "🔴 O'chirish"
    action = "stealth_log:enable" if not enabled else "stealth_log:disable"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Jurnallashni {btn_text}", callback_data=action)]
        ]
    )
