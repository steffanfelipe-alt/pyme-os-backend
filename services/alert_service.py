import logging
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.alerta import AlertaVencimiento, DocumentoRequerido
from models.documento import Documento
from models.vencimiento import EstadoVencimiento, Vencimiento

logger = logging.getLogger("pymeos")


# Umbral de días por defecto (puede sobreescribirse desde StudioConfig)
_UMBRAL_DIAS_DEFAULT = 5


def _get_umbral_dias(db: Session) -> int:
    """Lee umbral_dias_notificacion de StudioConfig o usa el default de 5."""
    try:
        from models.studio_config import StudioConfig
        cfg = db.query(StudioConfig).first()
        if cfg and cfg.umbral_dias_notificacion:
            return int(cfg.umbral_dias_notificacion)
    except Exception:
        pass
    return _UMBRAL_DIAS_DEFAULT


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


def _determinar_nivel(
    dias_restantes: int,
    faltantes: list[str],
    tiene_requeridos: bool = True,
    umbral: int = _UMBRAL_DIAS_DEFAULT,
) -> str | None:
    """
    Reglas de nivel:
    - critica: días_restantes <= 3 y hay faltantes
    - advertencia: días_restantes <= umbral y hay faltantes
    - informativa: documentación completa y días_restantes <= 2
    - informativa: sin docs requeridos configurados y días_restantes <= umbral (aviso de proximidad)
    - None: fuera del umbral o documentación al día con tiempo suficiente
    """
    hay_faltantes = len(faltantes) > 0
    if dias_restantes <= 3 and hay_faltantes:
        return "critica"
    if dias_restantes <= umbral and hay_faltantes:
        return "advertencia"
    if not hay_faltantes and dias_restantes <= 2:
        return "informativa"
    # Vencimiento próximo pero sin docs requeridos configurados → aviso preventivo
    if not tiene_requeridos and dias_restantes <= umbral:
        return "informativa"
    return None


def _generar_mensaje(nivel: str, dias_restantes: int, tipo_vencimiento: str,
                     faltantes: list[str], descripcion: str, tiene_requeridos: bool = True) -> str:
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
    if not tiene_requeridos:
        return (
            f"INFO: El vencimiento '{descripcion}' vence en {dias_restantes} día(s). "
            f"No hay documentos requeridos configurados para este tipo."
        )
    return (
        f"INFO: El vencimiento '{descripcion}' vence en {dias_restantes} día(s) "
        f"y la documentación está completa."
    )


