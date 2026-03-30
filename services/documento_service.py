import base64
import json
import logging
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import HTTPException, UploadFile
from PIL import Image
from pypdf import PdfReader
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.documento import Documento, EstadoDocumento, TipoDocumento
from models.empleado import Empleado  # noqa: F401 — resuelve FK
from models.vencimiento import Vencimiento  # noqa: F401 — resuelve FK
from schemas.documento import DocumentoResponse, DocumentoUpdate

logger = logging.getLogger("pymeos")

UPLOADS_BASE = Path("uploads")
MAX_FILE_BYTES = 10 * 1024 * 1024   # 10 MB
MAX_IMG_BYTES = 2 * 1024 * 1024     # 2 MB — si supera, se comprime
MAX_PDF_PAGES = 3
MAX_TEXT_CHARS = 8000
EXTENSIONES_VALIDAS = {".pdf", ".jpg", ".jpeg", ".png"}
CONFIANZA_MIN_PROCESADO = 0.5

_PROMPT_CLASIFICACION = """Sos un asistente contable argentino. Analizá este documento y extraé la información solicitada.
Tipos de documento posibles: factura, liquidacion_sueldo, ddjj, recibo, extracto_bancario, balance, contrato, otro.
Respondé ÚNICAMENTE con JSON válido, sin texto adicional ni bloques de código:
{"tipo":"...","confianza":0.95,"resumen":"descripcion breve en español","periodo":"YYYY-MM o null","cuit_detectado":"XX-XXXXXXXX-X o null","monto":15000.00 o null}"""


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
        doc.metadatos = {
            "periodo": resultado.get("periodo"),
            "cuit_detectado": resultado.get("cuit_detectado"),
            "monto": resultado.get("monto"),
        }
        doc.estado = estado
    except Exception as e:
        logger.error("documento_service: clasificación fallida para doc %d — %s", doc.id, e)
        doc.estado = EstadoDocumento.error

    db.commit()
    db.refresh(doc)
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
