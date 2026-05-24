"""
interfaces/web/app.py

FastAPI web server for Jarvis.
Serves the SPA frontend, REST API, and WebSocket chat.
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from interfaces.web.security import is_safe_web_origin, is_web_request_authorized

logger = logging.getLogger("jarvis.web")


class ChatRequest(BaseModel):
    message: str


class ModeRequest(BaseModel):
    mode: str


_APP: FastAPI | None = None
_MEMORY = None
_STATE = None


async def require_web_auth(request: Request) -> None:
    headers = request.headers
    if not is_safe_web_origin(headers.get("origin") or headers.get("referer"), headers.get("host", "")):
        raise HTTPException(status_code=403, detail="cross-origin request blocked")
    if not is_web_request_authorized(headers, request.query_params.get("token")):
        raise HTTPException(status_code=401, detail="web token required")


def _websocket_authorized(ws: WebSocket) -> bool:
    headers = ws.headers
    if not is_safe_web_origin(headers.get("origin"), headers.get("host", "")):
        return False
    return is_web_request_authorized(headers, ws.query_params.get("token"))


def create_app(memory, state) -> FastAPI:
    global _MEMORY, _STATE, _APP
    _MEMORY = memory
    _STATE = state

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Jarvis web server started")
        yield
        logger.info("Jarvis web server stopped")

    app = FastAPI(lifespan=lifespan)

    # Serve static frontend
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
    if os.path.isdir(frontend_dir):
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    async def index():
        index_path = os.path.join(frontend_dir, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        return {"error": "frontend not built"}

    # ── REST API ──────────────────────────────────

    @app.get("/api/status", dependencies=[Depends(require_web_auth)])
    async def get_status():
        """Full dev board status."""
        from interfaces.web.status import probe_all
        return probe_all(memory=_MEMORY)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "model": os.environ.get("JARVIS_MODEL", "qwen3:8b")}

    @app.get("/api/conversation", dependencies=[Depends(require_web_auth)])
    async def get_conversation():
        if _STATE is None:
            return []
        if hasattr(_STATE, "conversation_history"):
            return _STATE.conversation_history[-50:]
        return []

    @app.post("/api/chat", dependencies=[Depends(require_web_auth)])
    async def chat(req: ChatRequest):
        if not req.message.strip():
            return {"response": ""}
        from agent.loop import run_agent_cycle
        result = await run_agent_cycle(req.message, _MEMORY, _STATE)
        if isinstance(result, tuple) and result:
            cycle_result = result[0]
            if isinstance(cycle_result, dict):
                return {"response": cycle_result.get("output", "")}
            return {"response": str(cycle_result)}
        return {"response": str(result)}

    @app.post("/api/clear", dependencies=[Depends(require_web_auth)])
    async def clear_conversation():
        if _STATE is not None and hasattr(_STATE, "conversation_history"):
            _STATE.conversation_history.clear()
        return {"ok": True}

    @app.get("/api/models", dependencies=[Depends(require_web_auth)])
    async def list_models():
        try:
            from config import OLLAMA_TAGS_URL
            import urllib.request
            with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=5) as r:
                data = json.loads(r.read())
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/mode", dependencies=[Depends(require_web_auth)])
    async def set_mode(req: ModeRequest):
        valid = {"fast", "smart", "nerd"}
        if req.mode not in valid:
            return {"error": f"invalid mode: {req.mode}, valid: {valid}"}
        if _STATE is not None and hasattr(_STATE, "mode"):
            _STATE.mode = req.mode
        return {"ok": True, "mode": req.mode}

    # ── WEBSOCKET ─────────────────────────────────

    @app.websocket("/ws/chat")
    async def websocket_chat(ws: WebSocket):
        if not _websocket_authorized(ws):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                    message = data.get("message", "")
                except json.JSONDecodeError:
                    message = raw

                if not message.strip():
                    continue

                from agent.loop import run_agent_cycle
                result = await run_agent_cycle(message, _MEMORY, _STATE)
                if isinstance(result, tuple) and result:
                    cycle_result = result[0]
                    if isinstance(cycle_result, dict):
                        response = cycle_result.get("output", "")
                    else:
                        response = str(cycle_result)
                else:
                    response = str(result)

                await ws.send_json({"response": response})
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("WebSocket error: %s", e)

    _APP = app
    return app


def get_app() -> FastAPI | None:
    return _APP


def start_web_server(memory, state, host: str = "127.0.0.1", port: int = 9090):
    """Start the uvicorn server in a background thread."""
    import threading
    import uvicorn

    app = create_app(memory, state)

    def run():
        uvicorn.run(app, host=host, port=port, log_level="info")

    thread = threading.Thread(target=run, daemon=True, name="jarvis-web")
    thread.start()
    logger.info("Jarvis web UI: http://%s:%s", host, port)
    return thread
