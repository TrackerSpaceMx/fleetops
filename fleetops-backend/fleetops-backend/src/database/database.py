# src/config/database.py
import aiomysql
import os

async def get_connection():
    return await aiomysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASS", "12345678"),
        db=os.getenv("DB_NAME", "fleetops"),
        autocommit=True,
    )