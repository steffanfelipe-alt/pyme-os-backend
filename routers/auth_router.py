from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import create_access_token, hash_password, verify_password
from database import get_db
from models.empleado import Empleado
from models.usuario import Usuario

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    nombre: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
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
    })
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.email == data.email, Usuario.activo == True).first()
    if not usuario or not verify_password(data.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    empleado = db.query(Empleado).filter(Empleado.email == usuario.email, Empleado.activo == True).first()
    token = create_access_token({
        "sub": str(usuario.id),
        "email": usuario.email,
        "rol": empleado.rol if empleado else None,
        "empleado_id": empleado.id if empleado else None,
    })
    return TokenResponse(access_token=token)
