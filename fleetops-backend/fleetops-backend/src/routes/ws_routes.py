"""
ws_routes.py — Endpoints WebSocket del backend.
El frontend conecta a estos endpoints para recibir updates en tiempo real.

Canales disponibles:
  ws://host:8000/ws/fleet    → Dashboard + Flota
  ws://host:8000/ws/fuel     → Combustible
  ws://host:8000/ws/reports  → Reportes
  ws://host:8000/ws/alerts   → Alertas
  ws://host:8000/ws/all      → Todo (útil para debug)
"""
import json
import logging
from datetime import date, datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.database import db_service
from src.websocket.ws_manager import manager
from src.services import fleet_service, state_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


async def _send_initial_state(websocket: WebSocket, channel: str):
    """Envía el estado actual al cliente justo después de conectar."""
    payload = fleet_service.build_fleet_payload()
    payload["type"] = f"{channel}_initial"
    await websocket.send_text(json.dumps(payload, ensure_ascii=False, default=str))


async def _build_fuel_alerts() -> list[dict]:
    today = date.today()
    records = await db_service.get_fuel_records_by_date(today)
    alerts = []
    for r in records:
        r = dict(r)
        fecha = r.get("fecha") or r.get("created_at")
        if hasattr(fecha, "isoformat"):
            fecha = fecha.isoformat()
        vehicle_id = str(r.get("vehicle_id", ""))
        # Obtener el eco (nombre legible) desde state_store
        met = state_store.get_unit_metrics(vehicle_id)
        eco = met.get("eco") or vehicle_id
        alerts.append({
            "id":       f"fuel-{r.get('id', '')}",
            "type":     "info",
            "category": "Combustible",
            "title":    "Nuevo ticket de combustible",
            "unit":     eco,
            "raw_time": fecha,
        })
    return alerts

@router.websocket("/ws/fleet")
async def ws_fleet(websocket: WebSocket):
    """Canal principal: Dashboard + Gestión de Flota."""
    await manager.connect(websocket, channel="fleet")
    try:
        await _send_initial_state(websocket, "fleet")
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "refresh":
                await fleet_service.refresh_fleet_status()
                payload = fleet_service.build_fleet_payload()
                await manager.broadcast_fleet(payload)
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel="fleet")
    except Exception as exc:
        logger.error("WS fleet error: %s", exc)
        await manager.disconnect(websocket, channel="fleet")


@router.websocket("/ws/fuel")
async def ws_fuel(websocket: WebSocket):
    """Canal combustible."""
    await manager.connect(websocket, channel="fuel")
    try:
        all_records = state_store.get_state()["fuel_records"]
        await websocket.send_text(json.dumps({
            "type":    "fuel_initial",
            "records": all_records,
        }, ensure_ascii=False, default=str))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel="fuel")
    except Exception as exc:
        logger.error("WS fuel error: %s", exc)
        await manager.disconnect(websocket, channel="fuel")


@router.websocket("/ws/reports")
async def ws_reports(websocket: WebSocket):
    """Canal reportes."""
    await manager.connect(websocket, channel="reports")
    try:
        payload = fleet_service.build_fleet_payload()
        await websocket.send_text(json.dumps({
            "type":    "reports_initial",
            "summary": payload.get("dashboard", {}),
            "units":   payload.get("units", []),
        }, ensure_ascii=False, default=str))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel="reports")
    except Exception as exc:
        logger.error("WS reports error: %s", exc)
        await manager.disconnect(websocket, channel="reports")


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    await manager.connect(websocket, channel="alerts")
    try:
        fuel_alerts = await _build_fuel_alerts()  # ← await
        await websocket.send_text(json.dumps({
            "type":   "alerts_initial",
            "alerts": fuel_alerts,
        }, ensure_ascii=False, default=str))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel="alerts")
    except Exception as exc:
        logger.error("WS alerts error: %s", exc)
        await manager.disconnect(websocket, channel="alerts")


@router.websocket("/ws/all")
async def ws_all(websocket: WebSocket):
    """Canal global — recibe todos los eventos."""
    await manager.connect(websocket, channel="all")
    try:
        await _send_initial_state(websocket, "all")
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, channel="all")
    except Exception as exc:
        logger.error("WS all error: %s", exc)
        await manager.disconnect(websocket, channel="all")