def generar_alertas(db: Session, studio_id: int) -> list[dict]:
    """
    Recorre vencimientos pendientes. Genera o actualiza alertas para los que
    caen dentro del umbral configurado. Retorna la lista de alertas generadas/actualizadas.
    """
    hoy = date.today()
    umbral = _get_umbral_dias(db)

    vencimientos = db.query(Vencimiento).filter(
        Vencimiento.studio_id == studio_id,
        Vencimiento.estado == EstadoVencimiento.pendiente,
    ).all()

    generadas = []

    for venc in vencimientos:
        dias_restantes = (venc.fecha_vencimiento - hoy).days
        if dias_restantes > umbral:
            continue

        periodo = _periodo_de_fecha(venc.fecha_vencimiento)

        # Documentos requeridos para este tipo de vencimiento
        requeridos = db.query(DocumentoRequerido).filter(
            DocumentoRequerido.tipo_vencimiento == venc.tipo.value
        ).all()
        tipos_requeridos = [r.tipo_documento for r in requeridos]
        tiene_requeridos = len(tipos_requeridos) > 0

        # Documentos recibidos del cliente en ese período
        tipos_recibidos = _docs_del_cliente_en_periodo(db, venc.cliente_id, periodo)

        faltantes = [t for t in tipos_requeridos if t not in tipos_recibidos]

        nivel = _determinar_nivel(dias_restantes, faltantes, tiene_requeridos, umbral)
        if nivel is None:
            continue

        mensaje = _generar_mensaje(
            nivel, dias_restantes, venc.tipo.value, faltantes, venc.descripcion, tiene_requeridos
        )

        # Buscar alerta existente no resuelta para este vencimiento
        alerta = db.query(AlertaVencimiento).filter(
            AlertaVencimiento.vencimiento_id == venc.id,
            AlertaVencimiento.resuelta_at.is_(None),
        ).first()

        if alerta:
            alerta.nivel = nivel
            alerta.dias_restantes = dias_restantes
            alerta.documentos_faltantes = faltantes
            alerta.mensaje = mensaje
        else:
            alerta = AlertaVencimiento(
                studio_id=studio_id,
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
        cliente_nombre = cliente.nombre if cliente else f"Cliente #{venc.cliente_id}"
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


def listar_alertas(db: Session, studio_id: int, nivel: str | None = None) -> list[dict]:
    """
    Retorna alertas no resueltas, ordenadas por nivel (críticas primero)
    y luego por días_restantes ascendente.
    """
    from models.cliente import Cliente
    from models.vencimiento import Vencimiento

    query = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.studio_id == studio_id,
        AlertaVencimiento.resuelta_at.is_(None),
    )
    if nivel:
        query = query.filter(AlertaVencimiento.nivel == nivel)

    alertas = query.all()

    ORDEN_NIVEL = {"critica": 0, "advertencia": 1, "informativa": 2}
    alertas.sort(key=lambda a: (ORDEN_NIVEL.get(a.nivel, 9), a.dias_restantes))

    # Pre-fetch clientes y vencimientos para evitar N+1
    cliente_ids = {a.cliente_id for a in alertas if a.cliente_id}
    vencimiento_ids = {a.vencimiento_id for a in alertas if a.vencimiento_id}

    clientes_map = {
        c.id: c.nombre
        for c in db.query(Cliente).filter(Cliente.id.in_(cliente_ids)).all()
    } if cliente_ids else {}

    vencimientos_map = {
        v.id: v.descripcion
        for v in db.query(Vencimiento).filter(Vencimiento.id.in_(vencimiento_ids)).all()
    } if vencimiento_ids else {}

    return [
        {
            "id": a.id,
            "vencimiento_id": a.vencimiento_id,
            "vencimiento_descripcion": vencimientos_map.get(a.vencimiento_id),
            "cliente_id": a.cliente_id,
            "cliente_nombre": clientes_map.get(a.cliente_id),
            "nivel": a.nivel,
            "dias_restantes": a.dias_restantes,
            "documentos_faltantes": a.documentos_faltantes,
            "mensaje": a.mensaje,
            "vista": a.vista,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alertas
    ]


def resumen_alertas(db: Session, studio_id: int) -> dict:
    """Conteo de alertas no resueltas por nivel."""
    alertas = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.studio_id == studio_id,
        AlertaVencimiento.resuelta_at.is_(None),
    ).all()
    return {
        "criticas": sum(1 for a in alertas if a.nivel == "critica"),
        "advertencias": sum(1 for a in alertas if a.nivel == "advertencia"),
        "informativas": sum(1 for a in alertas if a.nivel == "informativa"),
    }


def marcar_vista(db: Session, alerta_id: int, studio_id: int) -> dict:
    alerta = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.id == alerta_id, AlertaVencimiento.studio_id == studio_id
    ).first()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    alerta.vista = True
    db.commit()
    return {"id": alerta.id, "vista": alerta.vista}


def resolver_alerta(db: Session, alerta_id: int, studio_id: int) -> dict:
    alerta = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.id == alerta_id, AlertaVencimiento.studio_id == studio_id
    ).first()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    alerta.resuelta_at = datetime.utcnow()
    db.commit()
    return {"id": alerta.id, "resuelta_at": alerta.resuelta_at.isoformat()}


