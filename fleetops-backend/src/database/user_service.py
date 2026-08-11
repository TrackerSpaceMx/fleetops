# src/database/user_service.py
"""
Capa de datos para usuarios / autenticación.
Tabla `usuarios` en MySQL — separada de db_service.py para mantener
la lógica de auth aislada del resto del negocio.
"""
import uuid
import logging
from datetime import datetime

import aiomysql

from src.database.database import get_connection

logger = logging.getLogger(__name__)


async def ensure_users_table() -> None:
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id            VARCHAR(36)  PRIMARY KEY,
                    username      VARCHAR(64)  NOT NULL UNIQUE,
                    nombre        VARCHAR(120) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    rol           ENUM('admin','operador') NOT NULL DEFAULT 'operador',
                    activo        TINYINT(1)   NOT NULL DEFAULT 1,
                    created_at    DATETIME     NOT NULL,
                    last_login_at DATETIME     NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
    finally:
        conn.close()


async def count_users() -> int:
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM usuarios")
            (n,) = await cur.fetchone()
            return n
    finally:
        conn.close()


async def create_user(username: str, nombre: str, password_hash: str, rol: str = "operador") -> dict:
    conn = await get_connection()
    try:
        user_id = str(uuid.uuid4())
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO usuarios (id, username, nombre, password_hash, rol, activo, created_at)
                VALUES (%s, %s, %s, %s, %s, 1, %s)
            """, (user_id, username, nombre, password_hash, rol, datetime.utcnow()))
        return {"id": user_id, "username": username, "nombre": nombre, "rol": rol, "activo": True}
    finally:
        conn.close()


async def get_user_by_username(username: str) -> dict | None:
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM usuarios WHERE username = %s", (username,))
            return await cur.fetchone()
    finally:
        conn.close()


async def get_user_by_id(user_id: str) -> dict | None:
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
            return await cur.fetchone()
    finally:
        conn.close()


async def list_users() -> list[dict]:
    conn = await get_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT id, username, nombre, rol, activo, created_at, last_login_at
                FROM usuarios ORDER BY created_at ASC
            """)
            return await cur.fetchall()
    finally:
        conn.close()


async def touch_last_login(user_id: str) -> None:
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE usuarios SET last_login_at = %s WHERE id = %s",
                (datetime.utcnow(), user_id),
            )
    finally:
        conn.close()


async def set_user_active(user_id: str, activo: bool) -> None:
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE usuarios SET activo = %s WHERE id = %s",
                (1 if activo else 0, user_id),
            )
    finally:
        conn.close()


async def set_user_role(user_id: str, rol: str) -> None:
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE usuarios SET rol = %s WHERE id = %s",
                (rol, user_id),
            )
    finally:
        conn.close()


async def set_user_password(user_id: str, password_hash: str) -> None:
    conn = await get_connection()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE usuarios SET password_hash = %s WHERE id = %s",
                (password_hash, user_id),
            )
    finally:
        conn.close()
