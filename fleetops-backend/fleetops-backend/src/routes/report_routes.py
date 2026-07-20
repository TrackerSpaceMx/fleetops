"""
report_routes.py — Endpoints REST para el Generador de Reportes

Todos los endpoints aceptan filtros de fecha:
  ?year=2026&month=5              → mes completo (como antes)
  ?date_from=2026-05-01&date_to=2026-05-15  → rango exacto de días
  ?date_from=2026-05-20&date_to=2026-05-20  → un solo día

Los datos de báscula y combustible incluyen fecha y hora en los registros
detallados (/actividad, /costo-combustible con include_detail=true).
"""

from src.database import db_service
from datetime import date as _date, datetime, timedelta
from fastapi import APIRouter, Query
from typing import Optional
from src.services import state_store, fleet_service
from src.services.metrics_engine import (
    calcular_hoja1, calcular_hoja2, calcular_hoja3,
    calcular_hoja4, calcular_hoja5, calcular_portada,
)

router = APIRouter(prefix="/api/reports", tags=["Reportes"])


# ─── Helpers de rango de fecha ────────────────────────────────────────────────

def _resolve_range(
    year: int | None, month: int | None,
    date_from: str | None, date_to: str | None
) -> tuple[_date, _date, int, int]:
    """
    Resuelve siempre un rango (date_from, date_to) + (year, month).

    Prioridad:
      1. Si se pasan date_from / date_to → usar esas fechas exactas.
      2. Si se pasa year/month           → primer y último día del mes.
      3. Sin nada                        → mes actual completo.

    Retorna (date_from, date_to, year, month)
    """
    from calendar import monthrange
    today = _date.today()

    if date_from or date_to:
        try:
            df = _date.fromisoformat(date_from) if date_from else today.replace(day=1)
            dt = _date.fromisoformat(date_to)   if date_to   else today
        except ValueError:
            df = today.replace(day=1); dt = today
        return df, dt, df.year, df.month

    y = year  or today.year
    m = month or today.month
    _, last = monthrange(y, m)
    return _date(y, m, 1), _date(y, m, last), y, m


def _current(year, month):
    today = _date.today()
    return year or today.year, month or today.month


def _record_in_range(record: dict, df: _date, dt: _date) -> bool:
    """Filtra un fuel_record por rango de fechas."""
    fecha = record.get("fecha")
    if not fecha:
        return False
    try:
        if isinstance(fecha, str):
            d = datetime.fromisoformat(fecha.replace("Z", "")).date()
        elif isinstance(fecha, (_date, datetime)):
            d = fecha if isinstance(fecha, _date) else fecha.date()
        else:
            return False
        return df <= d <= dt
    except (ValueError, TypeError):
        return False


def _get_all_unit_metrics(year: int, month: int) -> list[dict]:
    today = _date.today()
    if year == today.year and month == today.month:
        vehicles = state_store.get_vehicles()
        return [m for v in vehicles
                for vid in [str(v.get("ras_vei_id", ""))]
                for m in [state_store.get_unit_metrics(vid)] if m]
    return state_store.get_metrics_historico(year, month)


# ─── Portada ──────────────────────────────────────────────────────────────────

@router.get("/portada")
async def portada(
    year:      int = Query(default=None),
    month:     int = Query(default=None),
    date_from: str = Query(default=None, description="YYYY-MM-DD"),
    date_to:   str = Query(default=None, description="YYYY-MM-DD"),
):
    """Resumen ejecutivo mensual (Portada del Excel)."""
    _df, _dt, y, m = _resolve_range(year, month, date_from, date_to)
    metrics = _get_all_unit_metrics(y, m)
    return calcular_portada(metrics, y, m)


# ─── Hoja 1 — Operatividad ────────────────────────────────────────────────────