def ignorar_alerta(db: Session, alerta_id: int, studio_id: int) -> dict:
    alerta = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.id == alerta_id, AlertaVencimiento.studio_id == studio_id
    ).first()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    alerta.ignorada_at = datetime.utcnow()
    db.commit()
    return {"id": alerta.id, "ignorada_at": alerta.ignorada_at.isoformat()}


def listar_alertas_v2(
    db: Session,
    studio_id: int,
    tipo: str | None = None,
    cliente_id: int | None = None,
    incluir_resueltas: bool = False,
) -> list[dict]:
    """Lista alertas con filtros por tipo y cliente_id. Excluye ignoradas y resueltas por defecto."""
    from models.cliente import Cliente

    query = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.studio_id == studio_id,
    )
    if not incluir_resueltas:
        query = query.filter(
            AlertaVencimiento.resuelta_at.is_(None),
            AlertaVencimiento.ignorada_at.is_(None),
        )
    if tipo:
        query = query.filter(AlertaVencimiento.tipo == tipo)
    if cliente_id:
        query = query.filter(AlertaVencimiento.cliente_id == cliente_id)

    alertas = query.order_by(AlertaVencimiento.created_at.desc()).all()

    cliente_ids = {a.cliente_id for a in alertas if a.cliente_id}
    clientes_map = {
        c.id: c.nombre
        for c in db.query(Cliente).filter(Cliente.id.in_(cliente_ids)).all()
    } if cliente_ids else {}

    return [_serializar_alerta(a, clientes_map) for a in alertas]


def resumen_por_tipo(db: Session, studio_id: int) -> dict:
    """Conteo de alertas activas agrupadas por tipo."""
    alertas = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.studio_id == studio_id,
        AlertaVencimiento.resuelta_at.is_(None),
        AlertaVencimiento.ignorada_at.is_(None),
    ).all()
    conteo = {
        "vencimiento": 0, "mora": 0, "riesgo": 0,
        "tarea_vencida": 0, "documentacion": 0, "manual": 0,
    }
    for a in alertas:
        tipo = a.tipo or "vencimiento"
        if tipo in conteo:
            conteo[tipo] += 1
        else:
            conteo[tipo] = 1
    conteo["total"] = sum(conteo.values())
    return conteo


def crear_alerta_manual(db: Session, studio_id: int, data: dict) -> dict:
    """Crea una alerta manual del contador hacia un cliente."""
    from models.portal_notificacion import PortalNotificacion

    cliente_id = data["cliente_id"]
    canal = data.get("canal", "email")

    alerta = AlertaVencimiento(
        studio_id=studio_id,
        cliente_id=cliente_id,
        tipo="manual",
        origen="contador",
        titulo=data.get("titulo", ""),
        nivel="advertencia",
        mensaje=data.get("mensaje", ""),
        dias_restantes=0,
        canal=canal,
        tipo_vencimiento_ref=data.get("tipo_vencimiento"),
        tipo_documento_ref=data.get("tipo_documento"),
        documento_referencia=data.get("documento_referencia"),
    )
    db.add(alerta)
    db.flush()

    # Enviar por email si corresponde
    if canal in ("email", "ambos"):
        try:
            _enviar_alerta_manual_email(db, alerta, studio_id)
            alerta.sent_via_email = True
            alerta.email_sent_at = datetime.utcnow()
        except Exception as e:
            logger.warning("No se pudo enviar alerta manual por email: %s", e)

    # Crear notificación en el portal si corresponde
    if canal in ("portal", "ambos"):
        notif = PortalNotificacion(
            studio_id=studio_id,
            cliente_id=cliente_id,
            tipo="alerta_manual",
            titulo=alerta.titulo,
            mensaje=alerta.mensaje,
        )
        db.add(notif)
        alerta.sent_via_portal = True
        alerta.portal_sent_at = datetime.utcnow()

    db.commit()
    db.refresh(alerta)
    return _serializar_alerta(alerta, {})


