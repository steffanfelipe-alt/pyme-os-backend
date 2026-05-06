"""
Servicio de negocio para Facturación Electrónica.
Orquesta validaciones, emisión ARCA, PDF y persistencia.
"""
import base64
import logging
import os
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.facturacion import Comprobante, HonorarioRecurrente, PagoComprobante, StudioArcaConfig
from schemas.facturacion import (
    ArcaConfigCreate,
    ComprobanteCreate,
    HonorarioCreate,
    HonorarioUpdate,
    RegistrarPagoRequest,
)
from services import arca_service

logger = logging.getLogger("pymeos")

_ALICUOTAS_VALIDAS = {0.0, 10.5, 21.0, 27.0}


# ─── Helpers ──────────────────────────────────────────────────────────────────────────────

def _get_config_o_400(studio_id: int, db: Session) -> StudioArcaConfig:
    cfg = db.query(StudioArcaConfig).filter(StudioArcaConfig.studio_id == studio_id).first()
    if not cfg or not cfg.certificado_enc or not cfg.clave_privada_enc:
        raise HTTPException(
            status_code=400,
            detail="El estudio no tiene configuración ARCA completa. Configurá CUIT, punto de venta, certificado y clave privada en /api/facturacion/config.",
        )
    return cfg


def _get_comprobante_o_404(comp_id: int, studio_id: int, db: Session) -> Comprobante:
    comp = db.query(Comprobante).filter(
        Comprobante.id == comp_id,
        Comprobante.studio_id == studio_id,
    ).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")
    return comp


def _validar_tipo_x_condicion(tipo_cbte: str, cliente: Cliente) -> None:
    """
    Valida coherencia entre tipo de comprobante y condición fiscal del cliente.
    RI → A, Consumidor Final/Monotributista → B o C.
    """
    condicion = getattr(cliente, "condicion_fiscal", None)
    if not condicion:
        return
    if condicion == "responsable_inscripto" and tipo_cbte.upper() != "A":
        raise HTTPException(
            status_code=400,
            detail="El cliente es Responsable Inscripto — el comprobante debe ser tipo A.",
        )
    if condicion in {"monotributista", "consumidor_final", "exento"} and tipo_cbte.upper() == "A":
        raise HTTPException(
            status_code=400,
            detail=f"Cliente {condicion} — el comprobante debe ser tipo B o C (no A).",
        )


# ─── Configuración ARCA ──────────────────────────────────────────────────────────────────

def guardar_config_arca(studio_id: int, data: ArcaConfigCreate, db: Session) -> dict:
    cfg = db.query(StudioArcaConfig).filter(StudioArcaConfig.studio_id == studio_id).first()
    if not cfg:
        cfg = StudioArcaConfig(studio_id=studio_id)
        db.add(cfg)

    cfg.cuit = data.cuit
    cfg.punto_venta = data.punto_venta
    cfg.modo = data.modo

    try:
        cert_pem = base64.b64decode(data.certificado_b64).decode()
        key_pem = base64.b64decode(data.clave_privada_b64).decode()
        cfg.certificado_enc = arca_service.encrypt_cert(cert_pem)
        cfg.clave_privada_enc = arca_service.encrypt_cert(key_pem)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error procesando certificado: {e}")

    db.commit()
    db.refresh(cfg)
    return {
        "studio_id": studio_id,
        "cuit": cfg.cuit,
        "punto_venta": cfg.punto_venta,
        "modo": cfg.modo,
        "configurado": True,
    }


def obtener_config_arca(studio_id: int, db: Session) -> dict:
    cfg = db.query(StudioArcaConfig).filter(StudioArcaConfig.studio_id == studio_id).first()
    if not cfg:
        return {"studio_id": studio_id, "configurado": False, "cuit": None, "punto_venta": None, "modo": "homologacion"}
    return {
        "studio_id": studio_id,
        "cuit": cfg.cuit,
        "punto_venta": cfg.punto_venta,
        "modo": cfg.modo,
        "configurado": bool(cfg.certificado_enc and cfg.clave_privada_enc),
    }


