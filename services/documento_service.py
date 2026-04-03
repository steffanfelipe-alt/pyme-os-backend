import base64
import calendar
import hashlib
import json
import logging
import os
import uuid
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import HTTPException, UploadFile
from PIL import Image
from pypdf import PdfReader
from sqlalchemy.orm import Session

from models.alerta import AlertaVencimiento
from models.cliente import Cliente
from models.documento import Documento, EstadoDocumento, TipoDocumento
from models.empleado import Empleado  # noqa: F401 — resuelve FK
from models.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento  # noqa: F401 — resuelve FK
from schemas.documento import DocumentoResponse, DocumentoUpdate
from services import risk_service

logger = logging.getLogger("pymeos")

UPLOADS_BASE = Path("uploads")
MAX_FILE_BYTES = 10 * 1024 * 1024   # 10 MB
MAX_IMG_BYTES = 2 * 1024 * 1024     # 2 MB — si supera, se comprime
MAX_PDF_PAGES = 3
MAX_TEXT_CHARS = 8000
EXTENSIONES_VALIDAS = {".pdf", ".jpg", ".jpeg", ".png"}
CONFIANZA_MIN_PROCESADO = 0.5

MAPEO_DOCUMENTO_VENCIMIENTO: dict[str, list[str]] = {
    "factura":            ["iva", "iibb", "monotributo"],
    "ddjj":               ["iva", "ddjj_anual", "ganancias", "bienes_personales", "iibb"],
    "liquidacion_sueldo": ["sueldos_cargas"],
    "balance":            ["ganancias", "bienes_personales", "ddjj_anual"],
    "recibo":             ["autonomos"],
    "extracto_bancario":  [],
    "contrato":           [],
    "otro":               [],
}

# Mapeo inverso: tipo_vencimiento → tipos de documento que lo alimentan
# Se deriva de MAPEO_DOCUMENTO_VENCIMIENTO — no modificar manualmente
MAPEO_VENCIMIENTO_DOCUMENTO: dict[str, list[str]] = {}
for _tipo_doc, _tipos_venc in MAPEO_DOCUMENTO_VENCIMIENTO.items():
    for _tipo_venc in _tipos_venc:
        MAPEO_VENCIMIENTO_DOCUMENTO.setdefault(_tipo_venc, []).append(_tipo_doc)

_PROMPT_CLASIFICACION = """Sos un asistente contable argentino. Analizá este documento y extraé la información solicitada.

Tipos de documento válidos: factura, liquidacion_sueldo, ddjj, recibo, extracto_bancario, balance, contrato, otro.

Tipos de vencimiento fiscal argentino: iva, ddjj_anual, monotributo, iibb, ganancias, bienes_personales, autonomos, sueldos_cargas, otro.

Mapeo de referencia (tipo de documento → vencimientos que alimenta):
- factura → iva, iibb, monotributo
- ddjj → iva, ddjj_anual, ganancias, bienes_personales, iibb
- liquidacion_sueldo → sueldos_cargas
- balance → ganancias, bienes_personales, ddjj_anual
- recibo → autonomos
- extracto_bancario → (ninguno)
- contrato → (ninguno)
- otro → (ninguno)

Usá el mapeo como guía, pero si el documento es claramente de un tipo que alimenta vencimientos distintos a los listados, ajustá según el contenido real.

Respondé ÚNICAMENTE con JSON válido, sin texto adicional ni bloques de código:
{"tipo":"...","confianza":0.95,"resumen":"descripcion breve en español","periodo":"YYYY-MM o null","cuit_detectado":"XX-XXXXXXXX-X o null","monto":15000.00,"vencimientos_relacionados":["iva","iibb"]}

El campo vencimientos_relacionados debe ser una lista de strings con los valores exactos del enum. Lista vacía [] si el documento no está relacionado con ningún vencimiento fiscal."""


def _calcular_hash(contenido: bytes) -> str:
    """Calcula SHA-256 del contenido binario del archivo."""
    return hashlib.sha256(contenido).hexdigest()


