# src/services/db_service.py
import aiomysql
import json
from src.database.database import get_connection
import logging
from datetime import date

logger = logging.getLogger(__name__)

# ── Fuel records ──────────────────────────────────────────────────────────────

async def save_fuel_record(record: dict) -> None:
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO fuel_records
                    (id, vehicle_id, conductor, proveedor, tipo,
                     fecha, odometro_actual, liters, price_per_liter,
                     tanque_lleno, foto_ticket_url, created_at)
                VALUES
                    (%(id)s, %(vehicle_id)s, %(conductor)s, %(proveedor)s, %(tipo)s,
                     %(fecha)s, %(odometro_actual)s, %(liters)s, %(price_per_liter)s,
                     %(tanque_lleno)s, %(foto_ticket_url)s, %(created_at)s)
            """, record)
    finally:
        conn.close()

async def get_fuel_records_by_month(year: int, month: int) -> list[dict]:
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT * FROM fuel_records
                WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
                ORDER BY fecha ASC
            """, (year, month))
            rows = await cur.fetchall()
            # MySQL devuelve las columnas DECIMAL como Decimal, no float.
            # Se convierten aquí para que ningún cálculo aguas abajo truene
            # al mezclar Decimal con float (ej. litros * precio_por_litro).
            for r in rows:
                if r.get("liters") is not None:
                    r["liters"] = float(r["liters"])
                if r.get("price_per_liter") is not None:
                    r["price_per_liter"] = float(r["price_per_liter"])
                if r.get("odometro_actual") is not None:
                    r["odometro_actual"] = float(r["odometro_actual"])
            return rows
    finally:
        conn.close()

# ── Odómetro snapshots ─────────────────────────────────────────────────────────

async def save_odometer_snapshot(vehicle_id: str, km: float, tipo: str, year: int, month: int) -> None:
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO odometer_snapshots (vehicle_id, km, tipo, year, month, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW()) AS new_val
                ON DUPLICATE KEY UPDATE km = new_val.km, created_at = NOW()
            """, (vehicle_id, km, tipo, year, month))
    finally:
        conn.close()

async def get_odometer_snapshots(vehicle_id: str, year: int, month: int) -> dict:
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT tipo, km FROM odometer_snapshots
                WHERE vehicle_id = %s AND year = %s AND month = %s
            """, (vehicle_id, year, month))
            rows = await cur.fetchall()
            return {r["tipo"]: r["km"] for r in rows}
    finally:
        conn.close()


# ── Monthly fuel summary (top3 histórico) ─────────────────────────────────────

async def save_monthly_fuel_summary(year: int, month: int, data: list[dict]) -> None:
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO monthly_fuel_summary (year, month, data, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE data = VALUES(data), updated_at = NOW()
            """, (year, month, json.dumps(data, ensure_ascii=False)))
    finally:
        conn.close()


async def get_monthly_fuel_summary(year: int, month: int) -> list[dict]:
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT data FROM monthly_fuel_summary
                WHERE year = %s AND month = %s
            """, (year, month))
            row = await cur.fetchone()
            if row and row.get("data"):
                return json.loads(row["data"])
            return []
    finally:
        conn.close()


# ── Monthly KM (kilómetros por vehículo y mes desde Fulltrack) ────────────────

async def save_monthly_km(vehicle_id: str, year: int, month: int, km_total: float) -> None:
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO monthly_km (vehicle_id, year, month, km_total, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE km_total = VALUES(km_total), updated_at = NOW()
            """, (vehicle_id, year, month, round(km_total, 2)))
    finally:
        conn.close()


async def get_monthly_km(vehicle_id: str, year: int, month: int) -> float:
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT km_total FROM monthly_km
                WHERE vehicle_id = %s AND year = %s AND month = %s
            """, (vehicle_id, year, month))
            row = await cur.fetchone()
            return float(row["km_total"]) if row else 0.0
    finally:
        conn.close()