def _enviar_alerta_manual_email(db: Session, alerta: AlertaVencimiento, studio_id: int) -> None:
    """Envía email al cliente usando el servicio de emails existente."""
    from models.cliente import Cliente
    from models.studio import Studio

    cliente = db.query(Cliente).filter(Cliente.id == alerta.cliente_id).first()
    if not cliente or not getattr(cliente, "email", None):
        return

    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    nombre_remitente = (studio.email_nombre_remitente or studio.nombre) if studio else "Tu estudio"
    firma = (studio.email_firma or "") if studio else ""

    cuerpo_partes = []
    if alerta.tipo_vencimiento_ref:
        cuerpo_partes.append(f"Obligación fiscal: {alerta.tipo_vencimiento_ref}")
    if alerta.tipo_documento_ref and alerta.documento_referencia:
        cuerpo_partes.append(f"Documento: {alerta.tipo_documento_ref} — {alerta.documento_referencia}")
    elif alerta.tipo_documento_ref:
        cuerpo_partes.append(f"Tipo de documento: {alerta.tipo_documento_ref}")
    cuerpo_partes.append(f"\n{alerta.mensaje}")
    if firma:
        cuerpo_partes.append(f"\n\n{firma}")

    cuerpo = "\n".join(cuerpo_partes)

    try:
        from services.email_clasificador import enviar_email_simple
        enviar_email_simple(
            to=cliente.email,
            subject=alerta.titulo or "Mensaje de tu contador",
            body=cuerpo,
            from_name=nombre_remitente,
        )
    except Exception:
        # Intentar con el servicio de notificaciones
        from services.notificacion_service import enviar_email_notificacion
        enviar_email_notificacion(
            destinatario=cliente.email,
            asunto=alerta.titulo or "Mensaje de tu contador",
            cuerpo=cuerpo,
        )


def _serializar_alerta(alerta: AlertaVencimiento, clientes_map: dict) -> dict:
    return {
        "id": alerta.id,
        "tipo": alerta.tipo or "vencimiento",
        "origen": alerta.origen or "sistema",
        "titulo": alerta.titulo,
        "vencimiento_id": alerta.vencimiento_id,
        "cliente_id": alerta.cliente_id,
        "cliente_nombre": clientes_map.get(alerta.cliente_id),
        "nivel": alerta.nivel,
        "severidad": alerta.nivel,
        "dias_restantes": alerta.dias_restantes,
        "documentos_faltantes": alerta.documentos_faltantes,
        "mensaje": alerta.mensaje,
        "vista": alerta.vista,
        "canal": alerta.canal,
        "estado": "resuelta" if alerta.resuelta_at else ("ignorada" if alerta.ignorada_at else "activa"),
        "created_at": alerta.created_at.isoformat() if alerta.created_at else None,
        "resuelta_at": alerta.resuelta_at.isoformat() if alerta.resuelta_at else None,
        "ignorada_at": alerta.ignorada_at.isoformat() if alerta.ignorada_at else None,
    }


# ─── TRIGGERS AUTOMÁTICOS ────────────────────────────────────────────────────

