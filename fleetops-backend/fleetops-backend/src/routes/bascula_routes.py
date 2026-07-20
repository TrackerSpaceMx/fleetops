"""
bascula_routes.py — Endpoints de báscula.

Cambios v2:
  • GET /api/bascula/sync          → fuerza un pull de la API externa (para el scheduler)
  • GET /api/bascula/hoy           → toneladas + viajes del día actual
  • GET /api/bascula/diario        → tonelaje diario últimos N días (gráfico 30 días)
  • GET /api/bascula/por-unidad    → cuánto ha cargado cada vehículo hoy
  • GET /api/bascula/actividad     → últimos registros en vivo (Actividad de Báscula)
  • GET /api/bascula/registros     → consulta general con filtros
  • GET /api/bascula/resumen       → resumen por unidad (compatibilidad)
  • POST /api/bascula/registro     → recibe un pesaje manual (sistema externo)
  • POST /api/bascula/batch        → recibe múltiples pesajes manuales
"""
import logging
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.services import state_store, fleet_service
from src.services import bascula_client          # ← cliente HTTP nuevo
from src.database import db_service
from src.websocket.ws_manager import manager as ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bascula", tags=["Báscula"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class PesajeRecord(BaseModel):
    folio:           int | str
    placa:           str
    num_eco:         str
    razon_social:    str = ""
    fecha:           datetime
    hora_entrada:    str = ""
    hora_salida:     str = ""
    turno:           Literal["Matutino", "Vespertino", "Nocturno"] = "Matutino"
    peso_entrada:    float = 0.0
    peso_salida:     float = 0.0
    peso_neto:       float
    precio_ton:      float = 0.0
    importe:         float = 0.0
    iva:             float = 0.0
    total:           float = 0.0
    basculista:      str = ""
    tipo_cliente:    str = ""
    tipo_residuos:   str = ""


class PesajeBatch(BaseModel):
    registros: list[PesajeRecord]


# ─── Helper: normalizar registro de la API externa ───────────────────────────

def _normalize_api_record(r: dict) -> dict | None:
    """
    Convierte el dict crudo de la API externa a formato interno.
    Fecha viene como "14/MAY/2026" → date.
    """
    import re
    MESES = {
        "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
    }
    try:
        raw_fecha = r.get("fecha", "")
        # "14/MAY/2026"
        m = re.match(r"(\d{1,2})/([A-Z]{3})/(\d{4})", str(raw_fecha).upper())
        if m:
            d_int, mes_str, y_int = int(m.group(1)), m.group(2), int(m.group(3))
            fecha = date(y_int, MESES.get(mes_str, 1), d_int)
        else:
            # Intentar ISO
            fecha = date.fromisoformat(str(raw_fecha)[:10])

        return {
            "folio":         r.get("folio"),
            "placa":         r.get("placa", ""),
            "num_eco":       r.get("num_eco", r.get("placa", "")),
            "fecha":         fecha,
            "hora_entrada":  r.get("hora_entrada", ""),
            "hora_salida":   r.get("hora_salida", ""),
            "peso_entrada":  float(r.get("peso_entrada") or 0),
            "peso_salida":   float(r.get("peso_salida") or 0),
            "peso_neto":     float(r.get("peso_neto") or 0),
            "tipo_cliente":  r.get("tipo_cliente", ""),
            "tipo_residuo":  r.get("tipo_residuo", r.get("tipo_residuos", "")),
        }
    except Exception as e:
        logger.warning("No se pudo normalizar registro de báscula: %s | %s", e, r)
        return None


# ─── Sync desde API externa ───────────────────────────────────────────────────

async def sync_from_api(date_from: date | None = None, date_to: date | None = None) -> dict:
    """
    Llama a la API externa, parsea y persiste en MySQL.
    También actualiza state_store para que los WS tengan datos frescos.
    Retorna resumen de la operación.
    """
    if date_from is None:
        date_from = date.today()
    if date_to is None:
        date_to = date.today()

    try:
        raw_records = await bascula_client.get_records(date_from, date_to)
    except Exception as e:
        logger.error("Error al consumir API de báscula: %s", e)
        return {"error": str(e), "synced": 0}

    normalized = [_normalize_api_record(r) for r in raw_records]
    normalized = [n for n in normalized if n is not None]

    if not normalized:
        return {"synced": 0, "total_api": len(raw_records)}

    # Persistir en MySQL
    affected = await db_service.upsert_bascula_records(normalized)

    # Actualizar state_store (métricas de toneladas por vehículo del día)
    await _update_state_from_records(normalized)

    logger.info(
        "Báscula sync: %d registros de API → %d rows MySQL (rango %s→%s)",
        len(normalized), affected, date_from, date_to
    )
    return {
        "synced":     len(normalized),
        "db_rows":    affected,
        "date_from":  date_from.isoformat(),
        "date_to":    date_to.isoformat(),
    }


