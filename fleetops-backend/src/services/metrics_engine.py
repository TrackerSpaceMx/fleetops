"""
metrics_engine.py — Motor de cálculo con TODAS las reglas del Excel
Hojas implementadas:
  • Hoja 1  → Operatividad promedio por unidad (Ton, T.Prod, T.NoProd, Ton/T.Prod, km/prod, % Carga)
  • Hoja 2  → Kilómetros recorridos y rendimiento combustible (Prod/Trasl/Disp, km/lt)
  • Hoja 3  → Operatividad por ruta (agregado de unidades en misma ruta)
  • Hoja 4  → Costo y consumo de combustible por unidad (Lts Diesel, Importe)
  • Hoja 5  → Tonelaje por unidad y comparativo (Tons, Viajes, Ton/Viaje)
  • Portada → Resumen ejecutivo (Tons mes, Promedio hrs, Promedio km, Consumo total)
"""
from datetime import datetime, date
import math
import calendar
import logging

from src.config.settings import (
    KM_PROD_FACTOR, KM_TRASL_FACTOR, KM_DISP_FACTOR,
    HOURS_PROD_FACTOR, HOURS_NOPROD_FACTOR,
    RENDIMIENTO_HISTORICO, RENDIMIENTO_DEFAULT,
    TONS_POR_VIAJE_PROMEDIO,
    DIESEL_PRICE_PER_LITER, DIESEL_PRICE_HISTORICO,
    RENDIMIENTO_ALERTA_BAJO, RENDIMIENTO_ALERTA_MEDIO,
    HORAS_MINIMAS_DIARIAS,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _mes_nombre(mes: int) -> str:
    nombres = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
    }
    return nombres.get(mes, "desconocido")


def _dias_habiles_mes(year: int, month: int) -> int:
    """Aproximación: días del mes menos domingos."""
    _, days_in_month = calendar.monthrange(year, month)
    first_weekday = calendar.weekday(year, month, 1)
    sundays = sum(
        1 for d in range(1, days_in_month + 1)
        if calendar.weekday(year, month, d) == 6
    )
    return days_in_month - sundays


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    numerator = float(numerator or 0)
    denominator = float(denominator or 0)
    if denominator == 0:
        return default
    return round(numerator / denominator, 6)


def _rendimiento_del_mes(month: int) -> float:
    nombre = _mes_nombre(month)
    return RENDIMIENTO_HISTORICO.get(nombre, RENDIMIENTO_DEFAULT)


def _precio_diesel_del_mes(month: int) -> float:
    nombre = _mes_nombre(month)
    return DIESEL_PRICE_HISTORICO.get(nombre, DIESEL_PRICE_PER_LITER)


# ─────────────────────────────────────────────────────────────────────────────
# HOJA 1 — Operatividad promedio por unidad
# ─────────────────────────────────────────────────────────────────────────────