def generar_alertas_mora(db: Session, studio_id: int) -> int:
    """Genera alertas para clientes con cobros vencidos (mora en abono)."""
    generadas = 0
    try:
        from models.abono import Cobro, EstadoCobro
        from models.cliente import Cliente

        cobros_vencidos = db.query(Cobro).join(
            Cliente, Cobro.cliente_id == Cliente.id
        ).filter(
            Cliente.studio_id == studio_id,
            Cobro.estado == EstadoCobro.vencido,
        ).all()

        for cobro in cobros_vencidos:
            # Verificar que no exista alerta activa del mismo tipo para este cobro
            existente = db.query(AlertaVencimiento).filter(
                AlertaVencimiento.studio_id == studio_id,
                AlertaVencimiento.cobro_id == cobro.id,
                AlertaVencimiento.tipo == "mora",
                AlertaVencimiento.resuelta_at.is_(None),
                AlertaVencimiento.ignorada_at.is_(None),
            ).first()
            if existente:
                continue

            cliente = db.query(Cliente).filter(Cliente.id == cobro.cliente_id).first()
            nombre = cliente.nombre if cliente else f"Cliente #{cobro.cliente_id}"
            monto = getattr(cobro, "monto", 0)
            periodo = getattr(cobro, "periodo", "")

            alerta = AlertaVencimiento(
                studio_id=studio_id,
                cliente_id=cobro.cliente_id,
                tipo="mora",
                origen="sistema",
                titulo=f"Cobro vencido — {nombre}",
                nivel="critica",
                mensaje=f"El cliente {nombre} tiene un cobro vencido de ${monto} correspondiente a {periodo}",
                dias_restantes=0,
                cobro_id=cobro.id,
            )
            db.add(alerta)
            generadas += 1
    except Exception as e:
        logger.warning("Error generando alertas mora: %s", e)

    db.commit()
    return generadas


def generar_alertas_riesgo(db: Session, studio_id: int, umbral: int = 70) -> int:
    """Genera alertas para clientes con score de riesgo alto."""
    generadas = 0
    try:
        from models.cliente import Cliente

        clientes = db.query(Cliente).filter(
            Cliente.studio_id == studio_id,
            Cliente.activo == True,
        ).all()

        for cliente in clientes:
            score = getattr(cliente, "score_riesgo", None)
            if score is None or score < umbral:
                continue

            existente = db.query(AlertaVencimiento).filter(
                AlertaVencimiento.studio_id == studio_id,
                AlertaVencimiento.cliente_id == cliente.id,
                AlertaVencimiento.tipo == "riesgo",
                AlertaVencimiento.resuelta_at.is_(None),
                AlertaVencimiento.ignorada_at.is_(None),
            ).first()
            if existente:
                continue

            risk_exp = getattr(cliente, "risk_explanation", "Score alto detectado")
            alerta = AlertaVencimiento(
                studio_id=studio_id,
                cliente_id=cliente.id,
                tipo="riesgo",
                origen="sistema",
                titulo=f"Score de riesgo alto — {cliente.nombre}",
                nivel="advertencia",
                mensaje=f"El cliente {cliente.nombre} tiene un score de riesgo de {score}/100. Motivo: {risk_exp}",
                dias_restantes=0,
            )
            db.add(alerta)
            generadas += 1
    except Exception as e:
        logger.warning("Error generando alertas riesgo: %s", e)

    db.commit()
    return generadas


def generar_alertas_tareas_vencidas(db: Session, studio_id: int) -> int:
    """Genera alertas para tareas vencidas sin completar."""
    generadas = 0
    try:
        from models.tarea import EstadoTarea, Tarea
        from models.cliente import Cliente

        hoy = date.today()
        tareas = db.query(Tarea).filter(
            Tarea.studio_id == studio_id,
            Tarea.estado != EstadoTarea.completada,
            Tarea.fecha_limite < hoy,
            Tarea.activo == True,
        ).all()

        for tarea in tareas:
            existente = db.query(AlertaVencimiento).filter(
                AlertaVencimiento.studio_id == studio_id,
                AlertaVencimiento.tarea_id == tarea.id,
                AlertaVencimiento.tipo == "tarea_vencida",
                AlertaVencimiento.resuelta_at.is_(None),
            ).first()
            if existente:
                continue

            cliente_nombre = ""
            if tarea.cliente_id:
                cliente = db.query(Cliente).filter(Cliente.id == tarea.cliente_id).first()
                cliente_nombre = f" del cliente {cliente.nombre}" if cliente else ""

            fecha_str = tarea.fecha_limite.strftime("%d/%m/%Y") if tarea.fecha_limite else "fecha desconocida"
            alerta = AlertaVencimiento(
                studio_id=studio_id,
                cliente_id=tarea.cliente_id,
                tipo="tarea_vencida",
                origen="sistema",
                titulo=f"Tarea vencida — {tarea.titulo}",
                nivel="advertencia",
                mensaje=f"La tarea '{tarea.titulo}'{cliente_nombre} venció el {fecha_str} y sigue sin completarse",
                dias_restantes=0,
                tarea_id=tarea.id,
            )
            db.add(alerta)
            generadas += 1
    except Exception as e:
        logger.warning("Error generando alertas tareas vencidas: %s", e)

    db.commit()
    return generadas