async def sync_mes_completo(year: int | None = None, month: int | None = None) -> dict:
    """
    Trae TODOS los registros del mes completo desde la API externa (del día 1 al día de hoy).
    Se llama al arrancar la app y también puede invocarse manualmente.
    Un solo request a la API cubre todo el mes — mucho más rápido que 30 llamadas.
    """
    from calendar import monthrange
    today = date.today()
    if year  is None: year  = today.year
    if month is None: month = today.month

    # Si es el mes actual, hasta hoy; si es mes pasado, hasta el último día
    if year == today.year and month == today.month:
        date_to = today
    else:
        date_to = date(year, month, monthrange(year, month)[1])

    date_from = date(year, month, 1)

    logger.info("Báscula sync mes completo: %s → %s", date_from, date_to)
    return await sync_from_api(date_from, date_to)


async def _update_state_from_records(records: list[dict]) -> None:
    """
    Recalcula toneladas y viajes de hoy en el state_store para cada eco.
    Solo procesa registros del día actual.
    """
    today = date.today()
    today_records = [r for r in records if r.get("fecha") == today]
    if not today_records:
        return

    # Agrupar por eco
    from collections import defaultdict
    por_eco: dict[str, dict] = defaultdict(lambda: {"toneladas": 0.0, "num_viajes": 0})
    for r in today_records:
        eco = r.get("num_eco", "")
        por_eco[eco]["toneladas"]  += r.get("peso_neto", 0.0)
        por_eco[eco]["num_viajes"] += 1

    vehicles = state_store.get_vehicles()
    for v in vehicles:
        v_eco = v.get("ras_vei_eco") or v.get("ras_vei_placa") or ""
        eco_clean = v_eco.replace("-", "").upper()

        match = None
        for eco_key, datos in por_eco.items():
            if eco_key.replace("-", "").upper() == eco_clean:
                match = datos
                break

        if match is None:
            continue

        vid = str(v.get("ras_vei_id", ""))
        existing = state_store.get_unit_metrics(vid)
        await state_store.set_unit_metrics(vid, {
            **existing,
            "toneladas":  round(match["toneladas"], 3),
            "num_viajes": match["num_viajes"],
        })


# ─── Endpoints nuevos (dashboard) ────────────────────────────────────────────