async def get_monthly_km_all_vehicles(year: int, month: int) -> list[dict]:
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT vehicle_id, km_total FROM monthly_km
                WHERE year = %s AND month = %s
                ORDER BY vehicle_id
            """, (year, month))
            rows = await cur.fetchall()
            return [{"vehicle_id": r["vehicle_id"], "km_total": float(r["km_total"])} for r in rows]
    finally:
        conn.close()


async def get_monthly_km_last_months(vehicle_id: str, n_months: int = 3) -> list[dict]:
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT year, month, km_total FROM monthly_km
                WHERE vehicle_id = %s
                ORDER BY year DESC, month DESC
                LIMIT %s
            """, (vehicle_id, n_months))
            rows = await cur.fetchall()
            return [{"year": r["year"], "month": r["month"], "km_total": float(r["km_total"])} for r in rows]
    finally:
        conn.close()


# ── KM por odómetro (inicio / fin de mes desde Fulltrack) ────────────────────

async def save_km_odometro_snapshot(
    vehicle_id: str,
    year: int,
    month: int,
    tipo: str,          # "inicio" | "fin"
    odometro_km: float,
) -> None:
    """
    Guarda el odómetro del día 1 (tipo='inicio') y el último día (tipo='fin')
    del mes para calcular KM totales como diferencia: fin - inicio.
    ON DUPLICATE KEY UPDATE para poder re-ejecutar sin duplicar.
    """
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO km_odometro_snapshots
                    (vehicle_id, year, month, tipo, odometro_km, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    odometro_km = VALUES(odometro_km),
                    updated_at  = NOW()
            """, (vehicle_id, year, month, tipo, round(odometro_km, 2)))
    finally:
        conn.close()


async def get_km_odometro_snapshots(vehicle_id: str, year: int, month: int) -> dict:
    """
    Retorna {"inicio": float|None, "fin": float|None} para un mes.
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT tipo, odometro_km FROM km_odometro_snapshots
                WHERE vehicle_id = %s AND year = %s AND month = %s
            """, (vehicle_id, year, month))
            rows = await cur.fetchall()
            result = {"inicio": None, "fin": None}
            for r in rows:
                result[r["tipo"]] = float(r["odometro_km"])
            return result
    finally:
        conn.close()


async def get_km_odometro_all_months(vehicle_id: str, months: list[tuple]) -> dict:
    """
    Trae de una vez todos los snapshots para una lista de (year, month).
    Retorna: { (year, month): {"inicio": float|None, "fin": float|None} }
    """
    if not months:
        return {}
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            placeholders = ",".join(["(%s,%s)"] * len(months))
            params = [vehicle_id]
            for y, m in months:
                params += [y, m]
            await cur.execute(f"""
                SELECT year, month, tipo, odometro_km FROM km_odometro_snapshots
                WHERE vehicle_id = %s
                  AND (year, month) IN ({placeholders})
            """, params)
            rows = await cur.fetchall()
            result: dict = {(y, m): {"inicio": None, "fin": None} for y, m in months}
            for r in rows:
                key = (int(r["year"]), int(r["month"]))
                if key in result:
                    result[key][r["tipo"]] = float(r["odometro_km"])
            return result
    finally:
        conn.close()


async def get_fuel_records_by_date(target_date: date) -> list[dict]:
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT id, vehicle_id, conductor, fecha, created_at
                FROM fuel_records
                WHERE DATE(fecha) = %s
                ORDER BY fecha DESC
            """, (target_date,))
            return await cur.fetchall()
    finally:
        conn.close()


# ── Báscula records ───────────────────────────────────────────────────────────

def _trunc(val, max_len: int) -> str:
    """Convierte a str y trunca al máximo permitido por la columna."""
    return str(val or "")[:max_len]


def _serialize_bascula_row(r: dict) -> dict:
    """
    Normaliza un row de bascula_records para serialización JSON.
    - fecha (date)     → str ISO "2026-05-15"
    - hora_* (timedelta que devuelve aiomysql para columnas TIME) → "HH:MM:SS"
    """
    import datetime as _dt
    row = dict(r)
    # fecha
    if isinstance(row.get("fecha"), _dt.date):
        row["fecha"] = row["fecha"].isoformat()
    # hora_entrada / hora_salida: aiomysql devuelve timedelta para columnas TIME
    for campo in ("hora_entrada", "hora_salida"):
        val = row.get(campo)
        if isinstance(val, _dt.timedelta):
            total = int(val.total_seconds())
            h, rem = divmod(total, 3600)
            m, s   = divmod(rem, 60)
            row[campo] = f"{h:02d}:{m:02d}:{s:02d}"
    return row