# ─── Comprobantes ─────────────────────────────────────────────────────────────────────

def listar_comprobantes(
    studio_id: int,
    db: Session,
    cliente_id: Optional[int] = None,
    estado: Optional[str] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
) -> list[Comprobante]:
    q = db.query(Comprobante).filter(Comprobante.studio_id == studio_id)
    if cliente_id:
        q = q.filter(Comprobante.cliente_id == cliente_id)
    if estado:
        q = q.filter(Comprobante.estado == estado)
    if fecha_desde:
        q = q.filter(Comprobante.fecha_emision >= fecha_desde)
    if fecha_hasta:
        q = q.filter(Comprobante.fecha_emision <= fecha_hasta)
    return q.order_by(Comprobante.created_at.desc()).all()


def emitir_comprobante(studio_id: int, data: ComprobanteCreate, db: Session) -> Comprobante:
    """Flujo completo: valida → llama ARCA → guarda CAE."""
    cfg = _get_config_o_400(studio_id, db)

    cliente = db.query(Cliente).filter(Cliente.id == data.cliente_id, Cliente.activo == True).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    if not getattr(cliente, "cuit_cuil", None):
        raise HTTPException(status_code=400, detail="El cliente no tiene CUIT configurado")

    _validar_tipo_x_condicion(data.tipo_comprobante, cliente)

    if data.alicuota_iva not in _ALICUOTAS_VALIDAS:
        raise HTTPException(status_code=400, detail=f"alicuota_iva inválida. Valores válidos: {_ALICUOTAS_VALIDAS}")

    fecha_emision = data.fecha_emision or date.today()
    importe_iva = round(data.importe_neto * (data.alicuota_iva / 100), 2)
    importe_total = round(data.importe_neto + importe_iva, 2)

    tipo_int = arca_service.tipo_cbte_a_int(data.tipo_comprobante)

    # Crear registro en estado pendiente
    comp = Comprobante(
        studio_id=studio_id,
        cliente_id=data.cliente_id,
        tipo_comprobante=data.tipo_comprobante,
        punto_venta=cfg.punto_venta,
        fecha_emision=fecha_emision,
        concepto=data.concepto,
        descripcion_concepto=data.descripcion_concepto,
        importe_neto=data.importe_neto,
        importe_iva=importe_iva,
        importe_total=importe_total,
        alicuota_iva=data.alicuota_iva,
        estado="pendiente",
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)

    # Llamar a ARCA
    try:
        cert_pem = arca_service.decrypt_cert(cfg.certificado_enc)
        key_pem = arca_service.decrypt_cert(cfg.clave_privada_enc)

        ultimo = arca_service.obtener_ultimo_numero(
            cuit=cfg.cuit,
            punto_venta=cfg.punto_venta,
            tipo_cbte=tipo_int,
            cert_pem=cert_pem,
            key_pem=key_pem,
            modo=cfg.modo,
        )
        numero = ultimo + 1

        resultado = arca_service.emitir_comprobante(
            cuit=cfg.cuit,
            punto_venta=cfg.punto_venta,
            tipo_cbte=tipo_int,
            numero=numero,
            fecha_cbte=fecha_emision.strftime("%Y%m%d"),
            concepto=data.concepto,
            cuit_receptor=cliente.cuit_cuil,
            importe_neto=data.importe_neto,
            importe_iva=importe_iva,
            importe_total=importe_total,
            alicuota_id=arca_service.alicuota_a_id(data.alicuota_iva),
            cert_pem=cert_pem,
            key_pem=key_pem,
            modo=cfg.modo,
        )

        comp.numero_comprobante = resultado["numero"]
        comp.cae = resultado["cae"]
        vto_str = resultado["fecha_vto_cae"]  # YYYYMMDD
        comp.fecha_cae_vencimiento = date(int(vto_str[:4]), int(vto_str[4:6]), int(vto_str[6:]))
        comp.estado = "emitida"

        # Crear registro de pago pendiente automáticamente
        pago = PagoComprobante(
            studio_id=studio_id,
            comprobante_id=comp.id,
            estado="pendiente",
        )
        db.add(pago)

    except RuntimeError as e:
        comp.estado = "pendiente"
        comp.error_arca = str(e)
        logger.error("Error ARCA al emitir comprobante %d: %s", comp.id, e)

    db.commit()
    db.refresh(comp)
    return comp