@router.get("/sync")
async def force_sync(
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    """
    Fuerza un pull de la API externa y persiste en MySQL.
    El scheduler llama esto cada minuto, pero también puedes invocarlo manualmente.
    """
    result = await sync_from_api(date_from, date_to)
    # Emitir actualización a clientes WebSocket
    payload = fleet_service.build_fleet_payload()
    await ws_manager.broadcast_fleet(payload)
    return result


@router.get("/sync-mes")
async def force_sync_mes(
    year:  int = Query(default=None),
    month: int = Query(default=None),
):
    """
    Fuerza sync del mes completo desde la API externa.
    Útil para poblar histórico al arrancar o para reparar datos faltantes.
    """
    result = await sync_mes_completo(year, month)
    payload = fleet_service.build_fleet_payload()
    await ws_manager.broadcast_fleet(payload)
    return result


@router.get("/ayer")
async def toneladas_ayer():
    """
    Toneladas y viajes del día anterior.
    Si no hay datos en MySQL, los trae de la API externa.
    """
    ayer = date.today() - timedelta(days=1)
    records = await db_service.get_bascula_records_by_date(ayer)
    
    # Si no hay datos en MySQL (ej: ayer fue del mes anterior), pull de API externa
    if not records:
        try:
            result = await sync_from_api(ayer, ayer)
            if result.get("synced", 0) > 0:
                records = await db_service.get_bascula_records_by_date(ayer)
        except Exception as e:
            logger.warning("No se pudo obtener datos de ayer de API externa: %s", e)
    
    toneladas = round(sum(r.get("peso_neto", 0) for r in records), 3)
    return {
        "fecha":     ayer.isoformat(),
        "toneladas": toneladas,
        "viajes":    len(records),
    }


@router.get("/hoy")
async def toneladas_hoy():
    """
    Toneladas totales del día actual (el KPI principal del dashboard).
    Ejemplo: {"fecha": "2026-05-14", "toneladas": 486.13, "viajes": 64}
    """
    today = date.today()
    records = await db_service.get_bascula_records_by_date(today)
    toneladas = round(sum(r.get("peso_neto", 0) for r in records), 3)
    return {
        "fecha":     today.isoformat(),
        "toneladas": toneladas,
        "viajes":    len(records),
    }


@router.get("/diario")
async def tonelaje_diario(dias: int = Query(default=30, ge=1, le=365)):
    """
    Tonelaje diario para los últimos N días.
    Úsalo para el gráfico 'Tonelaje Diario — Últimos 30 días'.
    Retorna: [{"fecha": "2026-04-15", "toneladas": 421.5, "viajes": 58}, ...]
    """
    today = date.today()
    date_from = today - timedelta(days=dias - 1)
    summary = await db_service.get_bascula_daily_summary(date_from, today)
    return {
        "dias":    dias,
        "desde":   date_from.isoformat(),
        "hasta":   today.isoformat(),
        "serie":   summary,
        "total":   round(sum(d["toneladas"] for d in summary), 3),
    }


@router.get("/por-unidad")
async def toneladas_por_unidad(target_date: date = Query(default=None)):
    """
    Cuánto ha cargado cada vehículo en el día indicado (default: hoy).
    Úsalo para el widget 'Estado de la Flota' que muestra carga por unidad.
    Retorna: [{"num_eco": "TM-07", "toneladas": 38.4, "viajes": 5}, ...]
    """
    if target_date is None:
        target_date = date.today()
    data = await db_service.get_bascula_by_eco_today(target_date)
    total = round(sum(d["toneladas"] for d in data), 3)
    return {
        "fecha":     target_date.isoformat(),
        "unidades":  data,
        "total_toneladas": total,
        "total_viajes":    sum(d["viajes"] for d in data),
    }


@router.get("/actividad")
async def actividad_en_vivo(limit: int = Query(default=50, ge=1, le=500)):
    """
    Últimos N registros de báscula ordenados por hora de entrada.
    Úsalo para el widget 'Actividad de Báscula EN VIVO'.
    El frontend hace polling cada 1 min a este endpoint.
    """
    today = date.today()
    records = await db_service.get_bascula_records_by_date(today)
    # Ordenar por hora_entrada descendente (más reciente primero)
    records_sorted = sorted(
        records,
        key=lambda r: r.get("hora_entrada") or "",
        reverse=True,
    )
    # Serializar fechas
    result = []
    for r in records_sorted[:limit]:
        row = dict(r)
        if hasattr(row.get("fecha"), "isoformat"):
            row["fecha"] = row["fecha"].isoformat()
        result.append(row)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "fecha":     today.isoformat(),
        "total":     len(records),
        "registros": result,
    }


# ─── Endpoints existentes (compatibilidad) ───────────────────────────────────

@router.get("/registros")
async def get_bascula_records(
    eco:         str  = Query(default=None),
    fecha_desde: date = Query(default=None),
    fecha_hasta: date = Query(default=None),
):
    """Consulta registros de báscula con filtros opcionales."""
    today = date.today()
    d_from = fecha_desde or (today - timedelta(days=30))
    d_to   = fecha_hasta or today

    records = await db_service.get_bascula_records_by_range(d_from, d_to)

    if eco:
        eco_clean = eco.replace("-", "").upper()
        records = [
            r for r in records
            if str(r.get("num_eco", "")).replace("-", "").upper() == eco_clean
        ]

    # Serializar fechas
    result = []
    for r in records:
        row = dict(r)
        if hasattr(row.get("fecha"), "isoformat"):
            row["fecha"] = row["fecha"].isoformat()
        result.append(row)

    return {
        "total":           len(result),
        "total_toneladas": round(sum(r.get("peso_neto", 0) for r in result), 3),
        "registros":       result,
    }


