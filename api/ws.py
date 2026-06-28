"""WebSocket hub + the background loop that powers live quotes and alerts.

One persistent multiplexed channel (``/ws/stream``) carries everything the UI
needs pushed: {"type": "quotes"|"notification"|"heartbeat"}. The existing SSE
endpoint stays for chat streaming (request-scoped, a natural fit for SSE).

All DB/network work in the loop runs via ``asyncio.to_thread`` so the event
loop never blocks, and no DB session is ever held across an await.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from fastapi import WebSocket, WebSocketDisconnect

from portfolio_risk import config

log = logging.getLogger("api.ws")
if not log.handlers:
    _h = logging.StreamHandler(stream=sys.stderr)
    _h.setFormatter(logging.Formatter("%(name)s %(levelname)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)


class WSHub:
    """A set of connected sockets with a broadcast that prunes dead ones."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        # Last quotes broadcast, replayed to each new client so the ticker
        # tape fills immediately instead of waiting for the next poll cycle.
        self.last_quotes: dict = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        if self.last_quotes:
            try:
                await ws.send_text(json.dumps({"type": "quotes", "data": self.last_quotes}))
            except Exception:  # noqa: BLE001
                pass

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    @property
    def count(self) -> int:
        return len(self._clients)

    async def broadcast(self, message: dict) -> None:
        if not self._clients:
            return
        data = json.dumps(message)
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:  # noqa: BLE001 - any send failure means it's gone
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


hub = WSHub()


async def stream_endpoint(ws: WebSocket) -> None:
    """The /ws/stream handler: register, then sit on receive() until the
    client goes away (clients may send pings; we ignore the payload)."""
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        await hub.disconnect(ws)


async def alerts_quotes_loop() -> None:
    """Every ALERT_POLL_SEC: run one alert cycle and broadcast the results.

    Quote fetches are deduped by market_data's own 20s cache, and the cycle
    caps its ticker set, so this stays gentle on yfinance. In mock mode the
    cycle is fully offline.
    """
    from portfolio_risk.portfolio.alerts import run_alert_cycle

    # Let the server finish booting before the first pass.
    await asyncio.sleep(2.0)
    while True:
        try:
            result = await asyncio.to_thread(run_alert_cycle)
            if result["quotes"]:
                hub.last_quotes = result["quotes"]
                await hub.broadcast({"type": "quotes", "data": result["quotes"]})
            for n in result["notifications"]:
                await hub.broadcast({"type": "notification", "data": n})
            await hub.broadcast({"type": "heartbeat"})
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the loop must survive bad cycles
            log.warning("alert cycle failed: %s", exc)
        await asyncio.sleep(config.alert_poll_seconds())
