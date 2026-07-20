"""
main.py — Punto de entrada de la aplicación FleetOps Backend
"""
import logging
import sys
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routes.pdf_routes import router as pdf_router

from src.config.settings import HOST, PORT, FRONTEND_ORIGIN
from src.routes.fleet_routes   import router as fleet_router
from src.routes.export_routes import router as export_router
from src.routes.fuel_routes    import router as fuel_router
from src.routes.report_routes  import router as report_router
from src.routes.bascula_routes import router as bascula_router
from src.routes.ws_routes      import router as ws_router
from src.websocket.scheduler   import start_scheduler, stop_scheduler
from src.websocket.ws_manager  import manager as ws_manager
from src.database              import db_service
from src.services              import state_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("fleetops")


# ─── Lifespan (UN SOLO lifespan) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 FleetOps Backend iniciando...")

    # ── 0. Verificar/crear tablas nuevas ──────────────────────────────────
    try:
        await db_service.ensure_metrics_snapshot_table()
        logger.info("✅ Tabla metrics_snapshot verificada")
    except Exception as e:
        logger.error("❌ Error creando metrics_snapshot: %s", e)

    # ── 1. Cargar fuel_records del mes actual desde MySQL ─────────────────
    today = date.today()
    try:
        records = await db_service.get_fuel_records_by_month(today.year, today.month)
        for r in records:
            r = dict(r)
            if hasattr(r.get("fecha"), "isoformat"):
                r["fecha"] = r["fecha"].isoformat()
            if hasattr(r.get("created_at"), "isoformat"):
                r["created_at"] = r["created_at"].isoformat()
            state_store._state["fuel_records"].append(r)
        logger.info("✅ %d fuel records cargados desde MySQL", len(records))
    except Exception as e:
        logger.error("❌ Error cargando fuel records desde MySQL: %s", e)

    # ── 2. Cargar km mensuales desde MySQL ANTES de refrescar de Fulltrack
    try:
        km_rows = await db_service.get_monthly_km_all_vehicles(today.year, today.month)
        for row in km_rows:
            await state_store.set_km_month(row["vehicle_id"], row["km_total"])
        logger.info("✅ %d registros de km mensual cargados desde MySQL", len(km_rows))
    except Exception as e:
        logger.error("❌ Error cargando km mensuales desde MySQL: %s", e)

    # ── 3. Cargar vehículos, refrescar de Fulltrack y calcular métricas
    try:
        from src.services import fleet_service
        from src.websocket.scheduler import _task_refresh_km
        vehicles = await fleet_service.refresh_vehicles()
        if vehicles:
            await fleet_service.refresh_fleet_status()
            await _task_refresh_km()                       # sobreescribe con datos frescos
            await fleet_service.recalculate_all_metrics()
    except Exception as e:
        logger.error("❌ Error cargando estado inicial de flota: %s", e)

    # ── 3. Arrancar scheduler ─────────────────────────────────────────────
    start_scheduler()
    yield
    logger.info("🛑 FleetOps Backend deteniendo...")
    stop_scheduler()

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="FleetOps API — Tersa Mundi",
    description=(
        "Backend en tiempo real para el dashboard de gestión de flota.\n\n"
        "Integra datos GPS de Fulltrack, reglas operativas del Excel TECMED "
        "y expone todo por WebSocket + REST."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(export_router)
app.include_router(fleet_router)
app.include_router(fuel_router)
app.include_router(report_router)
app.include_router(bascula_router)
app.include_router(pdf_router)


@app.get("/health", tags=["Sistema"])
async def health():
    from src.services.state_store import get_vehicles, get_active_vehicles_count
    return {
        "status":          "ok",
        "vehicles_loaded": len(get_vehicles()),
        "active_units":    get_active_vehicles_count(),
        "ws_connections":  ws_manager.stats(),
    }


@app.get("/", tags=["Sistema"])
async def root():
    return {
        "app":     "FleetOps API — Tersa Mundi",
        "version": "1.0.0",
        "docs":    "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True, log_level="info")