"""
Autenticación JWT separada para el Portal del Cliente.
El cliente del estudio usa este endpoint — su token es distinto al del contador.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import hash_password, verify_password
from database import get_db
from models.cliente import Cliente
from models.portal_notificacion import PortalNotificacion
from models.portal_usuario import PortalUsuario
from models.studio import Studio

logger = logging.getLogger("pymeos")

router = APIRouter(prefix="/portal/auth", tags=["Portal - Auth"])

# Usar PORTAL_JWT_SECRET si está definido; caer en SECRET_KEY como fallback.
# En producción definir PORTAL_JWT_SECRET separado del JWT del dashboard.
_SECRET = os.getenv("PORTAL_JWT_SECRET") or os.getenv("SECRET_KEY", "pymeos_portal_secret_key_change_in_prod")
_ALGORITHM = "HS256"
_EXPIRE_HOURS = 24 * 7  # 7 días


def _create_portal_token(cliente_id: int, studio_id: int) -> str:
    payload = {
        "sub": str(cliente_id),
        "studio_id": studio_id,
        "tipo": "portal",
        "exp": datetime.now(timezone.utc) + timedelta(hours=_EXPIRE_HOURS),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def _decode_portal_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token de portal inválido o expirado")
    if payload.get("tipo") != "portal":
        raise HTTPException(status_code=401, detail="Token inválido")
    return payload


class LoginPortalRequest(BaseModel):
    email: str
    password: str


class PortalTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    cliente_id: int
    nombre: str


@router.post("/login", response_model=PortalTokenResponse)
def login_portal(data: LoginPortalRequest, db: Session = Depends(get_db)):
    """Login del cliente al portal. Retorna JWT de portal."""
    usuario = db.query(PortalUsuario).filter(
        PortalUsuario.email == data.email.lower().strip(),
        PortalUsuario.activo == True,
    ).first()
    if not usuario or not verify_password(data.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    usuario.ultimo_acceso = datetime.now(timezone.utc)
    db.commit()

    cliente = db.query(Cliente).filter(Cliente.id == usuario.cliente_id).first()
    token = _create_portal_token(usuario.cliente_id, usuario.studio_id)
    return PortalTokenResponse(
        access_token=token,
        cliente_id=usuario.cliente_id,
        nombre=cliente.nombre if cliente else "",
    )


# ─── Endpoints del portal (autenticados con JWT de portal) ────────────────────

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Security

_bearer = HTTPBearer()


def require_portal_auth(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: Session = Depends(get_db),
):
    """Dependencia que valida JWT de portal y retorna (cliente_id, studio_id)."""
    payload = _decode_portal_token(credentials.credentials)
    return {"cliente_id": int(payload["sub"]), "studio_id": payload["studio_id"]}


@router.get("/ficha")
def ficha_portal(
    portal_user: dict = Depends(require_portal_auth),
    db: Session = Depends(get_db),
):
    """Home del portal: un solo request con todos los datos del cliente."""
    cliente_id = portal_user["cliente_id"]
    studio_id = portal_user["studio_id"]

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    studio = db.query(Studio).filter(Studio.id == studio_id).first()

    # Vencimientos próximos
    from models.vencimiento import Vencimiento, EstadoVencimiento
    from datetime import date
    hoy = date.today()
    vencimientos = db.query(Vencimiento).filter(
        Vencimiento.cliente_id == cliente_id,
        Vencimiento.estado == EstadoVencimiento.pendiente,
        Vencimiento.fecha_vencimiento >= hoy,
    ).order_by(Vencimiento.fecha_vencimiento).limit(5).all()

    # Notificaciones no leídas
    notifs_no_leidas = db.query(PortalNotificacion).filter(
        PortalNotificacion.cliente_id == cliente_id,
        PortalNotificacion.leida == False,
    ).count()

    notifs_recientes = db.query(PortalNotificacion).filter(
        PortalNotificacion.cliente_id == cliente_id,
    ).order_by(PortalNotificacion.created_at.desc()).limit(3).all()

    # Cobro actual
    cobro_actual = None
    try:
        from models.abono import Abono, Cobro
        abono = db.query(Abono).filter(
            Abono.cliente_id == cliente_id,
            Abono.activo == True,
        ).first()
        if abono:
            cobro = db.query(Cobro).filter(
                Cobro.abono_id == abono.id,
            ).order_by(Cobro.created_at.desc()).first()
            if cobro:
                cobro_actual = {
                    "monto": float(cobro.monto or 0),
                    "estado": cobro.estado.value if hasattr(cobro.estado, "value") else str(cobro.estado),
                    "periodo": getattr(cobro, "periodo", ""),
                    "fecha_vencimiento": cobro.fecha_vencimiento.isoformat() if getattr(cobro, "fecha_vencimiento", None) else None,
                }
    except Exception:
        pass

    return {
        "cliente": {
            "nombre": cliente.nombre,
            "estudio_nombre": studio.nombre if studio else "",
            "estudio_logo_url": studio.logo_url if studio else None,
        },
        "resumen": {
            "vencimientos_proximos": len(vencimientos),
            "notificaciones_no_leidas": notifs_no_leidas,
            "cobro_estado": cobro_actual["estado"] if cobro_actual else "sin_abono",
        },
        "vencimientos_proximos": [
            {
                "id": v.id,
                "tipo_obligacion": v.tipo.value if hasattr(v.tipo, "value") else str(v.tipo),
                "fecha_vencimiento": v.fecha_vencimiento.isoformat(),
                "dias_restantes": (v.fecha_vencimiento - hoy).days,
                "estado": v.estado.value if hasattr(v.estado, "value") else str(v.estado),
            }
            for v in vencimientos
        ],
        "notificaciones_recientes": [
            {
                "id": n.id,
                "titulo": n.titulo,
                "tipo": n.tipo,
                "leida": n.leida,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifs_recientes
        ],
        "cobro_actual": cobro_actual,
    }


@router.get("/notificaciones")
def notificaciones_portal(
    portal_user: dict = Depends(require_portal_auth),
    db: Session = Depends(get_db),
):
    cliente_id = portal_user["cliente_id"]
    notifs = db.query(PortalNotificacion).filter(
        PortalNotificacion.cliente_id == cliente_id,
    ).order_by(PortalNotificacion.created_at.desc()).all()
    return [
        {
            "id": n.id,
            "tipo": n.tipo,
            "titulo": n.titulo,
            "mensaje": n.mensaje,
            "leida": n.leida,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifs
    ]


@router.put("/notificaciones/{notif_id}/leer")
def marcar_leida(
    notif_id: int,
    portal_user: dict = Depends(require_portal_auth),
    db: Session = Depends(get_db),
):
    notif = db.query(PortalNotificacion).filter(
        PortalNotificacion.id == notif_id,
        PortalNotificacion.cliente_id == portal_user["cliente_id"],
    ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notif.leida = True
    notif.leida_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.put("/notificaciones/leer-todas")
def marcar_todas_leidas(
    portal_user: dict = Depends(require_portal_auth),
    db: Session = Depends(get_db),
):
    db.query(PortalNotificacion).filter(
        PortalNotificacion.cliente_id == portal_user["cliente_id"],
        PortalNotificacion.leida == False,
    ).update({"leida": True, "leida_at": datetime.now(timezone.utc)})
    db.commit()
    return {"ok": True}


@router.get("/vencimientos")
def vencimientos_portal(
    portal_user: dict = Depends(require_portal_auth),
    db: Session = Depends(get_db),
):
    from models.vencimiento import Vencimiento, EstadoVencimiento
    from datetime import date
    hoy = date.today()
    vencimientos = db.query(Vencimiento).filter(
        Vencimiento.cliente_id == portal_user["cliente_id"],
    ).order_by(Vencimiento.fecha_vencimiento).all()

    NOMBRES_SIMPLES = {
        "IVA": "Impuesto al Valor Agregado (IVA)",
        "F931": "Cargas Sociales",
        "IIBB": "Ingresos Brutos",
        "Ganancias anticipos": "Anticipo de Impuesto a las Ganancias",
    }

    return [
        {
            "id": v.id,
            "tipo_obligacion": v.tipo.value if hasattr(v.tipo, "value") else str(v.tipo),
            "tipo_nombre_simple": NOMBRES_SIMPLES.get(
                v.tipo.value if hasattr(v.tipo, "value") else str(v.tipo),
                v.tipo.value if hasattr(v.tipo, "value") else str(v.tipo),
            ),
            "descripcion": v.descripcion,
            "fecha_vencimiento": v.fecha_vencimiento.isoformat(),
            "dias_restantes": (v.fecha_vencimiento - hoy).days,
            "estado": v.estado.value if hasattr(v.estado, "value") else str(v.estado),
        }
        for v in vencimientos
    ]


@router.get("/cobros")
def cobros_portal(
    portal_user: dict = Depends(require_portal_auth),
    db: Session = Depends(get_db),
):
    cliente_id = portal_user["cliente_id"]
    studio_id = portal_user["studio_id"]

    try:
        from models.abono import Abono, Cobro
        abono = db.query(Abono).filter(
            Abono.cliente_id == cliente_id,
            Abono.activo == True,
        ).first()
        if not abono:
            return {"sin_abono": True}

        cobros = db.query(Cobro).filter(
            Cobro.abono_id == abono.id,
        ).order_by(Cobro.created_at.desc()).limit(7).all()

        studio = db.query(Studio).filter(Studio.id == studio_id).first()
        datos_pago = None
        if studio and (studio.cobro_cbu_cvu or studio.cobro_alias):
            datos_pago = {
                "banco": studio.cobro_banco,
                "cbu_cvu": studio.cobro_cbu_cvu,
                "alias": studio.cobro_alias,
                "titular": studio.cobro_titular_cuenta,
            }

        return {
            "abono": {
                "monto": float(abono.monto or 0),
                "estado": abono.estado.value if hasattr(abono.estado, "value") else str(abono.estado),
                "descripcion": getattr(abono, "descripcion", "Honorarios mensuales"),
            },
            "cobro_actual": {
                "monto": float(cobros[0].monto or 0) if cobros else 0,
                "estado": (cobros[0].estado.value if hasattr(cobros[0].estado, "value") else str(cobros[0].estado)) if cobros else "sin_cobro",
                "periodo": getattr(cobros[0], "periodo", "") if cobros else "",
                "fecha_vencimiento": cobros[0].fecha_vencimiento.isoformat() if cobros and getattr(cobros[0], "fecha_vencimiento", None) else None,
            } if cobros else None,
            "historial": [
                {
                    "periodo": getattr(c, "periodo", ""),
                    "monto": float(c.monto or 0),
                    "estado": c.estado.value if hasattr(c.estado, "value") else str(c.estado),
                    "fecha_cobro": c.fecha_cobro.isoformat() if getattr(c, "fecha_cobro", None) else None,
                }
                for c in cobros[1:]  # Excluir el actual del historial
            ],
            "datos_pago": datos_pago,
        }
    except Exception as e:
        logger.warning("Error en cobros_portal: %s", e)
        return {"sin_abono": True}


# ─── Endpoint de dashboard: habilitar acceso al portal a un cliente ─────────────────

from auth_dependencies import get_studio_id, require_rol

class HabilitarPortalRequest(BaseModel):
    cliente_id: int
    email: str
    password: str | None = None  # Si None, se genera uno temporal


@router.post("/habilitar-cliente")
def habilitar_cliente_portal(
    data: HabilitarPortalRequest,
    db: Session = Depends(get_db),
    studio_id: int = Depends(get_studio_id),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Crea o actualiza acceso al portal para un cliente del estudio."""
    # Verificar que el cliente pertenece al studio
    cliente = db.query(Cliente).filter(
        Cliente.id == data.cliente_id,
        Cliente.studio_id == studio_id,
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    # Contraseña temporal si no se provee
    import secrets as _secrets
    password_plain = data.password or _secrets.token_urlsafe(8)

    usuario = db.query(PortalUsuario).filter(
        PortalUsuario.cliente_id == data.cliente_id,
        PortalUsuario.studio_id == studio_id,
    ).first()

    if usuario:
        # Actualizar email y contraseña
        usuario.email = data.email.lower().strip()
        if data.password:
            usuario.password_hash = hash_password(data.password)
        usuario.activo = True
    else:
        usuario = PortalUsuario(
            cliente_id=data.cliente_id,
            studio_id=studio_id,
            email=data.email.lower().strip(),
            password_hash=hash_password(password_plain),
            activo=True,
        )
        db.add(usuario)

    db.commit()
    return {
        "ok": True,
        "email": usuario.email,
        "password_temporal": password_plain if not data.password else None,
        "mensaje": "Acceso al portal habilitado correctamente",
    }
