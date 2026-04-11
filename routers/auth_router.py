import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from auth import create_access_token, hash_password, verify_password
from database import get_db
from models.empleado import Empleado
from models.usuario import Usuario
from rate_limiter import limiter

logger = logging.getLogger("pymeos")

router = APIRouter(prefix="/api/auth", tags=["Auth"])

_RESET_TOKEN_EXPIRE_MINUTES = 30


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nombre: str


class SetupEstudioRequest(BaseModel):
    nombre_estudio: str
    nombre_dueno: str
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SetupStatusResponse(BaseModel):
    necesita_setup: bool


@router.get("/setup/status", response_model=SetupStatusResponse)
def setup_status(db: Session = Depends(get_db)):
    """Indica si el sistema necesita configuración inicial (sin empleados todavía)."""
    hay_empleados = db.query(Empleado).filter(Empleado.activo == True).first() is not None
    return SetupStatusResponse(necesita_setup=not hay_empleados)


@router.post("/setup", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
def setup_estudio(request: Request, data: SetupEstudioRequest, db: Session = Depends(get_db)):
    """
    Crea el primer usuario dueño del estudio.
    Solo funciona cuando no hay empleados en la base de datos.
    """
    hay_empleados = db.query(Empleado).filter(Empleado.activo == True).first()
    if hay_empleados:
        raise HTTPException(
            status_code=409,
            detail="El sistema ya fue configurado. Usá /register para nuevos usuarios.",
        )

    if db.query(Usuario).filter(Usuario.email == data.email).first():
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email")

    if len(data.password) < 8:
        raise HTTPException(status_code=422, detail="La contraseña debe tener al menos 8 caracteres")

    # Crear usuario de autenticación
    usuario = Usuario(
        email=data.email,
        password_hash=hash_password(data.password),
        nombre=data.nombre_dueno,
    )
    db.add(usuario)
    db.flush()

    # Crear empleado como dueño
    empleado = Empleado(
        nombre=data.nombre_dueno,
        email=data.email,
        rol="dueno",
        capacidad_horas_mes=160,
        activo=True,
    )
    db.add(empleado)
    db.commit()
    db.refresh(empleado)

    logger.info("Estudio '%s' configurado. Dueño: %s (%s)", data.nombre_estudio, data.nombre_dueno, data.email)

    token = create_access_token({
        "sub": str(usuario.id),
        "email": usuario.email,
        "nombre": empleado.nombre,
        "rol": empleado.rol,
        "empleado_id": empleado.id,
        "studio_id": 1,
    })
    return TokenResponse(access_token=token)


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("10/minute")
def register(request: Request, data: RegisterRequest, db: Session = Depends(get_db)):
    existente = db.query(Usuario).filter(Usuario.email == data.email).first()
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email")

    usuario = Usuario(
        email=data.email,
        password_hash=hash_password(data.password),
        nombre=data.nombre,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    empleado = db.query(Empleado).filter(Empleado.email == usuario.email, Empleado.activo == True).first()
    token = create_access_token({
        "sub": str(usuario.id),
        "email": usuario.email,
        "rol": empleado.rol if empleado else None,
        "empleado_id": empleado.id if empleado else None,
        "studio_id": 1,
    })
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.email == data.email, Usuario.activo == True).first()
    if not usuario or not verify_password(data.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    empleado = db.query(Empleado).filter(Empleado.email == usuario.email, Empleado.activo == True).first()
    token = create_access_token({
        "sub": str(usuario.id),
        "email": usuario.email,
        "rol": empleado.rol if empleado else None,
        "empleado_id": empleado.id if empleado else None,
        "studio_id": 1,
    })
    return TokenResponse(access_token=token)


# ---------------------------------------------------------------------------
# Forgot / Reset password
# ---------------------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password", status_code=200)
@limiter.limit("5/minute")
def forgot_password(request: Request, data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Genera un token de reset de contraseña válido por 30 minutos.
    Si SMTP está configurado, envía el email automáticamente.
    Siempre responde 200 para no revelar si el email existe.
    """
    usuario = db.query(Usuario).filter(Usuario.email == data.email, Usuario.activo == True).first()
    if usuario:
        token = secrets.token_urlsafe(32)
        usuario.reset_token = token
        usuario.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=_RESET_TOKEN_EXPIRE_MINUTES)
        db.commit()

        _enviar_email_reset(usuario.email, usuario.nombre, token)

    return {"detail": "Si el email existe, recibirás instrucciones para restablecer tu contraseña."}


@router.post("/reset-password", status_code=200)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Valida el token y actualiza la contraseña.
    El token se invalida inmediatamente después de usarse.
    """
    if len(data.new_password) < 8:
        raise HTTPException(status_code=422, detail="La contraseña debe tener al menos 8 caracteres")

    usuario = db.query(Usuario).filter(
        Usuario.reset_token == data.token,
        Usuario.activo == True,
    ).first()

    if not usuario or not usuario.reset_token_expires_at:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")

    expires = usuario.reset_token_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token inválido o expirado")

    usuario.password_hash = hash_password(data.new_password)
    usuario.reset_token = None
    usuario.reset_token_expires_at = None
    db.commit()

    return {"detail": "Contraseña actualizada correctamente"}


def _enviar_email_reset(email: str, nombre: str, token: str) -> None:
    """Envía el email de reset si SMTP está configurado."""
    try:
        from modules.asistente.adaptadores.email import send_email, smtp_configurado
        if not smtp_configurado():
            logger.warning("SMTP no configurado — token reset para %s: %s", email, token)
            return

        frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
        link = f"{frontend_url}/reset-password?token={token}"
        nombre_estudio = os.environ.get("STUDIO_NAME", "PyME OS")

        cuerpo = (
            f"Hola {nombre},\n\n"
            f"Recibimos una solicitud para restablecer tu contraseña.\n\n"
            f"Usá este enlace (válido por {_RESET_TOKEN_EXPIRE_MINUTES} minutos):\n{link}\n\n"
            f"Si no solicitaste el cambio, ignorá este mensaje.\n\n"
            f"— {nombre_estudio}"
        )
        send_email(
            to=email,
            subject="Restablecer contraseña",
            body_text=cuerpo,
            nombre_estudio=nombre_estudio,
        )
    except Exception as exc:
        logger.error("Error enviando email de reset a %s: %s", email, exc)
