import os
import sys
import shutil
import glob
import asyncio
import logging

logger = logging.getLogger(__name__)

def get_ffmpeg_cmd() -> str:
    """
    Finds available ffmpeg binary on system or package binaries (cross-platform).
    Supports Windows, Linux (Railway / Render / Docker), and macOS.
    """
    # 1. Try imageio_ffmpeg get_ffmpeg_exe() Python helper first
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception as e:
        logger.warning(f"imageio_ffmpeg get_ffmpeg_exe error: {e}")

    # 2. Check system PATH
    cmd = shutil.which("ffmpeg")
    if cmd:
        return cmd
    
    # 3. Check site-packages imageio_ffmpeg binaries (Windows/Linux)
    for p in sys.path:
        b_dir = os.path.join(p, "imageio_ffmpeg", "binaries")
        if os.path.exists(b_dir):
            exes = glob.glob(os.path.join(b_dir, "ffmpeg*"))
            if exes:
                return exes[0]

    return "ffmpeg"

async def extract_audio_ffmpeg(input_mp4: str, output_mp3: str) -> bool:
    """
    Extracts MP3 audio from input video file using FFmpeg.
    Command: ffmpeg -y -i <input_mp4> -vn -acodec libmp3lame -q:a 2 <output_mp3>
    """
    ffmpeg_exe = get_ffmpeg_cmd()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", input_mp4,
        "-vn",
        "-acodec", "libmp3lame",
        "-q:a", "2",
        output_mp3
    ]
    logger.info(f"Running audio extraction command: {' '.join(cmd)}")
    
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.warning(f"FFmpeg libmp3lame failed (code {proc.returncode}), trying default audio encoder...")
            cmd_fallback = [
                ffmpeg_exe,
                "-y",
                "-i", input_mp4,
                "-vn",
                "-q:a", "2",
                output_mp3
            ]
            proc_f = await asyncio.create_subprocess_exec(
                *cmd_fallback,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr_f = await proc_f.communicate()
            if proc_f.returncode != 0:
                logger.error(f"FFmpeg fallback audio extraction failed: {stderr_f.decode(errors='ignore')}")
                return False
                
        return os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 0
    except Exception as e:
        logger.exception(f"Error in extract_audio_ffmpeg: {e}")
        return False

async def convert_video_note_ffmpeg(input_mp4: str, output_note_mp4: str) -> bool:
    """
    Converts video into a Telegram Video Note (cropped 1:1, scaled to 640x640).
    Command: ffmpeg -y -i <input_mp4> -vf "crop=min(iw,ih):min(iw,ih),scale=640:640" -c:v libx264 -crf 23 -preset ultrafast -c:a aac <output_note_mp4>
    """
    ffmpeg_exe = get_ffmpeg_cmd()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", input_mp4,
        "-vf", "crop=min(iw,ih):min(iw,ih),scale=640:640",
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "ultrafast",
        "-c:a", "aac",
        output_note_mp4
    ]
    logger.info(f"Running video note conversion command: {' '.join(cmd)}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.warning(f"FFmpeg libx264 video note conversion failed (code {proc.returncode}), trying default video encoder...")
            cmd_fallback = [
                ffmpeg_exe,
                "-y",
                "-i", input_mp4,
                "-vf", "crop=min(iw,ih):min(iw,ih),scale=640:640",
                output_note_mp4
            ]
            proc_f = await asyncio.create_subprocess_exec(
                *cmd_fallback,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr_f = await proc_f.communicate()
            if proc_f.returncode != 0:
                logger.error(f"FFmpeg video note fallback failed: {stderr_f.decode(errors='ignore')}")
                return False

        return os.path.exists(output_note_mp4) and os.path.getsize(output_note_mp4) > 0
    except Exception as e:
        logger.exception(f"Error in convert_video_note_ffmpeg: {e}")
        return False