@router.get("/operatividad")
async def reporte_operatividad(
    year:      int = Query(default=None),
    month:     int = Query(default=None),
    date_from: str = Query(default=None, description="YYYY-MM-DD"),
    date_to:   str = Query(default=None, description="YYYY-MM-DD"),
):
    """Hoja 1: Operatividad promedio por unidad."""
    _df, _dt, y, m = _resolve_range(year, month, date_from, date_to)
    metrics = _get_all_unit_metrics(y, m)
    rows = [
        {
            "eco":            met.get("eco"),
            "toneladas":      met.get("toneladas"),
            "num_viajes":     met.get("num_viajes"),
            "pct_carga":      met.get("pct_carga"),
        }
        for met in metrics
    ]
    return {"year": y, "month": m,
            "date_from": str(_df), "date_to": str(_dt),
            "unidades": rows}


# ─── Hoja 2 — Km recorridos y rendimiento ────────────────────────────────────

@router.get("/km-rendimiento")
async def reporte_km_rendimiento(
    year:      int = Query(default=None),
    month:     int = Query(default=None),
    date_from: str = Query(default=None, description="YYYY-MM-DD"),
    date_to:   str = Query(default=None, description="YYYY-MM-DD"),
):
    """
    Hoja 2: Km totales (Fulltrack) y km/litro.
    Con rango de fechas consulta Fulltrack directamente para ese período.
    """
    from src.services import fulltrack_client
    _df, _dt, y, m = _resolve_range(year, month, date_from, date_to)
    today = _date.today()
    is_range = bool(date_from or date_to)

    vehicles = state_store.get_vehicles()
    rows = []

    for v in vehicles:
        vid = str(v.get("ras_vei_id", ""))
        eco = v.get("ras_vei_eco") or v.get("ras_vei_placa") or vid

        # Km: si es rango específico → consultar Fulltrack para esas fechas
        if is_range:
            try:
                resp = await fulltrack_client.get_km_for_vehicle(vid, _df, _dt)
                km_total = fulltrack_client.extract_total_km(resp)
            except Exception:
                km_total = 0.0
        else:
            km_total = state_store.get_km_month(vid) or 0.0

        # Litros en el rango desde fuel_records
        all_fuel   = state_store.get_fuel_records_for_vehicle(vid)
        range_recs = [r for r in all_fuel if _record_in_range(r, _df, _dt)]
        litros     = round(sum(r.get("liters", 0) for r in range_recs), 2)

        if km_total <= 0 and litros <= 0:
            continue

        km_por_litro = round(km_total / litros, 3) if litros > 0 else 0.0
        alerta = "normal"
        if km_por_litro > 0:
            if km_por_litro < 1.2:  alerta = "critico"
            elif km_por_litro < 1.8: alerta = "bajo"

        rows.append({
            "eco":                eco,
            "km_total":           round(km_total, 2),
            "litros":             litros,
            "km_por_litro":       km_por_litro,
            "alerta_rendimiento": alerta,
        })

    rows.sort(key=lambda x: x["eco"])
    return {"year": y, "month": m,
            "date_from": str(_df), "date_to": str(_dt),
            "unidades": rows}


# ─── Hoja 3 — Operatividad por ruta ──────────────────────────────────────────

@router.get("/por-ruta")
async def reporte_por_ruta(
    year:  int = Query(default=None),
    month: int = Query(default=None),
):
    y, m = _current(year, month)
    vehicles = state_store.get_vehicles()
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

    return {"year": y, "month": m, "rutas": result}


# ─── Hoja 4 — Combustible ─────────────────────────────────────────────────────

