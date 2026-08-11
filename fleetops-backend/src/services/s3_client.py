"""
s3_client.py — Cliente S3 para subir tickets de combustible
Coloca este archivo en: src/services/s3_client.py
"""
import logging
import uuid
from datetime import datetime

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from src.config.settings import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    AWS_S3_BUCKET,
)

logger = logging.getLogger(__name__)

# ─── Cliente singleton ────────────────────────────────────────────────────────

def _get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )


# ─── Upload ───────────────────────────────────────────────────────────────────

async def upload_ticket(
    file_bytes: bytes,
    original_filename: str,
    vehicle_id: str,
    content_type: str = "application/octet-stream",
) -> str:
    """
    Sube un ticket (imagen o PDF) a S3.

    Retorna la URL pública del objeto subido.
    Lanza RuntimeError si falla.

    Estructura de la key:
        tickets/{year}/{month}/{vehicle_id}/{uuid}_{filename}
    """
    now = datetime.utcnow()
    ext = _safe_extension(original_filename)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    s3_key = f"tickets/{now.year}/{now.month:02d}/{vehicle_id}/{unique_name}"

    if not AWS_S3_BUCKET or not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        logger.error("❌ S3: faltan variables de entorno (AWS_S3_BUCKET / AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)")
        raise RuntimeError(
            "El almacenamiento de fotos (AWS S3) no está configurado en el servidor. "
            "Agrega AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY y AWS_S3_BUCKET a tu .env, "
            "o registra la carga sin foto."
        )

    try:
        s3 = _get_s3_client()
        s3.put_object(
            Bucket=AWS_S3_BUCKET,
            Key=s3_key,
            Body=file_bytes,
            ContentType=content_type,
        )
        url = f"https://{AWS_S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
        logger.info("✅ Ticket subido a S3: %s", url)
        return url

    except NoCredentialsError:
        logger.error("❌ S3: credenciales no encontradas")
        raise RuntimeError("Credenciales AWS no configuradas")
    except ClientError as e:
        logger.error("❌ S3 ClientError: %s", e)
        raise RuntimeError(f"Error S3: {e.response['Error']['Message']}")
    except Exception as e:
        # Cubre errores no anticipados (ej. bucket con nombre inválido, región mal
        # configurada, etc.) para que el endpoint responda con un mensaje claro
        # en vez de un 500 genérico.
        logger.error("❌ Error inesperado subiendo a S3: %s", e)
        raise RuntimeError(f"No se pudo subir el archivo: {e}")


def _safe_extension(filename: str) -> str:
    """Extrae la extensión del archivo de forma segura."""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        # Solo extensiones permitidas
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
            return ext
    return ".bin"


def get_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    """
    Genera una URL firmada (presigned) para acceder temporalmente a un objeto S3.
    
    - s3_key: la key del objeto en S3 (e.g. "tickets/2026/05/TM-04/abc123.jpg")
    - expires_in: segundos hasta que expire (default: 1 hora)
    """
    try:
        s3 = _get_s3_client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": AWS_S3_BUCKET, "Key": s3_key},
            ExpiresIn=expires_in,
        )
        return url
    except (NoCredentialsError, ClientError) as e:
        logger.error("❌ Error generando presigned URL: %s", e)
        raise RuntimeError(f"No se pudo generar URL firmada: {e}")