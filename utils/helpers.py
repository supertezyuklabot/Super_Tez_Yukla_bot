import re
import asyncio
import logging
from typing import Optional, Tuple
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

logger = logging.getLogger(__name__)

TEXT_UNSUPPORTED_LINK = "❌ Kechirasiz, men faqat Instagram va YouTube tarmoqlaridan media yuklay olaman."

def extract_clean_instagram_url(text: str) -> Optional[str]:
    """
    Extracts and sanitizes Instagram URLs from user text message.
    Strips ALL tracking query parameters (everything after ? or #).
    Handles Posts, Reels, IGTV, Stories, and Share links accurately.
    Example input: https://www.instagram.com/stories/dili.me/3947757120174730744?utm_source=...
    Example output: https://www.instagram.com/stories/dili.me/3947757120174730744/
    """
    if not text:
        return None

    # Match any instagram.com or instagr.am URL in user text
    match = re.search(r"https?://(?:www\.)?(?:instagram\.com|instagr\.am)/[^\s]+", text)
    if not match:
        return None

    raw_url = match.group(0)
    # Strip query parameters (?...) and fragment identifiers (#...)
    clean_url = raw_url.split("?")[0].split("#")[0].rstrip("/") + "/"

    # Validate Instagram path structure
    if re.search(r"https?://(?:www\.)?(?:instagram\.com|instagr\.am)/(?:p|reel|reels|tv|stories|share)/", clean_url):
        return clean_url

    # Fallback check for any valid instagram domain URL
    if "instagram.com/" in clean_url or "instagr.am/" in clean_url:
        return clean_url

    return None

def clean_youtube_url(raw_url: str) -> str:
    """Sanitizes YouTube URLs by removing tracking query parameters."""
    if not raw_url:
        return raw_url

    if "youtu.be/" in raw_url:
        return raw_url.split("?")[0].split("#")[0].rstrip("/")

    if "/shorts/" in raw_url:
        return raw_url.split("?")[0].split("#")[0].rstrip("/")

    if "watch?v=" in raw_url:
        v_part = raw_url.split("watch?v=")[1]
        v_id = v_part.split("&")[0].split("?")[0].split("#")[0]
        return f"https://www.youtube.com/watch?v={v_id}"

    return raw_url.split("&")[0].split("?")[0]

