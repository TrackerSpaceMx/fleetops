"""
fleet_service.py — Determina el estado de la flota a partir de eventos GPS
y actualiza el state_store con métricas calculadas.
"""
import logging
import asyncio
from datetime import datetime, timedelta
from src.routes.fuel_routes import _record_in_month
from src.services import state_store, fulltrack_client
from src.services.metrics_engine import calcular_metricas_unidad, calcular_portada
from src.config.settings import FULLTRACK_APIKEY

logger = logging.getLogger(__name__)

# Tiempo máximo sin comunicar para considerar unidad INACTIVA
INACTIVITY_MINUTES = 60


def _parse_fulltrack_datetime(dt_str: str) -> datetime | None:
    """Parsea el formato de fecha de Fulltrack: DD/MM/YYYY HH:MM:SS o ISO."""
    if not dt_str:
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _unit_status(event: dict) -> str:
    """
    Determina el estado de la unidad:
      ACTIVO   → GPS reportó hace menos de INACTIVITY_MINUTES min
      INACTIVO → sin comunicación reciente
      SIN_GPS  → no hay datos
    """
    gps_str = (
        event.get("ras_eve_data_gps")
        or event.get("ras_ras_data_ult_comunicacao")
        or ""
    )
    dt = _parse_fulltrack_datetime(gps_str)
    if dt is None:
        return "SIN_GPS"
    diff = (datetime.utcnow() - dt).total_seconds() / 60
    # Fulltrack usa hora local MX (UTC-6), ajustamos
    diff -= 360  # compensar UTC+6 → puede quedar negativo si el reporte es reciente
    if abs(diff) <= INACTIVITY_MINUTES:
        return "ACTIVO"
    return "INACTIVO"


async def refresh_fleet_status() -> list[dict]:
    """
    1. Trae todos los eventos de Fulltrack.
    2. Cruza con la lista de vehículos para obtener el eco (Num. Económico).
    3. Determina status ACTIVO/INACTIVO por tiempo de última comunicación.
    4. Actualiza el state_store.
    Retorna la lista de unidades con estado.
    """
    try:
        events = await fulltrack_client.get_all_events()
    except Exception as exc:
        logger.error("Error al obtener eventos de Fulltrack: %s", exc)
        return []

    vehicles = state_store.get_vehicles()
    # Mapa vehicle_id → eco para cruce rápido
    id_to_eco = {str(v.get("ras_vei_id", "")): v for v in vehicles}

    fleet_status = []
    for ev in events:
        vid = str(ev.get("ras_vei_id") or ev.get("vehicle_id") or "")
        vehicle_info = id_to_eco.get(vid, {})

        gps_date = (
            ev.get("ras_eve_data_gps")
            or ev.get("ras_ras_data_ult_comunicacao")
            or ""
        )
        status = _unit_status(ev)

        enriched = {
            "vehicle_id":   vid,
            "eco":          vehicle_info.get("ras_vei_eco", vehicle_info.get("ras_vei_placa", vid)),
            "placa":        vehicle_info.get("ras_vei_placa", ""),
            "descripcion":  vehicle_info.get("ras_vei_descripcion", ""),
            "status":       status,
            "gps_date":     gps_date,
            "lat":          ev.get("ras_eve_lat") or ev.get("lat"),
            "lng":          ev.get("ras_eve_lng") or ev.get("lng"),
            "velocidad":    ev.get("ras_eve_velocidade") or ev.get("speed", 0),
            "ruta":         vehicle_info.get("ruta", ""),
        }
        await state_store.update_fleet_event(vid, enriched)
        fleet_status.append(enriched)

    logger.info("Fleet status actualizado: %d unidades", len(fleet_status))
    return fleet_status


async def refresh_vehicles() -> list[dict]:
    """Actualiza la lista de vehículos desde Fulltrack."""
    try:
        vehicles = await fulltrack_client.get_vehicles()
        await state_store.set_vehicles(vehicles)
        logger.info("Vehículos cargados: %d", len(vehicles))
        return vehicles
    except Exception as exc:
        logger.error("Error al obtener vehículos: %s", exc)
        return []