@router.get("/resumen")
async def resumen_bascula(target_date: date = Query(default=None)):
    """Resumen por unidad para un día (default: hoy). Compatibilidad con versión anterior."""
    return await toneladas_por_unidad(target_date)


# ─── Endpoints de ingesta manual (sistema externo vía POST) ──────────────────

@router.post("/registro")
async def registrar_pesaje(body: PesajeRecord):
    """Recibe un registro de báscula desde sistema externo vía POST."""
    record = {
        "folio":        body.folio,
        "placa":        body.placa,
        "num_eco":      body.num_eco,
        "fecha":        body.fecha.date(),
        "hora_entrada": body.hora_entrada,
        "hora_salida":  body.hora_salida,
        "peso_entrada": body.peso_entrada,
        "peso_salida":  body.peso_salida,
        "peso_neto":    body.peso_neto,
        "tipo_cliente": body.tipo_cliente,
        "tipo_residuo": body.tipo_residuos,
    }
    await db_service.upsert_bascula_records([record])
    await _update_state_from_records([record])
    return {"status": "ok", "folio": body.folio}


@router.post("/batch")
async def registrar_pesaje_batch(body: PesajeBatch):
    """Recibe múltiples registros de báscula vía POST."""
    records = []
    for pesaje in body.registros:
        records.append({
            "folio":        pesaje.folio,
            "placa":        pesaje.placa,
            "num_eco":      pesaje.num_eco,
            "fecha":        pesaje.fecha.date(),
            "hora_entrada": pesaje.hora_entrada,
            "hora_salida":  pesaje.hora_salida,
            "peso_entrada": pesaje.peso_entrada,
            "peso_salida":  pesaje.peso_salida,
            "peso_neto":    pesaje.peso_neto,
            "tipo_cliente": pesaje.tipo_cliente,
            "tipo_residuo": pesaje.tipo_residuos,
        })

    await db_service.upsert_bascula_records(records)
    await _update_state_from_records(records)
    await fleet_service.recalculate_all_metrics()
    payload = fleet_service.build_fleet_payload()
    await ws_manager.broadcast_fleet(payload)

    return {"status": "ok", "registros_procesados": len(records)}



# ─── Reporte mensual de báscula ───────────────────────────────────────────────

@router.get("/mensual")
async def bascula_mensual(
    year:  int = Query(default=None),
    month: int = Query(default=None),
):
    """
    Hoja BASE DE DATOS — resumen mensual completo por unidad.

    Retorna:
    {
      "year": 2026, "month": 5, "periodo": "Mayo 2026",
      "totales": {"toneladas": 9820.4, "viajes": 1380},
      "por_unidad": [
        {"num_eco": "TM-07", "tipo_cliente": "MUNICIPIO",
         "toneladas": 412.5, "viajes": 58, "promedio_ton_viaje": 7.11}
      ],
      "por_tipo_cliente": [
        {"tipo_cliente": "MUNICIPIO", "toneladas": 8100.0, "viajes": 1200},
        {"tipo_cliente": "PARTICULAR", "toneladas": 1720.4, "viajes": 180}
      ]
    }
    """
    today = date.today()
    y = year  or today.year
    m = month or today.month

    por_unidad      = await db_service.get_bascula_monthly_by_eco(y, m)
    por_tipo        = await db_service.get_bascula_monthly_by_tipo_cliente(y, m)

    # Consolidar por_tipo al nivel de tipo_cliente (sin residuo)
    from collections import defaultdict
    tc_agg: dict[str, dict] = defaultdict(lambda: {"toneladas": 0.0, "viajes": 0})
    for row in por_tipo:
        tc = row["tipo_cliente"] or "SIN TIPO"
        tc_agg[tc]["toneladas"] += row["toneladas"]
        tc_agg[tc]["viajes"]    += row["viajes"]
    tipo_cliente_list = [
        {"tipo_cliente": tc, **datos}
        for tc, datos in sorted(tc_agg.items(), key=lambda x: -x[1]["toneladas"])
    ]

    # Consolidar por_unidad (puede tener mismo eco con distintos tipo_cliente)
    eco_agg: dict[str, dict] = defaultdict(lambda: {"toneladas": 0.0, "viajes": 0, "tipo_cliente": ""})
    for row in por_unidad:
        eco = row["num_eco"]
        eco_agg[eco]["toneladas"]   += row["toneladas"]
        eco_agg[eco]["viajes"]      += row["viajes"]
        eco_agg[eco]["tipo_cliente"] = row["tipo_cliente"]  # último gana (OK para municipio)
    por_unidad_merged = [
        {
            "num_eco":            eco,
            "tipo_cliente":       datos["tipo_cliente"],
            "toneladas":          round(datos["toneladas"], 3),
            "viajes":             datos["viajes"],
            "promedio_ton_viaje": round(datos["toneladas"] / datos["viajes"], 3) if datos["viajes"] else 0,
        }
        for eco, datos in sorted(eco_agg.items(), key=lambda x: -x[1]["toneladas"])
    ]

    total_tons   = round(sum(r["toneladas"] for r in por_unidad_merged), 3)
    total_viajes = sum(r["viajes"] for r in por_unidad_merged)

    MESES = {
        1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
        7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre",
    }

    return {
        "year":    y,
        "month":   m,
        "periodo": f"{MESES.get(m, str(m))} {y}",
        "totales": {
            "toneladas": total_tons,
            "viajes":    total_viajes,
            "promedio_ton_viaje": round(total_tons / total_viajes, 3) if total_viajes else 0,
        },
        "por_unidad":      por_unidad_merged,
        "por_tipo_cliente": tipo_cliente_list,
        "desglose_residuo": por_tipo,
    }


