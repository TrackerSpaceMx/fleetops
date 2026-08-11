"""
fleet_routes.py — Endpoints REST para Flota y Dashboard
"""
from datetime import date
from fastapi import APIRouter, HTTPException, Query
from src.services import state_store, fleet_service, fulltrack_client
from src.services.metrics_engine import calcular_hoja3

router = APIRouter(prefix="/api/fleet", tags=["Flota"])


@router.get("/vehicles")
async def list_vehicles():
    """Lista todos los vehículos registrados."""
    return {"vehicles": state_store.get_vehicles()}


@router.get("/status")
async def fleet_status():
    """Estado actual de la flota (GPS)."""
    events = state_store.get_fleet_events()
    vehicles = state_store.get_vehicles()
    active = state_store.get_active_vehicles_count()
    return {
        "total":    len(vehicles),
        "activos":  active,
        "inactivos": len(vehicles) - active,
        "eventos":  list(events.values()),
    }


@router.get("/unit/{vehicle_id}")
async def unit_detail(vehicle_id: str):
    """Detalle completo de una unidad: GPS + métricas + combustible."""
    ev  = state_store.get_fleet_events().get(vehicle_id)
    met = state_store.get_unit_metrics(vehicle_id)
    fuel = state_store.get_fuel_records_for_vehicle(vehicle_id)
    km_h = state_store.get_km_today(vehicle_id)

    if not ev and not met:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    return {
        "vehicle_id":  vehicle_id,
        "gps":         ev or {},
        "metricas":    met,
        "km_hoy":      km_h,
        "combustible": fuel,
    }


@router.get("/unit/{vehicle_id}/km")
async def unit_km(
    vehicle_id: str,
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    """Kilómetros recorridos en un rango de fechas (consulta Fulltrack)."""
    today = date.today()
    response = await fulltrack_client.get_km_for_vehicle(
        vehicle_id,
        date_initial=date_from or today,
        date_final=date_to or today,
    )
    km = fulltrack_client.extract_total_km(response)
    return {"vehicle_id": vehicle_id, "km": km, "raw": response}


@router.get("/routes")
async def routes_report(
    year:  int = Query(default=None),
    month: int = Query(default=None),
):
    """Reporte de operatividad por ruta (Hoja3 del Excel)."""
    from datetime import date as _date
    if year  is None: year  = _date.today().year
    if month is None: month = _date.today().month

    vehicles = state_store.get_vehicles()
    # Agrupar por ruta (campo ras_vei_ruta o similar)
    rutas: dict[str, list] = {}
    for v in vehicles:
        ruta = v.get("ruta") or v.get("ras_vei_ruta") or "Sin ruta"
        vid  = str(v.get("ras_vei_id", ""))
        met  = state_store.get_unit_metrics(vid)
        if met:
            rutas.setdefault(ruta, []).append(met)

    result = []
    for i, (ruta_nombre, units) in enumerate(rutas.items(), start=1):
        h3 = calcular_hoja3(i, units)
        h3["nombre_ruta"] = ruta_nombre
        result.append(h3)

    return {"year": year, "month": month, "rutas": result}


@router.post("/refresh")
async def force_refresh():
    """Fuerza una actualización inmediata del estado de flota."""
    await fleet_service.refresh_fleet_status()
    await fleet_service.recalculate_all_metrics()
    payload = fleet_service.build_fleet_payload()
    from src.websocket.ws_manager import manager
    await manager.broadcast_fleet(payload)
    return {"status": "ok", "units_updated": len(payload.get("units", []))}


# GET /api/fleet/rendimiento-historico/{vehicle_id}
# Devuelve las métricas de los últimos 3 meses para un vehículo.
# Usado por la tabla "Rendimiento Mensual" en VehicleDetail → pestaña Operatividad.
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/rendimiento-historico/{vehicle_id}")
async def get_rendimiento_historico(vehicle_id: str):
    """
    Retorna:
    {
      "vehicle_id": "TM-07",
      "meses": [
        {
          "periodo": "Mayo 2026",
          "year": 2026,
          "month": 5,
          "toneladas": 412.5,
          "km_total": 1820,
          "km_prod": 1274,
          "km_trasl": 364,
          "diesel_lts": 1080,
          "km_por_litro": 1.69
        },
        ...  // 3 meses en total (mes actual + 2 anteriores)
      ]
    }
    """
    meses = await fleet_service.get_rendimiento_historico_vehicle(vehicle_id)
    return {"vehicle_id": vehicle_id, "meses": meses}