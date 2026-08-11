"""
fulltrack_client.py — Cliente HTTP para la API de Fulltrack2
Endpoints usados:
  • /vehicles/all                     → lista de vehículos + ras_vei_id
  • /events/all                       → último evento GPS por unidad (flota activa)
  • /consolidatedevents/vehicle/...   → kilómetros recorridos por vehículo y rango
"""
import httpx
import logging
from datetime import date, timedelta
from src.config.settings import FULLTRACK_BASE_URL, FULLTRACK_APIKEY, FULLTRACK_SECRETKEY

logger = logging.getLogger(__name__)

# Timeout en segundos para todas las llamadas
_TIMEOUT = 20


def _base_url() -> str:
    return FULLTRACK_BASE_URL.rstrip("/")


def _auth() -> dict:
    return {
        "apiKey":    FULLTRACK_APIKEY,
        "secretKey": FULLTRACK_SECRETKEY,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. VEHÍCULOS
# ─────────────────────────────────────────────────────────────────────────────

async def get_vehicles() -> list[dict]:
    url = (
        f"{_base_url()}/vehicles/all"   # ← corregido
        f"/apiKey/{FULLTRACK_APIKEY}"
        f"/secretKey/{FULLTRACK_SECRETKEY}"
    )
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("data", data.get("vehicles", []))
        return data


# ─────────────────────────────────────────────────────────────────────────────
# 2. EVENTOS (estado de flota en tiempo real)
# ─────────────────────────────────────────────────────────────────────────────

async def get_all_events() -> list[dict]:
    """
    GET /events/all/apiKey/{key}/secretKey/{secret}
    Cada elemento tiene:
        ras_eve_data_gps            → última fecha/hora GPS
        ras_eve_data_enviado        → fecha envío
        ras_ras_data_ult_comunicacao → última comunicación
    Se usa para determinar si la unidad está ACTIVA (comunicó en los últimos N min).
    """
    url = (
        f"{_base_url()}/events/all"
        f"/apiKey/{FULLTRACK_APIKEY}"
        f"/secretKey/{FULLTRACK_SECRETKEY}"
    )
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("data", data.get("events", []))
        return data


# ─────────────────────────────────────────────────────────────────────────────
# 3. KILÓMETROS CONSOLIDADOS POR VEHÍCULO
# ─────────────────────────────────────────────────────────────────────────────

async def get_km_for_vehicle(
    vehicle_id: int | str,
    date_initial: date | None = None,
    date_final:   date | None = None,
    timeout: int = 20,
) -> dict:
    """
    GET /consolidatedevents/vehicle/id/{id}/initial/{YYYY-MM-DD}/final/{YYYY-MM-DD}/...
    Retorna eventos consolidados con distancia recorrida.
    Si no se pasan fechas usa hoy.
    """
    if date_initial is None:
        date_initial = date.today()
    if date_final is None:
        date_final = date.today()

    url = (
        f"{_base_url()}/consolidatedevents"
        f"/vehicle/id/{vehicle_id}"
        f"/initial/{date_initial.isoformat()}"
        f"/final/{date_final.isoformat()}"
        f"/apiKey/{FULLTRACK_APIKEY}"
        f"/secretKey/{FULLTRACK_SECRETKEY}"
    )
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data
        # Si regresa lista, empaquetamos
        return {"events": data}


async def get_km_for_vehicle_month(vehicle_id: int | str, year: int, month: int) -> dict:
    """Helper: km de un mes completo."""
    from calendar import monthrange
    first = date(year, month, 1)
    last  = date(year, month, monthrange(year, month)[1])
    return await get_km_for_vehicle(vehicle_id, first, last)


# ─────────────────────────────────────────────────────────────────────────────
# 4. UTILIDADES
# ─────────────────────────────────────────────────────────────────────────────

def extract_total_km(consolidated_response: dict) -> float:
    """
    Extrae el total de km recorridos de la respuesta consolidada de Fulltrack.
    El campo real es: data[0].odometro_total
    """
    data = consolidated_response.get("data", [])
    
    if isinstance(data, list) and len(data) > 0:
        # Sumar odometro_total de todos los registros del array
        total = 0.0
        for item in data:
            val = item.get("odometro_total", 0)
            try:
                total += float(val)
            except (TypeError, ValueError):
                pass
        return total

    return 0.0

    # Sumar eventos individuales
    events = consolidated_response.get("events", consolidated_response.get("data", []))
    if isinstance(events, list):
        total = 0.0
        for ev in events:
            for key in ("km", "distance", "distancia", "ras_eve_km", "odometer"):
                val = ev.get(key)
                if val is not None:
                    try:
                        total += float(val)
                        break
                    except (TypeError, ValueError):
                        pass
        return total

    return 0.0