# ─── Por cliente (particulares vs municipio) ──────────────────────────────────

@router.get("/por-cliente")
async def bascula_por_cliente(
    year:  int = Query(default=None),
    month: int = Query(default=None),
):
    """
    Agrupación de toneladas por tipo de cliente — Municipio / Particular / Disposición.
    Incluye desglose por tipo de residuo.

    Ejemplo de uso: widget 'Composición de residuos' y tabla de clientes.
    """
    today = date.today()
    y = year  or today.year
    m = month or today.month

    desglose = await db_service.get_bascula_monthly_by_tipo_cliente(y, m)

    from collections import defaultdict
    # Nivel 1: por tipo_cliente
    por_tipo: dict[str, dict] = defaultdict(lambda: {"toneladas": 0.0, "viajes": 0, "residuos": []})
    for row in desglose:
        tc = row["tipo_cliente"] or "SIN TIPO"
        por_tipo[tc]["toneladas"] += row["toneladas"]
        por_tipo[tc]["viajes"]    += row["viajes"]
        por_tipo[tc]["residuos"].append({
            "tipo_residuo": row["tipo_residuo"],
            "toneladas":    row["toneladas"],
            "viajes":       row["viajes"],
        })

    total_tons = sum(d["toneladas"] for d in por_tipo.values())
    clientes = [
        {
            "tipo_cliente": tc,
            "toneladas":    round(datos["toneladas"], 3),
            "viajes":       datos["viajes"],
            "pct_toneladas": round(datos["toneladas"] / total_tons * 100, 1) if total_tons else 0,
            "residuos":     sorted(datos["residuos"], key=lambda x: -x["toneladas"]),
        }
        for tc, datos in sorted(por_tipo.items(), key=lambda x: -x[1]["toneladas"])
    ]

    return {
        "year":     y,
        "month":    m,
        "total_toneladas": round(total_tons, 3),
        "clientes": clientes,
    }


# ─── Por turno / basculista (hoja Rossy) ──────────────────────────────────────

