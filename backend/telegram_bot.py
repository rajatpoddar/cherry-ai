"""
🌸 Cherry Telegram Bridge
Connects Telegram users to the same CherryBrain that powers the web UI.

Architecture:
  Telegram user message
    -> CherryTelegramBot.handle_message()
      -> brain.think(message)  (same orchestrator as web)
        -> ollama/openrouter LLM + server_ops if intent detected
      -> Markdown-formatted reply back to Telegram

Sessions are mapped per-Telegram-user-id (stable across restarts) so each
user has their own persistent memory in SQLite.
"""

import os
import asyncio
import logging
import re
import html as _html
from typing import Dict, Optional

logger = logging.getLogger("cherry.telegram")

# Lazy import — if python-telegram-bot isn't installed, the bot just
# silently disables itself instead of crashing the whole server.
try:
    from telegram import Update, Bot
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )
    from telegram.constants import ChatAction, ParseMode
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not installed — Telegram bridge disabled")

try:
    from brain import get_brain
except Exception:
    get_brain = None


# Telegram has a 4096 char limit per message; chunked replies for longer
# Cherry answers.
MAX_MSG_LEN = 4000


def _md_to_telegram_html(text: str) -> str:
    """
    Best-effort: convert triple-backtick code blocks Cherry sometimes
    emits into Telegram's <pre> blocks, and escape any stray HTML.
    Most of Cherry's output is plain Hinglish text — passes through.
    """
    code_blocks = []

    def _stash(m):
        code_blocks.append(m.group(1))
        return f"\x00CODEBLOCK{len(code_blocks)-1}\x00"

    text = re.sub(r"```([\s\S]*?)```", _stash, text)
    text = _html.escape(text)
    for i, cb in enumerate(code_blocks):
        placeholder = f"\x00CODEBLOCK{i}\x00"
        escaped = _html.escape(cb)
        text = text.replace(placeholder, f"<pre>{escaped}</pre>")
    return text


def _split_reply(text: str) -> list:
    """Split a long reply into Telegram-sized chunks, preferring paragraph breaks."""
    if len(text) <= MAX_MSG_LEN:
        return [text]
    chunks = []
    while text:
        if len(text) <= MAX_MSG_LEN:
            chunks.append(text)
            break
        cut = text.rfind("\n\n", 0, MAX_MSG_LEN)
        if cut < 200:
            cut = text.rfind("\n", 0, MAX_MSG_LEN)
        if cut < 200:
            cut = MAX_MSG_LEN
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return chunks