async def refresh_km(vehicle_id: str, date_initial=None, date_final=None) -> float:
    from datetime import date
    from calendar import monthrange
    from src.database import db_service

    today = date.today()
    try:
        # 1. Km de hoy (para el dashboard en tiempo real)
        response = await fulltrack_client.get_km_for_vehicle(
            vehicle_id, date_initial, date_final
        )
        km_hoy = fulltrack_client.extract_total_km(response)
        await state_store.set_km_today(vehicle_id, km_hoy)

        # 2. Km del mes completo (para métricas y reportes)
        first = date(today.year, today.month, 1)
        last  = date(today.year, today.month, monthrange(today.year, today.month)[1])
        response_mes = await fulltrack_client.get_km_for_vehicle(
            vehicle_id, first, last
        )
        km_mes = fulltrack_client.extract_total_km(response_mes)
        await state_store.set_km_month(vehicle_id, km_mes)

        # 3. Persistir en MySQL
        if km_mes > 0:
            await db_service.save_monthly_km(vehicle_id, today.year, today.month, km_mes)

        logger.info("✅ km para %s: hoy=%.2f mes=%.2f", vehicle_id, km_hoy, km_mes)
        return km_hoy

    except Exception as exc:
        logger.error("Error al obtener km para %s: %s", vehicle_id, exc)
        return state_store.get_km_today(vehicle_id)


async def recalculate_all_metrics(year: int | None = None, month: int | None = None):
    from datetime import date as _date
    from src.routes.fuel_routes import _record_in_month

    if year is None:
        year = _date.today().year
    if month is None:
        month = _date.today().month

    vehicles = state_store.get_vehicles()
    all_metrics = []

    for v in vehicles:
        vid = str(v.get("ras_vei_id", ""))
        eco = v.get("ras_vei_eco") or v.get("ras_vei_placa") or vid

        km_total       = state_store.get_km_month(vid) or state_store.get_km_today(vid)
        fuel_records   = state_store.get_fuel_records_for_vehicle(vid)
        month_records  = [r for r in fuel_records if _record_in_month(r, year, month)]
        litros_total   = sum(r.get("liters", 0) for r in month_records)
        precio_litro   = (
            month_records[-1].get("price_per_liter") if month_records else None
        )

        # Toneladas: vienen de la báscula (sistema externo); si no hay datos usamos 0
        bascula_data   = state_store.get_unit_metrics(vid)
        toneladas      = bascula_data.get("toneladas", 0.0)
        tons_ticket    = bascula_data.get("tons_ticket")
        num_viajes     = bascula_data.get("num_viajes")

        # Horas operativas: estimamos de km (se actualiza si hay telemetría real)
        horas_operativas = bascula_data.get("horas_operativas", 0.0)
        if horas_operativas <= 0 and km_total > 0:
            # Estimación: velocidad promedio municipal ≈ 20 km/h
            horas_operativas = km_total / 20.0

        # ── FIX: incluir unidades con litros aunque no tengan km aún ──────────
        # Antes: `if km_total <= 0 and toneladas <= 0: continue`
        # Ahora: solo saltamos si no hay absolutamente ningún dato
        if km_total <= 0 and toneladas <= 0 and litros_total <= 0:
            continue

        metrics = calcular_metricas_unidad(
            eco=eco,
            km_total=km_total,
            horas_operativas=horas_operativas,
            toneladas=toneladas,
            litros_cargados=litros_total,
            precio_litro=precio_litro,
            num_viajes=num_viajes,
            tons_ticket=tons_ticket,
            year=year,
            month=month,
        )
        metrics["vehicle_id"] = vid
        await state_store.set_unit_metrics(vid, metrics)
        all_metrics.append(metrics)

    # Calcular portada / resumen ejecutivo
    if all_metrics:
        portada = calcular_portada(all_metrics, year, month)
        await state_store.set_dashboard_summary(portada)

    logger.info("Métricas recalculadas para %d unidades", len(all_metrics))
    return all_metrics


def build_fleet_payload() -> dict:
    """
    Construye el payload completo para emitir por WebSocket al frontend.
    Contiene todo lo que necesitan Dashboard, Flota, Reportes y Combustible.
    """
    fleet_events = state_store.get_fleet_events()
    vehicles     = state_store.get_vehicles()
    summary      = state_store.get_dashboard_summary()

    units = []
    for v in vehicles:
        vid  = str(v.get("ras_vei_id", ""))
        eco  = v.get("ras_vei_eco") or v.get("ras_vei_placa") or vid
        ev   = fleet_events.get(vid, {})
        met  = state_store.get_unit_metrics(vid)
        fuel = state_store.get_fuel_records_for_vehicle(vid)
        km_h = state_store.get_km_today(vid)

        units.append({
            # Identidad
            "vehicle_id":    vid,
            "eco":           eco,
            "placa":         v.get("ras_vei_placa", ""),
            "descripcion":   v.get("ras_vei_descripcion", ""),
            # GPS / Estado flota
            "status":        ev.get("status", "SIN_GPS"),
            "gps_date":      ev.get("gps_date", ""),
            "lat":           ev.get("lat"),
            "lng":           ev.get("lng"),
            "velocidad":     ev.get("velocidad", 0),
            # Operatividad hoy
            "km_hoy":        km_h,
            # Métricas mensuales (Hoja1-5)
            **met,
            # Combustible
            "fuel_records":  fuel,
            "litros_mes":    sum(r.get("liters", 0) for r in fuel),
            "costo_mes":     sum(r.get("liters", 0) * r.get("price_per_liter", 0) for r in fuel),
        })

    active_count   = state_store.get_active_vehicles_count()
    inactive_count = len(vehicles) - active_count

    return {
        "type":            "fleet_update",
        "timestamp":       datetime.utcnow().isoformat(),
        "dashboard":       summary,
        "active_units":    active_count,
        "inactive_units":  inactive_count,
        "total_units":     len(vehicles),
        "units":           units,
    }


