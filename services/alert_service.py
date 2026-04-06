import logging
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.alerta import AlertaVencimiento, DocumentoRequerido
from models.documento import Documento
from models.vencimiento import EstadoVencimiento, Vencimiento

logger = logging.getLogger("pymeos")


# Umbral máximo de días para generar alertas
UMBRAL_DIAS = 5


def _periodo_de_fecha(fecha: date) -> str:
    """Convierte una fecha a string YYYY-MM."""
    return fecha.strftime("%Y-%m")


def _docs_del_cliente_en_periodo(db: Session, cliente_id: int, periodo: str) -> list[str]:
    """
    Retorna los tipos de documento recibidos para un cliente en el período dado.
    Filtrado en Python para compatibilidad con SQLite (sin .astext PostgreSQL).
    """
    todos = db.query(Documento).filter(
        Documento.cliente_id == cliente_id,
        Documento.activo == True,
    ).all()
    tipos = set()
    for doc in todos:
        if doc.metadatos and doc.metadatos.get("periodo") == periodo:
            tipos.add(doc.tipo_documento.value if hasattr(doc.tipo_documento, "value") else str(doc.tipo_documento))
    return list(tipos)


def _determinar_nivel(dias_restantes: int, faltantes: list[str]) -> str | None:
    """
    Reglas de nivel:
    - critica: días_restantes <= 3 y hay faltantes
    - advertencia: días_restantes <= 5 y hay faltantes
    - informativa: documentación completa y días_restantes <= 2
    - None: no aplica (sin faltantes y > 2 días, o > 5 días con faltantes)
    """
    hay_faltantes = len(faltantes) > 0
    if dias_restantes <= 3 and hay_faltantes:
        return "critica"
    if dias_restantes <= 5 and hay_faltantes:
        return "advertencia"
    if not hay_faltantes and dias_restantes <= 2:
        return "informativa"
    return None


def _generar_mensaje(nivel: str, dias_restantes: int, tipo_vencimiento: str,
                     faltantes: list[str], descripcion: str) -> str:
    if nivel == "critica":
        docs = ", ".join(faltantes) if faltantes else "ninguno"
        return (
            f"CRÍTICO: El vencimiento '{descripcion}' vence en {dias_restantes} día(s). "
            f"Documentación faltante: {docs}."
        )
    if nivel == "advertencia":
        docs = ", ".join(faltantes)
        return (
            f"ADVERTENCIA: El vencimiento '{descripcion}' vence en {dias_restantes} día(s). "
            f"Documentos pendientes de recibir: {docs}."
        )
    # informativa
    return (
        f"INFO: El vencimiento '{descripcion}' vence en {dias_restantes} día(s) "
        f"y la documentación está completa."
    )


def generar_alertas(db: Session) -> list[dict]:
    """
    Recorre vencimientos pendientes. Genera o actualiza alertas para los que
    caen dentro del umbral de 5 días. Retorna la lista de alertas generadas/actualizadas.
    """
    hoy = date.today()

    vencimientos = db.query(Vencimiento).filter(
        Vencimiento.estado == EstadoVencimiento.pendiente,
    ).all()

    generadas = []

    for venc in vencimientos:
        dias_restantes = (venc.fecha_vencimiento - hoy).days
        if dias_restantes > UMBRAL_DIAS:
            continue

        periodo = _periodo_de_fecha(venc.fecha_vencimiento)

        # Documentos requeridos para este tipo de vencimiento
        requeridos = db.query(DocumentoRequerido).filter(
            DocumentoRequerido.tipo_vencimiento == venc.tipo.value
        ).all()
        tipos_requeridos = [r.tipo_documento for r in requeridos]

        # Documentos recibidos del cliente en ese período
        tipos_recibidos = _docs_del_cliente_en_periodo(db, venc.cliente_id, periodo)

        faltantes = [t for t in tipos_requeridos if t not in tipos_recibidos]

        nivel = _determinar_nivel(dias_restantes, faltantes)
        if nivel is None:
            continue

        mensaje = _generar_mensaje(
            nivel, dias_restantes, venc.tipo.value, faltantes, venc.descripcion
        )

        # Buscar alerta existente no resuelta para este vencimiento
        alerta = db.query(AlertaVencimiento).filter(
            AlertaVencimiento.vencimiento_id == venc.id,
            AlertaVencimiento.resuelta_at == None,
        ).first()

        if alerta:
            alerta.nivel = nivel
            alerta.dias_restantes = dias_restantes
            alerta.documentos_faltantes = faltantes
            alerta.mensaje = mensaje
        else:
            alerta = AlertaVencimiento(
                vencimiento_id=venc.id,
                cliente_id=venc.cliente_id,
                nivel=nivel,
                dias_restantes=dias_restantes,
                documentos_faltantes=faltantes,
                mensaje=mensaje,
                vista=False,
            )
            db.add(alerta)

        db.flush()

        # Notificar via Telegram si hay canal activo y aún no se envió
        if nivel == "critica" and not alerta.sent_via_telegram:
            _intentar_notificar_telegram(db, alerta, venc)

        generadas.append({
            "vencimiento_id": venc.id,
            "cliente_id": venc.cliente_id,
            "nivel": nivel,
            "dias_restantes": dias_restantes,
            "documentos_faltantes": faltantes,
            "mensaje": mensaje,
        })

    db.commit()
    return generadas


