"""
bascula_client.py — Cliente HTTP para la API externa de báscula (pagaenlinea.com.mx)

URL patrón:
  GET https://pagaenlinea.com.mx/api/OtrasFunciones/{empresa_id};{sitio_id};{YYYYMMDD};{YYYYMMDD}

Retorna un string JSON (a veces mal formado — array sin comas entre objetos).
"""
import httpx
import json
import logging
import re
from datetime import date

from src.config.settings import (
    BASCULA_BASE_URL,      # "https://pagaenlinea.com.mx/api/OtrasFunciones"
    BASCULA_EMPRESA_ID,    # "27062"
    BASCULA_SITIO_ID,      # "148"
)

logger = logging.getLogger(__name__)

_TIMEOUT = 15


def _fmt_date(d: date) -> str:
    """20260514"""
    return d.strftime("%Y%m%d")


def _parse_response(raw: str) -> list[dict]:
    """
    La API devuelve un string JSON con doble encoding:
      El body es un string que contiene otro JSON array.
      Ej: "[{\"folio\":1,...},{\"folio\":2,...}]"

    Pasos:
      1. Primer json.loads → puede quedar str (double-encoded) o list/dict directamente
      2. Si quedó str, segundo json.loads
      3. Si el JSON está mal formado (objetos sin coma entre ellos), lo reparamos
    """
    if not raw:
        return []
    text = raw.strip()

    def _to_list(data) -> list[dict]:
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict):
            return [data]
        return []

    # Primer intento: parsear directamente
    try:
        data = json.loads(text)
        # Double-encoded: el resultado es otro string
        if isinstance(data, str):
            inner = data.strip()
            try:
                data2 = json.loads(inner)
                result = _to_list(data2)
                if result:
                    return result
            except json.JSONDecodeError:
                # Intentar reparar el inner string
                text = inner  # continuar con el inner para el fix de }{
        else:
            result = _to_list(data)
            if result:
                return result
    except json.JSONDecodeError:
        pass

    # Segundo intento: reparar objetos contiguos sin coma }{  →  },{
    fixed = re.sub(r"\}\s*\{", "},{", text)
    if not fixed.startswith("["):
        fixed = "[" + fixed + "]"
    try:
        data = json.loads(fixed)
        return _to_list(data)
    except json.JSONDecodeError as e:
        logger.error("No se pudo parsear respuesta de báscula: %s | raw=%s", e, text[:300])
        return []


async def get_records(date_from: date, date_to: date) -> list[dict]:
    """
    Trae registros de pesaje para el rango de fechas dado.
    Retorna lista de dicts con los campos del registro.
    """
    url = (
        f"{BASCULA_BASE_URL.rstrip('/')}"
        f"/{BASCULA_EMPRESA_ID};{BASCULA_SITIO_ID}"
        f";{_fmt_date(date_from)};{_fmt_date(date_to)}"
    )
    logger.debug("GET báscula: %s", url)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return _parse_response(resp.text)


async def get_records_today() -> list[dict]:
    today = date.today()
    return await get_records(today, today)


async def get_records_last_30_days() -> list[dict]:
    from datetime import timedelta
    today = date.today()
    return await get_records(today - timedelta(days=29), today)
