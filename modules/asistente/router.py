from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth_dependencies import require_rol
from database import get_db
from modules.asistente.models import AsistenteCanal
from modules.asistente.schemas import (
    CanalCreate,
    CanalResponse,
    ConfirmarRequest,
    MensajeEntrante,
    NotificacionRequest,
)
from modules.asistente import service

router = APIRouter(prefix="/api/asistente", tags=["Asistente"])


@router.post("/mensaje")
async def recibir_mensaje(
    body: MensajeEntrante,
    db: Session = Depends(get_db),
):
    """
    Recibe un mensaje normalizado desde n8n (Telegram o email) o directamente.
    No requiere autenticación JWT — el origen se verifica por asistente_canales.
    """
    return await service.procesar_mensaje(db, body)


@router.post("/confirmar/{confirmacion_id}")
def confirmar_operacion(
    confirmacion_id: int,
    body: ConfirmarRequest,
    db: Session = Depends(get_db),
):
    """Confirma o cancela una operación de escritura pendiente."""
    return service.procesar_confirmacion(db, confirmacion_id, body.confirmado)


@router.get("/mensajes")
def historial_mensajes(
    usuario_id: int | None = None,
    canal: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
):
    """Historial de mensajes del asistente (solo dueño)."""
    from modules.asistente.models import AsistenteMensaje
    query = db.query(AsistenteMensaje)
    if usuario_id:
        query = query.filter(AsistenteMensaje.usuario_id == usuario_id)
    if canal:
        query = query.filter(AsistenteMensaje.canal == canal)
    mensajes = query.order_by(AsistenteMensaje.created_at.desc()).limit(100).all()
    return [
        {
            "id": m.id,
            "usuario_id": m.usuario_id,
            "canal": m.canal,
            "direccion": m.direccion,
            "intencion": m.intencion_detectada,
            "estado": m.estado,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in mensajes
    ]


@router.get("/canales")
def listar_canales(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
):
    """Lista todos los canales registrados."""
    canales = db.query(AsistenteCanal).filter(AsistenteCanal.activo == True).all()
    return [
        CanalResponse(
            id=c.id,
            tipo_usuario=c.tipo_usuario,
            usuario_id=c.usuario_id,
            canal=c.canal,
            identificador=c.identificador,
            activo=c.activo,
        )
        for c in canales
    ]


@router.post("/canales", status_code=201)
def registrar_canal(
    body: CanalCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
):
    """Registra un canal para un usuario (vincula Telegram/email a empleado o cliente)."""
    existente = db.query(AsistenteCanal).filter(
        AsistenteCanal.canal == body.canal,
        AsistenteCanal.identificador == body.identificador,
    ).first()
    if existente:
        existente.activo = True
        existente.usuario_id = body.usuario_id
        existente.tipo_usuario = body.tipo_usuario
        db.commit()
        return CanalResponse(**existente.__dict__)

    canal = AsistenteCanal(
        tipo_usuario=body.tipo_usuario,
        usuario_id=body.usuario_id,
        canal=body.canal,
        identificador=body.identificador,
        activo=True,
    )
    db.add(canal)
    db.commit()
    db.refresh(canal)
    return CanalResponse(
        id=canal.id,
        tipo_usuario=canal.tipo_usuario,
        usuario_id=canal.usuario_id,
        canal=canal.canal,
        identificador=canal.identificador,
        activo=canal.activo,
    )


@router.post("/telegram/generar-codigo")
def generar_codigo_vinculacion(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
):
    """
    Genera un código de vinculación de 8 caracteres para conectar el bot de Telegram.
    El código expira en 30 minutos. Usarlo con /vincular CODIGO en el bot.
    """
    import random
    import string
    from datetime import datetime, timedelta
    from models.studio_config import StudioConfig

    config = db.query(StudioConfig).first()
    if not config:
        config = StudioConfig()
        db.add(config)

    codigo = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    config.telegram_connect_code = codigo
    config.telegram_connect_expires_at = datetime.utcnow() + timedelta(minutes=30)
    db.commit()

    return {
        "codigo": codigo,
        "expira_en_minutos": 30,
        "instruccion": f"Enviá este mensaje al bot de Telegram: /vincular {codigo}",
    }


@router.delete("/canales/{canal_id}", status_code=204)
def desactivar_canal(
    canal_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
):
    """Desactiva un canal (no lo elimina)."""
    canal = db.query(AsistenteCanal).filter(AsistenteCanal.id == canal_id).first()
    if not canal:
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    canal.activo = False
    db.commit()
