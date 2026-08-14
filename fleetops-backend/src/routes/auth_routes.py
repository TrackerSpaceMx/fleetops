# src/routes/auth_routes.py
"""
Autenticación y gestión de usuarios (MySQL).

- POST /api/auth/login              → username + password → JWT
- GET  /api/auth/me                 → info del usuario autenticado
- POST /api/auth/change-password    → el propio usuario cambia su contraseña
- GET  /api/auth/users              → (admin) listar usuarios
- POST /api/auth/users              → (admin) crear usuario
- PATCH /api/auth/users/{id}/estado → (admin) activar / desactivar
- PATCH /api/auth/users/{id}/rol    → (admin) cambiar rol
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.database import user_service
from src.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_admin,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Autenticación"])

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.]{3,64}$")


# ── Schemas ──────────────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    username: str
    password: str


class CreateUserBody(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    nombre: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    rol: str = "operador"


class ChangePasswordBody(BaseModel):
    password_actual: str
    password_nueva: str = Field(min_length=8, max_length=128)


class SetRolBody(BaseModel):
    rol: str


class UpdateUserBody(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    username: str | None = Field(default=None, min_length=3, max_length=64)


class AdminSetPasswordBody(BaseModel):
    password_nueva: str = Field(min_length=8, max_length=128)


# ── Endpoints públicos ────────────────────────────────────────────────────────

@router.post("/login")
async def login(body: LoginBody):
    user = await user_service.get_user_by_username(body.username.strip())
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos")
    if not user["activo"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Este usuario está desactivado")

    token = create_access_token(user)
    await user_service.touch_last_login(user["id"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "nombre": user["nombre"],
            "rol": user["rol"],
        },
    }


@router.get("/me")
async def me(current=Depends(get_current_user)):
    return current


@router.post("/change-password")
async def change_password(body: ChangePasswordBody, current=Depends(get_current_user)):
    user = await user_service.get_user_by_id(current["id"])
    if not user or not verify_password(body.password_actual, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña actual incorrecta")
    await user_service.set_user_password(current["id"], hash_password(body.password_nueva))
    return {"ok": True}


# ── Gestión de usuarios (solo admin) ──────────────────────────────────────────

@router.get("/users")
async def list_users(_admin=Depends(require_admin)):
    users = await user_service.list_users()
    for u in users:
        if hasattr(u.get("created_at"), "isoformat"):
            u["created_at"] = u["created_at"].isoformat()
        if hasattr(u.get("last_login_at"), "isoformat"):
            u["last_login_at"] = u["last_login_at"].isoformat()
    return {"usuarios": users}


@router.post("/users")
async def create_user(body: CreateUserBody, _admin=Depends(require_admin)):
    if not USERNAME_RE.match(body.username):
        raise HTTPException(status_code=400, detail="Usuario inválido: usa solo letras, números, '.' o '_' (3-64 caracteres)")
    if body.rol not in ("admin", "operador"):
        raise HTTPException(status_code=400, detail="Rol inválido, usa 'admin' u 'operador'")

    existing = await user_service.get_user_by_username(body.username.strip())
    if existing:
        raise HTTPException(status_code=409, detail="Ese nombre de usuario ya existe")

    user = await user_service.create_user(
        username=body.username.strip(),
        nombre=body.nombre.strip(),
        password_hash=hash_password(body.password),
        rol=body.rol,
    )
    return user


@router.patch("/users/{user_id}/estado")
async def set_user_estado(user_id: str, activo: bool, admin=Depends(require_admin)):
    if user_id == admin["id"] and not activo:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propio usuario")
    target = await user_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await user_service.set_user_active(user_id, activo)
    return {"ok": True}


@router.patch("/users/{user_id}/rol")
async def set_user_rol(user_id: str, body: SetRolBody, admin=Depends(require_admin)):
    if body.rol not in ("admin", "operador"):
        raise HTTPException(status_code=400, detail="Rol inválido")
    if user_id == admin["id"] and body.rol != "admin":
        raise HTTPException(status_code=400, detail="No puedes quitarte tu propio rol de administrador")
    target = await user_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await user_service.set_user_role(user_id, body.rol)
    return {"ok": True}


@router.patch("/users/{user_id}")
async def update_user(user_id: str, body: UpdateUserBody, _admin=Depends(require_admin)):
    target = await user_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if body.username is not None:
        if not USERNAME_RE.match(body.username):
            raise HTTPException(status_code=400, detail="Usuario inválido: usa solo letras, números, '.' o '_' (3-64 caracteres)")
        existing = await user_service.get_user_by_username(body.username.strip())
        if existing and existing["id"] != user_id:
            raise HTTPException(status_code=409, detail="Ese nombre de usuario ya existe")

    await user_service.update_user(
        user_id,
        nombre=body.nombre.strip() if body.nombre is not None else None,
        username=body.username.strip() if body.username is not None else None,
    )
    return {"ok": True}


@router.patch("/users/{user_id}/password")
async def admin_set_password(user_id: str, body: AdminSetPasswordBody, _admin=Depends(require_admin)):
    """Un administrador resetea la contraseña de otro usuario, sin necesitar la actual."""
    target = await user_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await user_service.set_user_password(user_id, hash_password(body.password_nueva))
    return {"ok": True}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")
    target = await user_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await user_service.delete_user(user_id)
    return {"ok": True}