@router.get("/turno-basculista")
async def bascula_por_turno(
    year:  int = Query(default=None),
    month: int = Query(default=None),
):
    """
    Reporte por turno (Matutino / Vespertino / Nocturno) y tipo de cliente.
    Replica las hojas 'OCT 25 ROSSY', 'NOV 25 ROSSY', 'DIC 25 ROSSY' del Excel.

    Retorna:
    {
      "turnos": {
        "Matutino":   {"toneladas": 7200, "viajes": 1000, "por_tipo": [...]},
        "Vespertino": {"toneladas": 2100, "viajes": 300,  "por_tipo": [...]}
      },
      "por_dia": [{"dia": "2026-05-14", "turno": "Matutino", ...}]
    }
    """
    today = date.today()
    y = year  or today.year
    m = month or today.month

    rows = await db_service.get_bascula_by_turno(y, m)

    from collections import defaultdict
    turnos: dict[str, dict] = defaultdict(lambda: {"toneladas": 0.0, "viajes": 0, "por_tipo": defaultdict(lambda: {"toneladas": 0.0, "viajes": 0})})

    for row in rows:
        t = row["turno"]
        tc = row["tipo_cliente"] or "SIN TIPO"
        turnos[t]["toneladas"] += row["toneladas"]
        turnos[t]["viajes"]    += row["viajes"]
        turnos[t]["por_tipo"][tc]["toneladas"] += row["toneladas"]
        turnos[t]["por_tipo"][tc]["viajes"]    += row["viajes"]

    turno_result = {}
    for t, datos in sorted(turnos.items()):
        turno_result[t] = {
            "toneladas": round(datos["toneladas"], 3),
            "viajes":    datos["viajes"],
            "por_tipo": [
                {"tipo_cliente": tc, "toneladas": round(d["toneladas"], 3), "viajes": d["viajes"]}
                for tc, d in sorted(datos["por_tipo"].items(), key=lambda x: -x[1]["toneladas"])
            ],
        }

    return {
        "year":    y,
        "month":   m,
        "turnos":  turno_result,
        "por_dia": rows,
    }


# ─── Diesel diario (hoja CONS. DIESEL Y RECORRIDO TOTAL) ──────────────────────

@router.get("/diesel-diario")
async def diesel_diario(
    year:  int = Query(default=None),
    month: int = Query(default=None),
):
    """
    Consumo de diesel por día por vehículo + km del día (Fulltrack).
    Replica 'CONS. DIESEL Y RECORRIDO TOTAL' del Excel.

    Retorna tabla pivote: cada fila = vehículo, cada columna = día del mes,
    valor = litros. También incluye km/litro si hay datos de km.
    """
    from src.services import state_store as _ss
    today = date.today()
    y = year  or today.year
    m = month or today.month

    diesel_rows = await db_service.get_diesel_daily_by_vehicle(y, m)
    bascula_rows = await db_service.get_bascula_daily_by_eco(y, m)

    # Mapa vehicle_id → eco
    vehicles = _ss.get_vehicles()
    id_to_eco = {str(v["ras_vei_id"]): v.get("ras_vei_eco") or v.get("ras_vei_placa", "") for v in vehicles}

    # Agrupar diesel por vehículo
    from collections import defaultdict
    by_vehicle: dict[str, dict] = defaultdict(lambda: {"litros_total": 0.0, "dias": {}})
    for row in diesel_rows:
        vid = row["vehicle_id"]
        dia = row["fecha"]
        by_vehicle[vid]["litros_total"] += row["litros"]
        by_vehicle[vid]["dias"][dia] = {
            "litros":  row["litros"],
            "importe": row["importe"],
        }

    # Agrupar toneladas por eco
    by_eco_tons: dict[str, float] = defaultdict(float)
    for row in bascula_rows:
        by_eco_tons[row["num_eco"]] += row["toneladas"]

    result_units = []
    for vid, datos in sorted(by_vehicle.items()):
        eco = id_to_eco.get(vid, vid)
        km_mes = _ss.get_km_month(vid) or 0
        lts    = datos["litros_total"]
        tons   = by_eco_tons.get(eco, 0) or by_eco_tons.get(eco.replace("-", ""), 0)
        result_units.append({
            "vehicle_id":  vid,
            "eco":         eco,
            "litros_mes":  round(lts, 2),
            "km_mes":      round(km_mes, 2),
            "km_por_litro": round(km_mes / lts, 3) if lts > 0 else 0,
            "toneladas_mes": round(tons, 3),
            "dias":         datos["dias"],
        })

    result_units.sort(key=lambda x: x["eco"])
    total_lts = round(sum(u["litros_mes"] for u in result_units), 2)
    total_km  = round(sum(u["km_mes"]     for u in result_units), 2)

    return {
        "year":  y,
        "month": m,
        "totales": {
            "litros": total_lts,
            "km":     total_km,
            "km_por_litro": round(total_km / total_lts, 3) if total_lts else 0,
        },
        "unidades": result_units,
    }