def calcular_hoja1(
    eco: str,
    toneladas: float,
    horas_operativas: float,
    km_productivos: float,
    dias_operativos: int = 0,
    year: int | None = None,
    month: int | None = None,
) -> dict:
    """
    Réplica exacta de Hoja1 del Excel.
    Entradas:
        eco              → No. Económico (e.g. "TM-04")
        toneladas        → Toneladas recolectadas en el período
        horas_operativas → Horas totales de operación
        km_productivos   → Kilómetros en ruta productiva
        dias_operativos  → Días con operación registrada
    """
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month
    if dias_operativos <= 0:
        dias_operativos = max(1, _dias_habiles_mes(year, month))

    # Tiempos (basados en proporciones históricas del Excel)
    t_prod   = round(horas_operativas * HOURS_PROD_FACTOR, 2)
    t_noprod = round(horas_operativas * HOURS_NOPROD_FACTOR, 2)

    # Promedio diario de toneladas
    tons_promedio_dia = _safe_div(toneladas, dias_operativos)

    # Ton / T.Prod  (productividad por hora productiva)
    ton_por_t_prod = _safe_div(toneladas, t_prod)

    # km productivos no prod (km traslado estimado)
    km_no_prod = round(km_productivos * (KM_NOPROD := KM_TRASL_FACTOR / KM_PROD_FACTOR), 2)

    # Ton/km.Prod
    ton_por_km_prod = _safe_div(toneladas, km_productivos)

    # % de carga (viajes productivos sobre total estimado)
    # En el Excel: % Carga = T.Prod / (T.Prod + T.NoProd) * 100
    pct_carga = round(_safe_div(t_prod, horas_operativas) * 100, 2)

    return {
        "eco":               eco,
        "toneladas":         round(toneladas, 3),
        "t_prod_hrs":        t_prod,
        "t_no_prod_hrs":     t_noprod,
        "ton_por_t_prod":    round(ton_por_t_prod, 6),
        "km_prod":           round(km_productivos, 2),
        "km_no_prod":        round(km_no_prod, 2),
        "ton_por_km_prod":   round(ton_por_km_prod, 6),
        "pct_carga":         pct_carga,
        "dias_operativos":   dias_operativos,
        "tons_promedio_dia": round(tons_promedio_dia, 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# HOJA 2 — Kilómetros recorridos y rendimiento combustible
# ─────────────────────────────────────────────────────────────────────────────

def calcular_hoja2(
    eco: str,
    km_total: float,
    litros_consumidos: float,
    month: int | None = None,
) -> dict:
    """
    Réplica de Hoja2 del Excel.
    Distribuye km en Prod / Traslado / Disposición y calcula km/lt.
    """
    if month is None:
        month = date.today().month

    km_prod  = round(km_total * KM_PROD_FACTOR, 2)
    km_trasl = round(km_total * KM_TRASL_FACTOR, 2)
    km_disp  = round(km_total * KM_DISP_FACTOR, 2)

    # Si no hay litros, usar rendimiento histórico para estimación
    if litros_consumidos <= 0:
        rendimiento = _rendimiento_del_mes(month)
        litros_consumidos = round(_safe_div(km_total, rendimiento), 2)
    else:
        rendimiento = _safe_div(km_total, litros_consumidos)

    # Alertas de rendimiento
    if rendimiento == 0:
        alerta_rendimiento = "sin_datos"
    elif rendimiento < RENDIMIENTO_ALERTA_BAJO:
        alerta_rendimiento = "critico"
    elif rendimiento < RENDIMIENTO_ALERTA_MEDIO:
        alerta_rendimiento = "bajo"
    else:
        alerta_rendimiento = "normal"

    return {
        "eco":                eco,
        "km_prod":            km_prod,
        "km_trasl":           km_trasl,
        "km_disp":            km_disp,
        "km_total":           round(km_total, 2),
        "litros":             round(litros_consumidos, 2),
        "km_por_litro":       round(rendimiento, 6),
        "alerta_rendimiento": alerta_rendimiento,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HOJA 3 — Operatividad por ruta
# ─────────────────────────────────────────────────────────────────────────────

def calcular_hoja3(ruta_numero: int, unidades: list[dict]) -> dict:
    """
    Agrega las métricas de las unidades que comparten una ruta.
    `unidades` es una lista de dicts con campos de Hoja1 + Hoja2.
    """
    if not unidades:
        return {"ruta": f"Ruta No. {ruta_numero}", "unidades": []}

    total_tons       = sum(u.get("toneladas", 0) for u in unidades)
    total_t_prod     = sum(u.get("t_prod_hrs", 0) for u in unidades)
    total_t_trasl    = sum(u.get("t_no_prod_hrs", 0) * KM_TRASL_FACTOR for u in unidades)
    total_t_disp     = sum(u.get("t_no_prod_hrs", 0) * KM_DISP_FACTOR for u in unidades)
    total_hrs        = total_t_prod + total_t_trasl + total_t_disp
    total_km_prod    = sum(u.get("km_prod", 0) for u in unidades)
    total_km_trasl   = sum(u.get("km_trasl", 0) for u in unidades)
    total_km_disp    = sum(u.get("km_disp", 0) for u in unidades)
    total_km         = total_km_prod + total_km_trasl + total_km_disp

    return {
        "ruta":         f"Ruta No. {ruta_numero}",
        "toneladas":    round(total_tons, 2),
        "t_prod_hrs":   round(total_t_prod, 2),
        "t_trasl_hrs":  round(total_t_trasl, 2),
        "t_disp_hrs":   round(total_t_disp, 2),
        "total_hrs":    round(total_hrs, 2),
        "km_prod":      round(total_km_prod, 2),
        "km_trasl":     round(total_km_trasl, 2),
        "km_disp":      round(total_km_disp, 2),
        "total_km":     round(total_km, 2),
        "unidades_eco": [u.get("eco") for u in unidades],
    }


# ─────────────────────────────────────────────────────────────────────────────
# HOJA 4 — Costo y consumo de combustible por unidad
# ─────────────────────────────────────────────────────────────────────────────

def calcular_hoja4(
    eco: str,
    litros_diesel: float,
    litros_gasolina: float = 0.0,
    month: int | None = None,
    precio_diesel_override: float | None = None,
    precio_gasolina_override: float | None = None,
) -> dict:
    """
    Réplica de Hoja4 del Excel.
    Calcula importe diesel, gasolina y total por unidad.
    """
    if month is None:
        month = date.today().month

    precio_diesel   = precio_diesel_override   or _precio_diesel_del_mes(month)
    precio_gasolina = precio_gasolina_override or precio_diesel  # misma referencia si no se especifica

    importe_diesel   = round(litros_diesel * precio_diesel, 4)
    importe_gasolina = round(litros_gasolina * precio_gasolina, 4)
    total_lts        = round(litros_diesel + litros_gasolina, 2)
    total_importe    = round(importe_diesel + importe_gasolina, 4)

    return {
        "eco":              eco,
        "diesel_lts":       round(litros_diesel, 2),
        "diesel_importe":   importe_diesel,
        "gasolina_lts":     round(litros_gasolina, 2),
        "gasolina_importe": importe_gasolina,
        "total_lts":        total_lts,
        "total_importe":    total_importe,
        "precio_diesel":    precio_diesel,
        "precio_gasolina":  precio_gasolina,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HOJA 5 — Tonelaje por unidad y comparativo
# ─────────────────────────────────────────────────────────────────────────────

def calcular_hoja5(
    eco: str,
    toneladas: float,
    num_viajes: int | None = None,
    tons_ticket: float | None = None,
) -> dict:
    """
    Réplica de Hoja5 del Excel.
    Calcula promedio de toneladas por viaje y variación Hoja Conductor vs Ticket.
    """
    if num_viajes is None or num_viajes <= 0:
        # Estimar viajes con promedio histórico
        num_viajes = max(1, round(toneladas / TONS_POR_VIAJE_PROMEDIO))

    tons_prom_por_viaje = _safe_div(toneladas, num_viajes)

    # Comparativo con ticket de báscula (si viene del sistema externo)
    variacion_importe = 0.0
    variacion_pct     = 0.0
    if tons_ticket is not None and tons_ticket > 0:
        variacion_importe = round(tons_ticket - toneladas, 3)
        variacion_pct     = round(_safe_div(variacion_importe, tons_ticket) * 100, 2)

    return {
        "eco":                  eco,
        "toneladas":            round(toneladas, 3),
        "num_viajes":           num_viajes,
        "tons_prom_por_viaje":  round(tons_prom_por_viaje, 6),
        "tons_ticket":          round(tons_ticket, 3) if tons_ticket else None,
        "variacion_importe":    variacion_importe,
        "variacion_pct":        variacion_pct,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PORTADA — Resumen ejecutivo mensual
# ─────────────────────────────────────────────────────────────────────────────

def calcular_portada(
    all_unit_metrics: list[dict],
    year: int | None = None,
    month: int | None = None,
) -> dict:
    """
    Replica la Portada del Excel.
    `all_unit_metrics` es una lista de dicts con campos combinados de todas las hojas.
    """
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month

    mes_nombre = _mes_nombre(month)

    total_toneladas     = sum(m.get("toneladas", 0) for m in all_unit_metrics)
    total_litros        = sum(m.get("total_lts", 0) for m in all_unit_metrics)
    total_km            = sum(m.get("km_total", 0) for m in all_unit_metrics)
    total_hrs           = sum(m.get("t_prod_hrs", 0) + m.get("t_no_prod_hrs", 0) for m in all_unit_metrics)
    total_importe_comb  = sum(m.get("total_importe", 0) for m in all_unit_metrics)

    n = len([m for m in all_unit_metrics if m.get("toneladas", 0) > 0])
    n = max(n, 1)

    promedio_hrs_ruta = round(_safe_div(total_hrs, n), 6)
    promedio_km_ruta  = round(_safe_div(total_km, n), 6)

    # Distribución turno (basada en Portada del Excel: 0.33 mat / 0.67 ves o viceversa)
    # En octubre/nov era 0.39 mat / 0.61 ves; en diciembre 0.33 mat / 0.67 ves
    turno_matutino_pct  = 0.33
    turno_vespertino_pct = 0.67

    return {
        "periodo":              f"{mes_nombre.capitalize()} {year}",
        "year":                 year,
        "month":                month,
        "toneladas_mes":        round(total_toneladas, 2),
        "promedio_hrs_rutas":   promedio_hrs_ruta,
        "promedio_km_rutas":    promedio_km_ruta,
        "consumo_combustible_lts":    round(total_litros, 2),
        "consumo_combustible_importe": round(total_importe_comb, 2),
        "personal_operativo":   159,
        "turno_matutino_pct":   turno_matutino_pct,
        "turno_vespertino_pct": turno_vespertino_pct,
        "unidades_activas":     n,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR PRINCIPAL — genera todas las métricas de una unidad de una vez
# ─────────────────────────────────────────────────────────────────────────────

def calcular_metricas_unidad(
    eco: str,
    km_total: float,
    horas_operativas: float,
    toneladas: float,
    litros_cargados: float,
    precio_litro: float | None = None,
    litros_gasolina: float = 0.0,
    num_viajes: int | None = None,
    tons_ticket: float | None = None,
    dias_operativos: int = 0,
    year: int | None = None,
    month: int | None = None,
) -> dict:
    """
    Punto de entrada único: calcula Hoja1+2+4+5 para una sola unidad.
    Retorna un dict plano con todos los campos listos para emitir por WS.
    """
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month

    km_prod = km_total * KM_PROD_FACTOR

    h1 = calcular_hoja1(eco, toneladas, horas_operativas, km_prod, dias_operativos, year, month)
    h2 = calcular_hoja2(eco, km_total, litros_cargados, month)
    h4 = calcular_hoja4(
        eco,
        litros_diesel=h2["litros"],
        litros_gasolina=litros_gasolina,
        month=month,
        precio_diesel_override=precio_litro,
    )
    h5 = calcular_hoja5(eco, toneladas, num_viajes, tons_ticket)

    return {
        "eco": eco,
        # Hoja 1
        "toneladas":          h1["toneladas"],
        "t_prod_hrs":         h1["t_prod_hrs"],
        "t_no_prod_hrs":      h1["t_no_prod_hrs"],
        "ton_por_t_prod":     h1["ton_por_t_prod"],
        "km_prod":            h1["km_prod"],
        "km_no_prod":         h1["km_no_prod"],
        "ton_por_km_prod":    h1["ton_por_km_prod"],
        "pct_carga":          h1["pct_carga"],
        # Hoja 2
        "km_total":           h2["km_total"],
        "km_trasl":           h2["km_trasl"],
        "km_disp":            h2["km_disp"],
        "km_por_litro":       h2["km_por_litro"],
        "alerta_rendimiento": h2["alerta_rendimiento"],
        # Hoja 4
        "diesel_lts":         h4["diesel_lts"],
        "diesel_importe":     h4["diesel_importe"],
        "gasolina_lts":       h4["gasolina_lts"],
        "total_lts":          h4["total_lts"],
        "total_importe":      h4["total_importe"],
        "precio_diesel":      h4["precio_diesel"],
        # Hoja 5
        "num_viajes":         h5["num_viajes"],
        "tons_prom_por_viaje": h5["tons_prom_por_viaje"],
        "tons_ticket":        h5["tons_ticket"],
        "variacion_pct":      h5["variacion_pct"],
        # Meta
        "year":               year,
        "month":              month,
        "periodo":            f"{_mes_nombre(month).capitalize()} {year}",
    }