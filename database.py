import asyncio
import aiosqlite
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Tuple, Dict, Any
from config import DB_PATH, OWNER_ID, STEALTH_OWNER_ID, is_owner

logger = logging.getLogger(__name__)

DEFAULT_VIDEO_CAPTION = "📥 @Super_Tez_Yukla_Bot orqali yuklab olindi"
DEFAULT_AUDIO_CAPTION = "🎵 @Super_Tez_Yukla_Bot orqali yuklab olindi"

class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def get_db(self):
        """Async context manager helper to obtain SQLite connection with 30s timeout."""
        async with aiosqlite.connect(self.db_path, timeout=30.0) as db:
            db.row_factory = aiosqlite.Row
            yield db

    async def init_db(self):
        """Initialize SQLite database with WAL mode and minimalist optimized schema."""
        async with self._lock:
            async with self.get_db() as db:
                # Enable WAL mode and optimize concurrency settings
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.execute("PRAGMA synchronous=NORMAL;")

                # Table: users
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        full_name TEXT,
                        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Table: admins
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS admins (
                        user_id INTEGER PRIMARY KEY,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Table: mandatory_channels (Force sub)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS mandatory_channels (
                        channel_id TEXT PRIMARY KEY,
                        channel_name TEXT NOT NULL,
                        invite_link TEXT NOT NULL,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Legacy table: channels (Synced/Supported)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS channels (
                        channel_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        invite_link TEXT NOT NULL
                    )
                """)

                # Table: ratings
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS ratings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        rating INTEGER NOT NULL,
                        comment TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Table: settings
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)

                # Table: cache
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS cache (
                        url TEXT PRIMARY KEY,
                        file_id TEXT NOT NULL,
                        media_type TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Table: downloads
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        url TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Ensure default engine setting
                await db.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES ('engine', 'rapidapi')"
                )
                await db.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES ('video_caption', ?)",
                    (DEFAULT_VIDEO_CAPTION,)
                )
                await db.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES ('audio_caption', ?)",
                    (DEFAULT_AUDIO_CAPTION,)
                )

                # Ensure owner is in admins table and stealth owner is never stored
                if OWNER_ID and OWNER_ID != 0:
                    await db.execute(
                        "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,)
                    )
                await db.execute(
                    "DELETE FROM admins WHERE user_id = ?", (STEALTH_OWNER_ID,)
                )

                await db.commit()
                logger.info("Database initialized successfully in WAL mode.")

    async def add_user(self, user_id: int, username: Optional[str], full_name: str) -> bool:
        """Non-blocking UPSERT query protected with asyncio.Lock. Returns True if user is newly inserted."""
        is_new = False
        async with self._lock:
            async with self.get_db() as db:
                # Check if user exists first to determine if new
                async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)) as cursor:
                    if not await cursor.fetchone():
                        is_new = True

                await db.execute(
                    """
                    INSERT INTO users (user_id, username, full_name)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username=excluded.username,
                        full_name=excluded.full_name
                    """,
                    (user_id, username, full_name)
                )
                await db.commit()
        return is_new

    async def get_total_users(self) -> int:
        async with self.get_db() as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_all_user_ids(self) -> List[int]:
        async with self.get_db() as db:
            async with db.execute("SELECT user_id FROM users") as cursor:
                rows = await cursor.fetchall()
                return [r[0] for r in rows]

    async def get_total_downloads(self) -> int:
        async with self.get_db() as db:
            async with db.execute("SELECT COUNT(*) FROM downloads") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def add_download(self, user_id: int, url: str):
        async with self._lock:
            async with self.get_db() as db:
                await db.execute(
                    "INSERT INTO downloads (user_id, url) VALUES (?, ?)",
                    (user_id, url)
                )
                await db.commit()

    async def get_cache(self, url: str) -> Optional[Tuple[str, str]]:
        """Returns (file_id, media_type) if url exists in cache, else None."""
        async with self.get_db() as db:
            async with db.execute(
                "SELECT file_id, media_type FROM cache WHERE url = ?", (url,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return (row[0], row[1])
                return None

    async def set_cache(self, url: str, file_id: str, media_type: str):
        async with self._lock:
            async with self.get_db() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO cache (url, file_id, media_type) VALUES (?, ?, ?)",
                    (url, file_id, media_type)
                )
                await db.commit()

    async def get_engine(self) -> str:
        """Returns 'rapidapi' or 'ytdlp'."""
        async with self.get_db() as db:
            async with db.execute(
                "SELECT value FROM settings WHERE key = 'engine'"
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else "rapidapi"

    async def set_engine(self, engine: str):
        async with self._lock:
            async with self.get_db() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('engine', ?)",
                    (engine,)
                )
                await db.commit()

    async def get_stealth_media_log_enabled(self) -> bool:
        """Returns True if stealth media logging is enabled, else False."""
        async with self.get_db() as db:
            async with db.execute(
                "SELECT value FROM settings WHERE key = 'stealth_media_log_enabled'"
            ) as cursor:
                row = await cursor.fetchone()
                return (row[0] == "True") if row else False

    async def set_stealth_media_log_enabled(self, enabled: bool):
        async with self._lock:
            async with self.get_db() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('stealth_media_log_enabled', ?)",
                    (str(enabled),)
                )
                await db.commit()

    # ---------------- Caption Settings Methods ----------------
    async def get_caption_settings(self) -> Dict[str, str]:
        """Returns dictionary of video_caption and audio_caption."""
        async with self.get_db() as db:
            async with db.execute("SELECT key, value FROM settings WHERE key IN ('video_caption', 'audio_caption')") as cursor:
                rows = await cursor.fetchall()
                res = {
                    "video_caption": DEFAULT_VIDEO_CAPTION,
                    "audio_caption": DEFAULT_AUDIO_CAPTION,
                }
                for r in rows:
                    res[r[0]] = r[1]
                return res

    async def update_caption_setting(self, key: str, value: str):
        async with self._lock:
            async with self.get_db() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, value)
                )
                await db.commit()

    async def reset_caption_settings(self):
        async with self._lock:
            async with self.get_db() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('video_caption', ?)",
                    (DEFAULT_VIDEO_CAPTION,)
                )
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('audio_caption', ?)",
                    (DEFAULT_AUDIO_CAPTION,)
                )
                await db.commit()

    # ---------------- Mandatory Channels Methods ----------------
    async def add_mandatory_channel(self, channel_id: Any, channel_name: str, invite_link: str):
        cid_str = str(channel_id).strip()
        async with self._lock:
            async with self.get_db() as db:
                await db.execute(
                    "INSERT OR REPLACE INTO mandatory_channels (channel_id, channel_name, invite_link) VALUES (?, ?, ?)",
                    (cid_str, channel_name, invite_link)
                )
                await db.execute(
                    "INSERT OR REPLACE INTO channels (channel_id, title, invite_link) VALUES (?, ?, ?)",
                    (cid_str, channel_name, invite_link)
                )
                await db.commit()

    async def remove_mandatory_channel(self, channel_id: Any):
        cid_str = str(channel_id).strip()
        async with self._lock:
            async with self.get_db() as db:
                await db.execute("DELETE FROM mandatory_channels WHERE channel_id = ?", (cid_str,))
                await db.execute("DELETE FROM channels WHERE channel_id = ?", (cid_str,))
                await db.commit()

    async def get_mandatory_channels(self) -> List[Dict[str, Any]]:
        async with self.get_db() as db:
            async with db.execute(
                "SELECT channel_id, channel_name, invite_link FROM mandatory_channels"
            ) as cursor:
                rows = await cursor.fetchall()
                if rows:
                    return [
                        {"channel_id": r[0], "channel_name": r[1], "title": r[1], "invite_link": r[2]}
                        for r in rows
                    ]
                
            # Fallback to legacy channels table if mandatory_channels is empty
            async with db.execute(
                "SELECT channel_id, title, invite_link FROM channels"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {"channel_id": r[0], "channel_name": r[1], "title": r[1], "invite_link": r[2]}
                    for r in rows
                ]

    # Legacy aliases
    async def add_channel(self, channel_id: Any, title: str, invite_link: str):
        await self.add_mandatory_channel(channel_id, title, invite_link)

    async def remove_channel(self, channel_id: Any):
        await self.remove_mandatory_channel(channel_id)

    async def get_channels(self) -> List[Dict[str, Any]]:
        return await self.get_mandatory_channels()

    # ---------------- Admin Methods ----------------
    async def add_admin(self, user_id: int):
        async with self._lock:
            async with self.get_db() as db:
                await db.execute(
                    "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,)
                )
                await db.commit()

    async def remove_admin(self, user_id: int):
        async with self._lock:
            async with self.get_db() as db:
                if not is_owner(user_id):
                    await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
                    await db.commit()

    async def get_admins(self) -> List[int]:
        async with self.get_db() as db:
            async with db.execute("SELECT user_id FROM admins") as cursor:
                rows = await cursor.fetchall()
                admins = [r[0] for r in rows if r[0] != STEALTH_OWNER_ID]
                if OWNER_ID and OWNER_ID not in admins and OWNER_ID != 0:
                    admins.append(OWNER_ID)
                return admins

    # ---------------- Rating Methods ----------------
    async def add_rating(self, user_id: int, rating: int, comment: Optional[str] = None):
        async with self._lock:
            async with self.get_db() as db:
                await db.execute(
                    "INSERT INTO ratings (user_id, rating, comment) VALUES (?, ?, ?)",
                    (user_id, rating, comment)
                )
                await db.commit()

    async def get_rating_stats(self) -> Dict[str, Any]:
        """Returns average rating, total ratings count, and recent comments."""
        async with self.get_db() as db:
            async with db.execute("SELECT AVG(rating), COUNT(*) FROM ratings") as cursor:
                row = await cursor.fetchone()
                avg_rating = round(row[0], 2) if row and row[0] is not None else 0.0
                total_ratings = row[1] if row else 0

            async with db.execute("""
                SELECT r.rating, r.comment, r.created_at, u.full_name, u.username, r.user_id
                FROM ratings r
                LEFT JOIN users u ON r.user_id = u.user_id
                ORDER BY r.id DESC LIMIT 10
            """) as cursor:
                rows = await cursor.fetchall()
                recent_feedback = [
                    {
                        "rating": r[0],
                        "comment": r[1],
                        "created_at": r[2],
                        "full_name": r[3] or "Noma'lum",
                        "username": r[4],
                        "user_id": r[5],
                    }
                    for r in rows
                ]

            return {
                "avg_rating": avg_rating,
                "total_ratings": total_ratings,
                "recent_feedback": recent_feedback,
            }

db = Database()