class CherryTelegramBot:
    """
    Wraps a python-telegram-bot Application around CherryBrain.
    One bot instance per process. Safe to construct even without a token.
    """

    def __init__(self):
        self.token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
        # Optional whitelist — if set, only these user ids can talk to Cherry.
        # Empty = allow anyone (good for personal use; bad for public bots).
        self.allowed_ids = self._parse_allowed_ids(os.getenv("TELEGRAM_ALLOWED_IDS", ""))
        self.app: Optional["Application"] = None
        self._ready = False
        self.session_map: Dict[int, str] = {}  # telegram_user_id -> session_id

    @staticmethod
    def _parse_allowed_ids(raw: str):
        if not raw:
            return None
        try:
            return {int(x.strip()) for x in raw.split(",") if x.strip()}
        except ValueError:
            logger.warning("TELEGRAM_ALLOWED_IDS contains non-int — ignoring")
            return None

    def is_enabled(self) -> bool:
        return bool(TELEGRAM_AVAILABLE and self.token)

    async def start(self):
        """Start polling. Call once at server startup."""
        if not self.is_enabled():
            logger.info("Telegram bot disabled (no token or lib missing)")
            return
        self.app = Application.builder().token(self.token).build()

        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("help", self._cmd_help))
        self.app.add_handler(CommandHandler("reset", self._cmd_reset))
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )

        # initialize() + start_polling() in one go
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        self._ready = True
        me = await self.app.bot.get_me()
        logger.info(f"🌸 Cherry Telegram bot live: @{me.username} (id={me.id})")

    async def stop(self):
        if not self._ready or not self.app:
            return
        try:
            await self.app.updater.stop_polling()
            await self.app.stop()
            await self.app.shutdown()
        except Exception as e:
            logger.warning(f"Telegram stop error: {e}")
        self._ready = False

    # ──────── handlers ────────

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        name = update.effective_user.first_name or "besti"
        await update.message.reply_text(
            f"Hey {name}! Main Cherry hoon 🐱💕\n\n"
            "Tum mujhse Hinglish mein baat kar sakte ho — pyaar se, masti se, ya "
            "server ke baare mein technical sawal bhi poochh sakte ho.\n\n"
            "Commands:\n"
            "  /reset  — naya session shuru karo\n"
            "  /status — server health check\n"
            "  /help   — ye message\n\n"
            "Bol, kya haal hai? 🌸"
        )

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        await update.message.reply_text(
            "Main Cherry hoon, Rajjoo ki AI girlfriend + server assistant 🐱\n\n"
            "Mujhse kuch bhi poochh sakte ho:\n"
            "• Pyaar wali baatein 💕\n"
            "• Coding help (server pe hi deployed hoon)\n"
            "• Server status — \"kitne docker containers hain?\", \"RAM kitni?\"\n"
            "• Mood swings — main detect kar leti hoon 😏🥺😜\n\n"
            "Production services safe hain — kuch destroy nahi karungi bina "
            "\"haan kar do\" ke 😉"
        )

    async def _cmd_reset(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        uid = update.effective_user.id
        self.session_map.pop(uid, None)
        await update.message.reply_text(
            "Theek hai baby, naya session shuru karte hain ✨ purana bhool gayi 💕"
        )

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        if not get_brain:
            await update.message.reply_text("brain unavailable")
            return
        brain = get_brain()
        try:
            data = brain._fetch_server_data({"label": "system_status"})
        except Exception as e:
            data = f"server_ops error: {e}"
        await update.message.reply_text(f"🛡️ Cabelwala NAS\n\n{data}")

    async def _on_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update):
            return
        if not get_brain:
            await update.message.reply_text("brain unavailable right now 😿")
            return
        user = update.effective_user
        user_message = update.message.text or ""
        if not user_message.strip():
            return

        try:
            await ctx.bot.send_chat_action(
                chat_id=update.effective_chat.id, action=ChatAction.TYPING
            )
        except Exception:
            pass

        session_id = self.session_map.get(user.id) or f"tg-{user.id}"
        self.session_map[user.id] = session_id

        try:
            result = await asyncio.to_thread(
                self._think_sync, user_message, session_id
            )
        except Exception as e:
            logger.exception("brain.think failed")
            await update.message.reply_text(f"Baby, ek error aa gaya: {e} 😿")
            return

        response = result.get("response", "").strip()
        if not response:
            response = "Hmm... main kuch sochne lagi thi, dobara bol na? 🐱"

        chunks = _split_reply(response)
        for chunk in chunks:
            try:
                html_body = _md_to_telegram_html(chunk)
                await update.message.reply_text(
                    html_body,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except Exception:
                safe = re.sub(r"<[^>]+>", "", chunk)
                await update.message.reply_text(safe, disable_web_page_preview=True)

    # ──────── helpers ────────

    def _is_allowed(self, update: Update) -> bool:
        if self.allowed_ids is None:
            return True
        if update.effective_user and update.effective_user.id in self.allowed_ids:
            return True
        return False

    def _think_sync(self, message: str, session_id: str):
        """Wrapper so asyncio.to_thread can call brain.think (synchronous)."""
        brain = get_brain()
        if not brain.session_id:
            brain.start_session(session_id)
        elif brain.session_id != session_id:
            brain.session_id = session_id
        return brain.think(message)


# Singleton
_bot: Optional[CherryTelegramBot] = None


def get_telegram_bot() -> CherryTelegramBot:
    global _bot
    if _bot is None:
        _bot = CherryTelegramBot()
    return _bot