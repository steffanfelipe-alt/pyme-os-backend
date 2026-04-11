"""
Generación de PDFs de comprobantes electrónicos con reportlab.
"""
import io
import logging
import os
from datetime import date

logger = logging.getLogger("pymeos")


def generar_pdf_comprobante(comp, cliente_nombre: str, cliente_cuit: str) -> bytes:
    """
    Genera el PDF del comprobante en memoria y lo retorna como bytes.
    Requiere: pip install reportlab
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors
    except ImportError:
        raise RuntimeError("reportlab no está instalado. Ejecutá: pip install reportlab")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Header con tipo de comprobante
    tipo = comp.tipo_comprobante
    c.setFillColor(colors.HexColor("#1e40af"))
    c.rect(0, h - 60 * mm, w, 60 * mm, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(w / 2, h - 35 * mm, f"FACTURA {tipo}")
    c.setFont("Helvetica", 14)
    nombre_estudio = os.environ.get("STUDIO_NAME", "Estudio Contable")
    c.drawCentredString(w / 2, h - 50 * mm, nombre_estudio)

    # Datos del comprobante
    y = h - 75 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)

    def field(label: str, value: str, y_pos: float, x: float = 20 * mm):
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y_pos, label + ":")
        c.setFont("Helvetica", 9)
        c.drawString(x + 45 * mm, y_pos, str(value))

    num_str = f"{comp.punto_venta:04d}-{comp.numero_comprobante:08d}" if comp.numero_comprobante else "PENDIENTE"
    field("N° Comprobante", num_str, y)
    y -= 6 * mm
    field("Fecha emisión", comp.fecha_emision.strftime("%d/%m/%Y") if comp.fecha_emision else "—", y)
    y -= 6 * mm

    # Separador
    y -= 4 * mm
    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.line(20 * mm, y, w - 20 * mm, y)
    y -= 8 * mm

    # Datos receptor
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "DATOS DEL RECEPTOR")
    y -= 6 * mm
    field("Cliente", cliente_nombre, y)
    y -= 6 * mm
    field("CUIT", cliente_cuit, y)
    y -= 10 * mm

    # Concepto
    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.line(20 * mm, y, w - 20 * mm, y)
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "CONCEPTO")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    descripcion = comp.descripcion_concepto or "Honorarios profesionales"
    c.drawString(20 * mm, y, descripcion[:80])
    y -= 15 * mm

    # Importes
    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.line(20 * mm, y, w - 20 * mm, y)
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "IMPORTES")
    y -= 6 * mm
    field("Importe neto", f"$ {float(comp.importe_neto):,.2f}", y)
    y -= 6 * mm
    field(f"IVA {float(comp.alicuota_iva):.0f}%", f"$ {float(comp.importe_iva):,.2f}", y)
    y -= 6 * mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "TOTAL:")
    c.drawString(65 * mm, y, f"$ {float(comp.importe_total):,.2f}")
    y -= 15 * mm

    # CAE
    if comp.cae:
        c.setStrokeColor(colors.HexColor("#e5e7eb"))
        c.line(20 * mm, y, w - 20 * mm, y)
        y -= 8 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, "AUTORIZACIÓN AFIP")
        y -= 6 * mm
        field("CAE", comp.cae, y)
        y -= 6 * mm
        vto = comp.fecha_cae_vencimiento
        field("Vto. CAE", vto.strftime("%d/%m/%Y") if vto else "—", y)
        y -= 8 * mm

        # QR con datos del CAE (simplificado — código de barras como texto)
        c.setFont("Helvetica", 7)
        c.drawString(20 * mm, y, f"QR: {comp.cae}|{comp.punto_venta}|{comp.numero_comprobante}|{comp.tipo_comprobante}")

    c.save()
    buf.seek(0)
    return buf.read()


def generar_y_subir_pdf(comp, db) -> str:
    """
    Genera el PDF y lo sube a Supabase Storage.
    Retorna la URL pública del PDF.
    """
    from models.cliente import Cliente

    cliente = db.query(Cliente).filter(Cliente.id == comp.cliente_id).first()
    cliente_nombre = cliente.nombre if cliente else "Cliente"
    cliente_cuit = getattr(cliente, "cuit_cuil", "") if cliente else ""

    try:
        pdf_bytes = generar_pdf_comprobante(comp, cliente_nombre, cliente_cuit)
    except Exception as e:
        logger.error("Error generando PDF para comprobante %d: %s", comp.id, e)
        return ""

    # Intentar subir a Supabase Storage
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not supabase_url or not supabase_key:
        # Guardar localmente como fallback
        import pathlib
        studio_id = comp.studio_id or 0
        anio = comp.fecha_emision.year if comp.fecha_emision else date.today().year
        mes = comp.fecha_emision.month if comp.fecha_emision else date.today().month
        local_dir = pathlib.Path(f"uploads/comprobantes/{studio_id}/{anio}/{mes}")
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / f"{comp.id}.pdf"
        local_path.write_bytes(pdf_bytes)
        return f"/static/comprobantes/{studio_id}/{anio}/{mes}/{comp.id}.pdf"

    # Subir a Supabase
    import requests
    studio_id = comp.studio_id or 0
    anio = comp.fecha_emision.year
    mes = comp.fecha_emision.month
    path = f"{studio_id}/{anio}/{mes:02d}/{comp.id}.pdf"

    resp = requests.put(
        f"{supabase_url}/storage/v1/object/comprobantes/{path}",
        headers={
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/pdf",
        },
        data=pdf_bytes,
    )
    if resp.status_code in (200, 201):
        return f"{supabase_url}/storage/v1/object/public/comprobantes/{path}"

    logger.error("Error subiendo PDF a Supabase: %s %s", resp.status_code, resp.text[:200])
    return ""