@router.get("/costo-combustible")
async def reporte_costo_combustible(
    year:           int  = Query(default=None),
    month:          int  = Query(default=None),
    date_from:      str  = Query(default=None, description="YYYY-MM-DD"),
    date_to:        str  = Query(default=None, description="YYYY-MM-DD"),
    include_detail: bool = Query(default=False, description="Incluir registros individuales con fecha y hora"),
):
    """
    Hoja 4: Costo y consumo de combustible por unidad.

    Con include_detail=true devuelve cada carga individual con fecha, hora,
    litros, precio y proveedor — útil para drill-down por día u horario.
    """
    _df, _dt, y, m = _resolve_range(year, month, date_from, date_to)
    today = _date.today()

    vehicles = state_store.get_vehicles()
    rows, detail_rows = [], []

    for v in vehicles:
        vid = str(v.get("ras_vei_id", ""))
        eco = v.get("ras_vei_eco") or v.get("ras_vei_placa") or vid

        all_fuel   = state_store.get_fuel_records_for_vehicle(vid)
        range_recs = [r for r in all_fuel if _record_in_range(r, _df, _dt)]

        if not range_recs:
            continue

        diesel_lts   = round(sum(r.get("liters", 0) for r in range_recs
                                 if r.get("tipo") in ("DIESEL", None, "")), 2)
        gasolina_lts = round(sum(r.get("liters", 0) for r in range_recs
                                 if r.get("tipo") in ("GASOLINA_COMUN", "GASOLINA_PREMIUM")), 2)
        total_lts    = round(diesel_lts + gasolina_lts, 2)
        total_importe= round(sum(r.get("liters", 0) * r.get("price_per_liter", 0) for r in range_recs), 2)
        precio_prom  = round(total_importe / total_lts, 4) if total_lts > 0 else 0.0
        last_precio  = range_recs[-1].get("price_per_liter", 0) if range_recs else 0

        if total_lts <= 0:
            continue

        rows.append({
            "eco":            eco,
            "vehicle_id":     vid,
            "diesel_lts":     diesel_lts,
            "diesel_importe": round(diesel_lts * (last_precio or precio_prom), 2),
            "gasolina_lts":   gasolina_lts,
            "total_lts":      total_lts,
            "total_importe":  total_importe,
            "precio_diesel":  last_precio or precio_prom,
            "cargas":         len(range_recs),
        })

        # Detalle por carga individual con fecha y hora
        if include_detail:
            for r in sorted(range_recs, key=lambda x: x.get("fecha", "")):
                fecha_str = str(r.get("fecha", ""))
                hora_str  = ""
                try:
                    dt_obj = datetime.fromisoformat(fecha_str.replace("Z", ""))
                    fecha_str = dt_obj.strftime("%Y-%m-%d")
                    hora_str  = dt_obj.strftime("%H:%M")
                except Exception:
                    pass
                detail_rows.append({
                    "eco":              eco,
                    "fecha":            fecha_str,
                    "hora":             hora_str,
                    "litros":           round(r.get("liters", 0), 2),
                    "precio_litro":     r.get("price_per_liter", 0),
                    "importe":          round(r.get("liters", 0) * r.get("price_per_liter", 0), 2),
                    "proveedor":        r.get("proveedor", ""),
                    "conductor":        r.get("conductor", ""),
                })

    rows.sort(key=lambda x: x["eco"])
    total_lts_g     = round(sum(r["total_lts"] for r in rows), 2)
    total_importe_g = round(sum(r["total_importe"] for r in rows), 2)

    resp = {
        "year": y, "month": m,
        "date_from": str(_df), "date_to": str(_dt),
        "unidades": rows,
        "totales": {"total_lts": total_lts_g, "total_importe": total_importe_g},
    }
    if include_detail:
        resp["detalle_cargas"] = detail_rows
    return resp


# ─── Hoja 5 — Tonelaje ────────────────────────────────────────────────────────