def _intentar_notificar_telegram(db: Session, alerta: "AlertaVencimiento", venc) -> None:
    """Envía alerta crítica por Telegram si el estudio tiene el canal activo."""
    try:
        from models.cliente import Cliente
        from models.studio_config import StudioConfig
        from modules.asistente.notificador import enviar_alerta_vencimiento_telegram

        config = db.query(StudioConfig).first()
        if not config or not config.telegram_active or not config.telegram_chat_id:
            return

        cliente = db.query(Cliente).filter(Cliente.id == venc.cliente_id).first()
        cliente_nombre = cliente.razon_social if cliente else f"Cliente #{venc.cliente_id}"
        fecha_str = venc.fecha_vencimiento.strftime("%d/%m/%Y")

        enviar_alerta_vencimiento_telegram(
            config.telegram_chat_id,
            cliente_nombre,
            venc.tipo.value,
            fecha_str,
            alerta.dias_restantes,
            alerta.id,
        )
        alerta.sent_via_telegram = True
        alerta.telegram_sent_at = datetime.utcnow()
    except Exception as e:
        logger.warning("No se pudo enviar alerta Telegram: %s", e)


def listar_alertas(db: Session, nivel: str | None = None) -> list[dict]:
    """
    Retorna alertas no resueltas, ordenadas por nivel (críticas primero)
    y luego por días_restantes ascendente.
    """
    query = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.resuelta_at == None,
    )
    if nivel:
        query = query.filter(AlertaVencimiento.nivel == nivel)

    alertas = query.all()

    ORDEN_NIVEL = {"critica": 0, "advertencia": 1, "informativa": 2}
    alertas.sort(key=lambda a: (ORDEN_NIVEL.get(a.nivel, 9), a.dias_restantes))

    return [
        {
            "id": a.id,
            "vencimiento_id": a.vencimiento_id,
            "cliente_id": a.cliente_id,
            "nivel": a.nivel,
            "dias_restantes": a.dias_restantes,
            "documentos_faltantes": a.documentos_faltantes,
            "mensaje": a.mensaje,
            "vista": a.vista,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alertas
    ]


def resumen_alertas(db: Session) -> dict:
    """Conteo de alertas no resueltas por nivel."""
    alertas = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.resuelta_at == None,
    ).all()
    return {
        "criticas": sum(1 for a in alertas if a.nivel == "critica"),
        "advertencias": sum(1 for a in alertas if a.nivel == "advertencia"),
        "informativas": sum(1 for a in alertas if a.nivel == "informativa"),
    }


def marcar_vista(db: Session, alerta_id: int) -> dict:
    alerta = db.query(AlertaVencimiento).filter(AlertaVencimiento.id == alerta_id).first()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    alerta.vista = True
    db.commit()
    return {"id": alerta.id, "vista": alerta.vista}


def resolver_alerta(db: Session, alerta_id: int) -> dict:
    alerta = db.query(AlertaVencimiento).filter(AlertaVencimiento.id == alerta_id).first()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    alerta.resuelta_at = datetime.utcnow()
    db.commit()
    return {"id": alerta.id, "resuelta_at": alerta.resuelta_at.isoformat()}
