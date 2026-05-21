"""
agent/harness/tab.py

Represents a single CDP-connected browser tab or Electron window.
All reading and writing to a browser context goes through Tab.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("jarvis.harness.tab")

_CMD_TIMEOUT = 10.0


class Tab:
    """
    A single CDP session - one browser tab or Electron window.

    Reading:
      get_dom()          full DOM tree as dict
      get_ax_tree()      accessibility tree
      get_url()          current URL
      get_title()        page title
      get_text()         visible text content
      get_console_logs() recent JS console output
      get_network_log()  recent network requests
      evaluate(js)       execute JavaScript, return result

    Writing:
      click(node_id)      click by CDP node ID
      type_text(text)     type text into element
      focus(node_id)      focus element
      navigate(url)       navigate to URL
      key(combo)          keyboard shortcut
      scroll(...)         scroll
      fetch(...)          make HTTP request as the page
      set_value(...)      set input value directly
    """

    def __init__(
        self,
        ws_url: str,
        tab_id: str,
        title: str = "",
        url: str = "",
    ):
        self.ws_url = ws_url
        self.tab_id = tab_id
        self.title = title
        self.url = url
        self._ws = None
        self._cmd_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._connected = False
        self._last_used = time.time()
        self._event_listeners: dict[str, list] = {}
        self._receiver_task: Optional[asyncio.Task] = None
        self._console_logs: list[str] = []
        self._network_log: list[dict[str, Any]] = []

    async def connect(self) -> bool:
        """Open WebSocket connection to this tab."""
        try:
            import websockets

            self._ws = await websockets.connect(
                self.ws_url,
                max_size=50 * 1024 * 1024,
                ping_interval=20,
                ping_timeout=10,
            )
            self._connected = True
            self._receiver_task = asyncio.ensure_future(self._receive_loop())
            await self._enable_domains()
            logger.info("[TAB] Connected: %s", self.title or self.url)
            return True
        except Exception as exc:
            logger.error("[TAB] Connect failed %s: %s", self.ws_url, exc)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._connected = False
        if self._receiver_task:
            self._receiver_task.cancel()
            self._receiver_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(RuntimeError("Tab disconnected"))
        self._pending.clear()

    async def _enable_domains(self) -> None:
        for domain in (
            "DOM.enable",
            "Accessibility.enable",
            "Page.enable",
            "Network.enable",
            "Runtime.enable",
        ):
            try:
                await self._send(domain)
            except Exception as exc:
                logger.debug("[TAB] Could not enable %s: %s", domain, exc)

    async def _receive_loop(self) -> None:
        """Background task receiving CDP messages."""
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if "id" in msg:
                    future = self._pending.pop(msg["id"], None)
                    if future and not future.done():
                        if "error" in msg:
                            future.set_exception(RuntimeError(f"CDP error: {msg['error']}"))
                        else:
                            future.set_result(msg.get("result", {}))
                    continue

                method = msg.get("method")
                if not method:
                    continue

                params = msg.get("params", {})
                self._record_event(method, params)
                for callback in self._event_listeners.get(method, []):
                    try:
                        callback(params)
                    except Exception:
                        logger.debug("[TAB] Event callback failed for %s", method, exc_info=True)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("[TAB] Receive loop ended: %s", exc)
        finally:
            self._connected = False

    def _record_event(self, method: str, params: dict[str, Any]) -> None:
        if method == "Runtime.consoleAPICalled":
            args = params.get("args", [])
            text = " ".join(str(arg.get("value", arg.get("description", ""))) for arg in args)
            if text:
                self._console_logs.append(text)
                self._console_logs = self._console_logs[-200:]
        elif method == "Network.requestWillBeSent":
            request = params.get("request", {})
            self._network_log.append(
                {
                    "type": "request",
                    "requestId": params.get("requestId"),
                    "url": request.get("url", ""),
                    "method": request.get("method", ""),
                    "timestamp": params.get("timestamp"),
                }
            )
            self._network_log = self._network_log[-500:]
        elif method == "Network.responseReceived":
            response = params.get("response", {})
            self._network_log.append(
                {
                    "type": "response",
                    "requestId": params.get("requestId"),
                    "url": response.get("url", ""),
                    "status": response.get("status"),
                    "mimeType": response.get("mimeType", ""),
                    "timestamp": params.get("timestamp"),
                }
            )
            self._network_log = self._network_log[-500:]

    async def _send(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Send CDP command and await response."""
        if not self._connected or not self._ws:
            raise RuntimeError("Tab not connected")

        self._cmd_id += 1
        cmd_id = self._cmd_id
        msg = {"id": cmd_id, "method": method, "params": params or {}}

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending[cmd_id] = future

        try:
            await self._ws.send(json.dumps(msg))
            result = await asyncio.wait_for(future, timeout=_CMD_TIMEOUT)
            self._last_used = time.time()
            return result
        except asyncio.TimeoutError:
            self._pending.pop(cmd_id, None)
            raise TimeoutError(f"CDP command timed out: {method}")
        except Exception:
            self._pending.pop(cmd_id, None)
            raise

    async def get_url(self) -> str:
        try:
            result = await self._send(
                "Runtime.evaluate",
                {"expression": "window.location.href", "returnByValue": True},
            )
            url = result.get("result", {}).get("value", "")
            self.url = url
            return url
        except Exception:
            return self.url

    async def get_title(self) -> str:
        try:
            result = await self._send(
                "Runtime.evaluate",
                {"expression": "document.title", "returnByValue": True},
            )
            title = result.get("result", {}).get("value", "")
            self.title = title
            return title
        except Exception:
            return self.title

    async def get_ax_tree(self) -> dict[str, Any]:
        """Get the full accessibility tree."""
        try:
            return await self._send("Accessibility.getFullAXTree")
        except Exception as exc:
            logger.warning("[TAB] AX tree failed: %s", exc)
            return {}

    async def get_dom(self) -> dict[str, Any]:
        """Get full DOM tree."""
        try:
            result = await self._send("DOM.getDocument", {"depth": -1, "pierce": True})
            return result.get("root", {})
        except Exception as exc:
            logger.warning("[TAB] DOM failed: %s", exc)
            return {}

    async def get_text(self) -> str:
        """Get visible text content of the page."""
        try:
            result = await self._send(
                "Runtime.evaluate",
                {"expression": "document.body ? document.body.innerText : ''", "returnByValue": True},
            )
            return result.get("result", {}).get("value", "")
        except Exception:
            return ""

    async def evaluate(self, js: str) -> Any:
        """Execute JavaScript in page context and return the result value."""
        try:
            result = await self._send(
                "Runtime.evaluate",
                {
                    "expression": js,
                    "returnByValue": True,
                    "awaitPromise": True,
                },
            )
            return result.get("result", {}).get("value")
        except Exception as exc:
            logger.error("[TAB] evaluate failed: %s", exc)
            return None

    async def get_console_logs(self) -> list[str]:
        """Get recent JS console output."""
        return list(self._console_logs)

    async def get_network_log(self) -> list[dict[str, Any]]:
        """Get recent network request/response events."""
        return list(self._network_log)

    async def get_node_box(self, node_id: int) -> Optional[dict[str, Any]]:
        """Get bounding box model of a DOM node."""
        try:
            result = await self._send("DOM.getBoxModel", {"nodeId": node_id})
            return result.get("model")
        except Exception:
            return None

    async def navigate(self, url: str) -> bool:
        """Navigate to URL."""
        try:
            await self._send("Page.navigate", {"url": url})
            await asyncio.sleep(0.5)
            self.url = url
            logger.info("[TAB] Navigated to %s", url)
            return True
        except Exception as exc:
            logger.error("[TAB] Navigate failed: %s", exc)
            return False

    async def click(self, node_id: int) -> bool:
        """Click a DOM node by CDP node ID."""
        try:
            box = await self.get_node_box(node_id)
            if box:
                quad = box.get("content", [])
                if len(quad) >= 8:
                    x = (quad[0] + quad[2] + quad[4] + quad[6]) / 4
                    y = (quad[1] + quad[3] + quad[5] + quad[7]) / 4
                    await self._send(
                        "Input.dispatchMouseEvent",
                        {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
                    )
                    await self._send(
                        "Input.dispatchMouseEvent",
                        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
                    )
                    return True

            object_id = await self._node_to_object(node_id)
            if not object_id:
                return False
            await self._send(
                "Runtime.callFunctionOn",
                {"objectId": object_id, "functionDeclaration": "function() { this.click(); }"},
            )
            return True
        except Exception as exc:
            logger.error("[TAB] click failed node_id=%s: %s", node_id, exc)
            return False

    async def click_ax_node(self, ax_node_id: str) -> bool:
        """Click using an accessibility node ID when the page exposes one."""
        try:
            js = f"""
            (function() {{
                var el = document.querySelector('[data-ax-id="{ax_node_id}"]');
                if (el) {{ el.click(); return true; }}
                return false;
            }})()
            """
            return bool(await self.evaluate(js))
        except Exception as exc:
            logger.error("[TAB] click_ax_node failed: %s", exc)
            return False

    async def type_text(
        self,
        text: str,
        node_id: Optional[int] = None,
        delay_ms: int = 30,
    ) -> bool:
        """Type text into the focused element, optionally focusing node_id first."""
        try:
            if node_id:
                await self.focus(node_id)
                await asyncio.sleep(0.1)

            await self._send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "modifiers": 2})
            await self._send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "modifiers": 2})

            for char in text:
                await self._send("Input.insertText", {"text": char})
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)

            return True
        except Exception as exc:
            logger.error("[TAB] type_text failed: %s", exc)
            return False

    async def type(self, node_id: int, text: str) -> bool:
        """Compatibility alias for typing into a specific node."""
        return await self.type_text(text=text, node_id=node_id)

    async def set_value(self, node_id: int, value: str) -> bool:
        """Set an input value directly and dispatch input/change events."""
        try:
            await self.focus(node_id)
            await self.evaluate(
                f"""
                (function() {{
                    var el = document.activeElement;
                    if (!el) {{ return false; }}
                    el.value = {json.dumps(value)};
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return true;
                }})()
                """
            )
            return True
        except Exception as exc:
            logger.error("[TAB] set_value failed: %s", exc)
            return False

    async def focus(self, node_id: int) -> bool:
        """Focus a DOM node."""
        try:
            await self._send("DOM.focus", {"nodeId": node_id})
            return True
        except Exception as exc:
            logger.debug("[TAB] focus failed: %s", exc)
            return False

    async def key(self, combo: str) -> bool:
        """Press a keyboard shortcut like Enter, Control+a, or Control+Shift+t."""
        try:
            parts = combo.split("+")
            key = parts[-1]
            modifiers = 0
            for mod in parts[:-1]:
                mod_lower = mod.lower()
                if mod_lower in {"ctrl", "control"}:
                    modifiers |= 2
                elif mod_lower == "shift":
                    modifiers |= 8
                elif mod_lower == "alt":
                    modifiers |= 1
                elif mod_lower in {"meta", "win"}:
                    modifiers |= 4

            await self._send("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "modifiers": modifiers})
            await self._send("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "modifiers": modifiers})
            return True
        except Exception as exc:
            logger.error("[TAB] key failed %s: %s", combo, exc)
            return False

    async def scroll(
        self,
        x: int,
        y: int,
        delta_x: int = 0,
        delta_y: int = 300,
    ) -> bool:
        """Scroll at a viewport position."""
        try:
            await self._send(
                "Input.dispatchMouseEvent",
                {"type": "mouseWheel", "x": x, "y": y, "deltaX": delta_x, "deltaY": delta_y},
            )
            return True
        except Exception as exc:
            logger.error("[TAB] scroll failed: %s", exc)
            return False

    async def fetch(
        self,
        url: str,
        method: str = "GET",
        body: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """Make an HTTP request as the page, using page cookies and auth."""
        headers_js = json.dumps(headers or {"Content-Type": "application/json"})
        body_js = json.dumps(json.dumps(body)) if body else "undefined"

        js = f"""
        (async function() {{
            try {{
                const response = await fetch({json.dumps(url)}, {{
                    method: {json.dumps(method)},
                    headers: {headers_js},
                    body: {body_js},
                    credentials: 'include'
                }});
                const text = await response.text();
                try {{
                    return {{ok: response.ok, status: response.status, data: JSON.parse(text)}};
                }} catch(e) {{
                    return {{ok: response.ok, status: response.status, data: text}};
                }}
            }} catch(e) {{
                return {{ok: false, error: e.toString()}};
            }}
        }})()
        """
        try:
            result = await self.evaluate(js)
            return result
        except Exception as exc:
            logger.error("[TAB] fetch failed: %s", exc)
            return None

    async def screenshot_b64(self) -> Optional[str]:
        """Take screenshot and return base64 PNG."""
        try:
            result = await self._send("Page.captureScreenshot", {"format": "png", "quality": 80})
            return result.get("data")
        except Exception as exc:
            logger.warning("[TAB] screenshot failed: %s", exc)
            return None

    async def wait_for_selector(self, selector: str, timeout_ms: int = 8000) -> bool:
        """Wait until a CSS selector appears in DOM."""
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            exists = await self.evaluate(f"!!document.querySelector({json.dumps(selector)})")
            if exists:
                return True
            await asyncio.sleep(0.2)
        return False

    async def wait_for_url_change(self, current_url: str, timeout_ms: int = 8000) -> bool:
        """Wait until page URL changes."""
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            new_url = await self.get_url()
            if new_url != current_url:
                return True
            await asyncio.sleep(0.2)
        return False

    async def _node_to_object(self, node_id: int) -> str:
        """Resolve DOM node ID to Runtime object ID."""
        result = await self._send("DOM.resolveNode", {"nodeId": node_id})
        return result.get("object", {}).get("objectId", "")

    def on_event(self, method: str, callback) -> None:
        """Register a CDP event listener."""
        self._event_listeners.setdefault(method, []).append(callback)

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"Tab({self.title!r} {self.url[:50]} [{status}])"
