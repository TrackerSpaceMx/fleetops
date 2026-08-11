"""
config.py — Configuración central leída desde .env
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Fulltrack ────────────────────────────────────────────────────────────────
FULLTRACK_BASE_URL   = os.getenv("FULLTRACK_BASE_URL", "https://ws.fulltrack2.com")
FULLTRACK_APIKEY     = os.getenv("FULLTRACK_APIKEY", "")
FULLTRACK_SECRETKEY  = os.getenv("FULLTRACK_SECRETKEY", "")

# ── Server ───────────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ── Polling intervals (segundos) ─────────────────────────────────────────────
FLEET_POLL_INTERVAL = int(os.getenv("FLEET_POLL_INTERVAL", "30"))
KM_POLL_INTERVAL    = int(os.getenv("KM_POLL_INTERVAL", "300"))

# ── Combustible ──────────────────────────────────────────────────────────────
DIESEL_PRICE_PER_LITER = float(os.getenv("DIESEL_PRICE_PER_LITER", "23.62"))

# ── CORS ─────────────────────────────────────────────────────────────────────
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

# ──────────────────────────────────────────────────────────────────────────────
# REGLAS OPERATIVAS — extraídas del Excel REPORTE_TIPO_TECMED_VERSION_FINAL
# ──────────────────────────────────────────────────────────────────────────────

# Distribución de km por tipo (basada en Hoja2)
#   km_prod   ≈ 33 % del km total  → factor Producción
#   km_trasl  ≈ 47 % del km total  → factor Traslado
#   km_disp   ≈ 20 % del km total  → factor Disposición
KM_PROD_FACTOR  = 0.33
KM_TRASL_FACTOR = 0.47
KM_DISP_FACTOR  = 0.20

# Distribución de horas operativas (Hoja1)
#   t_prod   ≈ 58 % del total     (Tiempo Productivo)
#   t_noprod ≈ 42 % del total     (Tiempo No Productivo / traslado+disp)
HOURS_PROD_FACTOR   = 0.58
HOURS_NOPROD_FACTOR = 0.42

# Rendimiento combustible promedio histórico (km/lt) por mes — Hoja2
RENDIMIENTO_HISTORICO = {
    "octubre":   1.580,
    "noviembre": 1.680,
    "diciembre": 1.800,
}
RENDIMIENTO_DEFAULT = 1.65   # fallback si no hay mes reconocido

# Toneladas promedio por viaje (Hoja1 / Hoja5) ─ usado para estimar si
# los datos GPS no tienen bàscula disponible
TONS_POR_VIAJE_PROMEDIO = 5.85

# Precio diesel por periodo (Hoja4) — MXN / litro
DIESEL_PRICE_HISTORICO = {
    "octubre":   23.62,
    "noviembre": 23.62,
    "diciembre": 23.62,
}

# Umbrales de alerta de rendimiento (km/lt)
RENDIMIENTO_ALERTA_BAJO  = 1.30   # por debajo → alerta roja
RENDIMIENTO_ALERTA_MEDIO = 1.50   # por debajo → alerta amarilla

# Umbral de horas operativas mínimas diarias por unidad
HORAS_MINIMAS_DIARIAS = 6.0

# Personal operativo (de Portada del Excel)
PERSONAL_OPERATIVO = 159

# Unidades municipales conocidas (Num. Eco.) que van al relleno DOMICILIARIO
UNIDADES_MUNICIPALES_PREFIX = ("TM-", "DOM")

# Turnos operativos
TURNOS = {
    "matutino":  {"inicio": "06:00", "fin": "14:00"},
    "vespertino": {"inicio": "14:00", "fin": "22:00"},
    "nocturno":  {"inicio": "22:00", "fin": "06:00"},
}

AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")
AWS_S3_BUCKET         = os.getenv("AWS_S3_BUCKET", "")


# ── Agregar estas líneas a tu src/config/settings.py existente ───────────────
# (no reemplaces el archivo completo, solo añade estas variables)

# Báscula externa (pagaenlinea.com.mx)
BASCULA_BASE_URL   = os.getenv("BASCULA_BASE_URL",   "https://pagaenlinea.com.mx/api/OtrasFunciones")
BASCULA_EMPRESA_ID = os.getenv("BASCULA_EMPRESA_ID", "27062")
BASCULA_SITIO_ID   = os.getenv("BASCULA_SITIO_ID",   "148")