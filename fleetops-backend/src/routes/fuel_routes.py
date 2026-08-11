"""
fuel_routes.py — Endpoints REST para Control de Combustible
Replica la pestaña "Combustible" del frontend (Nueva Carga, historial, etc.)
"""
from datetime import date, datetime, timezone, timedelta
from typing import Literal
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
import logging
import asyncio
from datetime import date as _date
from src.database import db_service
from src.services import fulltrack_client

from src.services import state_store, fleet_service
from src.services.metrics_engine import calcular_hoja4, calcular_portada
from src.websocket.ws_manager import manager as ws_manager
from src.config.settings import DIESEL_PRICE_PER_LITER
from src.services import s3_client

router = APIRouter(prefix="/api/fuel", tags=["Combustible"])

# Zona horaria CST (México Centro, UTC-6)
CST = timezone(timedelta(hours=-6))

# Tamaño máximo permitido: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}

# ─── Schemas ─────────────────────────────────────────────────────────────────

class FuelLoadRequest(BaseModel):
    vehicle_id:      str
    conductor:       str
    proveedor:       str = ""
    tipo:            Literal["DIESEL", "GASOLINA_COMUN", "GASOLINA_PREMIUM"] = "DIESEL"
    fecha:           datetime = Field(default_factory=lambda: datetime.now(CST))
    odometro_actual: float = 0.0
    liters:          float = Field(gt=0)
    price_per_liter: float = Field(gt=0, default=DIESEL_PRICE_PER_LITER)
    tanque_lleno:    bool = False
    foto_ticket_url: str = ""          # ← recibe la URL ya subida a S3


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/upload-ticket")
async def upload_ticket(
    vehicle_id: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Sube la foto o PDF del ticket a S3.
    Devuelve la URL pública para incluirla después en /api/fuel/load.

    El frontend debe llamar este endpoint PRIMERO, obtener la URL
    y pasarla como `foto_ticket_url` al registrar la carga.
    """
    logger = logging.getLogger(__name__)

    # ── Validar content-type ──────────────────────────────────────────────
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Tipo de archivo no permitido: {file.content_type}. "
                   f"Usa JPG, PNG, WEBP o PDF.",
        )

    # ── Leer y validar tamaño ─────────────────────────────────────────────
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="El archivo supera el límite de 10 MB.",
        )

    # ── Subir a S3 ────────────────────────────────────────────────────────
    try:
        url = await s3_client.upload_ticket(
            file_bytes=file_bytes,
            original_filename=file.filename or "ticket",
            vehicle_id=vehicle_id,
            content_type=file.content_type,
        )
    except RuntimeError as e:
        logger.error("Error subiendo ticket a S3: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    return {"url": url, "vehicle_id": vehicle_id, "filename": file.filename}


@router.post("/load")
async def register_fuel_load(body: FuelLoadRequest):
    """
    Registra una nueva carga de combustible.
    Responde inmediatamente; el snapshot de odómetro y recálculo van en background.
    """
    logger = logging.getLogger(__name__)

    # ── 1. Guardar en memoria ─────────────────────────────────────────────────
    record = await state_store.add_fuel_record(body.model_dump())

    # ── 2. Persistir en MySQL (rápido) ────────────────────────────────────────
    try:
        await db_service.save_fuel_record(record)
    except Exception as e:
        logger.error("Error guardando fuel_record en MySQL: %s", e)

    # ── 3. Emitir WS inmediatamente con lo que ya tenemos ─────────────────────
    met = state_store.get_unit_metrics(body.vehicle_id)
    fuel_records = state_store.get_fuel_records_for_vehicle(body.vehicle_id)
    await ws_manager.broadcast_fuel({
        "type":       "fuel_update",
        "vehicle_id": body.vehicle_id,
        "eco":        met.get("eco", body.vehicle_id),
        "record":     record,
        "resumen":    _fuel_summary(body.vehicle_id, fuel_records),
        "ts":         datetime.now(CST).isoformat(),
    })

    # ── 3b. Emitir alerta de nuevo ticket al canal alerts ─────────────────────
    await ws_manager.broadcast_alert({
        "type":     "new_fuel_alert",
        "category": "Combustible",
        "title":    "Nuevo ticket de combustible",
        "unit":     met.get("eco") or body.vehicle_id,
        "vehicle_id": body.vehicle_id,
        "time":     record.get("fecha") or record.get("created_at", ""),
        "read":     False,
    })

    # ── 4. Odómetro + recálculo en background (no bloquea la respuesta) ───────
    asyncio.create_task(_post_fuel_background(body, record))

    return {"status": "ok", "record": record}


async def _post_fuel_background(body: FuelLoadRequest, record: dict):
    """Snapshot de odómetro en Fulltrack + recálculo de métricas en background."""
    logger = logging.getLogger(__name__)
    today = datetime.now(CST).date()

    # ── Snapshot de odómetro ──────────────────────────────────────────────────
    try:
        response = await fulltrack_client.get_km_for_vehicle(
            body.vehicle_id,
            date_initial=today,
            date_final=today,
        )
        km_actual = fulltrack_client.extract_total_km(response)

        if km_actual > 0:
            existing = await db_service.get_odometer_snapshots(
                body.vehicle_id, today.year, today.month
            )
            if "inicio" not in existing:
                await db_service.save_odometer_snapshot(
                    body.vehicle_id, km_actual, "inicio", today.year, today.month
                )
            await db_service.save_odometer_snapshot(
                body.vehicle_id, km_actual, "fin", today.year, today.month
            )
    except Exception as e:
        logger.warning("No se pudo guardar snapshot de odómetro para %s: %s", body.vehicle_id, e)

    # ── Recalcular métricas y emitir update final ─────────────────────────────
    await fleet_service.recalculate_all_metrics()
    fuel_records = state_store.get_fuel_records_for_vehicle(body.vehicle_id)
    met = state_store.get_unit_metrics(body.vehicle_id)
    await ws_manager.broadcast_fuel({
        "type":       "fuel_update",
        "vehicle_id": body.vehicle_id,
        "eco":        met.get("eco", body.vehicle_id),
        "record":     record,
        "resumen":    _fuel_summary(body.vehicle_id, fuel_records),
        "ts":         datetime.now(CST).isoformat(),
    })

    await ws_manager.broadcast_alert({
        "type":       "new_fuel_alert",
        "category":   "Combustible",
        "title":      "Nuevo ticket de combustible",
        "unit":       met.get("eco") or body.vehicle_id,
        "vehicle_id": body.vehicle_id,
        "time":       record.get("fecha") or record.get("created_at", ""),
        "read":       False,
    })


@router.get("/records/{vehicle_id}")
async def get_fuel_records(vehicle_id: str):
    """Historial de cargas de combustible de una unidad."""
    records = state_store.get_fuel_records_for_vehicle(vehicle_id)
    return {
        "vehicle_id": vehicle_id,
        "records":    records,
        "resumen":    _fuel_summary(vehicle_id, records),
    }


@router.get("/records")
async def get_all_fuel_records():
    """Todos los registros de combustible (para Reportes)."""
    all_records = state_store.get_state()["fuel_records"]
    vehicles    = state_store.get_vehicles()

    by_unit = {}
    for v in vehicles:
        vid  = str(v.get("ras_vei_id", ""))
        recs = [r for r in all_records if str(r.get("vehicle_id")) == vid]
        if recs:
            eco = v.get("ras_vei_eco") or v.get("ras_vei_placa") or vid
            by_unit[eco] = {
                "vehicle_id": vid,
                "eco":        eco,
                "records":    recs,
                "resumen":    _fuel_summary(vid, recs),
            }

    return {"by_unit": by_unit, "total_records": len(all_records)}


@router.get("/report/hoja4")
async def fuel_cost_report(year: int = None, month: int = None):
    """
    Reporte Hoja4 del Excel: Costo y consumo de combustible por unidad.
    """
    if year  is None: year  = datetime.now(CST).year
    if month is None: month = datetime.now(CST).month

    vehicles = state_store.get_vehicles()
    result = []
    for v in vehicles:
        vid = str(v.get("ras_vei_id", ""))
        eco = v.get("ras_vei_eco") or v.get("ras_vei_placa") or vid
        recs = state_store.get_fuel_records_for_vehicle(vid)
        month_recs = [
            r for r in recs
            if _record_in_month(r, year, month)
        ]
        lts_diesel   = sum(r["liters"] for r in month_recs if r.get("tipo") in ("DIESEL", None, ""))
        lts_gasolina = sum(r["liters"] for r in month_recs if r.get("tipo") in ("GASOLINA_COMUN", "GASOLINA_PREMIUM"))
        if lts_diesel == 0 and lts_gasolina == 0:
            continue
        h4 = calcular_hoja4(eco, lts_diesel, lts_gasolina, month=month)
        h4["vehicle_id"] = vid
        result.append(h4)

    return {"year": year, "month": month, "unidades": result}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fuel_summary(vehicle_id: str, records: list) -> dict:
    met    = state_store.get_unit_metrics(vehicle_id)
    km_mes = state_store.get_km_month(vehicle_id) or state_store.get_km_today(vehicle_id)

    lts_total    = sum(r.get("liters", 0) for r in records)
    costo_total  = sum(r.get("liters", 0) * r.get("price_per_liter", 0) for r in records)
    rendimiento  = met.get("km_por_litro", 0)

    return {
        "total_litros":    round(lts_total, 2),
        "total_costo":     round(costo_total, 2),
        "km_por_litro":    round(rendimiento, 4),
        "total_cargas":    len(records),
    }


def _record_in_month(record: dict, year: int, month: int) -> bool:
    fecha = record.get("fecha")
    if not fecha:
        return False
    try:
        if isinstance(fecha, str):
            dt = datetime.fromisoformat(fecha.replace("Z", ""))
        elif isinstance(fecha, datetime):
            dt = fecha
        else:
            return False
        return dt.year == year and dt.month == month
    except (ValueError, TypeError):
        return False


@router.get("/ticket-url")
async def get_ticket_presigned_url(key: str):
    """
    Genera una URL firmada temporal para ver un ticket en S3.

    El frontend manda la key del objeto (no la URL completa).
    Ej: GET /api/fuel/ticket-url?key=tickets/2026/05/TM-04/abc.jpg
    """
    try:
        url = s3_client.get_presigned_url(key, expires_in=3600)
        return {"url": url}
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