@router.get("/tonelaje")
async def reporte_tonelaje(
    year:      int = Query(default=None),
    month:     int = Query(default=None),
    date_from: str = Query(default=None, description="YYYY-MM-DD"),
    date_to:   str = Query(default=None, description="YYYY-MM-DD"),
):
    """
    Hoja 5: Tonelaje por unidad.
    Con rango de fechas consulta directamente bascula_records.
    """
    _df, _dt, y, m = _resolve_range(year, month, date_from, date_to)

    # Toneladas desde báscula para el rango exacto
    bsc_rows = await db_service.get_bascula_records_by_range(_df, _dt)

    from collections import defaultdict
    eco_agg: dict[str, dict] = defaultdict(lambda: {"toneladas": 0.0, "viajes": 0})
    for r in bsc_rows:
        eco = r.get("num_eco") or r.get("placa") or "SIN ECO"
        eco_agg[eco]["toneladas"] += float(r.get("peso_neto") or 0)
        eco_agg[eco]["viajes"]    += 1

    rows = []
    for eco, d in sorted(eco_agg.items(), key=lambda x: -x[1]["toneladas"]):
        tons    = round(d["toneladas"], 3)
        viajes  = d["viajes"]
        rows.append({
            "eco":                 eco,
            "toneladas":           tons,
            "num_viajes":          viajes,
            "tons_prom_por_viaje": round(tons / viajes, 3) if viajes else 0,
        })

    return {
        "year": y, "month": m,
        "date_from": str(_df), "date_to": str(_dt),
        "unidades": rows,
        "total_toneladas": round(sum(r["toneladas"] for r in rows), 3),
    }


# ─── Actividad de báscula con fecha y hora ───────────────────────────────────

@router.get("/actividad-bascula")
async def actividad_bascula(
    date_from: str = Query(default=None, description="YYYY-MM-DD"),
    date_to:   str = Query(default=None, description="YYYY-MM-DD"),
    year:      int = Query(default=None),
    month:     int = Query(default=None),
    eco:       str = Query(default=None, description="Filtrar por No. Económico"),
    limit:     int = Query(default=200),
):
    """
    Registros individuales de báscula con fecha, hora de entrada/salida,
    peso neto, tipo de cliente y tipo de residuo.

    Ideal para drill-down por día específico u horario.
    """
    _df, _dt, y, m = _resolve_range(year, month, date_from, date_to)
    rows = await db_service.get_bascula_records_by_range(_df, _dt)

    if eco:
        rows = [r for r in rows if (r.get("num_eco") or "").upper() == eco.upper()]

    result = []
    for r in rows[:limit]:
        # Parsear y formatear hora si viene como TIME o string
        def _fmt_time(val) -> str:
            if not val: return ""
            try:
                if hasattr(val, "strftime"): return val.strftime("%H:%M")
                s = str(val)
                return s[:5] if len(s) >= 5 else s
            except Exception: return str(val)

        fecha = r.get("fecha")
        if hasattr(fecha, "isoformat"): fecha = fecha.isoformat()

        result.append({
            "folio":        r.get("folio"),
            "num_eco":      r.get("num_eco") or r.get("placa"),
            "placa":        r.get("placa"),
            "fecha":        str(fecha or ""),
            "hora_entrada": _fmt_time(r.get("hora_entrada")),
            "hora_salida":  _fmt_time(r.get("hora_salida")),
            "peso_entrada": r.get("peso_entrada"),
            "peso_salida":  r.get("peso_salida"),
            "peso_neto":    r.get("peso_neto"),
            "tipo_cliente": r.get("tipo_cliente"),
            "tipo_residuo": r.get("tipo_residuo"),
        })

    return {
        "date_from": str(_df), "date_to": str(_dt),
        "total":   len(result),
        "registros": result,
    }


# ─── Comparativo mensual (3 meses) ───────────────────────────────────────────

@router.get("/comparativo")
async def reporte_comparativo():
    today = _date.today()
    result = {}
    for i in range(3):
        m = today.month - i; y = today.year
        if m <= 0: m += 12; y -= 1
        metrics = _get_all_unit_metrics(y, m)
        if metrics:
            portada = calcular_portada(metrics, y, m)
            result[portada["periodo"]] = portada
    return {"comparativo": result}


# ─── Top 3 consumo ────────────────────────────────────────────────────────────

