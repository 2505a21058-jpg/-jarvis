"""
interfaces/remote_bridge.py

Jarvis Remote Bridge - phone-to-desktop control.
Supports Telegram bot (primary) and WebSocket (fallback).
All commands pass through run_agent_cycle() exactly as CLI.

Security:
- PIN/token auth required before commands accepted
- High-risk skill approval flow
- No public internet exposure by default - use Tailscale/VPN

Dependencies (all optional - graceful degradation):
- python-telegram-bot >= 21.0
- fastapi + uvicorn OR websockets
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable


logger = logging.getLogger("jarvis.remote_bridge")

_BRIDGE_TOKEN = os.environ.get("JARVIS_BRIDGE_TOKEN", "")
_AUTHORIZED_CHAT_IDS: set[int] = set()

if not _BRIDGE_TOKEN:
    logger.warning(
        "JARVIS_BRIDGE_TOKEN not set. Remote bridge will reject all connections."
    )


def _is_authorized(chat_id: int) -> bool:
    return chat_id in _AUTHORIZED_CHAT_IDS


def _authorize(chat_id: int, token: str) -> bool:
    if token == _BRIDGE_TOKEN and _BRIDGE_TOKEN:
        _AUTHORIZED_CHAT_IDS.add(chat_id)
        logger.info("Remote chat authorized: %s", chat_id)
        return True
    logger.warning("Auth failed for chat_id: %s", chat_id)
    return False


_HIGH_RISK_SKILLS = {"delete", "format", "system_command", "send_email"}
_pending_approvals: dict[str, dict] = {}


def _is_high_risk(user_input: str) -> bool:
    lowered = str(user_input or "").lower()
    return any(skill in lowered for skill in _HIGH_RISK_SKILLS)


async def _run_cycle(user_input: str, memory, state) -> str:
    from agent.loop import run_agent_cycle

    result = await run_agent_cycle(user_input, memory, state)
    if isinstance(result, tuple) and result:
        cycle_result = result[0]
        if isinstance(cycle_result, dict):
            return str(cycle_result.get("output") or "").strip()
        return str(cycle_result)
    return str(result)


async def _handle_remote_input(
    user_input: str,
    chat_id: int,
    responder: Callable[[str], Awaitable[None]],
    memory,
    state,
) -> None:
    if not _is_authorized(chat_id):
        if user_input.startswith("/auth "):
            token = user_input[6:].strip()
            if _authorize(chat_id, token):
                await responder("Authorized. You can now send commands to Jarvis.")
            else:
                await responder("Invalid token.")
        else:
            await responder("Not authorized. Send: /auth YOUR_TOKEN")
        return

    if user_input.strip() == "/status":
        await responder(
            f"Jarvis is running\n"
            f"Active app: {state.active_app or 'none'}\n"
            f"Mode: {state.mode}"
        )
        return

    if user_input.strip() == "/clear":
        state.conversation_history.clear()
        await responder("Conversation history cleared.")
        return

    if user_input.strip() == "/cancel":
        keys_to_clear = [key for key, item in _pending_approvals.items() if item.get("chat_id") == chat_id]
        if not keys_to_clear:
            await responder("Nothing pending approval.")
            return
        for key in keys_to_clear:
            _pending_approvals.pop(key, None)
        await responder("Action cancelled.")
        return

    if user_input.strip() == "/approve":
        matching = next(
            ((key, item) for key, item in _pending_approvals.items() if item.get("chat_id") == chat_id),
            None,
        )
        if matching is None:
            await responder("Nothing pending approval.")
            return
        key, item = matching
        _pending_approvals.pop(key, None)
        approved_input = str(item.get("input", "")).strip()
        await responder(f"Executing: {approved_input}")
        user_input = approved_input
    elif _is_high_risk(user_input):
        approval_key = f"{chat_id}:{user_input[:40]}"
        if approval_key not in _pending_approvals:
            _pending_approvals[approval_key] = {"input": user_input, "chat_id": chat_id}
            await responder(
                f"High-risk action:\n`{user_input}`\n\n"
                "Reply /approve to confirm or /cancel to abort."
            )
            return

    await responder("Processing...")
    try:
        response = await _run_cycle(user_input, memory, state)
        await responder(response or "I couldn't produce a useful response.")
    except Exception as exc:
        logger.error("Remote bridge agent error: %s", exc)
        await responder(f"Error: {str(exc)[:200]}")


class TelegramBridge:
    def __init__(self, memory, state):
        self._memory = memory
        self._state = state
        self._app = None

    def start(self) -> None:
        try:
            from telegram.ext import Application, CommandHandler, MessageHandler, filters
        except ImportError:
            logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot>=21.0")
            return

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set. Telegram bridge disabled.")
            return

        self._app = Application.builder().token(bot_token).build()
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("auth", self._on_auth))
        self._app.add_handler(CommandHandler("status", self._on_status))
        self._app.add_handler(CommandHandler("approve", self._on_approve))
        self._app.add_handler(CommandHandler("cancel", self._on_cancel))

        logger.info("Telegram bridge starting (polling mode)")
        self._app.run_polling(drop_pending_updates=True)

    def stop(self) -> None:
        if self._app is None:
            return
        try:
            self._app.stop()
        except Exception as exc:
            logger.warning("Telegram bridge stop warning: %s", exc)

    async def _on_start(self, update, context):
        await update.message.reply_text(
            "I'm Jarvis - your local AI agent.\n"
            "Send /auth YOUR_TOKEN to authenticate."
        )

    async def _on_auth(self, update, context):
        token = " ".join(context.args) if context.args else ""
        await _handle_remote_input(
            f"/auth {token}",
            update.effective_chat.id,
            update.message.reply_text,
            self._memory,
            self._state,
        )

    async def _on_status(self, update, context):
        await _handle_remote_input(
            "/status",
            update.effective_chat.id,
            update.message.reply_text,
            self._memory,
            self._state,
        )

    async def _on_approve(self, update, context):
        await _handle_remote_input(
            "/approve",
            update.effective_chat.id,
            update.message.reply_text,
            self._memory,
            self._state,
        )

    async def _on_cancel(self, update, context):
        await _handle_remote_input(
            "/cancel",
            update.effective_chat.id,
            update.message.reply_text,
            self._memory,
            self._state,
        )

    async def _on_message(self, update, context):
        await _handle_remote_input(
            update.message.text,
            update.effective_chat.id,
            update.message.reply_text,
            self._memory,
            self._state,
        )


class WebSocketBridge:
    def __init__(self, memory, state, host: str = "127.0.0.1", port: int = 8765):
        self._memory = memory
        self._state = state
        self._host = host
        self._port = port
        self._loop: asyncio.AbstractEventLoop | None = None

    def start_in_thread(self) -> None:
        import threading

        thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name="jarvis-websocket",
        )
        thread.start()
        logger.info("WebSocket bridge started on ws://%s:%s", self._host, self._port)

    def stop(self) -> None:
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_server(self) -> None:
        try:
            import websockets  # noqa: F401
        except ImportError:
            logger.error("websockets not installed. Run: pip install websockets")
            return
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        import websockets

        self._loop = asyncio.get_running_loop()
        async with websockets.serve(self._handle_connection, self._host, self._port):
            await asyncio.Future()

    async def _handle_connection(self, websocket) -> None:
        import json

        logger.info("WebSocket client connected: %s", getattr(websocket, "remote_address", "unknown"))
        try:
            async for raw_message in websocket:
                try:
                    data = json.loads(raw_message)
                    chat_id = int(data.get("chat_id", 0))
                    message = str(data.get("message", ""))
                except (json.JSONDecodeError, ValueError):
                    await websocket.send(json.dumps({"status": "error", "response": "Invalid JSON"}))
                    continue

                async def responder(text: str) -> None:
                    await websocket.send(json.dumps({"status": "ok", "response": text}))

                await _handle_remote_input(
                    message,
                    chat_id,
                    responder,
                    self._memory,
                    self._state,
                )
        except Exception as exc:
            logger.warning("WebSocket connection error: %s", exc)


class RemoteBridge:
    def __init__(self, memory, state):
        self._telegram = TelegramBridge(memory, state)
        self._websocket = WebSocketBridge(memory, state)

    def start(self, enable_telegram: bool = True, enable_websocket: bool = True) -> None:
        if enable_websocket:
            self._websocket.start_in_thread()
        if enable_telegram:
            import threading

            thread = threading.Thread(
                target=self._telegram.start,
                daemon=True,
                name="jarvis-telegram",
            )
            thread.start()
            logger.info("Telegram bridge starting in background thread")

    def stop(self) -> None:
        self._telegram.stop()
        self._websocket.stop()