def _directorio_cliente(cliente_id: int) -> Path:
    d = UPLOADS_BASE / str(cliente_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _extraer_texto_pdf(contenido: bytes) -> str:
    reader = PdfReader(BytesIO(contenido))
    partes = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        texto = page.extract_text() or ""
        partes.append(texto)
    return "\n".join(partes)[:MAX_TEXT_CHARS]


def _comprimir_imagen(contenido: bytes) -> bytes:
    img = Image.open(BytesIO(contenido))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=75, optimize=True)
    return buf.getvalue()


def _clasificar_con_ia(extension: str, contenido: bytes) -> dict:
    """Llama a Claude y devuelve el dict clasificado. Nunca lanza excepción."""
    try:
        client = anthropic.Anthropic()

        if extension == ".pdf":
            texto = _extraer_texto_pdf(contenido)
            if not texto.strip():
                return {"tipo": "otro", "confianza": 0.0, "resumen": "Sin texto extraíble",
                        "periodo": None, "cuit_detectado": None, "monto": None}
            mensaje = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                messages=[{"role": "user", "content": f"{_PROMPT_CLASIFICACION}\n\nDocumento:\n{texto}"}],
            )
        else:
            # imagen
            datos = contenido
            if len(datos) > MAX_IMG_BYTES:
                datos = _comprimir_imagen(datos)
            b64 = base64.standard_b64encode(datos).decode()
            media_type = "image/jpeg" if extension in (".jpg", ".jpeg") else "image/png"
            mensaje = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                        {"type": "text", "text": _PROMPT_CLASIFICACION},
                    ],
                }],
            )

        raw = mensaje.content[0].text.strip()
        # Limpiar posibles bloques markdown que Claude a veces agrega
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)

    except json.JSONDecodeError:
        logger.warning("documento_service: JSON inválido de Claude — aplicando fallback")
        return {"tipo": "otro", "confianza": 0.0, "resumen": "Clasificación no disponible",
                "periodo": None, "cuit_detectado": None, "monto": None}
    except Exception as e:
        logger.error("documento_service: error llamando a Claude — %s", e)
        raise  # se captura en subir_documento para marcar estado=error


