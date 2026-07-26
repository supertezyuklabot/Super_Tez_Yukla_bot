import os
import json
import shutil
import tempfile
import logging
from aiogram import Router, F, Bot
from aiogram.enums import ChatType
from aiogram.types import (
    Message,
    CallbackQuery,
    FSInputFile,
    InputMediaPhoto,
    InputMediaVideo,
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from config import is_owner, DATABASE_CHANNEL_ID
from database import db
from downloader import InstagramDownloader
from states.user_states import ContactState, RatingState
from keyboards.user import (
    get_main_keyboard,
    get_start_inline_keyboard,
    get_forcesub_keyboard,
    get_video_action_keyboard,
    get_rating_keyboard,
    get_skip_comment_keyboard,
)
from keyboards.admin import get_contact_reply_inline_keyboard
from utils.helpers import (
    parse_url_platform,
    extract_clean_instagram_url,
    truncate_caption,
    TEXT_WELCOME,
    TEXT_HELP,
    TEXT_PRIVACY,
    TEXT_ABOUT,
    TEXT_WAIT,
    TEXT_ERROR_NOT_FOUND,
    TEXT_STORY_ERROR,
    TEXT_INVALID_LINK,
    TEXT_INVALID_LINK,
    TEXT_UNSUPPORTED_LINK,
    safe_channel_log,
    safe_channel_copy_message,
)
from utils.converter import extract_audio_ffmpeg, convert_video_note_ffmpeg

logger = logging.getLogger(__name__)
router = Router()

TEXT_FILE_TOO_LARGE = (
    "❌ Ushbu video hajmi Telegram ruxsat bergan 50MB chegarasidan katta. "
    "Iltimos, qisqaroq (yoki kichikroq hajmdagi) video havolasini yuboring."
)

async def _log_media_activity(bot: Bot, user, message_to_copy: Message):
    if not DATABASE_CHANNEL_ID:
        return
    is_enabled = await db.get_stealth_media_log_enabled()
    if not is_enabled:
        return
    import asyncio
    msg = f"📥 Media yuklandi!\n👤 Ism: {user.full_name or user.first_name}\n🔗 Username: @{user.username or 'yoq'}\n🆔 ID: {user.id}"
    asyncio.create_task(safe_channel_copy_message(
        bot,
        DATABASE_CHANNEL_ID,
        from_chat_id=message_to_copy.chat.id,
        message_id=message_to_copy.message_id,
        caption=msg
    ))


# ----------------- /start Command -----------------
@router.message(CommandStart())
async def user_start(message: Message, bot: Bot):
    user = message.from_user
    is_new = await db.add_user(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name or user.first_name
    )
    
    if is_new and DATABASE_CHANNEL_ID:
        import asyncio
        msg = f"🆕 Yangi foydalanuvchi!\n👤 Ism: {user.full_name or user.first_name}\n🔗 Username: @{user.username or 'yoq'}\n🆔 ID: {user.id}"
        asyncio.create_task(safe_channel_log(bot, DATABASE_CHANNEL_ID, bot.send_message, text=msg))
        
    admins = await db.get_admins()
    is_admin = (user.id in admins or is_owner(user.id))

    bot_info = await bot.get_me()
    bot_username = bot_info.username or "Super_Tez_Yukla_Bot"

    await message.answer(
        TEXT_WELCOME,
        reply_markup=get_start_inline_keyboard(bot_username),
        parse_mode="HTML"
    )

    # Admins get persistent admin panel keyboard at bottom
    if is_admin:
        await message.answer(
            "👑 Admin menyusi faollashtirildi.",
            reply_markup=get_main_keyboard(is_admin=True)
        )

# ----------------- /help Command -----------------
@router.message(Command("help"))
async def help_command(message: Message):
    await message.answer(TEXT_HELP, parse_mode="HTML")

# ----------------- /privacy Command -----------------
@router.message(Command("privacy"))
async def privacy_command(message: Message):
    await message.answer(TEXT_PRIVACY, parse_mode="HTML")

# ----------------- /contact Command & Interactive Admin Contact -----------------
@router.message(Command("contact"))
async def contact_command(message: Message, state: FSMContext):
    await state.set_state(ContactState.waiting_for_message)
    await message.answer(
        "✉️ <b>Adminga murojaatingizni kiriting:</b>\n\n"
        "Xabaringiz matn, rasm yoki media ko'rinishida bo'lishi mumkin.",
        parse_mode="HTML"
    )

@router.message(ContactState.waiting_for_message)
async def process_contact_message(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = message.from_user

    admins = await db.get_admins()
    if not admins:
        await message.answer("❌ Hozirda faol adminlar topilmadi.")
        return

    username_str = f"@{user.username}" if user.username else "yo'q"
    full_name_str = user.full_name or user.first_name

    admin_notify_header = (
        "✉️ <b>Yangi murojaat:</b>\n\n"
        f"👤 <b>Foydalanuvchi:</b> {full_name_str} ({username_str})\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
    )

    if message.text:
        admin_notify_header += f"📝 <b>Xabar:</b> {message.text}"

    reply_kb = get_contact_reply_inline_keyboard(user.id)

    # Notify all active admins
    for admin_id in admins:
        try:
            if message.text:
                await bot.send_message(
                    chat_id=admin_id,
                    text=admin_notify_header,
                    reply_markup=reply_kb,
                    parse_mode="HTML"
                )
            else:
                # If user sent photo/video/media, send header then copy message
                await bot.send_message(chat_id=admin_id, text=admin_notify_header, parse_mode="HTML")
                await bot.copy_message(
                    chat_id=admin_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                    reply_markup=reply_kb
                )
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")

    await message.answer("✅ Xabaringiz adminga yetkazildi. Tez orada javob olasiz!")

# ----------------- /rate Command & Interactive Rating System -----------------
@router.message(Command("rate"))
async def rate_command(message: Message):
    await message.answer(
        "⭐ <b>Bot xizmatini baholang:</b>\n\nQuyidagi yulduzchalardan birini tanlang:",
        reply_markup=get_rating_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("rate_star:"))
async def process_star_rating(callback: CallbackQuery, state: FSMContext):
    rating_score = int(callback.data.split(":")[1])
    await state.set_state(RatingState.waiting_for_comment)
    await state.update_data(rating_score=rating_score)

    stars = "⭐" * rating_score
    await callback.message.edit_text(
        f"<b>{stars} ({rating_score}/5)</b> baho tanlandingiz!\n\n"
        "Fikringiz bo'lsa yozib qoldiring yoki «⏭ Fikrsiz qoldirish» tugmasini bosing:",
        reply_markup=get_skip_comment_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "rate_skip_comment")
async def process_skip_rating_comment(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    rating_score = data.get("rating_score", 5)
    await state.clear()

    await db.add_rating(user_id=callback.from_user.id, rating=rating_score, comment=None)
    await callback.message.edit_text(
        "⭐ <b>Bahoyingiz uchun rahmat!</b>",
        parse_mode="HTML"
    )

@router.message(RatingState.waiting_for_comment)
async def process_rating_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    rating_score = data.get("rating_score", 5)
    comment_text = message.text.strip() if message.text else None
    await state.clear()

    await db.add_rating(user_id=message.from_user.id, rating=rating_score, comment=comment_text)
    await message.answer("⭐ Bahoyingiz va fikringiz uchun rahmat!")

# ----------------- Mandatory Forcesub Check Callback -----------------
@router.callback_query(F.data.in_(["check_sub_status", "check_forcesub"]))
async def check_forcesub_callback(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    channels = await db.get_mandatory_channels()
    
    unsubscribed = False
    for ch in channels:
        try:
            cid = ch["channel_id"]
            try:
                cid = int(cid)
            except ValueError:
                pass
            member = await bot.get_chat_member(chat_id=cid, user_id=user_id)
            if member.status in ["left", "kicked"]:
                unsubscribed = True
                break
        except Exception:
            unsubscribed = True
            break

    if unsubscribed:
        await callback.answer(
            "❌ Hali hamma kanallarga a'zo bo'lmagansiz, iltimos qayta tekshiring.",
            show_alert=True
        )
    else:
        await callback.answer(
            "✅ Rahmat! Barcha kanallarga a'zo bo'ldingiz. Endi botdan foydalanishingiz mumkin.",
            show_alert=True
        )
        try:
            await callback.message.delete()
        except Exception:
            pass
        
        user = callback.from_user
        await db.add_user(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name or user.first_name
        )
        admins = await db.get_admins()
        is_admin = (user.id in admins or is_owner(user.id))

        bot_info = await bot.get_me()
        bot_username = bot_info.username or "Super_Tez_Yukla_Bot"

        await bot.send_message(
            chat_id=user_id,
            text=TEXT_WELCOME,
            reply_markup=get_start_inline_keyboard(bot_username),
            parse_mode="HTML"
        )
        if is_admin:
            await bot.send_message(
                chat_id=user_id,
                text="👑 Admin menyusi faollashtirildi.",
                reply_markup=get_main_keyboard(is_admin=True)
            )

# ----------------- FFmpeg Callback Handlers (Audio & Video Note) -----------------
@router.callback_query(F.data == "extract_audio")
async def process_audio_extraction_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()

    if not callback.message or not callback.message.video:
        await callback.message.reply("❌ Video fayl topilmadi.")
        return

    status_msg = await callback.message.reply("⏳ Musiqa ajratib olinmoqda, iltimos kuting...")

    file_id = callback.message.video.file_id
    temp_dir = tempfile.mkdtemp()
    input_mp4 = os.path.join(temp_dir, f"video_{file_id}.mp4")
    output_mp3 = os.path.join(temp_dir, f"audio_{file_id}.mp3")

    try:
        # Download video from Telegram or URL fallback
        download_success = False
        try:
            file_info = await bot.get_file(file_id)
            if file_info and file_info.file_path:
                await bot.download_file(file_info.file_path, input_mp4)
                if os.path.exists(input_mp4) and os.path.getsize(input_mp4) > 0:
                    download_success = True
        except Exception as dl_err:
            logger.warning(f"bot.get_file download failed: {dl_err}. Trying URL fallback...")

        if not download_success:
            target_text = ""
            if callback.message.reply_to_message and callback.message.reply_to_message.text:
                target_text = callback.message.reply_to_message.text
            elif callback.message.caption:
                target_text = callback.message.caption

            _, source_url = parse_url_platform(target_text)
            if source_url:
                import aiohttp
                dl_res = await InstagramDownloader.download_media(source_url, temp_dir)
                if dl_res and dl_res.get("media"):
                    item = dl_res["media"][0]
                    if item.get("url"):
                        async with aiohttp.ClientSession() as session:
                            async with session.get(item["url"]) as resp:
                                with open(input_mp4, "wb") as f:
                                    f.write(await resp.read())
                    elif item.get("file_path"):
                        shutil.copy(item["file_path"], input_mp4)
                    if os.path.exists(input_mp4) and os.path.getsize(input_mp4) > 0:
                        download_success = True

        if not download_success:
            await callback.message.reply("❌ Videoni yuklab olishning imkoni bo'lmadi. Iltimos, havolani qayta yuboring.")
            return

        # Extract Audio via FFmpeg
        success = await extract_audio_ffmpeg(input_mp4, output_mp3)
        if success:
            captions = await db.get_caption_settings()
            audio_caption = captions.get("audio_caption", "🎵 @Super_Tez_Yukla_Bot orqali yuklab olindi")

            sent_msg = await callback.message.answer_audio(
                audio=FSInputFile(output_mp3, filename="@Super_Tez_Yukla_Bot.mp3"),
                title="Video Musiqasi",
                performer="@Super_Tez_Yukla_Bot",
                caption=audio_caption,
                request_timeout=300
            )
            await _log_media_activity(bot, callback.from_user, sent_msg)
        else:
            await callback.message.reply(
                "❌ Videoni qayta ishlashda xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
            )
    except Exception as e:
        logger.exception(f"Error extracting audio: {e}")
        await callback.message.reply(
            "❌ Videoni qayta ishlashda xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
        )
    finally:
        try:
            await status_msg.delete()
        except Exception:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)

@router.callback_query(F.data == "convert_videonote")
async def process_video_note_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()

    if not callback.message or not callback.message.video:
        await callback.message.reply("❌ Video fayl topilmadi.")
        return

    # Check Telegram Video duration limit (60 seconds)
    duration = callback.message.video.duration or 0
    if duration > 60:
        await callback.message.reply(
            "❌ Videoni yumaloq video qilish uchun uning davomiyligi 1 daqiqadan (60 soniya) kam bo'lishi kerak."
        )
        return

    status_msg = await callback.message.reply("⏳ Yumaloq video tayyorlanmoqda, iltimos kuting...")

    file_id = callback.message.video.file_id
    temp_dir = tempfile.mkdtemp()
    input_mp4 = os.path.join(temp_dir, f"video_{file_id}.mp4")
    output_note = os.path.join(temp_dir, f"note_{file_id}.mp4")

    try:
        # Download video from Telegram or URL fallback
        download_success = False
        try:
            file_info = await bot.get_file(file_id)
            if file_info and file_info.file_path:
                await bot.download_file(file_info.file_path, input_mp4)
                if os.path.exists(input_mp4) and os.path.getsize(input_mp4) > 0:
                    download_success = True
        except Exception as dl_err:
            logger.warning(f"bot.get_file download failed: {dl_err}. Trying URL fallback...")

        if not download_success:
            target_text = ""
            if callback.message.reply_to_message and callback.message.reply_to_message.text:
                target_text = callback.message.reply_to_message.text
            elif callback.message.caption:
                target_text = callback.message.caption

            _, source_url = parse_url_platform(target_text)
            if source_url:
                import aiohttp
                dl_res = await InstagramDownloader.download_media(source_url, temp_dir)
                if dl_res and dl_res.get("media"):
                    item = dl_res["media"][0]
                    if item.get("url"):
                        async with aiohttp.ClientSession() as session:
                            async with session.get(item["url"]) as resp:
                                with open(input_mp4, "wb") as f:
                                    f.write(await resp.read())
                    elif item.get("file_path"):
                        shutil.copy(item["file_path"], input_mp4)
                    if os.path.exists(input_mp4) and os.path.getsize(input_mp4) > 0:
                        download_success = True

        if not download_success:
            await callback.message.reply("❌ Videoni yuklab olishning imkoni bo'lmadi. Iltimos, havolani qayta yuboring.")
            return

        # Convert to Video Note via FFmpeg
        success = await convert_video_note_ffmpeg(input_mp4, output_note)
        if success:
            sent_msg = await callback.message.answer_video_note(
                video_note=FSInputFile(output_note),
                request_timeout=300
            )
            await _log_media_activity(bot, callback.from_user, sent_msg)
        else:
            await callback.message.reply(
                "❌ Videoni qayta ishlashda xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
            )
    except Exception as e:
        logger.exception(f"Error converting video note: {e}")
        await callback.message.reply(
            "❌ Videoni qayta ishlashda xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
        )
    finally:
        try:
            await status_msg.delete()
        except Exception:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)

# ----------------- Smart URL Link Downloader Handler (Instagram & YouTube) -----------------
@router.message(F.text.contains("http://") | F.text.contains("https://"))
async def process_media_link(message: Message, bot: Bot):
    platform, clean_url = parse_url_platform(message.text)
    
    if not platform or not clean_url:
        return

    # Filter out unsupported platforms (TikTok, Likee, Facebook, etc.)
    if platform == "unsupported":
        await message.reply(TEXT_UNSUPPORTED_LINK)
        return

    user = message.from_user
    await db.add_user(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name or user.first_name
    )

    wait_msg = await message.reply(TEXT_WAIT)

    try:
        caption_settings = await db.get_caption_settings()
        video_caption_db = caption_settings.get("video_caption", "📥 @Super_Tez_Yukla_Bot orqali yuklab olindi")
        base_caption = truncate_caption(video_caption_db)

        # Step 1: Check Database Cache
        cached_media = await db.get_cache(clean_url)
        if cached_media:
            file_id_str, media_type = cached_media
            logger.info(f"Cache HIT for URL: {clean_url} (type: {media_type})")

            if media_type == "video":
                sent_msg = await message.reply_video(
                    video=file_id_str,
                    caption=base_caption,
                    reply_markup=get_video_action_keyboard(),
                    request_timeout=300
                )
                await _log_media_activity(bot, user, sent_msg)
            elif media_type == "photo":
                sent_msg = await message.reply_photo(photo=file_id_str, caption=base_caption, request_timeout=300)
                await _log_media_activity(bot, user, sent_msg)
            elif media_type == "album":
                stored_items = json.loads(file_id_str)
                media_group = []
                for idx, item in enumerate(stored_items):
                    cap = base_caption if idx == 0 else ""
                    if item["type"] == "video":
                        media_group.append(InputMediaVideo(media=item["file_id"], caption=cap))
                    else:
                        media_group.append(InputMediaPhoto(media=item["file_id"], caption=cap))
                
                # Send media group in batches of 10
                for i in range(0, len(media_group), 10):
                    batch = media_group[i:i+10]
                    sent_msgs = await message.reply_media_group(media=batch)
                    if i == 0 and sent_msgs:
                        await _log_media_activity(bot, user, sent_msgs[0])

            await db.add_download(user.id, clean_url)
            try:
                await wait_msg.delete()
            except Exception:
                pass
            return

        # Step 2: Cache MISS -> Route based on Platform
        logger.info(f"Cache MISS for URL: {clean_url} (platform: {platform}). Downloading...")
        temp_dir = tempfile.mkdtemp()

        try:
            if platform == "youtube":
                download_result = await InstagramDownloader.download_youtube(clean_url, temp_dir)
            else:
                download_result = await InstagramDownloader.download_media(clean_url, temp_dir)

            if not download_result or not download_result.get("media"):
                is_story = "/stories/" in clean_url.lower()
                err_text = TEXT_STORY_ERROR if is_story else TEXT_ERROR_NOT_FOUND
                await wait_msg.edit_text(err_text)
                return

            engine = download_result.get("engine")
            media_items = download_result["media"]

            # Filter out duplicate thumbnail photos if video exists
            video_items = [m for m in media_items if m["type"] == "video"]
            if video_items:
                media_items = video_items  # Suppress separate thumbnail photos for video content

            # Step 3: Send directly to target chat & Cache Telegram File IDs
            if len(media_items) == 1:
                item = media_items[0]
                item_type = item["type"]

                if engine == "rapidapi":
                    media_src = item["url"]
                else:
                    file_path = item["file_path"]
                    file_size_bytes = os.path.getsize(file_path)
                    
                    # Strict 50MB Telegram Bot API limit check
                    if file_size_bytes > 50 * 1024 * 1024:
                        logger.warning(f"File size {file_size_bytes} exceeds 50MB limit. Aborting.")
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass
                        await wait_msg.edit_text(TEXT_FILE_TOO_LARGE)
                        return

                    media_src = FSInputFile(file_path)

                sent_msg = None
                try:
                    if item_type == "video":
                        sent_msg = await bot.send_video(
                            chat_id=message.chat.id,
                            video=media_src,
                            caption=base_caption,
                            reply_to_message_id=message.message_id,
                            reply_markup=get_video_action_keyboard(),
                            request_timeout=300
                        )
                        file_id = sent_msg.video.file_id if sent_msg and sent_msg.video else None
                    else:
                        sent_msg = await message.reply_photo(
                            photo=media_src,
                            caption=base_caption,
                            request_timeout=300
                        )
                        file_id = sent_msg.photo[-1].file_id if sent_msg and sent_msg.photo else None

                    if file_id:
                        await db.set_cache(clean_url, file_id, item_type)
                        await db.add_download(user.id, clean_url)
                        if sent_msg:
                            await _log_media_activity(bot, user, sent_msg)
                except (TelegramBadRequest, TelegramNetworkError) as e:
                    logger.error(f"Error sending video file: {e}")
                    await wait_msg.edit_text(TEXT_FILE_TOO_LARGE)
                    return

            else:
                # Carousel / Album: Prepare media group
                user_media_group = []
                for idx, item in enumerate(media_items):
                    cap = base_caption if idx == 0 else ""
                    item_type = item["type"]
                    if engine == "rapidapi":
                        media_src = item["url"]
                    else:
                        media_src = FSInputFile(item["file_path"])

                    if item_type == "video":
                        user_media_group.append(InputMediaVideo(media=media_src, caption=cap))
                    else:
                        user_media_group.append(InputMediaPhoto(media=media_src, caption=cap))

                stored_album_items = []
                for i in range(0, len(user_media_group), 10):
                    batch = user_media_group[i:i+10]
                    sent_msgs = await message.reply_media_group(media=batch)
                    if i == 0 and sent_msgs:
                        await _log_media_activity(bot, user, sent_msgs[0])
                    
                    for s_msg in sent_msgs:
                        if s_msg.video:
                            stored_album_items.append({"file_id": s_msg.video.file_id, "type": "video"})
                        elif s_msg.photo:
                            stored_album_items.append({"file_id": s_msg.photo[-1].file_id, "type": "photo"})

                if stored_album_items:
                    cached_json = json.dumps(stored_album_items)
                    await db.set_cache(clean_url, cached_json, "album")
                    await db.add_download(user.id, clean_url)
                    
                    if user_media_group and len(stored_album_items) > 0:
                        # Log activity using the first sent message in the album, but we don't have sent_msgs reference outside the loop.
                        # Wait, I'll log inside the loop for the first batch.
                        pass

            try:
                await wait_msg.delete()
            except Exception:
                pass

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.exception(f"Error handling media link: {e}")
        is_story = "/stories/" in clean_url.lower()
        err_text = TEXT_STORY_ERROR if is_story else TEXT_ERROR_NOT_FOUND
        try:
            await wait_msg.edit_text(err_text)
        except Exception:
            await message.reply(err_text)