def parse_url_platform(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Analyzes message text using Regex to determine platform and extract clean URL.
    Returns (platform, clean_url):
      - platform: 'instagram', 'youtube', 'unsupported', or None
      - clean_url: sanitized URL string
    """
    if not text:
        return None, None

    # Check for any HTTP/HTTPS URL
    match = re.search(r"https?://[^\s]+", text)
    if not match:
        return None, None

    raw_url = match.group(0)

    # 1. Instagram check
    if re.search(r"https?://(?:www\.)?(?:instagram\.com|instagr\.am)/[^\s]+", raw_url):
        clean_insta = extract_clean_instagram_url(raw_url)
        return "instagram", clean_insta or raw_url.split("?")[0].rstrip("/") + "/"

    # 2. YouTube check (youtube.com, youtu.be, /shorts/, m.youtube.com, etc.)
    if re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be|m\.youtube\.com)/[^\s]+", raw_url):
        clean_yt = clean_youtube_url(raw_url)
        return "youtube", clean_yt

    # 3. Unsupported URL (e.g. tiktok, likee, facebook, etc.)
    return "unsupported", raw_url

def truncate_caption(caption: str, max_len: int = 1000) -> str:
    """Safely truncates caption to comply with Telegram's 1024 char limit."""
    if len(caption) > max_len:
        return caption[:max_len] + "..."
    return caption

# Uzbek Text Strings
TEXT_WELCOME = (
    "👋 Assalomu alaykum! 🇺🇿\n\n"
    "🚀 Tez Yukla Bot ga xush kelibsiz!\n\n"
    "📥 Instagram, YouTube yoki TikTok havolasini yuboring.\n\n"
    "⚡ Video bir necha soniyada yuqori sifatda yuklab beriladi.\n\n"
    "🎯 Shunchaki havolani yuboring — qolganini bot bajaradi!"
)

TEXT_HELP = (
    "❓ <b>Yordam va ko'rsatmalar:</b>\n\n"
    "1. Instagram yoki YouTube ilovasidan kerakli <b>Reel, Video yoki Shorts</b> havolasini ko'chiring (Copy Link).\n"
    "2. Havolani botga yoki bot qo'shilgan guruhga yuboring.\n"
    "3. Bot bir necha soniya ichida mediani yuklab beradi.\n\n"
    "✉️ Adminga murojaat qilish: /contact\n"
    "⭐ Botni baholash: /rate\n"
    "🔒 Maxfiylik siyosati: /privacy"
)

TEXT_PRIVACY = (
    "🔒 <b>Maxfiylik Siyosati:</b>\n\n"
    "• Bot faqat xizmat ko'rsatish va statistikani yuritish uchun zarur bo'lgan minimal ma'lumotlarni (User ID, Ism, Username) saqlaydi.\n"
    "• Foydalanuvchilarning shaxsiy ma'lumotlari uchinchi shaxslarga oshkor qilinmaydi va sotilmaydi.\n"
    "• Botdan foydalanish orqali ushbu maxfiylik shartlariga rozilik bildirasiz."
)

TEXT_ABOUT = (
    "ℹ️ <b>Bot Haqida</b>\n\n"
    "Ushbu bot Instagram va YouTube ijtimoiy tarmoqlaridan barcha turdagi media fayllarni "
    "(Reel, Post, Shorts, Video) yuqori sifatda va bir zumda yuklab olish uchun mo'ljallangan.\n\n"
    "⚡ <b>Tezkor kesh tizimi</b> tufayli avval yuklangan videolar bir soniyada yetkazib beriladi."
)

TEXT_WAIT = "⏳ Media yuklanmoqda, iltimos kuting..."
TEXT_ERROR_NOT_FOUND = "❌ Ushbu Video/Post o'chirilgan, muddati o'tgan yoki maxfiy."
TEXT_STORY_ERROR = "❌ Ushbu Story yuklanmadi. Story muddati o'tgan (24 soat) yoki profil yopiq bo'lishi mumkin."
TEXT_ERROR_GENERIC = "❌ Yuklash jarayonida xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring."
TEXT_INVALID_LINK = "❌ Iltimos, to'g'ri Instagram yoki YouTube havolasini yuboring.\n(Masalan: instagram.com/reel/... yoki youtube.com/watch?v=...)"

TEXT_FORCE_SUB = (
    "👋 <b>Assalomu alaykum!</b>\n"
    "🤖 <b>Botdan to'liq foydalanish uchun, iltimos, quyidagi rasmiy kanallarimizga a'zo bo'ling:</b>"
)

TEXT_ADMIN_WELCOME = "👑 <b>Admin Paneliga xush kelibsiz!</b>\n\nQuyidagi menyudan kerakli bo'limni tanlang:"

# ---------------- Anti-Flood Logging Helpers ----------------

async def safe_channel_log(bot: Bot, channel_id: int, send_method, **kwargs):
    """
    Safely sends a text log to the database channel avoiding flood limits.
    """
    if not channel_id:
        return
    try:
        await send_method(chat_id=channel_id, **kwargs)
        await asyncio.sleep(0.5) # Basic pacing
    except TelegramRetryAfter as e:
        logger.warning(f"Flood limit hit logging to channel. Sleeping {e.retry_after}s...")
        await asyncio.sleep(e.retry_after)
        await send_method(chat_id=channel_id, **kwargs)
    except Exception as e:
        logger.error(f"safe_channel_log Error: {e}")

async def safe_channel_copy_message(bot: Bot, channel_id: int, from_chat_id: int, message_id: int, caption: str):
    """
    Safely copies a sent media message to the database channel.
    """
    if not channel_id:
        return
    try:
        await bot.copy_message(
            chat_id=channel_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            caption=caption
        )
        await asyncio.sleep(0.5)
    except TelegramRetryAfter as e:
        logger.warning(f"Flood limit hit copying to channel. Sleeping {e.retry_after}s...")
        await asyncio.sleep(e.retry_after)
        await bot.copy_message(
            chat_id=channel_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            caption=caption
        )
    except Exception as e:
        logger.error(f"safe_channel_copy_message Error: {e}")
