#!/usr/bin/env python3
"""
Like Pro Bot v3.3 — Guest Mode (No UID Lock) + Admin Panel
==========================================================
Changes from v3.2:
  • Guest UID lock REMOVED — user can enter a NEW UID every time
  • Daily per-TG-ID like limit still enforced
  • Guest dashboard/menu shows "Last UID" (display only, not locked)
  • All text in LɪᴋᴇㅤPʀᴏㅤ small-caps style
"""
import asyncio
import base64
import html
import json
import logging
import os
import random
import signal
import time
from collections import deque
from datetime import datetime, timezone

import aiohttp
from aiohttp import web
from curl_cffi import CurlError
from curl_cffi.requests import AsyncSession
from dotenv import load_dotenv

try:
    from curl_cffi.requests.exceptions import ImpersonateError
except Exception:
    class ImpersonateError(Exception):
        pass

from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ErrorEvent,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

load_dotenv()

# =========================================================
# CONFIG
# =========================================================
BOT_TOKEN     = os.environ["BOT_TOKEN"]
GITHUB_TOKEN  = os.environ["GITHUB_TOKEN"]
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "hasanxld/ff-likeit")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
ADMIN_ID      = int(os.environ["ADMIN_ID"])
LIKE_KEY      = os.environ.get("LIKE_KEY", "HASAN")

TOKEN_API = os.environ.get(
    "TOKEN_API", "https://ff-jwt-gen-api.lovable.app/api/public/token")
LIKE_API = os.environ.get(
    "LIKE_API", "https://fflike.littleblog.online/like")
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8080"))

F_ACCESS   = "access_token.json"
F_BD       = "token_bd.json"
F_UID      = "users_uid.json"
F_CONF     = "bot_config.json"
F_HISTORY  = "like_history.json"
F_FAILED   = "failed_queue.json"
F_STATS    = "stats.json"
F_LOGS     = "activity_logs.json"
F_INVALID  = "invalid_token.json"
F_API      = "api_config.json"
F_GEN_INFO = "gen_info.json"

# Guest files
F_GUEST_USERS   = "guest_users.json"
F_GUEST_HISTORY = "guest_history.json"
F_GUEST_CONF    = "guest_config.json"

DEFAULT_CONF = {
    "gen_interval_hours": 6,
    "like_hour": 5,
    "like_minute": 0,
}

DEFAULT_API = {
    "gen_api":  TOKEN_API,
    "like_api": LIKE_API,
    "like_key": LIKE_KEY,
}

DEFAULT_GEN_INFO = {
    "lastGenAt": "",
    "lastGenTotal": 0,
    "lastGenSuccess": 0,
    "lastGenFailed": 0,
    "lastGenReasons": "",
    "lastGenDeadRemoved": 0,
    "totalGenRuns": 0,
    "totalGenSuccess": 0,
}

DEFAULT_GUEST_CONF = {
    "enabled": True,
    "daily_limit": 100,
}

BRAND = "LɪᴋᴇㅤPʀᴏㅤ"

GEN_RETRIES                = 4
LIKE_RETRIES               = 3
MAX_CONCURRENCY            = 20
MAX_CONCURRENCY_PER_REGION = 8
PER_IMP_SESSIONS           = 3
DEAD_ACCESS_THRESHOLD      = 3
GH_CACHE_TTL               = 30
HISTORY_KEEP               = 100
STATS_DAILY_KEEP           = 30

GEN_TOKEN_TIMEOUT     = 150.0
GEN_OVERALL_TIMEOUT   = 240.0
LIKE_TOKEN_TIMEOUT    = 120.0
POOL_ACQUIRE_TIMEOUT  = 20.0
LIKE_INTERNAL_TIMEOUT = 45

UA_POOL = [
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Redmi Note 11) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; Infinix X6819) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
]

IMPERSONATES = [
    "chrome", "chrome136", "chrome131", "chrome124", "chrome123",
    "chrome120", "chrome119", "chrome116", "chrome110",
]

_dead_imps: set[str] = set()

REGIONS = ["BD", "IN", "PK", "ID", "BR", "GLOBAL"]

_SMALL_CAPS = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ',
    'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ',
    'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ',
    's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
    'y': 'ʏ', 'z': 'ᴢ',
    'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ꜰ',
    'G': 'ɢ', 'H': 'ʜ', 'I': 'ɪ', 'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ',
    'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'ǫ', 'R': 'ʀ',
    'S': 's', 'T': 'ᴛ', 'U': 'ᴜ', 'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x',
    'Y': 'ʏ', 'Z': 'ᴢ',
}

_BI = {
    'A': '𝘼', 'B': '𝘽', 'C': '𝘾', 'D': '𝘿', 'E': '𝙀', 'F': '𝙁', 'G': '𝙂',
    'H': '𝙃', 'I': '𝙄', 'J': '𝙅', 'K': '𝙆', 'L': '𝙇', 'M': '𝙈', 'N': '𝙉',
    'O': '𝙊', 'P': '𝙋', 'Q': '𝙌', 'R': '𝙍', 'S': '𝙎', 'T': '𝙏', 'U': '𝙐',
    'V': '𝙑', 'W': '𝙒', 'X': '𝙓', 'Y': '𝙔', 'Z': '𝙕',
    'a': '𝙖', 'b': '𝙗', 'c': '𝙘', 'd': '𝙙', 'e': '𝙚', 'f': '𝙛', 'g': '𝙜',
    'h': '𝙝', 'i': '𝙞', 'j': '𝙟', 'k': '𝙠', 'l': '𝙡', 'm': '𝙢', 'n': '𝙣',
    'o': '𝙤', 'p': '𝙥', 'q': '𝙦', 'r': '𝙧', 's': '𝙨', 't': '𝙩', 'u': '𝙪',
    'v': '𝙫', 'w': '𝙬', 'x': '𝙭', 'y': '𝙮', 'z': '𝙯',
    '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰',
    '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵',
}


def st(text) -> str:
    return ''.join(_SMALL_CAPS.get(c, c) for c in str(text))


def bi(text) -> str:
    return ''.join(_BI.get(c, c) for c in str(text))


def esc(s) -> str:
    return html.escape(str(s), quote=False)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("likepro")


