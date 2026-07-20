"""
state_store.py — Almacén en memoria del estado global de la aplicación.
Actúa como "base de datos" liviana; toda la lógica de cálculo escribe aquí
y el WebSocket broadcaster lee desde aquí para emitir a los clientes.
"""
import asyncio
import logging
from datetime import datetime, date
from typing import Any

logger = logging.getLogger(__name__)

# ─── Estado global ────────────────────────────────────────────────────────────

_state: dict[str, Any] = {
    # Lista de vehículos registrados en Fulltrack
    "vehicles": [],                 # [{id, placa, eco, ...}, ...]

    # Mapa vehicle_id → último evento GPS
    "fleet_events": {},             # {vehicle_id: {gps_date, status, lat, lng, ...}}

    # Mapa vehicle_id → km acumulados hoy
    "km_today": {},                 # {vehicle_id: float}

    # Mapa vehicle_id → km del mes actual
    "km_month": {},                 # {vehicle_id: float}

    # Registros de combustible ingresados manualmente (desde el frontend)
    "fuel_records": [],             # [{vehicle_id, liters, price_per_liter, date, ...}]

    # Mapa vehicle_id → métricas calculadas (Hoja1 / Hoja2 Excel)
    "unit_metrics": {},             # {vehicle_id: UnitMetrics}

    # Resumen global del dashboard (Portada Excel)
    "dashboard_summary": {},

    # Historial de km diarios por vehículo (para gráficas)
    "km_daily_history": {},         # {vehicle_id: [{date, km}, ...]}

    # Último timestamp de actualización
    "last_updated": None,

    # Mapa vehicle_id → {año_mes: km}  ej: {"1213421": {"2026-02": 3200.5, "2026-03": 3100.2}}
    "km_historico": {},
    # Métricas históricas por mes  ej: {"2026-02": [{eco, diesel_lts, ...}, ...]}
    "metrics_historico": {},
}

_lock = asyncio.Lock()


# ─── Getters ─────────────────────────────────────────────────────────────────

def get_state() -> dict:
    return _state


def get_vehicles() -> list:
    return _state["vehicles"]


def get_fleet_events() -> dict:
    return _state["fleet_events"]


def get_km_today(vehicle_id: str | int) -> float:
    return _state["km_today"].get(str(vehicle_id), 0.0)


def get_km_month(vehicle_id: str | int) -> float:
    return _state["km_month"].get(str(vehicle_id), 0.0)


def get_unit_metrics(vehicle_id: str | int) -> dict:
    return _state["unit_metrics"].get(str(vehicle_id), {})


def get_fuel_records_for_vehicle(vehicle_id: str | int) -> list:
    vid = str(vehicle_id)
    return [r for r in _state["fuel_records"] if str(r.get("vehicle_id")) == vid]


def get_dashboard_summary() -> dict:
    return _state["dashboard_summary"]


def get_km_historico(vehicle_id: str, year: int, month: int) -> float:
    key = f"{year}-{month:02d}"
    return _state["km_historico"].get(str(vehicle_id), {}).get(key, 0.0)


def get_metrics_historico(year: int, month: int) -> list[dict]:
    key = f"{year}-{month:02d}"
    return _state["metrics_historico"].get(key, [])

# ─── Setters (thread-safe con asyncio.Lock) ───────────────────────────────────

async def set_km_historico(vehicle_id: str, year: int, month: int, km: float) -> None:
    async with _lock:
        key = f"{year}-{month:02d}"
        _state["km_historico"].setdefault(str(vehicle_id), {})[key] = round(km, 2)



async def set_metrics_historico(year: int, month: int, metrics: list[dict]) -> None:
    async with _lock:
        key = f"{year}-{month:02d}"
        _state["metrics_historico"][key] = metrics



async def set_vehicles(vehicles: list) -> None:
    async with _lock:
        _state["vehicles"] = vehicles
        _state["last_updated"] = datetime.utcnow().isoformat()


async def update_fleet_event(vehicle_id: str | int, event: dict) -> None:
    async with _lock:
        _state["fleet_events"][str(vehicle_id)] = {
            **event,
            "updated_at": datetime.utcnow().isoformat(),
        }


async def set_km_today(vehicle_id: str | int, km: float) -> None:
    async with _lock:
        _state["km_today"][str(vehicle_id)] = round(km, 2)
        # Actualizar historial diario
        vid = str(vehicle_id)
        today_str = date.today().isoformat()
        history = _state["km_daily_history"].setdefault(vid, [])
        # Actualizar o añadir entrada de hoy
        for entry in history:
            if entry["date"] == today_str:
                entry["km"] = round(km, 2)
                break
        else:
            history.append({"date": today_str, "km": round(km, 2)})
        # Mantener sólo últimos 31 días
        _state["km_daily_history"][vid] = sorted(history, key=lambda x: x["date"])[-31:]


async def set_km_month(vehicle_id: str | int, km: float) -> None:
    async with _lock:
        _state["km_month"][str(vehicle_id)] = round(km, 2)


async def set_unit_metrics(vehicle_id: str | int, metrics: dict) -> None:
    async with _lock:
        _state["unit_metrics"][str(vehicle_id)] = {
            **metrics,
            "calculated_at": datetime.utcnow().isoformat(),
        }


async def add_fuel_record(record: dict) -> dict:
    """Añade un registro de combustible y retorna el registro con ID asignado."""
    async with _lock:
        record_id = f"fuel_{len(_state['fuel_records']) + 1}_{int(datetime.utcnow().timestamp())}"
        full_record = {
            "id": record_id,
            "created_at": datetime.utcnow().isoformat(),
            **record,
        }
        _state["fuel_records"].append(full_record)
        return full_record


async def set_dashboard_summary(summary: dict) -> None:
    async with _lock:
        _state["dashboard_summary"] = {
            **summary,
            "updated_at": datetime.utcnow().isoformat(),
        }


def get_active_vehicles_count(inactivity_threshold_minutes: int = 60) -> int:
    """Cuenta vehículos con GPS reportado en los últimos N minutos."""
    now = datetime.utcnow()
    active = 0
    for event in _state["fleet_events"].values():
        gps_str = event.get("gps_date") or event.get("ras_eve_data_gps", "")
        if not gps_str:
            continue
        try:
            # Fulltrack usa formato "DD/MM/YYYY HH:MM:SS"
            gps_dt = datetime.strptime(gps_str, "%d/%m/%Y %H:%M:%S")
            diff_minutes = (now - gps_dt).total_seconds() / 60
            if diff_minutes <= inactivity_threshold_minutes:
                active += 1
        except ValueError:
            # Intentar ISO
            try:
                gps_dt = datetime.fromisoformat(gps_str.replace("Z", ""))
                diff_minutes = (now - gps_dt).total_seconds() / 60
                if diff_minutes <= inactivity_threshold_minutes:
                    active += 1
            except ValueError:
                pass
    return active