async def subir_documento(
    db: Session,
    cliente_id: int,
    file: UploadFile,
    vencimiento_id: Optional[int] = None,
) -> DocumentoResponse:
    # Validar cliente
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.activo == True).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    # Validar vencimiento si se proveyó
    if vencimiento_id is not None:
        venc = db.query(Vencimiento).filter(
            Vencimiento.id == vencimiento_id,
            Vencimiento.cliente_id == cliente_id,
        ).first()
        if not venc:
            raise HTTPException(status_code=404, detail="Vencimiento no encontrado para este cliente")

    # Validar extensión
    nombre_original = file.filename or "documento"
    ext = Path(nombre_original).suffix.lower()
    if ext not in EXTENSIONES_VALIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Extensión no permitida. Válidas: {', '.join(EXTENSIONES_VALIDAS)}",
        )

    # Leer contenido y validar tamaño
    contenido = await file.read()
    if len(contenido) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="Archivo demasiado grande. Máximo 10 MB.")

    # Detección de duplicados por hash SHA-256
    file_hash = _calcular_hash(contenido)
    doc_existente = db.query(Documento).filter(
        Documento.cliente_id == cliente_id,
        Documento.file_hash == file_hash,
        Documento.activo == True,
    ).first()
    if doc_existente:
        raise HTTPException(
            status_code=409,
            detail={
                "mensaje": "Este archivo ya fue subido anteriormente.",
                "documento_id": doc_existente.id,
                "nombre_original": doc_existente.nombre_original,
                "subido_el": doc_existente.created_at.isoformat(),
            }
        )

    # Guardar en disco
    directorio = _directorio_cliente(cliente_id)
    nombre_archivo = f"{uuid.uuid4().hex}_{nombre_original}"
    ruta = directorio / nombre_archivo
    ruta.write_bytes(contenido)

    # Crear registro en DB con estado pendiente
    doc = Documento(
        cliente_id=cliente_id,
        vencimiento_id=vencimiento_id,
        nombre_original=nombre_original,
        ruta_archivo=str(ruta.as_posix()),
        tipo_documento=TipoDocumento.otro,
        estado=EstadoDocumento.pendiente,
        file_hash=file_hash,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Clasificar con IA
    try:
        resultado = _clasificar_con_ia(ext, contenido)
        confianza = float(resultado.get("confianza") or 0.0)
        tipo_str = resultado.get("tipo", "otro")
        tipo = TipoDocumento(tipo_str) if tipo_str in TipoDocumento._value2member_map_ else TipoDocumento.otro
        estado = EstadoDocumento.procesado if confianza >= CONFIANZA_MIN_PROCESADO else EstadoDocumento.requiere_revision
        doc.tipo_documento = tipo
        doc.confianza = confianza
        doc.resumen = resultado.get("resumen")
        # Extraer vencimientos_relacionados con fallback al mapeo hardcodeado
        vencimientos_ia = resultado.get("vencimientos_relacionados")
        if isinstance(vencimientos_ia, list) and len(vencimientos_ia) > 0:
            tipos_validos = {t.value for t in TipoVencimiento}
            vencimientos_relacionados = [v for v in vencimientos_ia if v in tipos_validos]
            # Si todos los valores eran inválidos, usar fallback
            if not vencimientos_relacionados:
                vencimientos_relacionados = MAPEO_DOCUMENTO_VENCIMIENTO.get(tipo_str, [])
        else:
            vencimientos_relacionados = MAPEO_DOCUMENTO_VENCIMIENTO.get(tipo_str, [])

        doc.metadatos = {
            "periodo": resultado.get("periodo"),
            "cuit_detectado": resultado.get("cuit_detectado"),
            "monto": resultado.get("monto"),
            "vencimientos_relacionados": vencimientos_relacionados,
        }
        doc.estado = estado
    except Exception as e:
        logger.error("documento_service: clasificación fallida para doc %d — %s", doc.id, e)
        doc.estado = EstadoDocumento.error

    db.commit()
    db.refresh(doc)

    # Si el documento está asociado a un vencimiento, resolver las alertas abiertas de ese vencimiento
    if vencimiento_id is not None:
        try:
            alertas_abiertas = db.query(AlertaVencimiento).filter(
                AlertaVencimiento.vencimiento_id == vencimiento_id,
                AlertaVencimiento.resuelta_at == None,
            ).all()
            for alerta in alertas_abiertas:
                from datetime import datetime
                alerta.resuelta_at = datetime.utcnow()
            if alertas_abiertas:
                db.commit()
                logger.info(
                    "Documento %d — %d alerta(s) resueltas para vencimiento %d",
                    doc.id, len(alertas_abiertas), vencimiento_id,
                )
        except Exception as e:
            logger.error("Documento %d — error al resolver alertas: %s", doc.id, e)

    # Recalcular risk score del cliente (la documentación afecta la Variable 2)
    try:
        risk_service.calcular_score_cliente(db, cliente_id)
    except Exception as e:
        logger.error("Documento %d — error al recalcular risk score: %s", doc.id, e)

    logger.info("Documento %d subido — cliente %d, estado %s", doc.id, cliente_id, doc.estado.value)
    return DocumentoResponse.model_validate(doc)


def listar_documentos(db: Session, cliente_id: int) -> list[DocumentoResponse]:
    docs = (
        db.query(Documento)
        .filter(Documento.cliente_id == cliente_id, Documento.activo == True)
        .order_by(Documento.created_at.desc())
        .all()
    )
    return [DocumentoResponse.model_validate(d) for d in docs]


def actualizar_documento(db: Session, doc_id: int, data: DocumentoUpdate) -> DocumentoResponse:
    doc = db.query(Documento).filter(Documento.id == doc_id, Documento.activo == True).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(doc, campo, valor)
    # Si el contador corrigió manualmente el tipo, marcar como procesado
    if data.tipo_documento is not None:
        doc.estado = EstadoDocumento.procesado
    db.commit()
    db.refresh(doc)
    return DocumentoResponse.model_validate(doc)


def eliminar_documento(db: Session, doc_id: int) -> None:
    doc = db.query(Documento).filter(Documento.id == doc_id, Documento.activo == True).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    # Hard delete: borrar archivo físico
    ruta = Path(doc.ruta_archivo)
    if ruta.exists():
        ruta.unlink()
        logger.info("Archivo físico eliminado: %s", ruta)
    db.delete(doc)
    db.commit()


def obtener_checklist(
    db: Session,
    cliente_id: int,
    periodo: str,  # formato "YYYY-MM"
) -> dict:
    """
    Dado un cliente y un período fiscal, retorna qué documentos
    llegaron y cuáles faltan para cubrir los vencimientos activos.
    """
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.activo == True,
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    if len(periodo) != 7 or periodo[4] != "-":
        raise HTTPException(
            status_code=400,
            detail="Formato de período inválido. Usar YYYY-MM.",
        )
    try:
        anio, mes = int(periodo[:4]), int(periodo[5:7])
        if mes < 1 or mes > 12:
            raise ValueError()
    except (ValueError, IndexError):
        raise HTTPException(
            status_code=400,
            detail="Formato de período inválido. Usar YYYY-MM.",
        )

    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])

    # Paso 1 — Vencimientos activos del cliente en el período
    vencimientos_activos = db.query(Vencimiento).filter(
        Vencimiento.cliente_id == cliente_id,
        Vencimiento.estado == EstadoVencimiento.pendiente,
        Vencimiento.fecha_vencimiento >= primer_dia,
        Vencimiento.fecha_vencimiento <= ultimo_dia,
    ).all()

    # Paso 2 — Tipos de documento requeridos para esos vencimientos
    tipos_requeridos: set[str] = set()
    vencimientos_info = []
    for v in vencimientos_activos:
        docs_necesarios = MAPEO_VENCIMIENTO_DOCUMENTO.get(v.tipo.value, [])
        tipos_requeridos.update(docs_necesarios)
        vencimientos_info.append({
            "id": v.id,
            "tipo": v.tipo.value,
            "fecha_vencimiento": v.fecha_vencimiento.isoformat(),
            "documentos_necesarios": docs_necesarios,
        })

    # Paso 3 — Documentos recibidos del cliente en el período
    # Filtrado en Python para compatibilidad con SQLite y PostgreSQL
    todos_docs = db.query(Documento).filter(
        Documento.cliente_id == cliente_id,
        Documento.activo == True,
    ).all()
    documentos_periodo = [
        d for d in todos_docs
        if d.metadatos and d.metadatos.get("periodo") == periodo
    ]

    tipos_recibidos: set[str] = {d.tipo_documento.value for d in documentos_periodo}

    # Paso 4 — Cruzar requeridos vs recibidos
    faltantes = sorted(tipos_requeridos - tipos_recibidos)
    recibidos = sorted(tipos_requeridos & tipos_recibidos)
    extras = sorted(tipos_recibidos - tipos_requeridos)

    # Paso 5 — Completitud
    completitud_pct = (
        len(recibidos) / len(tipos_requeridos)
        if tipos_requeridos else 1.0
    )

    return {
        "cliente_id": cliente_id,
        "periodo": periodo,
        "vencimientos_activos": vencimientos_info,
        "tipos_requeridos": sorted(tipos_requeridos),
        "recibidos": recibidos,
        "faltantes": faltantes,
        "extras": extras,
        "completitud_pct": round(completitud_pct, 2),
        "completo": len(faltantes) == 0,
    }