async def refresh_km_historico():
    """
    Calcula KM de los últimos 3 meses para todos los vehículos usando
    ODÓMETRO: hace 2 peticiones por vehículo por mes (día 1 y último día).
    km_total = odómetro_fin - odómetro_inicio
    Persiste en km_odometro_snapshots y monthly_km.
    Se ejecuta una vez al día (scheduler) y al arrancar.
    """
    from calendar import monthrange
    from datetime import date
    from src.database import db_service

    today = date.today()
    vehicles = state_store.get_vehicles()

    # Últimos 3 meses (sin el mes actual para no pisar datos en curso)
    meses = []
    for i in range(1, 4):
        m = today.month - i
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        meses.append((y, m))

    logger.info("refresh_km_historico: %d meses × %d vehículos", len(meses), len(vehicles))

    for year, month in meses:
        _, days_in_month = monthrange(year, month)
        date_inicio = date(year, month, 1)
        date_fin    = date(year, month, days_in_month)

        # Traer snapshots ya guardados en DB para no repetir peticiones
        vids = [str(v.get("ras_vei_id", "")) for v in vehicles if v.get("ras_vei_id")]
        snapshots_existentes: dict = {}
        for vid in vids:
            snaps = await db_service.get_km_odometro_snapshots(vid, year, month)
            snapshots_existentes[vid] = snaps

        # Para cada vehículo: pedir inicio y fin sólo si no están en DB
        BATCH = 4   # peticiones en paralelo (conservador para no saturar Fulltrack)
        for batch_start in range(0, len(vids), BATCH):
            batch_vids = vids[batch_start:batch_start + BATCH]
            tasks_inicio = []
            tasks_fin    = []
            needs_inicio = []
            needs_fin    = []

            for vid in batch_vids:
                snap = snapshots_existentes.get(vid, {})
                # Pedir inicio si no está guardado
                if snap.get("inicio") is None:
                    tasks_inicio.append(
                        fulltrack_client.get_km_for_vehicle(vid, date_inicio, date_inicio)
                    )
                    needs_inicio.append(vid)
                # Pedir fin si no está guardado
                if snap.get("fin") is None:
                    tasks_fin.append(
                        fulltrack_client.get_km_for_vehicle(vid, date_fin, date_fin)
                    )
                    needs_fin.append(vid)

            # Ejecutar en paralelo
            if tasks_inicio:
                results_inicio = await asyncio.gather(*tasks_inicio, return_exceptions=True)
                for vid, res in zip(needs_inicio, results_inicio):
                    if isinstance(res, Exception):
                        logger.warning("Fulltrack inicio %s %d/%d: %s", vid, month, year, res)
                        continue
                    km_val = fulltrack_client.extract_total_km(res)
                    if km_val > 0:
                        await db_service.save_km_odometro_snapshot(vid, year, month, "inicio", km_val)
                        snapshots_existentes[vid]["inicio"] = km_val

            if tasks_fin:
                results_fin = await asyncio.gather(*tasks_fin, return_exceptions=True)
                for vid, res in zip(needs_fin, results_fin):
                    if isinstance(res, Exception):
                        logger.warning("Fulltrack fin %s %d/%d: %s", vid, month, year, res)
                        continue
                    km_val = fulltrack_client.extract_total_km(res)
                    if km_val > 0:
                        await db_service.save_km_odometro_snapshot(vid, year, month, "fin", km_val)
                        snapshots_existentes[vid]["fin"] = km_val

            if batch_start + BATCH < len(vids):
                await asyncio.sleep(1.5)   # pausa entre batches

        # Calcular km_total = fin - inicio y guardar en monthly_km
        all_metrics = []
        for v in vehicles:
            vid  = str(v.get("ras_vei_id", ""))
            eco  = v.get("ras_vei_eco") or v.get("ras_vei_placa") or vid
            snap = snapshots_existentes.get(vid, {})
            km_inicio = snap.get("inicio")
            km_fin    = snap.get("fin")

            if km_inicio is not None and km_fin is not None and km_fin > km_inicio:
                km_total = round(km_fin - km_inicio, 2)
            else:
                # Fallback: usar monthly_km si ya tenía datos
                km_total = await db_service.get_monthly_km(vid, year, month)

            if km_total <= 0:
                continue

            await db_service.save_monthly_km(vid, year, month, km_total)
            await state_store.set_km_historico(vid, year, month, km_total)

            # Litros de ese mes
            fuel_records = state_store.get_fuel_records_for_vehicle(vid)
            from src.routes.fuel_routes import _record_in_month
            month_recs = [r for r in fuel_records if _record_in_month(r, year, month)]
            litros = sum(r.get("liters", 0) for r in month_recs)

            if km_total <= 0 and litros <= 0:
                continue

            horas = (km_total / 20.0) if km_total > 0 else 0.0

            metrics = calcular_metricas_unidad(
                eco=eco,
                km_total=km_total,
                horas_operativas=horas,
                toneladas=0.0,
                litros_cargados=litros,
                year=year,
                month=month,
            )
            metrics["vehicle_id"] = vid
            all_metrics.append(metrics)

        await state_store.set_metrics_historico(year, month, all_metrics)
        logger.info("✅ KM odómetro %d/%d: %d unidades procesadas", month, year, len(all_metrics))