async def upsert_bascula_records(records: list[dict]) -> int:
    """
    Inserta o actualiza registros de báscula.
    Usa (folio, fecha) como PK natural.
    Retorna número de filas afectadas.
    """
    if not records:
        return 0
    conn = await get_connection()
    affected = 0
    try:
        async with conn.cursor() as cur:
            for r in records:
                await cur.execute("""
                    INSERT INTO bascula_records
                        (folio, placa, num_eco, fecha, hora_entrada, hora_salida,
                         peso_entrada, peso_salida, peso_neto,
                         tipo_cliente, tipo_residuo, fetched_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                        peso_entrada = VALUES(peso_entrada),
                        peso_salida  = VALUES(peso_salida),
                        peso_neto    = VALUES(peso_neto),
                        hora_entrada = VALUES(hora_entrada),
                        hora_salida  = VALUES(hora_salida),
                        fetched_at   = NOW()
                """, (
                    r.get("folio"),
                    _trunc(r.get("placa"),         50),
                    _trunc(r.get("num_eco"),        50),
                    r.get("fecha"),          # DATE ya parseado en bascula_routes
                    _trunc(r.get("hora_entrada"),   10),
                    _trunc(r.get("hora_salida"),    10),
                    r.get("peso_entrada", 0.0),
                    r.get("peso_salida",  0.0),
                    r.get("peso_neto",    0.0),
                    _trunc(r.get("tipo_cliente"),  150),
                    _trunc(r.get("tipo_residuo"),  150),
                ))
                affected += cur.rowcount
    finally:
        conn.close()
    return affected


async def get_bascula_records_by_date(target_date: date) -> list[dict]:
    """Registros de báscula de un día específico."""
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT * FROM bascula_records
                WHERE fecha = %s
                ORDER BY hora_entrada ASC
            """, (target_date,))
            rows = await cur.fetchall()
            return [_serialize_bascula_row(r) for r in rows]
    finally:
        conn.close()


async def get_bascula_records_by_range(date_from: date, date_to: date) -> list[dict]:
    """Registros de báscula para un rango (últimos 30 días, mes, etc.)."""
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT * FROM bascula_records
                WHERE fecha BETWEEN %s AND %s
                ORDER BY fecha ASC, hora_entrada ASC
            """, (date_from, date_to))
            rows = await cur.fetchall()
            return [_serialize_bascula_row(r) for r in rows]
    finally:
        conn.close()


