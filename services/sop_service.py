"""
Generación de SOPs en PDF usando reportlab.
"""
import logging
import os

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.proceso import ProcesoTemplate, ProcesoPasoTemplate

logger = logging.getLogger("pymeos")


def generar_sop_pdf(db: Session, template_id: int) -> str:
    """
    Genera un PDF SOP para el template y retorna la ruta relativa.
    Actualiza sop_url y sop_version en el template.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors

    template = db.query(ProcesoTemplate).filter(
        ProcesoTemplate.id == template_id, ProcesoTemplate.activo == True
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template no encontrado")

    pasos = (
        db.query(ProcesoPasoTemplate)
        .filter(ProcesoPasoTemplate.template_id == template_id)
        .order_by(ProcesoPasoTemplate.orden)
        .all()
    )

    os.makedirs("uploads/sops", exist_ok=True)
    nueva_version = template.sop_version + (1 if template.sop_url else 0)
    nombre_archivo = f"sop_{template_id}_v{nueva_version}.pdf"
    ruta_disco = f"uploads/sops/{nombre_archivo}"
    # URL servida por FastAPI StaticFiles: /uploads/sops/...
    ruta_url = f"/uploads/sops/{nombre_archivo}"

    doc = SimpleDocTemplate(
        ruta_disco,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle(
        "Titulo",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=6,
    )
    subtitulo_style = ParagraphStyle(
        "Subtitulo",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=20,
    )
    paso_titulo_style = ParagraphStyle(
        "PasoTitulo",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=12,
        spaceAfter=4,
    )
    paso_desc_style = ParagraphStyle(
        "PasoDesc",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=4,
        leftIndent=10,
    )

    story = []
    story.append(Paragraph(f"SOP: {template.nombre}", titulo_style))
    tipo_label = template.tipo.value.replace("_", " ").title()
    story.append(Paragraph(f"Tipo: {tipo_label} — Versión {nueva_version}", subtitulo_style))

    if template.descripcion:
        story.append(Paragraph(template.descripcion, styles["Normal"]))
        story.append(Spacer(1, 0.3 * cm))

    if template.tiempo_estimado_minutos:
        horas = template.tiempo_estimado_minutos // 60
        minutos = template.tiempo_estimado_minutos % 60
        tiempo_str = f"{horas}h {minutos}min" if horas else f"{minutos}min"
        story.append(Paragraph(f"Tiempo estimado total: {tiempo_str}", styles["Normal"]))
        story.append(Spacer(1, 0.5 * cm))

    if pasos:
        story.append(Paragraph("Pasos del proceso", styles["Heading1"]))
        for paso in pasos:
            auto_label = " [Automatizable]" if paso.es_automatizable else ""
            story.append(Paragraph(f"{paso.orden}. {paso.titulo}{auto_label}", paso_titulo_style))
            if paso.descripcion:
                story.append(Paragraph(paso.descripcion, paso_desc_style))
            if paso.tiempo_estimado_minutos:
                story.append(
                    Paragraph(
                        f"Tiempo estimado: {paso.tiempo_estimado_minutos} min",
                        ParagraphStyle("mini", parent=styles["Normal"], fontSize=9, textColor=colors.grey, leftIndent=10),
                    )
                )
    else:
        story.append(Paragraph("Este proceso no tiene pasos definidos.", styles["Normal"]))

    doc.build(story)

    template.sop_url = ruta_url
    template.sop_version = nueva_version
    db.commit()
    db.refresh(template)

    logger.info("SOP generado: %s (template_id=%s, v%s)", ruta_url, template_id, nueva_version)
    return ruta_url