@router.get("/top3-consumo")
async def top3_consumo(
    year:      int = Query(default=None),
    month:     int = Query(default=None),
    date_from: str = Query(default=None),
    date_to:   str = Query(default=None),
):
    _df, _dt, y, m = _resolve_range(year, month, date_from, date_to)
    today = _date.today()
    is_current = (y == today.year and m == today.month) and not (date_from or date_to)

    if not is_current:
        try:
            cached = await db_service.get_monthly_fuel_summary(y, m)
            if cached and not (date_from or date_to):
                return {"year": y, "month": m, "date_from": str(_df), "date_to": str(_dt), "top3": cached[:3], "todas": cached}
        except Exception:
            pass

    try:
        records = await db_service.get_fuel_records_by_month(y, m)
    except Exception:
        records = []

    ram_records = [r for r in state_store.get_state()["fuel_records"] if _record_in_range(r, _df, _dt)]
    db_ids      = {str(r.get("id")) for r in records}
    all_records = list(records) + [r for r in ram_records if str(r.get("id")) not in db_ids]
    all_records = [r for r in all_records if _record_in_range(r, _df, _dt)]

    por_vehiculo: dict[str, dict] = {}
    for r in all_records:
        vid   = str(r["vehicle_id"])
        entry = por_vehiculo.setdefault(vid, {"litros": 0.0, "costo": 0.0, "cargas": 0})
        liters = float(r.get("liters") or 0)
        entry["litros"] += liters
        entry["costo"]  += liters * float(r.get("price_per_liter") or 0)
        entry["cargas"] += 1

    if not por_vehiculo:
        return {"year": y, "month": m, "date_from": str(_df), "date_to": str(_dt), "top3": [], "todas": []}

    vehicles  = state_store.get_vehicles()
    id_to_eco = {str(v["ras_vei_id"]): v.get("ras_vei_eco") or v.get("ras_vei_placa", "") for v in vehicles}

    result = []
    for vid, datos in por_vehiculo.items():
        km_mes = state_store.get_km_month(vid) or state_store.get_km_today(vid)
        litros = datos["litros"]
        result.append({
            "vehicle_id":   vid,
            "eco":          id_to_eco.get(vid, vid),
            "litros_mes":   round(litros, 2),
            "costo_mes":    round(datos["costo"], 2),
            "km_mes":       round(km_mes, 2),
            "km_por_litro": round(km_mes / litros, 4) if litros > 0 else 0.0,
            "cargas":       datos["cargas"],
        })

    result.sort(key=lambda x: x["litros_mes"], reverse=True)
    if not is_current and result and not (date_from or date_to):
        try:
            await db_service.save_monthly_fuel_summary(y, m, result)
        except Exception:
            pass

    return {"year": y, "month": m, "date_from": str(_df), "date_to": str(_dt), "top3": result[:3], "todas": result}


# ─── Mensual consolidado ──────────────────────────────────────────────────────

@router.get("/mensual")
async def reporte_mensual(
    year:  int = Query(default=None),
    month: int = Query(default=None),
):
    y, m = _current(year, month)
    metrics = _get_all_unit_metrics(y, m)
    portada = calcular_portada(metrics, y, m)
    return {
        "portada":       portada,
        "operatividad":  [{k: met.get(k) for k in ("eco","toneladas","num_viajes","pct_carga")} for met in metrics],
        "km_rendimiento":[{k: met.get(k) for k in ("eco","km_total","diesel_lts","km_por_litro","alerta_rendimiento")} for met in metrics],
        "combustible":   [{k: met.get(k) for k in ("eco","diesel_lts","diesel_importe","total_lts","total_importe")} for met in metrics],
        "tonelaje":      [{k: met.get(k) for k in ("eco","toneladas","num_viajes","tons_prom_por_viaje")} for met in metrics],
    }


def _fuel_record_in_month(record: dict, year: int, month: int) -> bool:
    from datetime import datetime
    fecha = record.get("fecha")
    if not fecha: return False
    try:
        dt = datetime.fromisoformat(str(fecha).replace("Z","")) if isinstance(fecha, str) else fecha
        return dt.year == year and dt.month == month
    except (ValueError, TypeError):
        return False