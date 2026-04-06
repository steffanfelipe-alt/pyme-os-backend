"""
Tests del diagnóstico de madurez (Bloque 4).
"""
from datetime import datetime, timedelta

import pytest

from models.proceso import (
    Automatizacion, EstadoInstancia, EstadoRevisionAutomatizacion,
    ProcesoInstancia, ProcesoTemplate, TipoProceso,
)
from models.sop_documento import EstadoSop, SopDocumento
from tests.conftest import _crear_token_con_rol


@pytest.fixture()
def token_dueno(db):
    return _crear_token_con_rol(db, "dueno_mad@pymeos.com", "Dueño Madurez", "dueno")


@pytest.fixture()
def headers(token_dueno):
    return {"Authorization": f"Bearer {token_dueno}"}


def _crear_templates(db, cantidad: int) -> list[ProcesoTemplate]:
    templates = []
    for i in range(cantidad):
        t = ProcesoTemplate(
            nombre=f"Proceso {i+1}",
            tipo=TipoProceso.liquidacion_iva,
            activo=True,
        )
        db.add(t)
        templates.append(t)
    db.commit()
    for t in templates:
        db.refresh(t)
    return templates


def _crear_instancias_completadas(db, template_id: int, cantidad: int):
    """Crea instancias completadas en los últimos 90 días."""
    for i in range(cantidad):
        inst = ProcesoInstancia(
            template_id=template_id,
            estado=EstadoInstancia.completado,
            fecha_inicio=datetime.utcnow() - timedelta(days=5),
            fecha_fin=datetime.utcnow() - timedelta(days=1),
        )
        db.add(inst)
    db.commit()


def _crear_sops_activos(db, cantidad: int, proceso_id: int = None) -> list[SopDocumento]:
    sops = []
    for i in range(cantidad):
        s = SopDocumento(
            titulo=f"SOP {i+1}",
            area="impuestos",
            estado=EstadoSop.activo,
            fecha_ultima_revision=datetime.utcnow(),
            proceso_id=proceso_id,
        )
        db.add(s)
        sops.append(s)
    db.commit()
    for s in sops:
        db.refresh(s)
    return sops


def _crear_automatizaciones_aprobadas(db, template_id: int, cantidad: int):
    for i in range(cantidad):
        a = Automatizacion(
            template_id=template_id,
            ahorro_horas_mes=5.0,
            estado_revision=EstadoRevisionAutomatizacion.aprobada,
            aprobado_at=datetime.utcnow(),
        )
        db.add(a)
    db.commit()


# ─── Tests de estructura ────────────────────────────────────────────────────

def test_madurez_estructura_respuesta(client, headers):
    """GET /reportes/madurez retorna la estructura correcta."""
    resp = client.get("/api/reportes/madurez", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "etapa" in data
    assert "indicadores" in data
    assert "proximos_pasos" in data
    assert "numero" in data["etapa"]
    assert "nombre" in data["etapa"]
    assert isinstance(data["proximos_pasos"], list)


def test_madurez_etapa1_survival(client, db, headers):
    """Sin procesos ni SOPs → Etapa 1 Survival."""
    resp = client.get("/api/reportes/madurez", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["etapa"]["numero"] == 1
    assert data["etapa"]["nombre"] == "Survival"
    assert len(data["proximos_pasos"]) > 0


def test_madurez_etapa2_stationary_con_procesos(client, db, headers):
    """Con 3+ procesos activos → al menos Etapa 2 Stationary."""
    _crear_templates(db, 3)

    resp = client.get("/api/reportes/madurez", headers=headers)
    data = resp.json()
    assert data["etapa"]["numero"] >= 2
    assert data["etapa"]["nombre"] == "Stationary"
    assert data["indicadores"]["procesos_activos"] >= 3


def test_madurez_etapa2_stationary_con_sop(client, db, headers):
    """Con 1+ SOPs activos → al menos Etapa 2 Stationary."""
    _crear_sops_activos(db, 1)

    resp = client.get("/api/reportes/madurez", headers=headers)
    data = resp.json()
    assert data["etapa"]["numero"] >= 2


def test_madurez_etapa3_scalable(client, db, headers):
    """Con 5+ procesos, 1+ SOPs y 1+ automatizaciones aprobadas → Etapa 3 Scalable."""
    templates = _crear_templates(db, 5)
    _crear_sops_activos(db, 1)
    _crear_automatizaciones_aprobadas(db, templates[0].id, 1)

    resp = client.get("/api/reportes/madurez", headers=headers)
    data = resp.json()
    # Puede ser 3 o 4 dependiendo de la eficiencia
    assert data["etapa"]["numero"] >= 3
    assert data["indicadores"]["procesos_activos"] >= 5
    assert data["indicadores"]["sops_activos"] >= 1
    assert data["indicadores"]["automatizaciones_aprobadas"] >= 1


def test_madurez_indicadores_instancias_90d(client, db, headers):
    """Los indicadores incluyen instancias completadas en los últimos 90 días."""
    templates = _crear_templates(db, 1)
    _crear_instancias_completadas(db, templates[0].id, 3)

    resp = client.get("/api/reportes/madurez", headers=headers)
    data = resp.json()
    assert data["indicadores"]["instancias_completadas_90d"] >= 3


def test_madurez_proximos_pasos_etapa1(client, db, headers):
    """Etapa 1 muestra pasos para empezar a documentar."""
    resp = client.get("/api/reportes/madurez", headers=headers)
    data = resp.json()
    if data["etapa"]["numero"] == 1:
        pasos = " ".join(p["descripcion"] for p in data["proximos_pasos"]).lower()
        assert any(k in pasos for k in ["proceso", "sop", "instancia"])


def test_madurez_requiere_autenticacion(client):
    """Sin token → 403."""
    resp = client.get("/api/reportes/madurez")
    assert resp.status_code == 403


def test_madurez_no_accesible_para_contador(client, db):
    """Solo el dueño puede ver el diagnóstico de madurez."""
    token = _crear_token_con_rol(db, "cont_mad@pymeos.com", "Contador Mad", "contador")
    resp = client.get("/api/reportes/madurez", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