async def get_rendimiento_historico_vehicle(vehicle_id: str) -> list[dict]:
    """
    Devuelve las métricas de los últimos 3 meses para un vehículo específico.
    Combina monthly_km + monthly_fuel_summary + bascula para construir la fila.
    Usado por el endpoint GET /api/fleet/rendimiento-historico/{vehicle_id}
    """
    from calendar import monthrange
    from datetime import date
    from src.database import db_service
    from src.services.metrics_engine import calcular_metricas_unidad, _mes_nombre
    from src.config.settings import KM_PROD_FACTOR, KM_TRASL_FACTOR

    today = date.today()
    meses = []
    for i in range(0, 3):           # incluye mes actual + 2 anteriores
        m = today.month - i
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        meses.append((y, m))

    # Determinar eco del vehículo
    vehicles = state_store.get_vehicles()
    v_info   = next((v for v in vehicles if
                     str(v.get("ras_vei_id", "")) == str(vehicle_id) or
                     v.get("ras_vei_eco") == vehicle_id or
                     v.get("ras_vei_placa") == vehicle_id), {})
    eco = v_info.get("ras_vei_eco") or v_info.get("ras_vei_placa") or vehicle_id
    vid = str(v_info.get("ras_vei_id", vehicle_id))

    result = []
    from src.routes.fuel_routes import _record_in_month
    fuel_records = state_store.get_fuel_records_for_vehicle(vid)

    for year, month in meses:
        # KM del mes
        km_total = await db_service.get_monthly_km(vid, year, month)
        if km_total <= 0:
            km_total = state_store.get_km_historico(vid, year, month) or 0.0

        # Litros del mes (de fuel_records en memoria)
        month_recs = [r for r in fuel_records if _record_in_month(r, year, month)]
        litros = sum(r.get("liters", 0) for r in month_recs)

        # Toneladas del mes desde métricas históricas guardadas
        hist_metrics = state_store.get_metrics_historico(year, month) or []
        unit_hist    = next((m for m in hist_metrics if str(m.get("vehicle_id")) == vid), {})
        toneladas    = unit_hist.get("toneladas", 0.0)

        # Si no hay nada, skip
        if km_total <= 0 and litros <= 0 and toneladas <= 0:
            continue

        # Calcular distribución
        km_prod  = round(km_total * KM_PROD_FACTOR, 0)
        km_trasl = round(km_total * KM_TRASL_FACTOR, 0)
        km_por_litro = round(km_total / litros, 2) if litros > 0 else 0.0

        result.append({
            "periodo":    f"{_mes_nombre(month).capitalize()} {year}",
            "year":       year,
            "month":      month,
            "toneladas":  round(toneladas, 2),
            "km_total":   round(km_total, 0),
            "km_prod":    km_prod,
            "km_trasl":   km_trasl,
            "diesel_lts": round(litros, 0),
            "km_por_litro": km_por_litro,
        })

    return result