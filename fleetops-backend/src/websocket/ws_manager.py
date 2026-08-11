"""
ws_manager.py — Gestor de conexiones WebSocket.
Mantiene la lista de clientes conectados y transmite actualizaciones
a todos ellos en broadcast o a canales específicos.
"""
import asyncio
import json
import logging
from datetime import datetime
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Maneja múltiples clientes WebSocket simultáneos con soporte de canales."""

    def __init__(self):
        # canal → lista de WebSockets suscritos
        self._channels: dict[str, list[WebSocket]] = {
            "fleet":       [],   # Dashboard y pestaña Flota
            "fuel":        [],   # Pestaña Combustible
            "reports":     [],   # Pestaña Reportes
            "alerts":      [],   # Alertas
            "all":         [],   # Suscripción global
        }
        self._lock = asyncio.Lock()

    # ── Conexión / desconexión ─────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, channel: str = "all") -> None:
        await websocket.accept()
        async with self._lock:
            if channel not in self._channels:
                self._channels[channel] = []
            self._channels[channel].append(websocket)
        logger.info("WS cliente conectado al canal '%s'. Total: %d",
                    channel, self._total_connections())

        # Enviar un ping inmediato con timestamp
        await self._send_json(websocket, {
            "type":    "connected",
            "channel": channel,
            "ts":      datetime.utcnow().isoformat(),
        })

    async def disconnect(self, websocket: WebSocket, channel: str = "all") -> None:
        async with self._lock:
            ch_list = self._channels.get(channel, [])
            if websocket in ch_list:
                ch_list.remove(websocket)
        logger.info("WS cliente desconectado del canal '%s'.", channel)

    # ── Broadcast ─────────────────────────────────────────────────────────

    async def broadcast(self, data: dict, channel: str = "all") -> None:
        """
        Emite `data` a todos los clientes suscritos al `channel` Y al canal 'all'.
        Elimina automáticamente sockets muertos.
        """
        targets = set(self._channels.get(channel, []) + self._channels.get("all", []))
        dead = []
        for ws in targets:
            try:
                await self._send_json(ws, data)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ch in self._channels.values():
                    for d in dead:
                        if d in ch:
                            ch.remove(d)

    async def broadcast_fleet(self, payload: dict) -> None:
        await self.broadcast(payload, channel="fleet")

    async def broadcast_fuel(self, payload: dict) -> None:
        await self.broadcast(payload, channel="fuel")

    async def broadcast_alert(self, payload: dict) -> None:
        await self.broadcast(payload, channel="alerts")

    async def broadcast_reports(self, payload: dict) -> None:
        await self.broadcast(payload, channel="reports")

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    async def _send_json(ws: WebSocket, data: dict) -> None:
        await ws.send_text(json.dumps(data, ensure_ascii=False, default=str))

    def _total_connections(self) -> int:
        return sum(len(v) for v in self._channels.values())

    def stats(self) -> dict:
        return {ch: len(ws_list) for ch, ws_list in self._channels.items()}


# Instancia singleton compartida por toda la app
manager = ConnectionManager()
