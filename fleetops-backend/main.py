"""
main.py — Punto de entrada de la aplicación FleetOps Backend
"""
import logging
import sys
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.routes.pdf_routes import router as pdf_router

from src.config.settings import (
    HOST, PORT, FRONTEND_ORIGIN,
    DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_NOMBRE,
)
from src.routes.fleet_routes   import router as fleet_router
from src.routes.export_routes import router as export_router
from src.routes.fuel_routes    import router as fuel_router
from src.routes.report_routes  import router as report_router
from src.routes.bascula_routes import router as bascula_router
from src.routes.auth_routes    import router as auth_router
from src.routes.ws_routes      import router as ws_router
from src.websocket.scheduler   import start_scheduler, stop_scheduler
from src.websocket.ws_manager  import manager as ws_manager
from src.database              import db_service, user_service
from src.services               import state_store
from src.services.auth_service  import decode_access_token, hash_password

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

    # ── 0.b Verificar/crear tabla de usuarios + sembrar admin por defecto ──
    try:
        await user_service.ensure_users_table()
        if await user_service.count_users() == 0:
            await user_service.create_user(
                username=DEFAULT_ADMIN_USERNAME,
                nombre=DEFAULT_ADMIN_NOMBRE,
                password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
                rol="admin",
            )
            logger.warning(
                "⚠️  Usuario admin creado automáticamente → usuario: '%s' / contraseña: '%s'. "
                "¡Cámbiala en cuanto inicies sesión!",
                DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD,
            )
        logger.info("✅ Tabla usuarios verificada")
    except Exception as e:
        logger.error("❌ Error creando/sembrando tabla usuarios: %s", e)

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

# ─── Middleware de autenticación ──────────────────────────────────────────────
# Protege todas las rutas /api/* con un JWT válido, excepto /api/auth/login
# (para poder loguearse). Los canales WebSocket (/ws/*) no pasan por este
# middleware — ver nota de seguridad en el README.
_PUBLIC_API_PATHS = {"/api/auth/login"}


@app.middleware("http")
async def require_auth_for_api(request: Request, call_next):
    path = request.url.path
    if request.method != "OPTIONS" and path.startswith("/api/") and path not in _PUBLIC_API_PATHS:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return JSONResponse(status_code=401, content={"detail": "No autenticado"})
        token = auth_header.split(" ", 1)[1].strip()
        try:
            decode_access_token(token)
        except Exception:
            return JSONResponse(status_code=401, content={"detail": "Token inválido o expirado"})
    return await call_next(request)


app.include_router(ws_router)
app.include_router(export_router)
app.include_router(fleet_router)
app.include_router(fuel_router)
app.include_router(report_router)
app.include_router(bascula_router)
app.include_router(pdf_router)
app.include_router(auth_router)


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