# =========================================================
# GITHUB CLIENT
# =========================================================
class GitHub:
    def __init__(self, token, repo, branch="main"):
        self.base = f"https://api.github.com/repos/{repo}/contents"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "LikePro-Bot",
        }
        self.branch = branch
        self._locks: dict[str, asyncio.Lock] = {}
        self._cache: dict[str, tuple[str, float]] = {}
        self._session: aiohttp.ClientSession | None = None

    async def init(self):
        self._session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=20),
            timeout=aiohttp.ClientTimeout(total=60),
        )

    async def close(self):
        if self._session:
            await self._session.close()

    def _lock(self, path: str) -> asyncio.Lock:
        if path not in self._locks:
            self._locks[path] = asyncio.Lock()
        return self._locks[path]

    async def _read_unlocked(self, path: str):
        assert self._session
        async with self._session.get(
            f"{self.base}/{path}", headers=self.headers
        ) as r:
            if r.status == 404:
                return None, None
            if r.status != 200:
                raise Exception(
                    f"GitHub read {r.status}: {(await r.text())[:200]}")
            d = await r.json()
            return base64.b64decode(d["content"]).decode("utf-8"), d["sha"]

    async def _write_unlocked(self, path: str, content: str, sha):
        assert self._session
        payload = {
            "message": f"bot: update {path}",
            "content": base64.b64encode(content.encode("utf-8")).decode(),
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        async with self._session.put(
            f"{self.base}/{path}", headers=self.headers, json=payload
        ) as r:
            if r.status not in (200, 201):
                raise Exception(
                    f"GitHub write {r.status}: {(await r.text())[:200]}")
            return await r.json()

    async def read(self, path: str):
        if path in self._cache:
            content, ts = self._cache[path]
            if time.time() - ts < GH_CACHE_TTL:
                return content, None
        async with self._lock(path):
            content, sha = await self._read_unlocked(path)
            if content is not None:
                self._cache[path] = (content, time.time())
            return content, sha

    async def write(self, path: str, content: str, sha=None):
        async with self._lock(path):
            if sha is None:
                _, sha = await self._read_unlocked(path)
            await self._write_unlocked(path, content, sha)
            self._cache.pop(path, None)

    async def update_json(self, path: str, mutator, default=None):
        async with self._lock(path):
            content, sha = await self._read_unlocked(path)
            if content and content.strip():
                data = json.loads(content)
            else:
                data = default if default is not None else []
            new = mutator(data)
            encoded = json.dumps(new, indent=2, ensure_ascii=False)
            await self._write_unlocked(path, encoded, sha)
            self._cache[path] = (encoded, time.time())
            return new


gh = GitHub(GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH)


# =========================================================
# SESSION POOL
# =========================================================
class SessionPool:
    def __init__(self, per_imp: int = PER_IMP_SESSIONS):
        self._per = per_imp
        self._pools: dict[str, asyncio.Queue] = {}
        self._closed = False

    def _make_session(self, imp: str) -> AsyncSession:
        try:
            return AsyncSession(impersonate=imp)
        except Exception:
            return AsyncSession(impersonate="chrome")

    def _get_pool(self, imp: str) -> asyncio.Queue:
        q = self._pools.get(imp)
        if q is None:
            q = asyncio.Queue()
            for _ in range(self._per):
                q.put_nowait(self._make_session(imp))
            self._pools[imp] = q
        return q

    async def acquire(self, imp: str) -> AsyncSession:
        if self._closed:
            return self._make_session(imp)
        q = self._get_pool(imp)
        try:
            return await asyncio.wait_for(q.get(), timeout=POOL_ACQUIRE_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning(f"Pool exhausted for {imp}; using temporary session")
            return self._make_session(imp)

    def release(self, imp: str, s: AsyncSession, healthy: bool = True):
        if self._closed:
            asyncio.create_task(self._safe_close(s))
            return
        q = self._get_pool(imp)
        if healthy:
            q.put_nowait(s)
        else:
            asyncio.create_task(self._safe_close(s))
            try:
                q.put_nowait(self._make_session(imp))
            except Exception:
                pass

    async def _safe_close(self, s):
        try:
            await s.close()
        except Exception:
            pass

    async def close_all(self):
        self._closed = True
        for q in self._pools.values():
            while not q.empty():
                try:
                    s = q.get_nowait()
                    await self._safe_close(s)
                except Exception:
                    pass


pool = SessionPool()


# =========================================================
# STORAGE
# =========================================================
_SENTINEL = object()


async def read_json(path: str, default=_SENTINEL):
    if default is _SENTINEL:
        default = []
    try:
        c, _ = await gh.read(path)
        if not c or not c.strip():
            return default
        return json.loads(c)
    except Exception as e:
        log.error(f"read_json({path}): {e}")
        return default


async def write_json(path: str, data):
    await gh.write(path, json.dumps(data, indent=2, ensure_ascii=False))


async def update_json(path: str, mutator, default=None):
    return await gh.update_json(path, mutator, default=default)


class ActivityLog:
    def __init__(self, path, keep_mem=200, keep_disk=100):
        self.path = path
        self.keep_mem = keep_mem
        self.keep_disk = keep_disk
        self._mem: deque = deque(maxlen=keep_mem)
        self._pending: list[str] = []
        self._flush_task: asyncio.Task | None = None

    async def load(self):
        data = await read_json(self.path, [])
        if isinstance(data, list):
            for x in data[-self.keep_mem:]:
                self._mem.appendleft(x)

    def entries(self) -> list[str]:
        return list(self._mem)

    async def add(self, msg: str):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        line = f"[{ts}] {msg}"
        self._mem.appendleft(line)
        self._pending.append(line)
        log.info(msg)
        if not self._flush_task or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush())

    async def _flush(self):
        await asyncio.sleep(5)
        if not self._pending:
            return
        pending = self._pending[:]
        self._pending.clear()

        def mut(old):
            base = old if isinstance(old, list) else []
            return (base + list(reversed(pending)))[-self.keep_disk:]

        try:
            await gh.update_json(self.path, mut, default=[])
        except Exception as e:
            log.error(f"activity flush: {e}")
            self._pending.extend(pending)


activity = ActivityLog(F_LOGS)


def log_activity(msg: str):
    asyncio.create_task(activity.add(msg))


# =========================================================
# API CONFIG (cached)
# =========================================================
_api_cache = {"data": None, "ts": 0.0}


async def load_api_conf() -> dict:
    now = time.time()
    if _api_cache["data"] and now - _api_cache["ts"] < 30:
        return _api_cache["data"]
    raw = await read_json(F_API, None)
    data = dict(DEFAULT_API)
    if isinstance(raw, dict):
        for k in DEFAULT_API:
            v = raw.get(k)
            if isinstance(v, str) and v.strip():
                data[k] = v.strip()
    _api_cache["data"] = data
    _api_cache["ts"] = now
    return data


def invalidate_api_cache():
    _api_cache["data"] = None
    _api_cache["ts"] = 0.0


# =========================================================
# WORKERS
# =========================================================
_gen_lock  = asyncio.Lock()
_like_lock = asyncio.Lock()

_global_sem = asyncio.Semaphore(MAX_CONCURRENCY)
_region_sems: dict[str, asyncio.Semaphore] = {}


def _region_sem(region: str) -> asyncio.Semaphore:
    if region not in _region_sems:
        _region_sems[region] = asyncio.Semaphore(MAX_CONCURRENCY_PER_REGION)
    return _region_sems[region]


def _random_ua() -> str:
    return random.choice(UA_POOL)


def _random_imp() -> str:
    alive = [x for x in IMPERSONATES if x not in _dead_imps]
    if not alive:
        return "chrome"
    weighted = [x for x in alive if x != "chrome"] * 4 + ["chrome"]
    return random.choice(weighted)


def _is_impersonate_error(e: Exception) -> bool:
    name = type(e).__name__
    msg = str(e).lower()
    return (
        name in ("ImpersonateError", "ImpersonationError")
        or ("impersonat" in msg and ("not supported" in msg or "not available" in msg))
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _humanize_delta(dt) -> str:
    if not dt:
        return "never"
    delta = (datetime.now(timezone.utc) - dt).total_seconds()
    if delta < 0:
        return "just now"
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    return f"{int(delta / 86400)}d ago"


def _clean_access_token(raw) -> str:
    t = str(raw or "").strip().strip("\ufeff")
    t = t.strip('"').strip("'")
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return "".join(t.split())


# =========================================================
# PROGRESS FORMATTERS
# =========================================================
def _progress_bar(done: int, total: int, width: int = 16) -> str:
    if total <= 0:
        return "▱" * width
    p = max(0.0, min(1.0, done / total))
    filled = int(p * width)
    return "▰" * filled + "▱" * (width - filled)


def format_progress(info: dict) -> str:
    done = int(info.get("done", 0))
    total = max(1, int(info.get("total", 1)))
    stage = info.get("stage", "sending")
    pct = int(100 * done / total)
    bar = _progress_bar(done, total)

    if stage == "gen":
        title = "Generating Data"
        stats = (
            f"✅ {info.get('ok', 0)}   ❌ {info.get('fail', 0)}   "
            f"📦 {done}/{total}"
        )
    else:
        title = "Sending Likes"
        stats = (
            f"✅ {info.get('sent', 0)}   ⚪ {info.get('zero', 0)}   "
            f"❌ {info.get('fail', 0)}   📦 {done}/{total}"
        )

    text = (
        f"🔄  {bi(title)}...\n"
        f"{'─' * 15}\n"
        f"{bar} {pct}%\n"
        f"{stats}"
    )
    cur = info.get("current_uid")
    if cur:
        text += f"\n\n🔄 {bi('Sending to')} <code>{esc(cur)}</code>"
    return text


# =========================================================
# INVALID TOKEN STORAGE
# =========================================================
async def save_invalid_tokens(items: list[dict]):
    items = [x for x in items if x and x.get("token")]
    if not items:
        return
    now = _now_iso()

    def mut(old):
        base = old if isinstance(old, list) else []
        existing = {x.get("token") for x in base if isinstance(x, dict)}
        for it in items:
            tok = it["token"]
            if tok not in existing:
                base.append({
                    "token": tok,
                    "reason": it.get("reason", "unknown"),
                    "addedAt": now,
                })
                existing.add(tok)
        return base[-500:]

    try:
        await update_json(F_INVALID, mut, default=[])
    except Exception as e:
        log.error(f"save_invalid_tokens: {e}")


# =========================================================
# GEN INFO STORAGE
# =========================================================
async def save_gen_info(total: int, success: int, failed: int,
                        reasons: str, dead_removed: int):
    try:
        def mut(old):
            base = old if isinstance(old, dict) else {}
            base.setdefault("totalGenRuns", 0)
            base.setdefault("totalGenSuccess", 0)
            base["lastGenAt"] = _now_iso()
            base["lastGenTotal"] = int(total)
            base["lastGenSuccess"] = int(success)
            base["lastGenFailed"] = int(failed)
            base["lastGenReasons"] = reasons or ""
            base["lastGenDeadRemoved"] = int(dead_removed)
            base["totalGenRuns"] = int(base["totalGenRuns"]) + 1
            base["totalGenSuccess"] = int(base["totalGenSuccess"]) + int(success)
            return base
        await update_json(F_GEN_INFO, mut, default=DEFAULT_GEN_INFO)
    except Exception as e:
        log.error(f"save_gen_info: {e}")


# =========================================================
# GUEST HELPERS
# =========================================================
async def load_guest_conf() -> dict:
    raw = await read_json(F_GUEST_CONF, None)
    data = dict(DEFAULT_GUEST_CONF)
    if isinstance(raw, dict):
        if "enabled" in raw:
            data["enabled"] = bool(raw["enabled"])
        if "daily_limit" in raw:
            try:
                data["daily_limit"] = max(1, int(raw["daily_limit"]))
            except Exception:
                pass
    return data


async def save_guest_conf(data: dict):
    await write_json(F_GUEST_CONF, data)


async def get_guest_user(tg_id: int):
    users = await read_json(F_GUEST_USERS, [])
    if not isinstance(users, list):
        return None
    for u in users:
        if isinstance(u, dict) and u.get("tg_id") == tg_id:
            return u
    return None


async def upsert_guest_user(tg_id: int, name: str, username: str):
    now_iso = _now_iso()
    result = {"user": None}

    def mut(old):
        base = old if isinstance(old, list) else []
        for u in base:
            if isinstance(u, dict) and u.get("tg_id") == tg_id:
                u["name"] = name or u.get("name", "")
                u["username"] = username or u.get("username", "")
                u["last_seen"] = now_iso
                result["user"] = u
                return base
        new_u = {
            "tg_id": tg_id,
            "name": name or "",
            "username": username or "",
            "uid": "",
            "region": "BD",
            "date": "",
            "likes_today": 0,
            "total_likes": 0,
            "total_runs": 0,
            "first_seen": now_iso,
            "last_seen": now_iso,
        }
        base.append(new_u)
        result["user"] = new_u
        return base

    await update_json(F_GUEST_USERS, mut, default=[])
    return result["user"]


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def guest_daily_state(user: dict) -> dict:
    """Returns daily state. NOTE: no UID lock — last_uid is display-only."""
    today = _today_str()
    if not user:
        return {"last_uid": "", "region": "BD", "likes_today": 0}
    if user.get("date") == today:
        return {
            "last_uid": user.get("uid") or "",
            "region": user.get("region", "BD"),
            "likes_today": int(user.get("likes_today", 0)),
        }
    return {
        "last_uid": user.get("uid") or "",
        "region": user.get("region", "BD"),
        "likes_today": 0,
    }


async def add_guest_history(rec: dict):
    def mut(old):
        base = old if isinstance(old, list) else []
        base.append(rec)
        return base[-5000:]
    try:
        await update_json(F_GUEST_HISTORY, mut, default=[])
    except Exception as e:
        log.error(f"add_guest_history: {e}")


async def guest_send_like(tg_id: int, uid: str, region: str):
    """Send a like for a guest. Assumes all checks passed."""
    user = await get_guest_user(tg_id)
    if not user:
        return None, "user-not-found"

    today = _today_str()
    before_likes = int(user.get("total_likes", 0))

    r = await _like_one(uid, region)
    d = r.get("data") or {}
    s = status_int(d)
    likes = likes_given(d) if s == 1 else 0

    status_str = "success" if s == 1 else ("zero" if s == 2 else "fail")

    def mut(old):
        base = old if isinstance(old, list) else []
        for u in base:
            if isinstance(u, dict) and u.get("tg_id") == tg_id:
                if u.get("date") != today:
                    u["date"] = today
                    u["likes_today"] = 0
                u["uid"] = uid          # display only — not locked
                u["region"] = region
                u["likes_today"] = int(u.get("likes_today", 0)) + likes
                u["total_likes"] = int(u.get("total_likes", 0)) + likes
                u["total_runs"] = int(u.get("total_runs", 0)) + 1
                u["last_seen"] = _now_iso()
                break
        return base
    await update_json(F_GUEST_USERS, mut, default=[])

    rec = {
        "tg_id": tg_id,
        "name": user.get("name", ""),
        "username": user.get("username", ""),
        "uid": uid,
        "region": region,
        "likes_given": likes,
        "before_likes": before_likes,
        "after_likes": before_likes + likes,
        "status": status_str,
        "reason": r.get("error") or "",
        "nickname": d.get("PlayerNickname", ""),
        "level": d.get("Level", 0),
        "time": _now_iso(),
    }
    await add_guest_history(rec)
    return rec, None


# =========================================================
# TOKEN GENERATION
# =========================================================
async def _gen_one(access_token: str):
    token = _clean_access_token(access_token)
    if not token:
        return None, "empty-token", "empty"

    api_conf = await load_api_conf()
    gen_url = api_conf.get("gen_api") or TOKEN_API

    last_err = "unknown"
    reason = "unknown"
    used_imps: set[str] = set()

    for attempt in range(GEN_RETRIES):
        imp = _random_imp()
        tries = 0
        while imp in used_imps and tries < 3 and len(used_imps) < len(IMPERSONATES):
            imp = _random_imp()
            tries += 1
        used_imps.add(imp)

        session = None
        healthy = True
        try:
            session = await pool.acquire(imp)
            headers = {
                "User-Agent": _random_ua(),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://ff-jwt-gen-api.lovable.app/",
                "Origin": "https://ff-jwt-gen-api.lovable.app",
            }
            params = {
                "access_token": token,
                "_": str(int(time.time() * 1000)),
            }
            r = await session.get(gen_url, params=params, headers=headers, timeout=45)
            text = r.text or ""

            if r.status_code == 200:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    last_err, reason = f"non-json:{text[:40]}", "non-json"
                    await asyncio.sleep(0.5)
                    continue

                body = data.get("body") or {}
                for tok in (
                    body.get("token"), data.get("token"),
                    (data.get("data") or {}).get("token"),
                    data.get("jwt"),
                    (body.get("jwt_decoded") or {}).get("token"),
                ):
                    if isinstance(tok, str) and tok.startswith("eyJ"):
                        return tok, "", ""

                api_status = data.get("status") or data.get("code")
                last_err = f"no-token(status:{api_status})"
                reason = f"no-token:{api_status}"
                await asyncio.sleep(0.5)
                continue

            if r.status_code == 429:
                last_err, reason = "429", "rate-limit"
                await asyncio.sleep(2.0 * (attempt + 1))
                continue

            if r.status_code == 400:
                snippet = text[:120].replace("\n", " ")
                low = snippet.lower()
                if any(x in low for x in ("expired", "invalid", "not valid",
                                          "invalid_token", "unauthorized")):
                    reason = "invalid-token"
                elif "required" in low or "missing" in low:
                    reason = "missing-param"
                else:
                    reason = "http400"
                last_err = f"400:{snippet}"
                await asyncio.sleep(1.0)
                continue

            last_err, reason = f"HTTP:{r.status_code}", f"http{r.status_code}"
            await asyncio.sleep(0.8)

        except (CurlError, asyncio.TimeoutError) as e:
            healthy = False
            last_err, reason = f"curl:{str(e)[:40]}", "timeout"
            await asyncio.sleep(0.5)

        except Exception as e:
            if _is_impersonate_error(e):
                _dead_imps.add(imp)
                healthy = False
                last_err, reason = f"imp:{imp}", "impersonate"
                log.warning(f"Dead impersonate target removed: {imp}")
                continue
            last_err, reason = f"err:{str(e)[:40]}", "exception"
            await asyncio.sleep(0.5)

        finally:
            if session is not None:
                pool.release(imp, session, healthy=healthy)

    return None, last_err, reason


async def generate_bd_tokens(progress_cb=None, report_cb=None, only_tokens=None):
    if _gen_lock.locked():
        return None, 0, "Already in progress", {}
    async with _gen_lock:
        try:
            previous_bd = await read_json(F_BD, [])

            if only_tokens:
                tokens = [{"token": _clean_access_token(t)} for t in only_tokens
                          if _clean_access_token(t)]
            else:
                access = await read_json(F_ACCESS, [])
                tokens = []
                seen: set[str] = set()
                for x in access:
                    raw = None
                    if isinstance(x, dict) and x.get("token"):
                        raw = x["token"]
                    elif isinstance(x, str):
                        raw = x
                    clean = _clean_access_token(raw)
                    if clean and clean not in seen:
                        seen.add(clean)
                        tokens.append({"token": clean})

            if not tokens:
                await activity.add("Token gen skipped: no access tokens")
                return 0, 0, "No access tokens found", {}

            total = len(tokens)
            done = 0
            new_bd: list[dict] = []
            error_reasons: dict[str, int] = {}
            success_tokens: set[str] = set()
            fail_tokens: set[str] = set()
            invalid_pairs: list[dict] = []

            sem = asyncio.Semaphore(MAX_CONCURRENCY)
            last_progress = [0.0]

            async def worker(item: dict):
                nonlocal done
                tok, err, reason = None, "worker-timeout", "timeout"
                try:
                    async with sem:
                        try:
                            tok, err, reason = await asyncio.wait_for(
                                _gen_one(item["token"]),
                                timeout=GEN_TOKEN_TIMEOUT,
                            )
                        except asyncio.TimeoutError:
                            tok, err, reason = None, "timeout", "timeout"
                        except Exception as e:
                            tok, err, reason = (
                                None, f"worker:{str(e)[:40]}", "worker-error")
                finally:
                    done += 1
                    if tok:
                        new_bd.append({"token": tok})
                        success_tokens.add(item["token"])
                    elif err:
                        error_reasons[reason] = error_reasons.get(reason, 0) + 1
                        fail_tokens.add(item["token"])
                        if reason in ("invalid-token", "missing-param", "http400"):
                            invalid_pairs.append(
                                {"token": item["token"], "reason": reason})
                    if progress_cb:
                        now = time.time()
                        if done == total or (now - last_progress[0] > 1.5):
                            last_progress[0] = now
                            try:
                                await progress_cb({
                                    "stage": "gen",
                                    "done": done, "total": total,
                                    "ok": len(new_bd),
                                    "fail": len(fail_tokens),
                                })
                            except Exception:
                                pass

            tasks = [asyncio.create_task(worker(t)) for t in tokens]
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=GEN_OVERALL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                log.warning(
                    f"Generation timeout: {done}/{total}, cancelling remaining")
                for t in tasks:
                    if not t.done():
                        t.cancel()
                await asyncio.sleep(0.5)

            for item in tokens:
                t = item["token"]
                if t not in success_tokens and t not in fail_tokens:
                    fail_tokens.add(t)
                    error_reasons["worker-timeout"] = \
                        error_reasons.get("worker-timeout", 0) + 1

            dead_removed = 0
            dead_tokens: list[dict] = []

            def mutate_access(old):
                nonlocal dead_removed
                now = _now_iso()
                result = []
                if not isinstance(old, list):
                    return result
                for item in old:
                    if not isinstance(item, dict):
                        continue
                    tok = _clean_access_token(item.get("token"))
                    if tok in success_tokens:
                        item["token"] = tok
                        item["failCount"] = 0
                        item["lastStatus"] = "ok"
                        item["lastUsedAt"] = now
                    elif tok in fail_tokens:
                        item["token"] = tok
                        item["failCount"] = int(item.get("failCount", 0)) + 1
                        item["lastStatus"] = "fail"
                        item["lastUsedAt"] = now
                        if item["failCount"] >= DEAD_ACCESS_THRESHOLD:
                            dead_removed += 1
                            dead_tokens.append({
                                "token": tok,
                                "reason": "dead-after-retries",
                            })
                            continue
                    result.append(item)
                return result

            await update_json(F_ACCESS, mutate_access, default=[])

            if invalid_pairs or dead_tokens:
                try:
                    await save_invalid_tokens(invalid_pairs + dead_tokens)
                except Exception as e:
                    log.error(f"save_invalid_tokens: {e}")

            reasons_str = ", ".join(
                f"{k}×{v}" for k, v in sorted(
                    error_reasons.items(), key=lambda kv: -kv[1])
            ) or "-"

            if new_bd:
                if only_tokens:
                    def merge_bd(old):
                        base = old if isinstance(old, list) else []
                        existing = {x.get("token") for x in base
                                    if isinstance(x, dict)}
                        for t in new_bd:
                            if t["token"] not in existing:
                                base.append(t)
                        return base[-100:]
                    await update_json(F_BD, merge_bd, default=[])
                else:
                    await write_json(F_BD, new_bd)
                await activity.add(
                    f"BD tokens: {len(new_bd)}/{total} ok"
                    + (f" | errs: {reasons_str}" if error_reasons else "")
                    + (f" | dead-removed: {dead_removed}" if dead_removed else "")
                )
            elif previous_bd:
                await activity.add(
                    f"BD gen failed all {total}, KEPT {len(previous_bd)}. "
                    f"Reasons: {reasons_str}"
                )
            else:
                await write_json(F_BD, [])

            await save_gen_info(
                total=total,
                success=len(new_bd),
                failed=len(fail_tokens),
                reasons=reasons_str,
                dead_removed=dead_removed,
            )

            if report_cb:
                try:
                    await report_cb(
                        total=total,
                        success=len(new_bd),
                        failed=len(fail_tokens),
                        dead_removed=dead_removed,
                        reasons=reasons_str,
                        invalid_count=len(invalid_pairs),
                    )
                except Exception as e:
                    log.error(f"report_cb: {e}")

            if not new_bd and not previous_bd:
                return 0, total, f"All {total} failed. {reasons_str}", error_reasons
            return len(new_bd), total, None, error_reasons

        except Exception as e:
            log.exception(f"generate_bd_tokens: {e}")
            return 0, 0, str(e), {}


# =========================================================
# LIKE SENDER
# =========================================================
async def _like_one(uid, region):
    last_err = "unknown"
    used_imps: set[str] = set()
    api_conf = await load_api_conf()
    url_template = api_conf.get("like_api") or LIKE_API
    like_key = api_conf.get("like_key") or LIKE_KEY

    for attempt in range(LIKE_RETRIES):
        imp = _random_imp()
        tries = 0
        while imp in used_imps and tries < 3 and len(used_imps) < len(IMPERSONATES):
            imp = _random_imp()
            tries += 1
        used_imps.add(imp)

        session = None
        healthy = True
        try:
            session = await pool.acquire(imp)
            if "{" in url_template:
                url = (url_template
                       .replace("{uid}", str(uid))
                       .replace("{region}", str(region))
                       .replace("{key}", str(like_key)))
            else:
                sep = "&" if "?" in url_template else "?"
                url = (f"{url_template}{sep}uid={uid}&region={region}&key={like_key}")

            headers = {
                "User-Agent": _random_ua(),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://fflike.littleblog.online/",
            }
            r = await session.get(url, headers=headers, timeout=LIKE_INTERNAL_TIMEOUT)
            text = r.text or ""

            if r.status_code == 200:
                try:
                    return {"uid": uid, "data": json.loads(text)}
                except json.JSONDecodeError:
                    last_err = f"non-json:{text[:40]}"
                    await asyncio.sleep(0.8)
                    continue

            if r.status_code == 429:
                last_err = "429"
                await asyncio.sleep(2.0 * (attempt + 1))
                continue
            if r.status_code >= 500:
                last_err = f"HTTP:{r.status_code}"
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            last_err = f"HTTP:{r.status_code}"
            await asyncio.sleep(0.8)

        except (CurlError, asyncio.TimeoutError) as e:
            healthy = False
            last_err = f"curl:{str(e)[:40]}"
            await asyncio.sleep(0.8)
        except Exception as e:
            if _is_impersonate_error(e):
                _dead_imps.add(imp)
                healthy = False
                last_err = f"imp:{imp}"
                continue
            last_err = f"err:{str(e)[:40]}"
            await asyncio.sleep(0.8)
        finally:
            if session is not None:
                pool.release(imp, session, healthy=healthy)

    return {"uid": uid, "error": last_err}


def status_int(d: dict) -> int:
    try:
        return int((d or {}).get("status", -1))
    except Exception:
        return -1


def likes_given(d: dict) -> int:
    try:
        return int((d or {}).get("LikesGivenByAPI", 0) or 0)
    except Exception:
        return 0


async def send_all_likes(progress_cb=None):
    if _like_lock.locked():
        return None, "Already in progress"
    async with _like_lock:
        try:
            uids = await read_json(F_UID, [])
            if not uids:
                return [], "No UIDs configured"

            targets: list[dict] = []
            for u in uids:
                if not isinstance(u, dict):
                    continue
                if not u.get("uid"):
                    continue
                targets.append(u)

            total = len(targets)
            if total == 0:
                return [], "No UIDs configured"

            results: list[dict] = []
            sent_ok = 0
            zero_ok = 0
            fail_count = 0

            for i, u in enumerate(targets):
                uid = u.get("uid")
                region = u.get("region", "BD")
                if progress_cb:
                    try:
                        await progress_cb({
                            "stage": "sending",
                            "done": i, "total": total,
                            "sent": sent_ok, "zero": zero_ok,
                            "fail": fail_count,
                            "current_uid": uid,
                        })
                    except Exception:
                        pass

                r = {"uid": uid, "error": "timeout"}
                try:
                    r = await asyncio.wait_for(
                        _like_one(uid, region),
                        timeout=LIKE_TOKEN_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    r = {"uid": uid, "error": "timeout"}
                except Exception as e:
                    r = {"uid": uid, "error": f"worker:{str(e)[:40]}"}
                r["_region"] = region

                s = status_int(r.get("data") or {})
                if s == 1:
                    sent_ok += 1
                elif s == 2:
                    zero_ok += 1
                else:
                    fail_count += 1

                results.append(r)

                if progress_cb:
                    try:
                        await progress_cb({
                            "stage": "sending",
                            "done": i + 1, "total": total,
                            "sent": sent_ok, "zero": zero_ok,
                            "fail": fail_count,
                            "current_uid": uid,
                        })
                    except Exception:
                        pass

            now_iso = _now_iso()
            by_uid = {str(u.get("uid")): u for u in uids if isinstance(u, dict)}
            failed_map: dict[str, dict] = {}
            total_likes = 0

            sent_ok = 0
            zero_ok = 0
            fail_count = 0

            for r in results:
                d = r.get("data") or {}
                s = status_int(d)
                uid = str(r.get("uid"))
                item = by_uid.get(uid)
                if s == 1:
                    sent_ok += 1
                    add = likes_given(d)
                    total_likes += add
                    if item:
                        item["likesGiven"] = int(item.get("likesGiven", 0) or 0) + add
                        item["lastLikeCount"] = add
                        item["lastLikeAt"] = now_iso
                        item["lastUpdated"] = now_iso
                        if d.get("PlayerNickname"):
                            item["nickname"] = d["PlayerNickname"]
                        if d.get("Level") is not None:
                            item["level"] = d["Level"]
                        if d.get("Region"):
                            item["region"] = d["Region"]
                elif s == 2:
                    zero_ok += 1
                    if item:
                        item["lastLikeAt"] = now_iso
                        item["lastLikeCount"] = 0
                else:
                    fail_count += 1
                    err = r.get("error") or f"status:{d.get('status')}"
                    failed_map[uid] = {
                        "uid": uid,
                        "region": r.get("_region") or (item or {}).get("region", "BD"),
                        "last_error": err,
                    }

            await write_json(F_UID, list(by_uid.values()))

            def mutate_failed(old):
                old_map = {x.get("uid"): x for x in old if isinstance(x, dict)}
                for r in results:
                    d = r.get("data") or {}
                    if status_int(d) in (1, 2):
                        old_map.pop(str(r.get("uid")), None)
                for uid, info in failed_map.items():
                    prev = old_map.get(uid, {})
                    old_map[uid] = {
                        "uid": uid,
                        "region": info["region"],
                        "last_error": info["last_error"],
                        "attempts": int(prev.get("attempts", 0)) + 1,
                        "added_at": prev.get("added_at") or now_iso,
                    }
                return list(old_map.values())

            await update_json(F_FAILED, mutate_failed, default=[])

            summary = {
                "ts": now_iso,
                "total": len(targets),
                "sent_players": sent_ok,
                "zero_players": zero_ok,
                "fail": fail_count,
                "cooldown_skipped": 0,
                "likes_given": total_likes,
            }

            def mutate_stats(old):
                base = old if isinstance(old, dict) else {}
                base.setdefault("total_likes_sent", 0)
                base.setdefault("total_runs", 0)
                base.setdefault("total_uid_processed", 0)
                base.setdefault("daily", {})
                base["total_likes_sent"] += total_likes
                base["total_runs"] += 1
                base["total_uid_processed"] += len(targets)
                day = now_iso[:10]
                dd = base["daily"].setdefault(day, {"likes": 0, "runs": 0})
                dd["likes"] += total_likes
                dd["runs"] += 1
                days = sorted(base["daily"].keys())
                for old_day in days[:-STATS_DAILY_KEEP]:
                    base["daily"].pop(old_day, None)
                base["last_run_at"] = now_iso
                base["last_run_summary"] = summary
                return base

            await update_json(F_STATS, mutate_stats, default={})

            def mutate_hist(old):
                base = old if isinstance(old, list) else []
                base.append(summary)
                return base[-HISTORY_KEEP:]

            await update_json(F_HISTORY, mutate_hist, default=[])

            await activity.add(
                f"Likes run: sent={sent_ok} ({total_likes} likes), "
                f"zero={zero_ok}, fail={fail_count}, "
                f"total_uids={len(targets)}"
            )
            return results, None

        except Exception as e:
            log.exception(f"send_all_likes: {e}")
            return None, str(e)


async def retry_failed(progress_cb=None):
    if _like_lock.locked():
        return None, "Already in progress"
    async with _like_lock:
        try:
            failed = await read_json(F_FAILED, [])
            if not failed:
                return [], "Failed queue is empty"

            total = len(failed)
            results: list[dict] = []
            sent_ok = 0
            zero_ok = 0
            fail_count = 0

            for i, u in enumerate(failed):
                uid = u.get("uid")
                region = u.get("region", "BD")
                if progress_cb:
                    try:
                        await progress_cb({
                            "stage": "sending",
                            "done": i, "total": total,
                            "sent": sent_ok, "zero": zero_ok,
                            "fail": fail_count,
                            "current_uid": uid,
                        })
                    except Exception:
                        pass

                r = {"uid": uid, "error": "timeout"}
                try:
                    r = await asyncio.wait_for(
                        _like_one(uid, region),
                        timeout=LIKE_TOKEN_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    r = {"uid": uid, "error": "timeout"}
                except Exception as e:
                    r = {"uid": uid, "error": f"worker:{str(e)[:40]}"}
                r["_region"] = region
                results.append(r)

                s = status_int(r.get("data") or {})
                if s == 1:
                    sent_ok += 1
                elif s == 2:
                    zero_ok += 1
                else:
                    fail_count += 1

                if progress_cb:
                    try:
                        await progress_cb({
                            "stage": "sending",
                            "done": i + 1, "total": total,
                            "sent": sent_ok, "zero": zero_ok,
                            "fail": fail_count,
                        })
                    except Exception:
                        pass

            def mutate_failed(old):
                old_map = {x.get("uid"): x for x in old if isinstance(x, dict)}
                for r in results:
                    d = r.get("data") or {}
                    if status_int(d) in (1, 2):
                        old_map.pop(str(r.get("uid")), None)
                    else:
                        prev = old_map.get(str(r.get("uid")), {})
                        prev["attempts"] = int(prev.get("attempts", 0)) + 1
                        prev["last_error"] = r.get("error") or "status"
                        old_map[str(r.get("uid"))] = prev
                return list(old_map.values())

            await update_json(F_FAILED, mutate_failed, default=[])

            recovered = sum(
                1 for r in results if status_int(r.get("data") or {}) in (1, 2))
            await activity.add(
                f"Retry run: {recovered}/{total} recovered")
            return results, None

        except Exception as e:
            log.exception(f"retry_failed: {e}")
            return None, str(e)


# =========================================================
# KEYBOARDS
# =========================================================
def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu() -> InlineKeyboardMarkup:
    return kb([
        [InlineKeyboardButton(text=st("📊 Statistics"), callback_data="v_stats"),
         InlineKeyboardButton(text=st("📜 Logs"), callback_data="v_logs")],
        [InlineKeyboardButton(text=st("🔑 Access Token"), callback_data="v_access"),
         InlineKeyboardButton(text=st("🎫 BD Token"), callback_data="v_bd")],
        [InlineKeyboardButton(text=st("👥 UIDs"), callback_data="v_uids"),
         InlineKeyboardButton(text=st("🌐 API Settings"), callback_data="v_api")],
        [InlineKeyboardButton(text=st("🎭 Guest Mode"), callback_data="adm_guest"),
         InlineKeyboardButton(text=st("⚙️ Auto Settings"), callback_data="v_auto")],
        [InlineKeyboardButton(text=st("❤️ Send Like"), callback_data="send_like")],
        [InlineKeyboardButton(text=st("🔁 Retry Failed"), callback_data="retry_failed")],
        [InlineKeyboardButton(text=st("🔍 Find UID"), callback_data="find_uid")],
    ])


def back_kb(target="back"):
    return kb([[InlineKeyboardButton(text=st("⬅️ Back"), callback_data=target)]])


def paginated_kb(items, page, per_page, prefix, extra_rows=None,
                 show_delete=True):
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    start = page * per_page
    chunk = items[start:start + per_page]
    rows = []
    for i, (label, ident) in enumerate(chunk):
        idx = start + i
        if show_delete:
            rows.append([
                InlineKeyboardButton(text=label,
                                     callback_data=f"{prefix}_info_{idx}"),
                InlineKeyboardButton(text="🗑",
                                     callback_data=f"{prefix}_del_cfm_{idx}"),
            ])
        else:
            rows.append([InlineKeyboardButton(
                text=label, callback_data=f"{prefix}_info_{idx}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️",
                                        callback_data=f"{prefix}_pg_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}",
                                    callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="➡️",
                                        callback_data=f"{prefix}_pg_{page+1}"))
    if len(nav) > 1:
        rows.append(nav)
    if extra_rows:
        rows.extend(extra_rows)
    return kb(rows)


def region_picker(prefix="set_region"):
    rows = []
    row = []
    for r in REGIONS:
        row.append(InlineKeyboardButton(text=r, callback_data=f"{prefix}:{r}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=st("⬅️ Cancel"), callback_data="back")])
    return kb(rows)


def confirm_kb(yes_cb, no_cb):
    return kb([
        [InlineKeyboardButton(text=st("✅ Yes, delete"), callback_data=yes_cb),
         InlineKeyboardButton(text=st("❌ No"), callback_data=no_cb)],
    ])


# =========================================================
# MIDDLEWARE / STATES
# =========================================================
ADMIN_STATES = {
    "S:add_access", "S:add_uid", "S:set_gen_h", "S:set_like_h",
    "S:set_like_m", "S:find_uid", "S:pending_region",
    "S:set_api_gen", "S:set_api_like", "S:set_api_key",
    "S:adm_guest_limit",
}

GUEST_CALLBACK_PREFIXES = ("g_",)
ALLOW_IN_GUEST_VIEW = {"adm_back_panel", "noop"}


class AdminGate(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)

        is_admin = (user.id == ADMIN_ID)
        state: FSMContext | None = data.get("state")

        cur_state = None
        if state is not None:
            try:
                cur_state = await state.get_state()
            except Exception:
                cur_state = None

        in_guest_view = is_admin and cur_state == "S:guest_view"

        if isinstance(event, CallbackQuery):
            cb_data = event.data or ""

            if cb_data in ALLOW_IN_GUEST_VIEW or any(
                cb_data.startswith(p) for p in GUEST_CALLBACK_PREFIXES
            ):
                if cb_data == "adm_back_panel" and not is_admin:
                    return
                return await handler(event, data)

            if not is_admin:
                try:
                    await event.answer("🔒 Admin only", show_alert=True)
                except Exception:
                    pass
                return

            if in_guest_view:
                try:
                    await event.answer(
                        "🔒 Exit Guest View first", show_alert=True)
                except Exception:
                    pass
                return

            return await handler(event, data)

        if isinstance(event, Message):
            if cur_state in ADMIN_STATES and not is_admin:
                return

        return await handler(event, data)


class S(StatesGroup):
    add_access      = State()
    add_uid         = State()
    set_gen_h       = State()
    set_like_h      = State()
    set_like_m      = State()
    find_uid        = State()
    pending_region  = State()
    set_api_gen     = State()
    set_api_like    = State()
    set_api_key     = State()
    guest_input_uid = State()
    guest_view      = State()
    adm_guest_limit = State()


# =========================================================
# HANDLERS
# =========================================================
router = Router()
PER_PAGE = 8


async def safe_edit(msg: Message, text: str, kb_markup=None):
    try:
        await asyncio.wait_for(
            msg.edit_text(text, reply_markup=kb_markup,
                          disable_web_page_preview=True),
            timeout=10,
        )
    except Exception:
        pass


async def _is_admin_panel_cb(cb: CallbackQuery, state: FSMContext) -> bool:
    if cb.from_user.id != ADMIN_ID:
        return False
    try:
        if await state.get_state() == S.guest_view.state:
            return False
    except Exception:
        pass
    return True


def _stats_summary_text(stats: dict, conf: dict) -> str:
    total_likes = stats.get("total_likes_sent", 0) or 0
    total_runs = stats.get("total_runs", 0) or 0
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today = (stats.get("daily") or {}).get(day, {})
    return (
        f"<b>{BRAND} — {st('Admin')}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"❤️ {st('Total likes')}: <b>{total_likes}</b>\n"
        f"📊 {st('Today')}: <b>{today.get('likes', 0)}</b> "
        f"({today.get('runs', 0)} {st('runs')})\n"
        f"🔁 {st('All-time runs')}: <b>{total_runs}</b>\n"
        f"⏰ {st('Auto-like')}: <b>{conf['like_hour']:02d}:{conf['like_minute']:02d}</b> "
        f"| {st('Gen')}: <b>{conf['gen_interval_hours']}h</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"<i>{st('Select an option below')}</i>"
    )


async def _load_conf():
    c = await read_json(F_CONF, None)
    if not isinstance(c, dict):
        return dict(DEFAULT_CONF)
    merged = dict(DEFAULT_CONF)
    merged.update({k: v for k, v in c.items() if k in DEFAULT_CONF})
    for k in ("gen_interval_hours", "like_hour", "like_minute"):
        try:
            merged[k] = int(merged[k])
        except Exception:
            merged[k] = DEFAULT_CONF[k]
    return merged


async def _render_main():
    conf = await _load_conf()
    stats = await read_json(F_STATS, {}) or {}
    return _stats_summary_text(stats, conf), main_menu()


# ---------- START / MENU / CANCEL ----------
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    user = msg.from_user
    if not user:
        return

    if user.id == ADMIN_ID:
        text, kb_m = await _render_main()
        await msg.answer(text, reply_markup=kb_m)
        return

    conf = await load_guest_conf()
    if not conf["enabled"]:
        await msg.answer(
            st("⚠️ Service is temporarily unavailable. Please try again later."))
        return

    guser = await upsert_guest_user(
        user.id, user.full_name, user.username or "")
    text, kb_m = await _guest_menu_text_kb(guser, is_admin=False)
    await msg.answer(text, reply_markup=kb_m)


@router.message(Command("panel"))
async def cmd_panel(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    await state.clear()
    text, kb_m = await _render_main()
    await msg.answer(text, reply_markup=kb_m)


@router.message(Command("menu"))
async def cmd_menu(msg: Message, state: FSMContext):
    await state.clear()
    user = msg.from_user
    if not user:
        return
    if user.id == ADMIN_ID:
        text, kb_m = await _render_main()
        await msg.answer(text, reply_markup=kb_m)
        return
    conf = await load_guest_conf()
    if not conf["enabled"]:
        await msg.answer(st("⚠️ Service is temporarily unavailable."))
        return
    guser = await upsert_guest_user(
        user.id, user.full_name, user.username or "")
    text, kb_m = await _guest_menu_text_kb(guser, is_admin=False)
    await msg.answer(text, reply_markup=kb_m)


@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    user = msg.from_user
    if not user:
        return
    if user.id == ADMIN_ID:
        text, kb_m = await _render_main()
        await msg.answer(st("❌ Cancelled."), reply_markup=kb_m)
        return
    conf = await load_guest_conf()
    if not conf["enabled"]:
        await msg.answer(st("❌ Cancelled."))
        return
    guser = await upsert_guest_user(
        user.id, user.full_name, user.username or "")
    text, kb_m = await _guest_menu_text_kb(guser, is_admin=False)
    await msg.answer(st("❌ Cancelled."), reply_markup=kb_m)


@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    await _show_stats(msg, editing=False)


# ---------- STATS / LOGS ----------
async def _show_stats(target, editing=True):
    stats = await read_json(F_STATS, {}) or {}
    hist = await read_json(F_HISTORY, []) or []
    total_likes = stats.get("total_likes_sent", 0) or 0
    total_runs = stats.get("total_runs", 0) or 0
    total_processed = stats.get("total_uid_processed", 0) or 0
    last_run = stats.get("last_run_at") or "-"
    daily = stats.get("daily") or {}

    lines = [
        f"<b>{st('📊 Statistics')}</b>",
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈",
        f"❤️ {st('Total likes sent')}: <b>{total_likes}</b>",
        f"🔁 {st('Total runs')}: <b>{total_runs}</b>",
        f"👥 {st('Total UID processed')}: <b>{total_processed}</b>",
        f"🕒 {st('Last run')}: <code>{esc(last_run)}</code>",
        "",
        f"<b>{st('Last 7 days')}</b>",
    ]
    days = sorted(daily.keys())[-7:]
    if not days:
        lines.append(st("No runs yet."))
    else:
        for d in days:
            info = daily[d]
            lines.append(
                f"• {d}: <b>{info.get('likes', 0)}</b> likes, "
                f"{info.get('runs', 0)} runs")
    if hist:
        last = hist[-1]
        lines += [
            "",
            f"<b>{st('Last run detail')}</b>",
            f"• {st('Players')}: sent={last.get('sent_players', 0)} "
            f"zero={last.get('zero_players', 0)} fail={last.get('fail', 0)}",
            f"• {st('Likes given')}: {last.get('likes_given', 0)}",
        ]
    text = "\n".join(lines)
    if editing:
        await safe_edit(target, text, back_kb())
    else:
        await target.answer(text, reply_markup=back_kb())


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data == "back")
async def cb_back(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    text, kb_m = await _render_main()
    await safe_edit(cb.message, text, kb_m)
    await cb.answer()


@router.callback_query(F.data == "v_stats")
async def cb_v_stats(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒 Admin only", show_alert=True)
        return
    await _show_stats(cb.message, editing=True)
    await cb.answer()


@router.callback_query(F.data == "v_logs")
async def cb_v_logs(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒 Admin only", show_alert=True)
        return
    entries = activity.entries()
    if not entries:
        body = st("No activity yet.")
    else:
        joined = "\n".join(entries[:50])
        if len(joined) > 3400:
            joined = joined[:3400] + "\n... [truncated]"
        body = f"<pre>{esc(joined)}</pre>"
    await safe_edit(cb.message,
                    f"<b>{st('📜 Activity Log')}</b>\n\n{body}", back_kb())
    await cb.answer()


# ---------- ACCESS ----------
async def _show_access(cb_or_msg, page=0, editing=True):
    data = await read_json(F_ACCESS, [])
    if not isinstance(data, list):
        data = []
    items = []
    for i, item in enumerate(data):
        tok = (item.get("token") if isinstance(item, dict) else str(item)) or ""
        short = tok[:12] + "..." if len(tok) > 12 else tok
        status = ""
        if isinstance(item, dict):
            fc = item.get("failCount", 0)
            if fc >= 2:
                status = " ⚠️"
            elif item.get("lastStatus") == "ok":
                status = " ✅"
        items.append((f"{i+1}. {short}{status}", i))
    extra = [
        [InlineKeyboardButton(text=st("➕ Add Token"), callback_data="add_access")],
        [InlineKeyboardButton(text=st("⚡ Generate Now"), callback_data="do_gen")],
        [InlineKeyboardButton(text=st("🚫 Invalid Tokens"), callback_data="v_invalid")],
        [InlineKeyboardButton(text=st("⬅️ Back"), callback_data="back")],
    ]
    header = (
        f"<b>{st('🔑 Access Tokens')}: {len(data)}</b>\n"
        f"<i>{st('Tap item to view, 🗑 to delete')}</i>\n"
    )
    kb_m = paginated_kb(items, page, PER_PAGE, "at", extra_rows=extra)
    if editing:
        await safe_edit(cb_or_msg, header, kb_m)
    else:
        await cb_or_msg.answer(header, reply_markup=kb_m)


@router.callback_query(F.data == "v_access")
async def cb_v_access(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒 Admin only", show_alert=True)
        return
    await _show_access(cb.message)
    await cb.answer()


@router.callback_query(F.data.startswith("at_pg_"))
async def cb_at_pg(cb: CallbackQuery):
    page = int(cb.data.rsplit("_", 1)[1])
    await _show_access(cb.message, page=page)
    await cb.answer()


@router.callback_query(F.data.startswith("at_info_"))
async def cb_at_info(cb: CallbackQuery):
    idx = int(cb.data.rsplit("_", 1)[1])
    data = await read_json(F_ACCESS, [])
    if not (0 <= idx < len(data)):
        await cb.answer("Not found", show_alert=True)
        return
    item = data[idx]
    if not isinstance(item, dict):
        item = {"token": str(item)}
    body = json.dumps(item, indent=2, ensure_ascii=False)
    txt = f"<b>{st('Access Token')} #{idx+1}</b>\n<pre>{esc(body)}</pre>"
    await safe_edit(cb.message, txt, kb([
        [InlineKeyboardButton(text=st("🗑 Delete"),
                              callback_data=f"at_del_cfm_{idx}")],
        [InlineKeyboardButton(text=st("⬅️ Back"), callback_data="v_access")],
    ]))
    await cb.answer()


@router.callback_query(F.data.startswith("at_del_cfm_"))
async def cb_at_del_cfm(cb: CallbackQuery):
    idx = int(cb.data.rsplit("_", 1)[1])
    await safe_edit(cb.message, st(f"⚠️ Delete access token #{idx+1}?"),
                    confirm_kb(f"at_del_yes_{idx}", f"at_del_no_{idx}"))
    await cb.answer()


@router.callback_query(F.data.startswith("at_del_yes_"))
async def cb_at_del_yes(cb: CallbackQuery):
    idx = int(cb.data.rsplit("_", 1)[1])

    def mut(old):
        if isinstance(old, list) and 0 <= idx < len(old):
            old.pop(idx)
        return old

    await update_json(F_ACCESS, mut, default=[])
    await activity.add(f"Access token deleted (idx {idx})")
    await _show_access(cb.message)
    await cb.answer("Deleted ✅")


@router.callback_query(F.data.startswith("at_del_no_"))
async def cb_at_del_no(cb: CallbackQuery):
    await _show_access(cb.message)
    await cb.answer("Cancelled")


@router.callback_query(F.data == "add_access")
async def cb_add_access(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒 Admin only", show_alert=True)
        return
    await state.set_state(S.add_access)
    await safe_edit(
        cb.message,
        st("📥 Send access token(s), one per line.\n/cancel to abort."),
        back_kb())
    await cb.answer()


@router.message(S.add_access)
async def on_add_access(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    if text == "/cancel":
        await state.clear()
        t, kb_m = await _render_main()
        await msg.answer(t, reply_markup=kb_m)
        return

    lines = [t.strip() for t in text.splitlines() if t.strip()]
    valid: list[str] = []
    invalid = 0
    for t in lines:
        clean = _clean_access_token(t)
        if clean and len(clean) >= 10:
            valid.append(clean)
        else:
            invalid += 1

    added = 0
    new_tokens_for_gen: list[str] = []

    def mut(old):
        nonlocal added
        if not isinstance(old, list):
            old = []
        existing = {_clean_access_token(x.get("token"))
                    for x in old if isinstance(x, dict)}
        for t in valid:
            if t not in existing:
                old.append({
                    "token": t,
                    "failCount": 0,
                    "lastStatus": "new",
                    "lastUsedAt": None,
                })
                added += 1
                new_tokens_for_gen.append(t)
        return old

    await update_json(F_ACCESS, mut, default=[])
    await activity.add(f"Access tokens added: {added} (skipped {invalid})")
    await state.clear()

    if not new_tokens_for_gen:
        t, kb_m = await _render_main()
        await msg.answer(
            st(f"✅ Added {added}. Skipped {invalid}.\nNo new tokens to generate."),
            reply_markup=kb_m)
        return

    if _gen_lock.locked():
        t, kb_m = await _render_main()
        await msg.answer(
            st(f"✅ Added {added}. Skipped {invalid}.\n"
               f"⏳ Gen already running."),
            reply_markup=kb_m)
        return

    status_msg = await msg.answer(
        st(f"✅ Added {added}. Skipped {invalid}.\n"
           f"🔄 Generating BD tokens..."))

    async def progress_cb(info: dict):
        await safe_edit(status_msg, format_progress(info))

    async def report_cb(total, success, failed, dead_removed, reasons,
                        invalid_count):
        pass

    count, total_gen, err, _ = await generate_bd_tokens(
        progress_cb=progress_cb,
        report_cb=report_cb,
        only_tokens=new_tokens_for_gen,
    )

    if err:
        await safe_edit(status_msg,
                        f"⚠️ {esc(err)}\n"
                        f"✅ {st('Added')} {added} {st('access tokens')}")
    else:
        await safe_edit(
            status_msg,
            f"<b>✅ {st('Done')}</b>\n"
            f"➕ {st('Access added')}: <b>{added}</b>\n"
            f"🎫 {st('BD generated')}: <b>{count}/{total_gen}</b>")

    t, kb_m = await _render_main()
    await msg.answer(t, reply_markup=kb_m)


# ---------- INVALID TOKENS ----------
@router.callback_query(F.data == "v_invalid")
async def cb_v_invalid(cb: CallbackQuery):
    data = await read_json(F_INVALID, [])
    if not isinstance(data, list):
        data = []
    lines = [f"<b>{st('🚫 Invalid Tokens')}: {len(data)}</b>\n"]
    if not data:
        lines.append(st("None yet."))
    else:
        for i, it in enumerate(data[-15:], 1):
            if not isinstance(it, dict):
                continue
            tok = str(it.get("token", ""))[:24]
            reason = it.get("reason", "?")
            lines.append(f"{i}. <code>{esc(tok)}...</code>\n   {esc(reason)}")
    txt = "\n".join(lines)
    await safe_edit(cb.message, txt, kb([
        [InlineKeyboardButton(text=st("🗑 Clear All"),
                              callback_data="inv_clear_cfm")],
        [InlineKeyboardButton(text=st("⬅️ Back"), callback_data="v_access")],
    ]))
    await cb.answer()


@router.callback_query(F.data == "inv_clear_cfm")
async def cb_inv_clear_cfm(cb: CallbackQuery):
    await safe_edit(cb.message, st("⚠️ Clear all invalid tokens?"),
                    confirm_kb("inv_clear_yes", "inv_clear_no"))
    await cb.answer()


@router.callback_query(F.data == "inv_clear_yes")
async def cb_inv_clear_yes(cb: CallbackQuery):
    await write_json(F_INVALID, [])
    await activity.add("Invalid tokens cleared")
    await cb_v_invalid(cb)


@router.callback_query(F.data == "inv_clear_no")
async def cb_inv_clear_no(cb: CallbackQuery):
    await cb_v_invalid(cb)


# ---------- BD TOKENS ----------
def _bd_header_text(count: int, gen_info: dict, conf: dict) -> str:
    last_at = gen_info.get("lastGenAt") or ""
    if last_at:
        dt = _parse_iso(last_at)
        if dt:
            last_str = (f"<b>{dt.strftime('%Y-%m-%d %H:%M:%S')} UTC</b>\n"
                        f"   <i>({_humanize_delta(dt)})</i>")
        else:
            last_str = f"<code>{esc(last_at)}</code>"
    else:
        last_str = "<i>never</i>"

    total_runs = int(gen_info.get("totalGenRuns", 0) or 0)
    last_success = int(gen_info.get("lastGenSuccess", 0) or 0)
    last_total = int(gen_info.get("lastGenTotal", 0) or 0)
    last_failed = int(gen_info.get("lastGenFailed", 0) or 0)
    last_reasons = gen_info.get("lastGenReasons") or ""
    last_dead = int(gen_info.get("lastGenDeadRemoved", 0) or 0)
    total_success = int(gen_info.get("totalGenSuccess", 0) or 0)
    interval = conf.get("gen_interval_hours", 6)

    parts = [
        f"<b>{st('🎫 BD Tokens')}: {count}</b>",
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈",
        f"📊 <b>{st('Generation Stats')}</b>",
        f"🕒 {st('Last')}: {last_str}",
    ]

    if last_total > 0:
        parts.append(
            f"✅ {st('Last run')}: <b>{last_success}/{last_total}</b>"
            f"  ·  ❌ <b>{last_failed}</b>"
        )
        if last_reasons and last_reasons != "-":
            parts.append(f"⚠️ {st('Reasons')}: <code>{esc(last_reasons[:80])}</code>")
        if last_dead:
            parts.append(f"🧹 {st('Dead removed')}: <b>{last_dead}</b>")
    else:
        parts.append(f"✅ {st('Last run')}: <i>no data yet</i>")

    parts.append(f"🔁 {st('Total runs')}: <b>{total_runs}</b>")
    parts.append(f"📈 {st('All-time generated')}: <b>{total_success}</b>")
    parts.append("┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈")
    parts.append(f"<i>{st('Auto-gen every')} {interval}h</i>")

    return "\n".join(parts)


async def _show_bd(cb_or_msg, page=0, editing=True):
    data = await read_json(F_BD, [])
    if not isinstance(data, list):
        data = []
    gen_info = await read_json(F_GEN_INFO, {}) or {}
    conf = await _load_conf()

    items = []
    for i, item in enumerate(data):
        tok = (item.get("token") if isinstance(item, dict) else str(item)) or ""
        items.append((f"{i+1}. {tok[:16]}...", i))
    extra = [
        [InlineKeyboardButton(text=st("⚡ Generate Now"), callback_data="do_gen")],
        [InlineKeyboardButton(text=st("⬅️ Back"), callback_data="back")],
    ]
    header = _bd_header_text(len(data), gen_info, conf)
    kb_m = paginated_kb(items, page, PER_PAGE, "bd",
                        extra_rows=extra, show_delete=False)
    if editing:
        await safe_edit(cb_or_msg, header, kb_m)
    else:
        await cb_or_msg.answer(header, reply_markup=kb_m)


@router.callback_query(F.data == "v_bd")
async def cb_v_bd(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒 Admin only", show_alert=True)
        return
    await _show_bd(cb.message)
    await cb.answer()


@router.callback_query(F.data.startswith("bd_pg_"))
async def cb_bd_pg(cb: CallbackQuery):
    page = int(cb.data.rsplit("_", 1)[1])
    await _show_bd(cb.message, page=page)
    await cb.answer()


@router.callback_query(F.data.startswith("bd_info_"))
async def cb_bd_info(cb: CallbackQuery):
    idx = int(cb.data.rsplit("_", 1)[1])
    data = await read_json(F_BD, [])
    if not (0 <= idx < len(data)):
        await cb.answer("Not found", show_alert=True)
        return
    item = data[idx]
    if not isinstance(item, dict):
        item = {"token": str(item)}
    body = json.dumps(item, indent=2, ensure_ascii=False)
    txt = f"<b>{st('BD Token')} #{idx+1}</b>\n<pre>{esc(body)}</pre>"
    await safe_edit(cb.message, txt, kb([
        [InlineKeyboardButton(text=st("⬅️ Back"), callback_data="v_bd")],
    ]))
    await cb.answer()


# ---------- API SETTINGS ----------
async def _show_api(msg):
    api_conf = await load_api_conf()
    alive_imps = [x for x in IMPERSONATES if x not in _dead_imps]
    txt = (
        f"<b>{st('🌐 API Settings')}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"<b>{st('Gen API')}</b>:\n<code>{esc(api_conf['gen_api'])}</code>\n\n"
        f"<b>{st('Like API')}</b>:\n<code>{esc(api_conf['like_api'])}</code>\n\n"
        f"<b>{st('Like Key')}</b>: <code>{esc(api_conf['like_key'])}</code>\n\n"
        f"<b>{st('Impersonation')}</b>:\n"
        f"<code>{', '.join(alive_imps) or '-'}</code>\n"
        f"<b>{st('Dead')}</b>: <code>{', '.join(_dead_imps) or '-'}</code>\n\n"
        f"<i>{st('In Like API you can use {uid}, {region}, {key} placeholders.')}</i>"
    )
    await safe_edit(msg, txt, kb([
        [InlineKeyboardButton(text=st("✏️ Edit Gen API"),
                              callback_data="api_edit_gen")],
        [InlineKeyboardButton(text=st("✏️ Edit Like API"),
                              callback_data="api_edit_like")],
        [InlineKeyboardButton(text=st("🔑 Edit Like Key"),
                              callback_data="api_edit_key")],
        [InlineKeyboardButton(text=st("🔄 Reset Defaults"),
                              callback_data="api_reset_cfm")],
        [InlineKeyboardButton(text=st("⬅️ Back"), callback_data="back")],
    ]))


@router.callback_query(F.data == "v_api")
async def cb_v_api(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒 Admin only", show_alert=True)
        return
    await _show_api(cb.message)
    await cb.answer()


@router.callback_query(F.data == "api_edit_gen")
async def cb_api_edit_gen(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    await state.set_state(S.set_api_gen)
    await safe_edit(cb.message,
                    st("✏️ Send new Gen API URL.\n/cancel to abort."),
                    back_kb("v_api"))
    await cb.answer()


@router.message(S.set_api_gen)
async def on_set_api_gen(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if txt == "/cancel":
        await state.clear()
        t, kb_m = await _render_main()
        await msg.answer(t, reply_markup=kb_m)
        return
    if not txt.startswith(("http://", "https://")):
        await msg.answer(st("❌ Must start with http:// or https://"))
        return

    def mut(old):
        base = old if isinstance(old, dict) else dict(DEFAULT_API)
        base["gen_api"] = txt
        return base

    await update_json(F_API, mut, default=DEFAULT_API)
    invalidate_api_cache()
    await state.clear()
    await activity.add(f"API: gen_api updated")
    t, kb_m = await _render_main()
    await msg.answer(st("✅ Gen API updated."), reply_markup=kb_m)


@router.callback_query(F.data == "api_edit_like")
async def cb_api_edit_like(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    await state.set_state(S.set_api_like)
    await safe_edit(
        cb.message,
        st("✏️ Send new Like API URL.\n"
           "Use {uid}, {region}, {key} placeholders.\n"
           "/cancel to abort."),
        back_kb("v_api"))
    await cb.answer()


@router.message(S.set_api_like)
async def on_set_api_like(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if txt == "/cancel":
        await state.clear()
        t, kb_m = await _render_main()
        await msg.answer(t, reply_markup=kb_m)
        return
    if not txt.startswith(("http://", "https://")):
        await msg.answer(st("❌ Must start with http:// or https://"))
        return

    def mut(old):
        base = old if isinstance(old, dict) else dict(DEFAULT_API)
        base["like_api"] = txt
        return base

    await update_json(F_API, mut, default=DEFAULT_API)
    invalidate_api_cache()
    await state.clear()
    await activity.add(f"API: like_api updated")
    t, kb_m = await _render_main()
    await msg.answer(st("✅ Like API updated."), reply_markup=kb_m)


@router.callback_query(F.data == "api_edit_key")
async def cb_api_edit_key(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    await state.set_state(S.set_api_key)
    await safe_edit(cb.message,
                    st("🔑 Send new Like API Key.\n/cancel to abort."),
                    back_kb("v_api"))
    await cb.answer()


@router.message(S.set_api_key)
async def on_set_api_key(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if txt == "/cancel":
        await state.clear()
        t, kb_m = await _render_main()
        await msg.answer(t, reply_markup=kb_m)
        return
    if not txt:
        await msg.answer(st("❌ Empty key."))
        return

    def mut(old):
        base = old if isinstance(old, dict) else dict(DEFAULT_API)
        base["like_key"] = txt
        return base

    await update_json(F_API, mut, default=DEFAULT_API)
    invalidate_api_cache()
    await state.clear()
    await activity.add(f"API: like_key updated")
    t, kb_m = await _render_main()
    await msg.answer(st("✅ Like Key updated."), reply_markup=kb_m)


@router.callback_query(F.data == "api_reset_cfm")
async def cb_api_reset_cfm(cb: CallbackQuery):
    await safe_edit(cb.message, st("⚠️ Reset API config to defaults?"),
                    confirm_kb("api_reset_yes", "api_reset_no"))
    await cb.answer()


@router.callback_query(F.data == "api_reset_yes")
async def cb_api_reset_yes(cb: CallbackQuery):
    await write_json(F_API, dict(DEFAULT_API))
    invalidate_api_cache()
    await activity.add("API config reset to defaults")
    await _show_api(cb.message)


@router.callback_query(F.data == "api_reset_no")
async def cb_api_reset_no(cb: CallbackQuery):
    await _show_api(cb.message)


# ---------- GENERATE NOW ----------
@router.callback_query(F.data == "do_gen")
async def cb_do_gen(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    if _gen_lock.locked():
        await cb.answer("⏳ Generation already running", show_alert=True)
        return
    await cb.answer()
    await safe_edit(
        cb.message,
        format_progress({"stage": "gen", "done": 0, "total": 1}))

    async def progress(info: dict):
        await safe_edit(cb.message, format_progress(info))

    async def report(total, success, failed, dead_removed, reasons, invalid_count):
        try:
            msg = (
                f"⚙️ <b>{st('BD Token Generation Report')}</b>\n"
                f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
                f"📦 {st('Total')}: <b>{total}</b>\n"
                f"✅ {st('Success')}: <b>{success}</b>\n"
                f"❌ {st('Failed')}: <b>{failed}</b>\n"
            )
            if reasons and reasons != "-":
                msg += f"⚠️ {st('Errors')}: <code>{esc(reasons)}</code>\n"
            if dead_removed:
                msg += f"🧹 {st('Dead removed')}: <b>{dead_removed}</b>\n"
            if invalid_count:
                msg += f"🚫 {st('Invalid tokens')}: <b>{invalid_count}</b>"
            await cb.bot.send_message(ADMIN_ID, msg)
        except Exception:
            pass

    count, total, err, _ = await generate_bd_tokens(progress, report)
    if err:
        await safe_edit(cb.message, f"❌ {esc(err)}", back_kb())
        return
    await safe_edit(
        cb.message,
        f"<b>✅ {st('BD generation complete')}</b>\n"
        f"{st('Success')}: <b>{count}/{total}</b>",
        back_kb())


# ---------- UIDs ----------
async def _show_uids(cb_or_msg, page=0, editing=True):
    data = await read_json(F_UID, [])
    if not isinstance(data, list):
        data = []
    items = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        uid = str(item.get("uid", "?"))
        reg = item.get("region", "?")
        nick = item.get("nickname") or ""
        likes = item.get("likesGiven", 0)
        label = f"{uid} · {reg} · ❤{likes}"
        if nick:
            label += f" · {nick[:10]}"
        items.append((label, i))
    extra = [
        [InlineKeyboardButton(text=st("➕ Add UID"),
                              callback_data="add_uid_region")],
        [InlineKeyboardButton(text=st("⬅️ Back"), callback_data="back")],
    ]
    header = (
        f"<b>{st('👥 UIDs')}: {len(data)}</b>\n"
        f"<i>{st('Tap 🗑 to remove. Click item for details.')}</i>"
    )
    kb_m = paginated_kb(items, page, PER_PAGE, "uid", extra_rows=extra)
    if editing:
        await safe_edit(cb_or_msg, header, kb_m)
    else:
        await cb_or_msg.answer(header, reply_markup=kb_m)


@router.callback_query(F.data == "v_uids")
async def cb_v_uids(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒 Admin only", show_alert=True)
        return
    await _show_uids(cb.message)
    await cb.answer()


@router.callback_query(F.data.startswith("uid_pg_"))
async def cb_uid_pg(cb: CallbackQuery):
    page = int(cb.data.rsplit("_", 1)[1])
    await _show_uids(cb.message, page=page)
    await cb.answer()


@router.callback_query(F.data.startswith("uid_info_"))
async def cb_uid_info(cb: CallbackQuery):
    idx = int(cb.data.rsplit("_", 1)[1])
    data = await read_json(F_UID, [])
    if not (0 <= idx < len(data)):
        await cb.answer("Not found", show_alert=True)
        return
    item = data[idx]
    body = json.dumps(item, indent=2, ensure_ascii=False)
    txt = f"<b>{st('UID Detail')} #{idx+1}</b>\n<pre>{esc(body)}</pre>"
    await safe_edit(cb.message, txt, kb([
        [InlineKeyboardButton(text=st("🌍 Change Region"),
                              callback_data=f"uid_region_{idx}")],
        [InlineKeyboardButton(text=st("🗑 Delete"),
                              callback_data=f"uid_del_cfm_{idx}")],
        [InlineKeyboardButton(text=st("⬅️ Back"), callback_data="v_uids")],
    ]))
    await cb.answer()


@router.callback_query(F.data.startswith("uid_del_cfm_"))
async def cb_uid_del_cfm(cb: CallbackQuery):
    idx = int(cb.data.rsplit("_", 1)[1])
    await safe_edit(cb.message, st(f"⚠️ Delete UID #{idx+1}?"),
                    confirm_kb(f"uid_del_yes_{idx}", f"uid_del_no_{idx}"))
    await cb.answer()


@router.callback_query(F.data.startswith("uid_del_yes_"))
async def cb_uid_del_yes(cb: CallbackQuery):
    idx = int(cb.data.rsplit("_", 1)[1])

    def mut(old):
        if isinstance(old, list) and 0 <= idx < len(old):
            old.pop(idx)
        return old

    await update_json(F_UID, mut, default=[])
    await activity.add(f"UID deleted (idx {idx})")
    await _show_uids(cb.message)
    await cb.answer("Deleted ✅")


@router.callback_query(F.data.startswith("uid_del_no_"))
async def cb_uid_del_no(cb: CallbackQuery):
    await _show_uids(cb.message)
    await cb.answer("Cancelled")


@router.callback_query(F.data.startswith("uid_region_"))
async def cb_uid_region(cb: CallbackQuery):
    idx = int(cb.data.rsplit("_", 1)[1])
    await safe_edit(cb.message, st("🌍 Select new region:"),
                    region_picker(f"uid_rset:{idx}"))
    await cb.answer()


@router.callback_query(F.data.startswith("uid_rset:"))
async def cb_uid_rset(cb: CallbackQuery):
    payload = cb.data.split(":", 1)[1]
    idx_s, region = payload.split(":", 1)
    idx = int(idx_s)

    def mut(old):
        if isinstance(old, list) and 0 <= idx < len(old) and isinstance(old[idx], dict):
            old[idx]["region"] = region
        return old

    await update_json(F_UID, mut, default=[])
    await activity.add(f"UID region: idx {idx} -> {region}")
    await _show_uids(cb.message)
    await cb.answer(f"Region: {region}")


@router.callback_query(F.data == "add_uid_region")
async def cb_add_uid_region(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    await state.set_state(S.pending_region)
    await safe_edit(cb.message, st("🌍 Select region for new UIDs:"),
                    region_picker("addur"))
    await cb.answer()


@router.callback_query(F.data.startswith("addur:"))
async def cb_addur(cb: CallbackQuery, state: FSMContext):
    region = cb.data.split(":", 1)[1]
    await state.update_data(add_region=region)
    await state.set_state(S.add_uid)
    await safe_edit(
        cb.message,
        st(f"📥 Send UID(s) for {region}, one per line.\n/cancel to abort."),
        back_kb())
    await cb.answer()


@router.message(S.add_uid)
async def on_add_uid(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    if text == "/cancel":
        await state.clear()
        t, kb_m = await _render_main()
        await msg.answer(t, reply_markup=kb_m)
        return
    data_state = await state.get_data()
    region = data_state.get("add_region", "BD")
    lines = [u.strip() for u in text.splitlines() if u.strip()]
    valid, invalid = [], 0
    for u in lines:
        if u.isdigit() and 6 <= len(u) <= 15:
            valid.append(u)
        else:
            invalid += 1
    added = 0

    def mut(old):
        nonlocal added
        if not isinstance(old, list):
            old = []
        existing = {str(x.get("uid")) for x in old if isinstance(x, dict)}
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        for u in valid:
            if u in existing:
                continue
            old.append({
                "uid": u, "region": region,
                "nickname": "", "level": 0,
                "likesGiven": 0, "lastLikeCount": 0,
                "lastLikeAt": None,
                "lastUpdated": now,
            })
            added += 1
        return old

    await update_json(F_UID, mut, default=[])
    await activity.add(
        f"UIDs added: {added} (region {region}, skipped {invalid})")
    await state.clear()
    t, kb_m = await _render_main()
    await msg.answer(st(f"✅ Added {added}. Skipped {invalid} invalid."),
                     reply_markup=kb_m)


# ---------- AUTO SETTINGS ----------
async def _show_auto(cb_or_msg, editing=True):
    conf = await _load_conf()
    txt = (
        f"<b>{st('⚙️ Auto Settings')}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"⚡ {st('Gen interval')}: <b>{conf['gen_interval_hours']}h</b>\n"
        f"❤️ {st('Daily like time')}: "
        f"<b>{conf['like_hour']:02d}:{conf['like_minute']:02d}</b> (Asia/Dhaka)\n"
        f"<i>{st('Every run sends to ALL UIDs sequentially.')}</i>\n"
    )
    kb_m = kb([
        [InlineKeyboardButton(text=st("⚡ Set Gen Hours"),
                              callback_data="set_gen_h")],
        [InlineKeyboardButton(text=st("🕒 Set Like Hour"),
                              callback_data="set_like_h")],
        [InlineKeyboardButton(text=st("⏱ Set Like Minute"),
                              callback_data="set_like_m")],
        [InlineKeyboardButton(text=st("⬅️ Back"), callback_data="back")],
    ])
    if editing:
        await safe_edit(cb_or_msg, txt, kb_m)
    else:
        await cb_or_msg.answer(txt, reply_markup=kb_m)


@router.callback_query(F.data == "v_auto")
async def cb_v_auto(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    await _show_auto(cb.message)
    await cb.answer()


@router.callback_query(F.data == "set_gen_h")
async def cb_set_gen_h(cb: CallbackQuery, state: FSMContext):
    await state.set_state(S.set_gen_h)
    await safe_edit(cb.message, st("⚡ Send interval hours (1-24)."), back_kb())
    await cb.answer()


@router.message(S.set_gen_h)
async def on_set_gen_h(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if txt == "/cancel":
        await state.clear()
        t, kb_m = await _render_main()
        await msg.answer(t, reply_markup=kb_m)
        return
    try:
        h = int(txt)
        assert 1 <= h <= 24
    except Exception:
        await msg.answer(st("Invalid. Send 1-24."))
        return

    def mut(old):
        base = old if isinstance(old, dict) else dict(DEFAULT_CONF)
        base["gen_interval_hours"] = h
        return base

    await update_json(F_CONF, mut, default=DEFAULT_CONF)
    await state.clear()
    await activity.add(f"Config: gen_interval_hours={h}")
    await reschedule_jobs()
    t, kb_m = await _render_main()
    await msg.answer(st(f"✅ Gen interval = {h}h"), reply_markup=kb_m)


@router.callback_query(F.data == "set_like_h")
async def cb_set_like_h(cb: CallbackQuery, state: FSMContext):
    await state.set_state(S.set_like_h)
    await safe_edit(cb.message, st("🕒 Send hour (0-23)."), back_kb())
    await cb.answer()


@router.message(S.set_like_h)
async def on_set_like_h(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if txt == "/cancel":
        await state.clear()
        t, kb_m = await _render_main()
        await msg.answer(t, reply_markup=kb_m)
        return
    try:
        h = int(txt)
        assert 0 <= h <= 23
    except Exception:
        await msg.answer(st("Invalid. Send 0-23."))
        return

    def mut(old):
        base = old if isinstance(old, dict) else dict(DEFAULT_CONF)
        base["like_hour"] = h
        return base

    await update_json(F_CONF, mut, default=DEFAULT_CONF)
    await state.clear()
    await activity.add(f"Config: like_hour={h}")
    await reschedule_jobs()
    t, kb_m = await _render_main()
    await msg.answer(st(f"✅ Like hour = {h}"), reply_markup=kb_m)


@router.callback_query(F.data == "set_like_m")
async def cb_set_like_m(cb: CallbackQuery, state: FSMContext):
    await state.set_state(S.set_like_m)
    await safe_edit(cb.message, st("⏱ Send minute (0-59)."), back_kb())
    await cb.answer()


@router.message(S.set_like_m)
async def on_set_like_m(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if txt == "/cancel":
        await state.clear()
        t, kb_m = await _render_main()
        await msg.answer(t, reply_markup=kb_m)
        return
    try:
        m = int(txt)
        assert 0 <= m <= 59
    except Exception:
        await msg.answer(st("Invalid. Send 0-59."))
        return

    def mut(old):
        base = old if isinstance(old, dict) else dict(DEFAULT_CONF)
        base["like_minute"] = m
        return base

    await update_json(F_CONF, mut, default=DEFAULT_CONF)
    await state.clear()
    await activity.add(f"Config: like_minute={m}")
    await reschedule_jobs()
    t, kb_m = await _render_main()
    await msg.answer(st(f"✅ Like minute = {m}"), reply_markup=kb_m)


# ---------- SEND LIKE (admin) ----------
_last_results: list = []


def _result_page_text(results, page, per_page=6):
    total = len(results)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = results[page * per_page:(page + 1) * per_page]
    sent = sum(1 for r in results if status_int(r.get("data") or {}) == 1)
    zero = sum(1 for r in results if status_int(r.get("data") or {}) == 2)
    fail = total - sent - zero
    likes = sum(likes_given(r.get("data") or {}) for r in results
                if status_int(r.get("data") or {}) == 1)
    lines = [
        f"<b>{st('❤️ Like Send Result')}</b>",
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈",
        f"📦 {st('Total')}: <b>{total}</b>",
        f"✅ {st('Sent')}: <b>{sent}</b> ({likes} likes)",
        f"⚪ {st('Zero')}: <b>{zero}</b>",
        f"❌ {st('Failed')}: <b>{fail}</b>",
        "",
        f"<b>{st('Page')} {page+1}/{pages}</b>",
    ]
    for r in chunk:
        uid = esc(r.get("uid"))
        d = r.get("data") or {}
        s = status_int(d)
        if s == 1:
            lines.append(
                f"<code>{uid}</code> → ✅ +{likes_given(d)}\n"
                f"   👤 {esc(d.get('PlayerNickname', '?'))} · "
                f"Lv{d.get('Level', '?')} · {esc(d.get('Region', '?'))}")
        elif s == 2:
            lines.append(
                f"<code>{uid}</code> → ⚪ 0\n"
                f"   👤 {esc(d.get('PlayerNickname', '?'))} · cooldown/max")
        else:
            err = r.get("error") or f"status:{d.get('status')}"
            lines.append(f"<code>{uid}</code> → ❌ {esc(err)}")
    return "\n".join(lines), page, pages


def _result_kb(page, pages, prefix="rlike"):
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️",
                                        callback_data=f"{prefix}_pg_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}",
                                    callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="➡️",
                                        callback_data=f"{prefix}_pg_{page+1}"))
    rows = []
    if len(nav) > 1:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=st("⬅️ Back"), callback_data="back")])
    return kb(rows)


@router.callback_query(F.data == "send_like")
async def cb_send_like(cb: CallbackQuery, state: FSMContext):
    global _last_results
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    if _like_lock.locked():
        await cb.answer("⏳ Like run already in progress", show_alert=True)
        return
    await cb.answer()
    await safe_edit(
        cb.message,
        format_progress({"stage": "sending", "done": 0, "total": 1}))

    async def progress(info: dict):
        await safe_edit(cb.message, format_progress(info))

    results, err = await send_all_likes(progress)
    if err or results is None:
        await safe_edit(cb.message, f"❌ {esc(err or 'failed')}", back_kb())
        return
    _last_results = results
    text, page, pages = _result_page_text(results, 0)
    await safe_edit(cb.message, text, _result_kb(page, pages))


@router.callback_query(F.data.startswith("rlike_pg_"))
async def cb_rlike_pg(cb: CallbackQuery):
    page = int(cb.data.rsplit("_", 1)[1])
    if not _last_results:
        await cb.answer("No results")
        return
    text, page, pages = _result_page_text(_last_results, page)
    await safe_edit(cb.message, text, _result_kb(page, pages))
    await cb.answer()


@router.callback_query(F.data == "retry_failed")
async def cb_retry_failed(cb: CallbackQuery, state: FSMContext):
    global _last_results
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    failed = await read_json(F_FAILED, [])
    if not failed:
        await cb.answer("✅ Failed queue is empty", show_alert=True)
        return
    if _like_lock.locked():
        await cb.answer("⏳ Another run in progress", show_alert=True)
        return
    await cb.answer()
    await safe_edit(
        cb.message,
        format_progress({"stage": "sending", "done": 0, "total": 1}))

    async def progress(info: dict):
        await safe_edit(cb.message, format_progress(info))

    results, err = await retry_failed(progress)
    if err or results is None:
        await safe_edit(cb.message, f"❌ {esc(err or 'failed')}", back_kb())
        return
    _last_results = results
    text, page, pages = _result_page_text(results, 0)
    await safe_edit(cb.message, text, _result_kb(page, pages))


# ---------- FIND UID ----------
@router.callback_query(F.data == "find_uid")
async def cb_find_uid(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    await state.set_state(S.find_uid)
    await safe_edit(cb.message, st("🔍 Send UID to find."), back_kb())
    await cb.answer()


@router.message(S.find_uid)
async def on_find_uid(msg: Message, state: FSMContext):
    query = (msg.text or "").strip()
    await state.clear()
    data = await read_json(F_UID, [])
    found = [x for x in data
             if isinstance(x, dict) and query in str(x.get("uid"))]
    if not found:
        t, kb_m = await _render_main()
        await msg.answer(st(f"No UID matches: {query}"), reply_markup=kb_m)
        return
    body = json.dumps(found[:5], indent=2, ensure_ascii=False)
    await msg.answer(
        f"<b>{st('🔍 Found')}: {len(found)}</b>\n<pre>{esc(body)}</pre>",
        reply_markup=back_kb())


# =========================================================
# GUEST PANEL
# =========================================================
async def _guest_menu_text_kb(user: dict, is_admin: bool = False):
    conf = await load_guest_conf()
    if not conf["enabled"]:
        return st("⚠️ Service is temporarily unavailable. Please try again later."), None

    daily = await guest_daily_state(user)
    total_likes = int(user.get("total_likes", 0)) if user else 0
    today_likes = daily["likes_today"]
    limit = conf["daily_limit"]
    last_uid = daily["last_uid"] or "—"

    text = (
        f"<b>{BRAND}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"👤 {st('Name')}: <b>{esc(user.get('name', 'Guest'))}</b>\n"
        f"🎮 {st('Last UID')}: <code>{esc(last_uid)}</code>\n"
        f"🌍 {st('Region')}: <b>{daily['region']}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"❤️ {st('Today')}: <b>{today_likes}</b> / {limit}\n"
        f"📊 {st('Total likes')}: <b>{total_likes}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"<i>{st('Select an option below')}</i>"
    )

    rows = [
        [InlineKeyboardButton(text=st("❤️ Send Like"), callback_data="g_send_like")],
        [InlineKeyboardButton(text=st("📊 Dashboard"), callback_data="g_dash"),
         InlineKeyboardButton(text=st("📜 History"), callback_data="g_hist")],
        [InlineKeyboardButton(text=st("🛒 Buy Auto Like"),
                              url="https://t.me/hasan_x_fire")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(
            text=st("🔙 Back to Panel"), callback_data="adm_back_panel")])

    return text, kb(rows)


@router.callback_query(F.data == "g_home")
async def cb_g_home(cb: CallbackQuery, state: FSMContext):
    user = cb.from_user
    if not user:
        return
    is_admin = user.id == ADMIN_ID
    guser = await upsert_guest_user(
        user.id, user.full_name, user.username or "")
    text, kb_m = await _guest_menu_text_kb(guser, is_admin=is_admin)
    if kb_m is None:
        await safe_edit(cb.message, text)
    else:
        await safe_edit(cb.message, text, kb_m)
    await cb.answer()


@router.callback_query(F.data == "g_send_like")
async def cb_g_send_like(cb: CallbackQuery, state: FSMContext):
    conf = await load_guest_conf()
    if not conf["enabled"]:
        await cb.answer(st("⚠️ Service unavailable"), show_alert=True)
        return

    user = cb.from_user
    guser = await upsert_guest_user(
        user.id, user.full_name, user.username or "")
    daily = await guest_daily_state(guser)

    if daily["likes_today"] >= conf["daily_limit"]:
        await cb.answer(
            st(f"⚠️ Daily limit reached ({conf['daily_limit']} likes). "
               f"Come back tomorrow!"),
            show_alert=True,
        )
        return

    # Always ask for UID — user can enter a new one each time
    await state.set_state(S.guest_input_uid)
    await safe_edit(
        cb.message,
        f"<b>{st('📥 Send your Free Fire UID')}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"<i>{st('6–15 digits. You can enter a new UID every time.')}</i>",
        back_kb("g_home"))
    await cb.answer()


async def _do_guest_like(cb_or_msg, tg_user, uid, region, conf,
                          via_message: bool = False):
    if via_message:
        status_msg = await cb_or_msg.answer(
            format_progress({"stage": "sending", "done": 0, "total": 1}))
    else:
        status_msg = cb_or_msg.message
        await safe_edit(status_msg,
                        format_progress({"stage": "sending", "done": 0,
                                         "total": 1}))

    rec, err = await guest_send_like(tg_user.id, uid, region)

    if err or not rec:
        await safe_edit(status_msg,
                        f"❌ {st('Failed')}: {esc(err or 'unknown')}",
                        back_kb("g_home"))
        return

    likes = rec.get("likes_given", 0)
    status_str = rec.get("status", "fail")
    guser = await get_guest_user(tg_user.id) or {}
    daily = await guest_daily_state(guser)

    if status_str == "success":
        txt = (
            f"<b>✅ {st('Like Sent')}</b>\n"
            f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            f"🎮 {st('UID')}: <code>{esc(uid)}</code>\n"
            f"👤 {st('Player')}: {esc(rec.get('nickname') or '?')}\n"
            f"❤️ {st('Likes given')}: <b>+{likes}</b>\n"
            f"📊 {st('Your total')}: <b>{rec.get('after_likes', 0)}</b>\n"
            f"🎯 {st('Today')}: <b>{daily['likes_today']}/{conf['daily_limit']}</b>"
        )
    elif status_str == "zero":
        txt = (
            f"<b>⚪ {st('No Likes')}</b>\n"
            f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            f"🎮 {st('UID')}: <code>{esc(uid)}</code>\n"
            f"⚠️ {st('Cooldown or max likes reached for this player.')}"
        )
    else:
        txt = (
            f"<b>❌ {st('Failed')}</b>\n"
            f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            f"🎮 {st('UID')}: <code>{esc(uid)}</code>\n"
            f"⚠️ {esc(rec.get('reason') or 'unknown')}"
        )
    await safe_edit(status_msg, txt, back_kb("g_home"))


@router.message(S.guest_input_uid)
async def on_guest_uid(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    user = msg.from_user
    if not user:
        return

    if txt == "/cancel":
        await state.clear()
        is_admin = user.id == ADMIN_ID
        guser = await upsert_guest_user(
            user.id, user.full_name, user.username or "")
        text, kb_m = await _guest_menu_text_kb(guser, is_admin=is_admin)
        if kb_m is None:
            await msg.answer(text)
        else:
            await msg.answer(text, reply_markup=kb_m)
        return

    if not (txt.isdigit() and 6 <= len(txt) <= 15):
        await msg.answer(st("❌ Invalid UID. Send 6–15 digits."))
        return

    conf = await load_guest_conf()
    if not conf["enabled"]:
        await state.clear()
        await msg.answer(st("⚠️ Service unavailable"))
        return

    guser = await upsert_guest_user(
        user.id, user.full_name, user.username or "")
    daily = await guest_daily_state(guser)

    if daily["likes_today"] >= conf["daily_limit"]:
        await state.clear()
        await msg.answer(
            st(f"⚠️ Daily limit reached ({conf['daily_limit']} likes)."))
        return

    # No UID lock — send like directly with the UID just provided
    await state.clear()
    await _do_guest_like(msg, user, txt, "BD", conf, via_message=True)


@router.callback_query(F.data == "g_dash")
async def cb_g_dash(cb: CallbackQuery, state: FSMContext):
    conf = await load_guest_conf()
    guser = await upsert_guest_user(
        cb.from_user.id, cb.from_user.full_name,
        cb.from_user.username or "")
    daily = await guest_daily_state(guser)

    text = (
        f"<b>{st('📊 Dashboard')}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"👤 {st('Name')}: <b>{esc(guser.get('name', 'Guest'))}</b>\n"
        f"🆔 {st('TG ID')}: <code>{cb.from_user.id}</code>\n"
        f"🎮 {st('Last UID')}: <code>{esc(daily['last_uid'] or '—')}</code>\n"
        f"🌍 {st('Region')}: <b>{daily['region']}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"❤️ {st('Today')}: <b>{daily['likes_today']}</b> / {conf['daily_limit']}\n"
        f"📊 {st('Total likes')}: <b>{guser.get('total_likes', 0)}</b>\n"
        f"🔁 {st('Total runs')}: <b>{guser.get('total_runs', 0)}</b>\n"
        f"📅 {st('Member since')}: {esc((guser.get('first_seen') or '')[:10])}"
    )
    await safe_edit(cb.message, text, back_kb("g_home"))
    await cb.answer()


async def _show_guest_hist(msg, tg_id, page=0, per_page=5, back_cb="g_home"):
    history = await read_json(F_GUEST_HISTORY, [])
    if not isinstance(history, list):
        history = []
    user_hist = [h for h in history
                 if isinstance(h, dict) and h.get("tg_id") == tg_id]
    user_hist = list(reversed(user_hist))
    total = len(user_hist)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = user_hist[page * per_page:(page + 1) * per_page]

    lines = [f"<b>{st('📜 History')}</b>",
             "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"]
    if not chunk:
        lines.append(st("No history yet."))
    else:
        for h in chunk:
            st_str = h.get("status", "?")
            icon = ("✅" if st_str == "success"
                    else ("⚪" if st_str == "zero" else "❌"))
            t = (h.get("time") or "")[:16].replace("T", " ")
            lines.append(
                f"{icon} <code>{esc(h.get('uid', '?'))}</code> "
                f"+{h.get('likes_given', 0)}\n   🕒 {t}"
            )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️", callback_data=f"g_hist_pg_{page-1}"))
    nav.append(InlineKeyboardButton(
        text=f"{page+1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(
            text="➡️", callback_data=f"g_hist_pg_{page+1}"))
    rows = []
    if len(nav) > 1:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text=st("⬅️ Back"), callback_data=back_cb)])
    await safe_edit(msg, "\n".join(lines), kb(rows))


@router.callback_query(F.data == "g_hist")
async def cb_g_hist(cb: CallbackQuery):
    await _show_guest_hist(cb.message, cb.from_user.id, page=0)
    await cb.answer()


@router.callback_query(F.data.startswith("g_hist_pg_"))
async def cb_g_hist_pg(cb: CallbackQuery):
    page = int(cb.data.rsplit("_", 1)[1])
    await _show_guest_hist(cb.message, cb.from_user.id, page=page)
    await cb.answer()


# =========================================================
# ADMIN GUEST PANEL
# =========================================================
async def _show_adm_guest(msg):
    conf = await load_guest_conf()
    users = await read_json(F_GUEST_USERS, [])
    user_count = len(users) if isinstance(users, list) else 0
    hist = await read_json(F_GUEST_HISTORY, [])
    hist_count = len(hist) if isinstance(hist, list) else 0

    status_icon = "✅ ON" if conf["enabled"] else "❌ OFF"
    text = (
        f"<b>{st('🎭 Guest Mode')}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"📡 {st('Status')}: <b>{status_icon}</b>\n"
        f"🎯 {st('Daily limit')}: <b>{conf['daily_limit']}</b> "
        f"{st('likes/ID')}\n"
        f"👥 {st('Total users')}: <b>{user_count}</b>\n"
        f"📜 {st('Total requests')}: <b>{hist_count}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"
    )
    kb_m = kb([
        [InlineKeyboardButton(text=st("⚙️ Settings"),
                              callback_data="adm_guest_set")],
        [InlineKeyboardButton(text=st("👁️ Open Mode"),
                              callback_data="adm_guest_open")],
        [InlineKeyboardButton(text=st("📜 Guest History"),
                              callback_data="adm_guest_hist")],
        [InlineKeyboardButton(text=st("👥 Users"),
                              callback_data="adm_guest_users")],
        [InlineKeyboardButton(text=st("⬅️ Back"), callback_data="back")],
    ])
    await safe_edit(msg, text, kb_m)


@router.callback_query(F.data == "adm_guest")
async def cb_adm_guest(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒 Admin only", show_alert=True)
        return
    await _show_adm_guest(cb.message)
    await cb.answer()


async def _show_adm_guest_set(msg):
    conf = await load_guest_conf()
    status_icon = "✅ ON" if conf["enabled"] else "❌ OFF"
    text = (
        f"<b>{st('⚙️ Guest Settings')}</b>\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"📡 {st('Status')}: <b>{status_icon}</b>\n"
        f"🎯 {st('Daily limit')}: <b>{conf['daily_limit']}</b> "
        f"{st('likes/ID')}\n"
        f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"<i>{st('Users can enter a new UID each time '
                'until daily limit is reached.')}</i>"
    )
    kb_m = kb([
        [InlineKeyboardButton(
            text=st("🔴 Turn OFF") if conf["enabled"] else st("🟢 Turn ON"),
            callback_data="adm_guest_toggle")],
        [InlineKeyboardButton(text=st("🎯 Set Daily Limit"),
                              callback_data="adm_guest_limit")],
        [InlineKeyboardButton(text=st("⬅️ Back"),
                              callback_data="adm_guest")],
    ])
    await safe_edit(msg, text, kb_m)


@router.callback_query(F.data == "adm_guest_set")
async def cb_adm_guest_set(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    await _show_adm_guest_set(cb.message)
    await cb.answer()


@router.callback_query(F.data == "adm_guest_toggle")
async def cb_adm_guest_toggle(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    conf = await load_guest_conf()
    conf["enabled"] = not conf["enabled"]
    await save_guest_conf(conf)
    await activity.add(f"Guest mode: {'ON' if conf['enabled'] else 'OFF'}")
    await _show_adm_guest_set(cb.message)
    await cb.answer(f"Guest mode: {'ON' if conf['enabled'] else 'OFF'}")


@router.callback_query(F.data == "adm_guest_limit")
async def cb_adm_guest_limit(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    await state.set_state(S.adm_guest_limit)
    await safe_edit(cb.message,
                    st("🎯 Send daily limit (1-1000):"),
                    back_kb("adm_guest_set"))
    await cb.answer()


@router.message(S.adm_guest_limit)
async def on_adm_guest_limit(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    txt = (msg.text or "").strip()
    if txt == "/cancel":
        await state.clear()
        t, kb_m = await _render_main()
        await msg.answer(t, reply_markup=kb_m)
        return
    try:
        limit = int(txt)
        assert 1 <= limit <= 1000
    except Exception:
        await msg.answer(st("❌ Invalid. Send 1-1000."))
        return
    conf = await load_guest_conf()
    conf["daily_limit"] = limit
    await save_guest_conf(conf)
    await state.clear()
    await activity.add(f"Guest daily limit: {limit}")
    t, kb_m = await _render_main()
    await msg.answer(st(f"✅ Daily limit = {limit}"), reply_markup=kb_m)


@router.callback_query(F.data == "adm_guest_open")
async def cb_adm_guest_open(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    await state.set_state(S.guest_view)
    guser = await upsert_guest_user(
        cb.from_user.id, cb.from_user.full_name,
        cb.from_user.username or "")
    text, kb_m = await _guest_menu_text_kb(guser, is_admin=True)
    if kb_m is None:
        await safe_edit(cb.message, text)
    else:
        await safe_edit(cb.message, text, kb_m)
    await cb.answer(st("👁️ Guest View Mode"))


@router.callback_query(F.data == "adm_back_panel")
async def cb_adm_back_panel(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return
    await state.clear()
    text, kb_m = await _render_main()
    await safe_edit(cb.message, text, kb_m)
    await cb.answer(st("Panel"))


async def _show_adm_guest_hist(msg, page=0, per_page=4):
    history = await read_json(F_GUEST_HISTORY, [])
    if not isinstance(history, list):
        history = []
    history = list(reversed(history))
    total = len(history)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = history[page * per_page:(page + 1) * per_page]

    lines = [f"<b>{st('📜 Guest History')} ({total})</b>",
             "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"]
    if not chunk:
        lines.append(st("No history yet."))
    else:
        for h in chunk:
            st_str = h.get("status", "?")
            icon = ("✅" if st_str == "success"
                    else ("⚪" if st_str == "zero" else "❌"))
            name = h.get("name") or "?"
            uname = h.get("username") or ""
            tg_id = h.get("tg_id", "?")
            profile = f"tg://user?id={tg_id}"
            t = (h.get("time") or "")[:16].replace("T", " ")
            lines.append(
                f"{icon} <b>{esc(name)}</b>"
                + (f" @{esc(uname)}" if uname else "") + "\n"
                f"   🆔 <a href='{profile}'>{tg_id}</a>\n"
                f"   🎮 <code>{esc(h.get('uid', '?'))}</code> "
                f"({esc(h.get('region', '?'))})\n"
                f"   ❤️ {h.get('likes_given', 0)} "
                f"({h.get('before_likes', 0)} → {h.get('after_likes', 0)})\n"
                f"   🕒 {t}"
            )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️", callback_data=f"adm_hist_pg_{page-1}"))
    nav.append(InlineKeyboardButton(
        text=f"{page+1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(
            text="➡️", callback_data=f"adm_hist_pg_{page+1}"))
    rows = []
    if len(nav) > 1:
        rows.append(nav)
    rows.append([InlineKeyboardButton(
        text=st("⬅️ Back"), callback_data="adm_guest")])
    await safe_edit(msg, "\n".join(lines), kb(rows))


@router.callback_query(F.data == "adm_guest_hist")
async def cb_adm_guest_hist(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    await _show_adm_guest_hist(cb.message, page=0)
    await cb.answer()


@router.callback_query(F.data.startswith("adm_hist_pg_"))
async def cb_adm_hist_pg(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    page = int(cb.data.rsplit("_", 1)[1])
    await _show_adm_guest_hist(cb.message, page=page)
    await cb.answer()


async def _show_adm_guest_users(msg, page=0, per_page=5):
    users = await read_json(F_GUEST_USERS, [])
    if not isinstance(users, list):
        users = []
    users = [u for u in users if isinstance(u, dict)]
    users_sorted = sorted(users, key=lambda x: x.get("last_seen", ""),
                          reverse=True)
    total = len(users_sorted)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = users_sorted[page * per_page:(page + 1) * per_page]

    lines = [f"<b>{st('👥 Guest Users')} ({total})</b>",
             "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"]
    if not chunk:
        lines.append(st("No users yet."))
    else:
        for u in chunk:
            name = u.get("name") or "?"
            uname = u.get("username") or ""
            tg_id = u.get("tg_id", "?")
            uid = u.get("uid") or "—"
            total_likes = u.get("total_likes", 0)
            total_runs = u.get("total_runs", 0)
            profile = f"tg://user?id={tg_id}"
            lines.append(
                f"👤 <b>{esc(name)}</b>"
                + (f" @{esc(uname)}" if uname else "") + "\n"
                f"   🆔 <a href='{profile}'>{tg_id}</a>\n"
                f"   🎮 <code>{esc(uid)}</code>\n"
                f"   ❤️ {total_likes} ({total_runs} runs)"
            )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️", callback_data=f"adm_usr_pg_{page-1}"))
    nav.append(InlineKeyboardButton(
        text=f"{page+1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(
            text="➡️", callback_data=f"adm_usr_pg_{page+1}"))
    rows = []
    if len(nav) > 1:
        rows.append(nav)
    rows.append([InlineKeyboardButton(
        text=st("⬅️ Back"), callback_data="adm_guest")])
    await safe_edit(msg, "\n".join(lines), kb(rows))


@router.callback_query(F.data == "adm_guest_users")
async def cb_adm_guest_users(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    await _show_adm_guest_users(cb.message, page=0)
    await cb.answer()


@router.callback_query(F.data.startswith("adm_usr_pg_"))
async def cb_adm_usr_pg(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin_panel_cb(cb, state):
        await cb.answer("🔒", show_alert=True)
        return
    page = int(cb.data.rsplit("_", 1)[1])
    await _show_adm_guest_users(cb.message, page=page)
    await cb.answer()


# =========================================================
# SCHEDULER
# =========================================================
_sched: AsyncIOScheduler | None = None
_bot_ref = None


def bind_scheduler(bot, sched):
    global _bot_ref, _sched
    _bot_ref = bot
    _sched = sched


async def auto_gen():
    try:
        async def report(total, success, failed, dead_removed, reasons,
                         invalid_count):
            try:
                msg = (
                    f"⚙️ <b>{st('Auto BD Token Gen')}</b>\n"
                    f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
                    f"📦 {st('Total')}: <b>{total}</b>\n"
                    f"✅ {st('Success')}: <b>{success}</b>\n"
                    f"❌ {st('Failed')}: <b>{failed}</b>\n"
                )
                if reasons and reasons != "-":
                    msg += f"⚠️ {st('Errors')}: <code>{esc(reasons)}</code>\n"
                if dead_removed:
                    msg += f"🧹 {st('Dead removed')}: <b>{dead_removed}</b>\n"
                if invalid_count:
                    msg += f"🚫 {st('Invalid tokens saved')}: <b>{invalid_count}</b>"
                await _bot_ref.send_message(ADMIN_ID, msg)
            except Exception as e:
                log.error(f"auto_gen report: {e}")

        await generate_bd_tokens(report_cb=report)
    except Exception as e:
        log.exception(f"auto_gen: {e}")
        try:
            await _bot_ref.send_message(ADMIN_ID, f"⚠️ Auto gen error: {e}")
        except Exception:
            pass


async def auto_like():
    try:
        results, err = await send_all_likes()
        if err:
            await _bot_ref.send_message(
                ADMIN_ID, f"⚠️ Auto like skipped/error: {err}")
            return
        if results is None:
            return
        sent = sum(1 for r in results
                   if status_int(r.get("data") or {}) == 1)
        zero = sum(1 for r in results
                   if status_int(r.get("data") or {}) == 2)
        fail = len(results) - sent - zero
        likes = sum(likes_given(r.get("data") or {}) for r in results
                    if status_int(r.get("data") or {}) == 1)
        await _bot_ref.send_message(
            ADMIN_ID,
            f"🌅 <b>{st('Auto daily likes')}</b>\n"
            f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            f"📦 {st('Total UIDs')}: {len(results)}\n"
            f"✅ {st('Sent')}: {likes} ({sent} players)\n"
            f"⚪ {st('Zero')}: {zero}\n"
            f"❌ {st('Failed')}: {fail}"
        )
    except Exception as e:
        log.exception(f"auto_like: {e}")
        try:
            await _bot_ref.send_message(ADMIN_ID, f"⚠️ Auto like error: {e}")
        except Exception:
            pass


async def reschedule_jobs():
    if _sched is None:
        return
    conf = await _load_conf()
    try:
        for jid in ("gen_bd", "daily_like"):
            if _sched.get_job(jid):
                _sched.remove_job(jid)
        _sched.add_job(
            auto_gen,
            IntervalTrigger(hours=max(1, int(conf["gen_interval_hours"]))),
            id="gen_bd", replace_existing=True,
            misfire_grace_time=300)
        _sched.add_job(
            auto_like,
            CronTrigger(hour=int(conf["like_hour"]),
                        minute=int(conf["like_minute"])),
            id="daily_like", replace_existing=True,
            misfire_grace_time=600)
        await activity.add(
            f"Scheduler: gen={conf['gen_interval_hours']}h, "
            f"like={conf['like_hour']:02d}:{conf['like_minute']:02d}"
        )
    except Exception as e:
        log.exception(f"reschedule_jobs: {e}")


# =========================================================
# HEALTH + STARTUP
# =========================================================
async def health_server(port: int):
    async def health(request):
        gen_info = await read_json(F_GEN_INFO, {}) or {}
        guest_conf = await load_guest_conf()
        return web.json_response({
            "status": "ok",
            "dead_imps": list(_dead_imps),
            "gen_running": _gen_lock.locked(),
            "like_running": _like_lock.locked(),
            "last_gen_at": gen_info.get("lastGenAt", ""),
            "last_gen_success": gen_info.get("lastGenSuccess", 0),
            "guest_mode": guest_conf.get("enabled", True),
            "guest_daily_limit": guest_conf.get("daily_limit", 100),
        })
    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner


async def startup_validate():
    for f, d in [
        (F_ACCESS, []), (F_BD, []), (F_UID, []),
        (F_CONF, DEFAULT_CONF), (F_FAILED, []),
        (F_HISTORY, []), (F_STATS, {}), (F_LOGS, []),
        (F_INVALID, []), (F_API, DEFAULT_API),
        (F_GEN_INFO, DEFAULT_GEN_INFO),
        (F_GUEST_USERS, []),
        (F_GUEST_HISTORY, []),
        (F_GUEST_CONF, DEFAULT_GUEST_CONF),
    ]:
        try:
            c, _ = await gh.read(f)
            if c is None:
                await gh.write(f, json.dumps(d))
                log.info(f"Created default {f}")
        except Exception as e:
            log.error(f"Init {f}: {e}")
            raise


async def main():
    await gh.init()
    await startup_validate()
    await activity.load()

    bot = Bot(BOT_TOKEN,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AdminGate())
    dp.callback_query.middleware(AdminGate())
    dp.include_router(router)

    @dp.error()
    async def on_error(event: ErrorEvent):
        log.exception(f"Handler error: {event.exception}")
        try:
            await bot.send_message(ADMIN_ID,
                                   f"⚠️ Handler error: {event.exception}")
        except Exception:
            pass

    sched = AsyncIOScheduler(timezone="Asia/Dhaka")
    bind_scheduler(bot, sched)
    await reschedule_jobs()
    sched.start()

    health_runner = await health_server(HEALTH_PORT)

    bd = await read_json(F_BD, [])
    if not bd:
        asyncio.create_task(generate_bd_tokens())

    stop_event = asyncio.Event()

    def _signal(*_):
        log.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, _signal)
        except Exception:
            pass

    log.info("✅ Bot v3.3 started (Guest Mode — No UID Lock)")
    polling = asyncio.create_task(
        dp.start_polling(bot,
                         allowed_updates=dp.resolve_used_update_types()))

    await stop_event.wait()
    log.info("Stopping...")

    try:
        sched.shutdown(wait=False)
    except Exception:
        pass
    try:
        await health_runner.cleanup()
    except Exception:
        pass
    try:
        await pool.close_all()
    except Exception:
        pass
    try:
        await gh.close()
    except Exception:
        pass
    try:
        await bot.session.close()
    except Exception:
        pass
    polling.cancel()
    try:
        await polling
    except Exception:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Stopped")