async def get_bascula_daily_summary(date_from: date, date_to: date) -> list[dict]:
    """
    Resumen por día: total de toneladas y viajes.
    Útil para el gráfico de 'Tonelaje Diario — últimos 30 días'.
    Retorna: [{"fecha": "2026-05-14", "toneladas": 486.13, "viajes": 64}, ...]
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    fecha,
                    ROUND(SUM(peso_neto), 3)  AS toneladas,
                    COUNT(*)                   AS viajes
                FROM bascula_records
                WHERE fecha BETWEEN %s AND %s
                GROUP BY fecha
                ORDER BY fecha ASC
            """, (date_from, date_to))
            rows = await cur.fetchall()
            return [
                {
                    "fecha":     r["fecha"].isoformat() if hasattr(r["fecha"], "isoformat") else str(r["fecha"]),
                    "toneladas": float(r["toneladas"] or 0),
                    "viajes":    int(r["viajes"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


async def get_bascula_by_eco_today(target_date: date) -> list[dict]:
    """
    Toneladas y viajes por eco (unidad) en el día.
    Útil para el widget 'Estado de la Flota — cuánto ha cargado cada vehículo hoy'.
    Retorna: [{"num_eco": "TM-07", "toneladas": 38.4, "viajes": 5}, ...]
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    num_eco,
                    ROUND(SUM(peso_neto), 3) AS toneladas,
                    COUNT(*)                  AS viajes
                FROM bascula_records
                WHERE fecha = %s
                GROUP BY num_eco
                ORDER BY toneladas DESC
            """, (target_date,))
            rows = await cur.fetchall()
            return [
                {
                    "num_eco":   r["num_eco"],
                    "toneladas": float(r["toneladas"] or 0),
                    "viajes":    int(r["viajes"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


# ── Báscula: resumen mensual por unidad ──────────────────────────────────────

async def get_bascula_monthly_by_eco(year: int, month: int) -> list[dict]:
    """
    Toneladas, viajes y peso promedio por unidad en el mes.
    Retorna: [{"num_eco": "TM-07", "toneladas": 412.5, "viajes": 58,
               "promedio_ton_viaje": 7.11, "tipo_cliente": "MUNICIPIO"}, ...]
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    num_eco,
                    tipo_cliente,
                    ROUND(SUM(peso_neto), 3)           AS toneladas,
                    COUNT(*)                            AS viajes,
                    ROUND(AVG(peso_neto), 3)            AS promedio_ton_viaje
                FROM bascula_records
                WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
                  AND peso_neto > 0
                GROUP BY num_eco, tipo_cliente
                ORDER BY toneladas DESC
            """, (year, month))
            rows = await cur.fetchall()
            return [
                {
                    "num_eco":           r["num_eco"],
                    "tipo_cliente":      r["tipo_cliente"] or "",
                    "toneladas":         float(r["toneladas"] or 0),
                    "viajes":            int(r["viajes"] or 0),
                    "promedio_ton_viaje": float(r["promedio_ton_viaje"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


async def get_bascula_monthly_by_tipo_cliente(year: int, month: int) -> list[dict]:
    """
    Agrupación de toneladas e importe por tipo de cliente en el mes.
    Cubre: MUNICIPIO, PARTICULAR, DISPOSICION, etc.
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    tipo_cliente,
                    tipo_residuo,
                    ROUND(SUM(peso_neto), 3) AS toneladas,
                    COUNT(*)                  AS viajes
                FROM bascula_records
                WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
                  AND peso_neto > 0
                GROUP BY tipo_cliente, tipo_residuo
                ORDER BY toneladas DESC
            """, (year, month))
            rows = await cur.fetchall()
            return [
                {
                    "tipo_cliente": r["tipo_cliente"] or "SIN TIPO",
                    "tipo_residuo": r["tipo_residuo"] or "",
                    "toneladas":    float(r["toneladas"] or 0),
                    "viajes":       int(r["viajes"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


async def get_bascula_by_turno(year: int, month: int) -> list[dict]:
    """
    Resumen por basculista y turno — replica hoja 'ROSSY' del Excel.
    La tabla bascula_records no tiene columna turno, se calcula desde hora_entrada:
      06:00-13:59 → Matutino | 14:00-21:59 → Vespertino | resto → Nocturno
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    DATE(fecha) AS dia,
                    CASE
                        WHEN TIME(hora_entrada) >= '06:00:00' AND TIME(hora_entrada) < '14:00:00' THEN 'Matutino'
                        WHEN TIME(hora_entrada) >= '14:00:00' AND TIME(hora_entrada) < '22:00:00' THEN 'Vespertino'
                        ELSE 'Nocturno'
                    END AS turno,
                    tipo_cliente,
                    ROUND(SUM(peso_neto), 3) AS toneladas,
                    COUNT(*)                  AS viajes
                FROM bascula_records
                WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
                  AND peso_neto > 0
                GROUP BY dia, turno, tipo_cliente
                ORDER BY dia ASC, turno ASC
            """, (year, month))
            rows = await cur.fetchall()
            return [
                {
                    "dia":          r["dia"].isoformat() if hasattr(r["dia"], "isoformat") else str(r["dia"]),
                    "turno":        r["turno"],
                    "tipo_cliente": r["tipo_cliente"] or "",
                    "toneladas":    float(r["toneladas"] or 0),
                    "viajes":       int(r["viajes"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


async def get_bascula_daily_by_eco(year: int, month: int) -> list[dict]:
    """
    Toneladas diarias por unidad para el mes — base del gráfico de diesel diario
    cruzado con km. Retorna todos los días del mes con sus ecos.
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    DATE(fecha)              AS fecha,
                    num_eco,
                    ROUND(SUM(peso_neto),3)  AS toneladas,
                    COUNT(*)                  AS viajes
                FROM bascula_records
                WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
                  AND peso_neto > 0
                GROUP BY DATE(fecha), num_eco
                ORDER BY fecha ASC, num_eco ASC
            """, (year, month))
            rows = await cur.fetchall()
            return [
                {
                    "fecha":     r["fecha"].isoformat() if hasattr(r["fecha"], "isoformat") else str(r["fecha"]),
                    "num_eco":   r["num_eco"],
                    "toneladas": float(r["toneladas"] or 0),
                    "viajes":    int(r["viajes"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


# ── Métricas snapshot (histórico mensual) ────────────────────────────────────

async def save_metrics_snapshot(year: int, month: int, vehicle_id: str, metrics: dict) -> None:
    """
    Guarda el snapshot de métricas de un vehículo al cierre del mes.
    Permite recuperar datos de meses anteriores sin depender de Fulltrack.
    Tabla: metrics_snapshot (vehicle_id, year, month, data JSON)
    """
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO metrics_snapshot (vehicle_id, year, month, data, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE data = VALUES(data), updated_at = NOW()
            """, (vehicle_id, year, month, json.dumps(metrics, ensure_ascii=False, default=str)))
    finally:
        conn.close()


async def get_metrics_snapshot(year: int, month: int) -> list[dict]:
    """
    Recupera todos los snapshots de métricas del mes.
    Retorna lista de dicts con las métricas completas de cada vehículo.
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT vehicle_id, data FROM metrics_snapshot
                WHERE year = %s AND month = %s
            """, (year, month))
            rows = await cur.fetchall()
            result = []
            for r in rows:
                try:
                    m = json.loads(r["data"])
                    m["vehicle_id"] = r["vehicle_id"]
                    result.append(m)
                except Exception:
                    pass
            return result
    finally:
        conn.close()


async def ensure_metrics_snapshot_table() -> None:
    """Crea la tabla metrics_snapshot si no existe."""
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS metrics_snapshot (
                    vehicle_id  VARCHAR(50)  NOT NULL,
                    year        SMALLINT     NOT NULL,
                    month       TINYINT      NOT NULL,
                    data        MEDIUMTEXT   NOT NULL,
                    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (vehicle_id, year, month)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
    finally:
        conn.close()


# ── Diesel diario por unidad (desde fuel_records) ────────────────────────────

async def get_diesel_daily_by_vehicle(year: int, month: int) -> list[dict]:
    """
    Litros de diesel cargados por día por vehículo en el mes.
    Base para la hoja 'CONS. DIESEL Y RECORRIDO TOTAL' del Excel.
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    DATE(fecha)                     AS fecha,
                    vehicle_id,
                    ROUND(SUM(liters), 2)           AS litros,
                    ROUND(SUM(liters * price_per_liter), 2) AS importe
                FROM fuel_records
                WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
                GROUP BY DATE(fecha), vehicle_id
                ORDER BY fecha ASC, vehicle_id ASC
            """, (year, month))
            rows = await cur.fetchall()
            return [
                {
                    "fecha":     r["fecha"].isoformat() if hasattr(r["fecha"], "isoformat") else str(r["fecha"]),
                    "vehicle_id": str(r["vehicle_id"]),
                    "litros":    float(r["litros"] or 0),
                    "importe":   float(r["importe"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# ADICIONES A src/database/db_service.py
# Pega estas funciones al final del archivo existente.
# ─────────────────────────────────────────────────────────────────────────────

# ── Báscula: resumen mensual por unidad ──────────────────────────────────────

async def get_bascula_monthly_by_eco(year: int, month: int) -> list[dict]:
    """
    Toneladas, viajes y peso promedio por unidad en el mes.
    Retorna: [{"num_eco": "TM-07", "toneladas": 412.5, "viajes": 58,
               "promedio_ton_viaje": 7.11, "tipo_cliente": "MUNICIPIO"}, ...]
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    num_eco,
                    tipo_cliente,
                    ROUND(SUM(peso_neto), 3)           AS toneladas,
                    COUNT(*)                            AS viajes,
                    ROUND(AVG(peso_neto), 3)            AS promedio_ton_viaje
                FROM bascula_records
                WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
                  AND peso_neto > 0
                GROUP BY num_eco, tipo_cliente
                ORDER BY toneladas DESC
            """, (year, month))
            rows = await cur.fetchall()
            return [
                {
                    "num_eco":           r["num_eco"],
                    "tipo_cliente":      r["tipo_cliente"] or "",
                    "toneladas":         float(r["toneladas"] or 0),
                    "viajes":            int(r["viajes"] or 0),
                    "promedio_ton_viaje": float(r["promedio_ton_viaje"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


async def get_bascula_monthly_by_tipo_cliente(year: int, month: int) -> list[dict]:
    """
    Agrupación de toneladas e importe por tipo de cliente en el mes.
    Cubre: MUNICIPIO, PARTICULAR, DISPOSICION, etc.
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    tipo_cliente,
                    tipo_residuo,
                    ROUND(SUM(peso_neto), 3) AS toneladas,
                    COUNT(*)                  AS viajes
                FROM bascula_records
                WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
                  AND peso_neto > 0
                GROUP BY tipo_cliente, tipo_residuo
                ORDER BY toneladas DESC
            """, (year, month))
            rows = await cur.fetchall()
            return [
                {
                    "tipo_cliente": r["tipo_cliente"] or "SIN TIPO",
                    "tipo_residuo": r["tipo_residuo"] or "",
                    "toneladas":    float(r["toneladas"] or 0),
                    "viajes":       int(r["viajes"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


async def get_bascula_by_turno(year: int, month: int) -> list[dict]:
    """
    Resumen por basculista y turno — replica hoja 'ROSSY' del Excel.
    La tabla bascula_records no tiene columna turno, se calcula desde hora_entrada:
      06:00-13:59 → Matutino | 14:00-21:59 → Vespertino | resto → Nocturno
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    DATE(fecha) AS dia,
                    CASE
                        WHEN TIME(hora_entrada) >= '06:00:00' AND TIME(hora_entrada) < '14:00:00' THEN 'Matutino'
                        WHEN TIME(hora_entrada) >= '14:00:00' AND TIME(hora_entrada) < '22:00:00' THEN 'Vespertino'
                        ELSE 'Nocturno'
                    END AS turno,
                    tipo_cliente,
                    ROUND(SUM(peso_neto), 3) AS toneladas,
                    COUNT(*)                  AS viajes
                FROM bascula_records
                WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
                  AND peso_neto > 0
                GROUP BY dia, turno, tipo_cliente
                ORDER BY dia ASC, turno ASC
            """, (year, month))
            rows = await cur.fetchall()
            return [
                {
                    "dia":          r["dia"].isoformat() if hasattr(r["dia"], "isoformat") else str(r["dia"]),
                    "turno":        r["turno"],
                    "tipo_cliente": r["tipo_cliente"] or "",
                    "toneladas":    float(r["toneladas"] or 0),
                    "viajes":       int(r["viajes"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


async def get_bascula_daily_by_eco(year: int, month: int) -> list[dict]:
    """
    Toneladas diarias por unidad para el mes — base del gráfico de diesel diario
    cruzado con km. Retorna todos los días del mes con sus ecos.
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    DATE(fecha)              AS fecha,
                    num_eco,
                    ROUND(SUM(peso_neto),3)  AS toneladas,
                    COUNT(*)                  AS viajes
                FROM bascula_records
                WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
                  AND peso_neto > 0
                GROUP BY DATE(fecha), num_eco
                ORDER BY fecha ASC, num_eco ASC
            """, (year, month))
            rows = await cur.fetchall()
            return [
                {
                    "fecha":     r["fecha"].isoformat() if hasattr(r["fecha"], "isoformat") else str(r["fecha"]),
                    "num_eco":   r["num_eco"],
                    "toneladas": float(r["toneladas"] or 0),
                    "viajes":    int(r["viajes"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


# ── Métricas snapshot (histórico mensual) ────────────────────────────────────

async def save_metrics_snapshot(year: int, month: int, vehicle_id: str, metrics: dict) -> None:
    """
    Guarda el snapshot de métricas de un vehículo al cierre del mes.
    Permite recuperar datos de meses anteriores sin depender de Fulltrack.
    Tabla: metrics_snapshot (vehicle_id, year, month, data JSON)
    """
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO metrics_snapshot (vehicle_id, year, month, data, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE data = VALUES(data), updated_at = NOW()
            """, (vehicle_id, year, month, json.dumps(metrics, ensure_ascii=False, default=str)))
    finally:
        conn.close()


async def get_metrics_snapshot(year: int, month: int) -> list[dict]:
    """
    Recupera todos los snapshots de métricas del mes.
    Retorna lista de dicts con las métricas completas de cada vehículo.
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT vehicle_id, data FROM metrics_snapshot
                WHERE year = %s AND month = %s
            """, (year, month))
            rows = await cur.fetchall()
            result = []
            for r in rows:
                try:
                    m = json.loads(r["data"])
                    m["vehicle_id"] = r["vehicle_id"]
                    result.append(m)
                except Exception:
                    pass
            return result
    finally:
        conn.close()


async def ensure_metrics_snapshot_table() -> None:
    """Crea la tabla metrics_snapshot si no existe."""
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS metrics_snapshot (
                    vehicle_id  VARCHAR(50)  NOT NULL,
                    year        SMALLINT     NOT NULL,
                    month       TINYINT      NOT NULL,
                    data        MEDIUMTEXT   NOT NULL,
                    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (vehicle_id, year, month)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
    finally:
        conn.close()


# ── Diesel diario por unidad (desde fuel_records) ────────────────────────────

async def get_diesel_daily_by_vehicle(year: int, month: int) -> list[dict]:
    """
    Litros de diesel cargados por día por vehículo en el mes.
    Base para la hoja 'CONS. DIESEL Y RECORRIDO TOTAL' del Excel.
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    DATE(fecha)                     AS fecha,
                    vehicle_id,
                    ROUND(SUM(liters), 2)           AS litros,
                    ROUND(SUM(liters * price_per_liter), 2) AS importe
                FROM fuel_records
                WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
                GROUP BY DATE(fecha), vehicle_id
                ORDER BY fecha ASC, vehicle_id ASC
            """, (year, month))
            rows = await cur.fetchall()
            return [
                {
                    "fecha":     r["fecha"].isoformat() if hasattr(r["fecha"], "isoformat") else str(r["fecha"]),
                    "vehicle_id": str(r["vehicle_id"]),
                    "litros":    float(r["litros"] or 0),
                    "importe":   float(r["importe"] or 0),
                }
                for r in rows
            ]
    finally:
        conn.close()


# ── Báscula por rango de fechas ───────────────────────────────────────────────

async def get_bascula_records_by_range(date_from, date_to) -> list[dict]:
    """
    Registros individuales de báscula entre date_from y date_to inclusive.
    Retorna todos los campos incluyendo hora_entrada y hora_salida.
    """
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT
                    folio, placa, num_eco, fecha,
                    hora_entrada, hora_salida,
                    peso_entrada, peso_salida,
                    ROUND(peso_neto, 3) AS peso_neto,
                    tipo_cliente, tipo_residuo
                FROM bascula_records
                WHERE fecha BETWEEN %s AND %s
                  AND peso_neto > 0
                ORDER BY fecha ASC, hora_entrada ASC
            """, (date_from, date_to))
            rows = await cur.fetchall()
            result = []
            for r in rows:
                row = dict(r)
                if hasattr(row.get("fecha"), "isoformat"):
                    row["fecha"] = row["fecha"].isoformat()
                # hora_entrada / hora_salida pueden ser timedelta en aiomysql
                for hk in ("hora_entrada", "hora_salida"):
                    v = row.get(hk)
                    if v is None:
                        row[hk] = ""
                    elif hasattr(v, "strftime"):
                        row[hk] = v.strftime("%H:%M")
                    elif hasattr(v, "seconds"):   # timedelta
                        total = int(v.total_seconds())
                        row[hk] = f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
                    else:
                        row[hk] = str(v)[:5]
                row["peso_neto"] = float(row["peso_neto"] or 0)
                result.append(row)
            return result
    finally:
        conn.close()