def enviar_comprobante(comp_id: int, studio_id: int, db: Session) -> Comprobante:
    comp = _get_comprobante_o_404(comp_id, studio_id, db)
    if comp.estado not in {"emitida", "enviada"}:
        raise HTTPException(status_code=400, detail="El comprobante debe estar en estado 'emitida' para enviarse")

    cliente = db.query(Cliente).filter(Cliente.id == comp.cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    # Email
    email_dest = getattr(cliente, "email_notificaciones", None) or getattr(cliente, "email", None)
    if email_dest:
        try:
            from modules.asistente.adaptadores.email import send_email
            nombre_estudio = os.environ.get("STUDIO_NAME", "el estudio")
            asunto = f"Comprobante {comp.tipo_comprobante}-{comp.punto_venta:04d}-{comp.numero_comprobante:08d}"
            cuerpo = (
                f"Estimado/a {cliente.nombre},\n\n"
                f"Adjuntamos el comprobante electrónico N° {asunto}.\n"
                f"Importe total: ${comp.importe_total:,.2f}\n"
                f"CAE: {comp.cae}\n\n"
                f"Saludos,\n{nombre_estudio}"
            )
            send_email(email_dest, asunto, cuerpo, nombre_estudio)
            comp.enviada_por_email = True
        except Exception as e:
            logger.error("Error enviando comprobante %d por email: %s", comp.id, e)

    comp.estado = "enviada"
    db.commit()
    db.refresh(comp)
    return comp


def registrar_pago(comp_id: int, studio_id: int, data: RegistrarPagoRequest, db: Session) -> PagoComprobante:
    comp = _get_comprobante_o_404(comp_id, studio_id, db)
    pago = db.query(PagoComprobante).filter(PagoComprobante.comprobante_id == comp_id).first()
    if not pago:
        pago = PagoComprobante(studio_id=studio_id, comprobante_id=comp_id)
        db.add(pago)

    pago.fecha_pago = data.fecha_pago or date.today()
    pago.medio_pago = data.medio_pago
    pago.nota = data.nota
    pago.estado = "cobrado"
    db.commit()
    db.refresh(pago)
    return pago


def obtener_pdf_url(comp_id: int, studio_id: int, db: Session) -> str:
    comp = _get_comprobante_o_404(comp_id, studio_id, db)
    if comp.pdf_url:
        return comp.pdf_url

    from services.pdf_comprobante_service import generar_y_subir_pdf
    url = generar_y_subir_pdf(comp, db)
    comp.pdf_url = url
    db.commit()
    return url


# ─── Honorarios recurrentes ───────────────────────────────────────────────────────────────

def listar_honorarios(studio_id: int, db: Session) -> list[HonorarioRecurrente]:
    return db.query(HonorarioRecurrente).filter(HonorarioRecurrente.studio_id == studio_id).all()


def crear_honorario(studio_id: int, data: HonorarioCreate, db: Session) -> HonorarioRecurrente:
    cliente = db.query(Cliente).filter(Cliente.id == data.cliente_id, Cliente.activo == True).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    hon = HonorarioRecurrente(
        studio_id=studio_id,
        cliente_id=data.cliente_id,
        descripcion=data.descripcion,
        importe_neto=data.importe_neto,
        alicuota_iva=data.alicuota_iva,
        tipo_comprobante=data.tipo_comprobante,
        dia_emision=data.dia_emision,
    )
    db.add(hon)
    db.commit()
    db.refresh(hon)
    return hon


def actualizar_honorario(hon_id: int, studio_id: int, data: HonorarioUpdate, db: Session) -> HonorarioRecurrente:
    hon = db.query(HonorarioRecurrente).filter(
        HonorarioRecurrente.id == hon_id,
        HonorarioRecurrente.studio_id == studio_id,
    ).first()
    if not hon:
        raise HTTPException(status_code=404, detail="Honorario recurrente no encontrado")

    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(hon, campo, valor)
    db.commit()
    db.refresh(hon)
    return hon


def eliminar_honorario(hon_id: int, studio_id: int, db: Session) -> None:
    hon = db.query(HonorarioRecurrente).filter(
        HonorarioRecurrente.id == hon_id,
        HonorarioRecurrente.studio_id == studio_id,
    ).first()
    if not hon:
        raise HTTPException(status_code=404, detail="Honorario recurrente no encontrado")
    hon.activo = False
    db.commit()


def emitir_honorario_ahora(hon_id: int, studio_id: int, db: Session) -> Comprobante:
    hon = db.query(HonorarioRecurrente).filter(
        HonorarioRecurrente.id == hon_id,
        HonorarioRecurrente.studio_id == studio_id,
    ).first()
    if not hon:
        raise HTTPException(status_code=404, detail="Honorario recurrente no encontrado")

    data = ComprobanteCreate(
        cliente_id=hon.cliente_id,
        tipo_comprobante=hon.tipo_comprobante,
        concepto=2,
        descripcion_concepto=hon.descripcion,
        importe_neto=float(hon.importe_neto),
        alicuota_iva=float(hon.alicuota_iva),
    )
    comp = emitir_comprobante(studio_id, data, db)
    hon.ultimo_emitido = date.today()
    db.commit()
    return comp


# ─── Pagos ──────────────────────────────────────────────────────────────────────────────

def listar_pagos(studio_id: int, estado: Optional[str], db: Session) -> list[PagoComprobante]:
    q = db.query(PagoComprobante).filter(PagoComprobante.studio_id == studio_id)
    if estado:
        q = q.filter(PagoComprobante.estado == estado)
    return q.order_by(PagoComprobante.created_at.desc()).all()


# ─── Job: emisión automática de honorarios recurrentes ──────────────────────────────────────

def job_emitir_honorarios_recurrentes(db: Session) -> None:
    """
    Ejecutado por APScheduler a las 08:00 hora Argentina.
    Emite comprobantes para reglas activas cuyo dia_emision coincide con hoy
    y que no fueron emitidas este mes.
    """
    hoy = date.today()
    dia_hoy = hoy.day
    mes_hoy = hoy.strftime("%Y-%m")

    reglas = db.query(HonorarioRecurrente).filter(
        HonorarioRecurrente.activo == True,
        HonorarioRecurrente.dia_emision == dia_hoy,
    ).all()

    for regla in reglas:
        # Verificar que no se emitió en el mes actual
        if regla.ultimo_emitido and regla.ultimo_emitido.strftime("%Y-%m") == mes_hoy:
            continue

        # studio_id puede ser None en reglas legacy; omitir si no tiene
        studio_id = regla.studio_id
        if studio_id is None:
            logger.warning("Honorario recurrente %d sin studio_id — omitido", regla.id)
            continue

        try:
            data = ComprobanteCreate(
                cliente_id=regla.cliente_id,
                tipo_comprobante=regla.tipo_comprobante,
                concepto=2,
                descripcion_concepto=regla.descripcion,
                importe_neto=float(regla.importe_neto),
                alicuota_iva=float(regla.alicuota_iva),
            )
            emitir_comprobante(studio_id, data, db)
            regla.ultimo_emitido = hoy
            db.commit()
            logger.info("Honorario recurrente %d emitido OK para cliente %d", regla.id, regla.cliente_id)
        except Exception as e:
            logger.error("Error emitiendo honorario recurrente %d: %s", regla.id, e)
