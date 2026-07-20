"""
scheduler.py — Tareas periódicas en background.
• Cada FLEET_POLL_INTERVAL seg  → refresca estado GPS y emite por WS
• Cada KM_POLL_INTERVAL seg     → refresca km de cada vehículo
• Cada 1 min                    → sincroniza báscula (solo hoy)
• Al inicio                     → carga vehículos + sincroniza mes completo de báscula
• Cada 24 h                     → refresca km histórico
"""
import asyncio
import logging
from datetime import date, timedelta
from src.database import db_service
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config.settings import FLEET_POLL_INTERVAL, KM_POLL_INTERVAL
from src.services import fleet_service, state_store
from src.websocket.ws_manager import manager as ws_manager

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="America/Monterrey")


# ─────────────────────────────────────────────────────────────────────────────
# TAREAS
# ─────────────────────────────────────────────────────────────────────────────

async def _task_refresh_fleet():
    """Trae eventos GPS, determina ACTIVO/INACTIVO y emite a los clientes."""
    logger.debug("▶ task: refresh_fleet")
    try:
        await fleet_service.refresh_fleet_status()
        await fleet_service.recalculate_all_metrics()
        payload = fleet_service.build_fleet_payload()
        await ws_manager.broadcast_fleet(payload)

        # Verificar alertas de rendimiento
        for unit in payload.get("units", []):
            alerta = unit.get("alerta_rendimiento", "normal")
            if alerta in ("critico", "bajo"):
                await ws_manager.broadcast_alert({
                    "type":    "alerta_rendimiento",
                    "eco":     unit.get("eco"),
                    "nivel":   alerta,
                    "km_lts":  unit.get("km_por_litro"),
                    "ts":      payload["timestamp"],
                })
    except Exception as exc:
        logger.error("Error en task refresh_fleet: %s", exc, exc_info=True)


async def _task_refresh_km():
    """Actualiza km recorridos hoy para todos los vehículos."""
    logger.debug("▶ task: refresh_km")
    today = date.today()
    vehicles = state_store.get_vehicles()

    tasks = []
    vids = []
    for v in vehicles:
        vid = str(v.get("ras_vei_id", ""))
        if vid:
            tasks.append(
                fleet_service.refresh_km(vid, date_initial=today, date_final=today)
            )
            vids.append(vid)

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            logger.warning("Errores al obtener km: %d/%d", len(errors), len(tasks))

        # Persistir km en MySQL
        for vid, result in zip(vids, results):
            if not isinstance(result, Exception) and result > 0:
                try:
                    await db_service.save_monthly_km(vid, today.year, today.month, result)
                except Exception as e:
                    logger.warning("No se pudo guardar km mensual para %s: %s", vid, e)

    # Recalcular métricas tras actualizar km
    await fleet_service.recalculate_all_metrics()
    payload = fleet_service.build_fleet_payload()
    await ws_manager.broadcast_fleet(payload)


async def _task_sync_bascula_hoy():
    """
    Sincroniza SOLO el día de hoy desde la API externa de báscula.
    Se ejecuta cada 1 minuto — rápido porque es 1 solo día.
    """
    logger.debug("▶ task: sync_bascula_hoy")
    try:
        from src.routes.bascula_routes import sync_from_api
        result = await sync_from_api(date.today(), date.today())

        if result.get("synced", 0) > 0:
            # Nuevos registros: recalcular métricas y notificar por WS
            await fleet_service.recalculate_all_metrics()
            payload = fleet_service.build_fleet_payload()
            await ws_manager.broadcast_fleet(payload)

            # Evento específico de báscula
            from src.database import db_service as _db
            records = await _db.get_bascula_records_by_date(date.today())
            toneladas_hoy = round(sum(r.get("peso_neto", 0) for r in records), 3)
            await ws_manager.broadcast_alert({
                "type":             "bascula_update",
                "fecha":            date.today().isoformat(),
                "toneladas_hoy":    toneladas_hoy,
                "viajes_hoy":       len(records),
                "nuevos_registros": result.get("synced", 0),
            })

        logger.debug("Báscula hoy sync: %s", result)
    except Exception as exc:
        logger.error("Error en task sync_bascula_hoy: %s", exc, exc_info=True)


async def _task_sync_bascula_mes():
    """
    Sincroniza el mes completo de báscula desde la API externa (día 1 → hoy).
    Se ejecuta UNA VEZ al arrancar la app para poblar el histórico del mes.
    También se programa para correr a medianoche del día 1 de cada mes.
    Un solo request a la API cubre todo el mes: sin loops, sin rate-limiting.
    """
    logger.info("▶ task: sync_bascula_mes (mes completo)")
    try:
        from src.routes.bascula_routes import sync_mes_completo
        result = await sync_mes_completo()
        logger.info("✅ Báscula mes completo: %d registros sincronizados", result.get("synced", 0))
    except Exception as exc:
        logger.error("Error en task sync_bascula_mes: %s", exc, exc_info=True)


async def _task_load_vehicles():
    logger.info("▶ task: load_vehicles")
    
    # Si el lifespan ya cargó los vehículos, no repetir la llamada a Fulltrack
    vehicles = state_store.get_vehicles()
    if not vehicles:
        vehicles = await fleet_service.refresh_vehicles()
    
    if vehicles:
        logger.info("✓ %d vehículos en memoria", len(vehicles))
        for v in vehicles[:3]:
            logger.info("  → vehículo: %s", v)
        await _task_refresh_km()
        await _task_refresh_km_historico()
        # Cargar histórico de báscula del mes actual al arrancar
        await _task_sync_bascula_mes()
    else:
        logger.warning("No se obtuvieron vehículos de Fulltrack.")


async def _task_refresh_km_historico():
    """Actualiza km históricos de los últimos 3 meses. Se ejecuta una vez al día."""
    logger.info("▶ task: refresh_km_historico")
    try:
        await fleet_service.refresh_km_historico()
    except Exception as exc:
        logger.error("Error en task refresh_km_historico: %s", exc, exc_info=True)



# ─────────────────────────────────────────────────────────────────────────────
# INICIO / DETENCIÓN
# ─────────────────────────────────────────────────────────────────────────────

def start_scheduler():
    """Registra y arranca el scheduler. Llamar al startup de FastAPI."""

    scheduler.add_job(
        _task_refresh_fleet,
        trigger=IntervalTrigger(seconds=FLEET_POLL_INTERVAL),
        id="refresh_fleet",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        _task_refresh_km_historico,
        trigger=IntervalTrigger(hours=24),
        id="refresh_km_historico",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # ── Báscula: solo hoy cada 1 minuto ────────────────────────────────────
    scheduler.add_job(
        _task_sync_bascula_hoy,
        trigger=IntervalTrigger(minutes=1),
        id="sync_bascula_hoy",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler iniciado. Fleet cada %ds, KM cada %ds, Báscula hoy cada 60s",
        FLEET_POLL_INTERVAL, KM_POLL_INTERVAL,
    )

    # Cargar vehículos inmediatamente al arrancar
    asyncio.create_task(_task_load_vehicles())


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido.")