def generar_alertas_documentacion(db: Session, studio_id: int, dias_anticipacion: int = 5) -> int:
    """Genera alertas para clientes con documentación pendiente y vencimiento próximo."""
    generadas = 0
    try:
        from models.cliente import Cliente
        from models.vencimiento import Vencimiento, EstadoVencimiento
        from models.documento import Documento

        hoy = date.today()
        from datetime import timedelta
        limite = hoy + timedelta(days=dias_anticipacion)

        vencimientos = db.query(Vencimiento).join(
            Cliente, Vencimiento.cliente_id == Cliente.id
        ).filter(
            Cliente.studio_id == studio_id,
            Vencimiento.estado == EstadoVencimiento.pendiente,
            Vencimiento.fecha_vencimiento >= hoy,
            Vencimiento.fecha_vencimiento <= limite,
        ).all()

        for venc in vencimientos:
            # Verificar si hay documentos pendientes
            docs_pendientes = db.query(Documento).filter(
                Documento.cliente_id == venc.cliente_id,
                Documento.activo == True,
            ).filter(
                Documento.estado_clasificacion.in_(["pendiente", "procesando"])
            ).count()

            if docs_pendientes == 0:
                continue

            existente = db.query(AlertaVencimiento).filter(
                AlertaVencimiento.studio_id == studio_id,
                AlertaVencimiento.vencimiento_id == venc.id,
                AlertaVencimiento.tipo == "documentacion",
                AlertaVencimiento.resuelta_at.is_(None),
            ).first()
            if existente:
                continue

            cliente = db.query(Cliente).filter(Cliente.id == venc.cliente_id).first()
            nombre = cliente.nombre if cliente else f"Cliente #{venc.cliente_id}"
            dias = (venc.fecha_vencimiento - hoy).days

            alerta = AlertaVencimiento(
                studio_id=studio_id,
                cliente_id=venc.cliente_id,
                vencimiento_id=venc.id,
                tipo="documentacion",
                origen="sistema",
                titulo=f"Documentación pendiente — {nombre}",
                nivel="critica",
                mensaje=f"El cliente {nombre} tiene documentación pendiente y vence {venc.tipo.value} en {dias} días",
                dias_restantes=dias,
            )
            db.add(alerta)
            generadas += 1
    except Exception as e:
        logger.warning("Error generando alertas documentación: %s", e)

    db.commit()
    return generadas


def generar_todos_los_triggers(db: Session, studio_id: int) -> dict:
    """Ejecuta todos los triggers automáticos de alertas."""
    from models.studio import Studio
    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    umbral_riesgo = (studio.alerta_riesgo_umbral if studio else 70) or 70
    dias_doc = (studio.alerta_documentacion_dias if studio else 5) or 5

    return {
        "mora": generar_alertas_mora(db, studio_id),
        "riesgo": generar_alertas_riesgo(db, studio_id, umbral_riesgo),
        "tarea_vencida": generar_alertas_tareas_vencidas(db, studio_id),
        "documentacion": generar_alertas_documentacion(db, studio_id, dias_doc),
        "vencimiento": len(generar_alertas(db, studio_id)),
    }
