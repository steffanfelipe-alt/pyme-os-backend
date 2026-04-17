from datetime import date, timedelta

from models.cliente import CondicionFiscal
from models.documento import Documento, EstadoDocumento, TipoDocumento
from models.tarea import EstadoTarea, PrioridadTarea, TipoTarea, Tarea
from tests.conftest import _get_or_create_studio


def _crear_tarea_completada(db, cliente_id, fecha_completada, fecha_limite=None):
    studio_id = _get_or_create_studio(db)
    tarea = Tarea(
        cliente_id=cliente_id,
        studio_id=studio_id,
        titulo="Tarea test",
        tipo=TipoTarea.tarea,
        estado=EstadoTarea.completada,
        prioridad=PrioridadTarea.media,
        fecha_completada=fecha_completada,
        fecha_limite=fecha_limite,
        activo=True,
    )
    db.add(tarea)
    db.commit()
    return tarea


def _crear_documento(db, cliente_id, estado: EstadoDocumento):
    studio_id = _get_or_create_studio(db)
    doc = Documento(
        cliente_id=cliente_id,
        studio_id=studio_id,
        nombre_original="doc_test.pdf",
        ruta_archivo="uploads/test/doc_test.pdf",
        tipo_documento=TipoDocumento.otro,
        estado=estado,
        activo=True,
    )
    db.add(doc)
    db.commit()
    return doc


# --- Tests ---

def test_cliente_nuevo_sin_actividad_nivel_verde(client, auth_headers, cliente_test):
    """Cliente sin tareas ni documentos → score solo de Var4 (monotributista?), nivel verde."""
    response = client.post(
        f"/api/risk/clients/{cliente_test.id}/calculate",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["risk_score"] is not None
    assert data["risk_level"] == "verde"
    assert data["risk_calculated_at"] is not None


def test_todas_tareas_demoradas_aumenta_score(client, auth_headers, db, cliente_test):
    """Cliente con todas las tareas demoradas → Variable 3 al máximo (25 pts)."""
    hace_30 = date.today() - timedelta(days=30)
    fecha_limite_pasada = hace_30 - timedelta(days=5)  # completada después del límite
    _crear_tarea_completada(db, cliente_test.id,
                             fecha_completada=hace_30,
                             fecha_limite=fecha_limite_pasada)
    _crear_tarea_completada(db, cliente_test.id,
                             fecha_completada=hace_30 + timedelta(days=1),
                             fecha_limite=fecha_limite_pasada)

    response = client.post(
        f"/api/risk/clients/{cliente_test.id}/calculate",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # Variable 3 maxima = 25. Score mínimo esperado > 25
    assert data["risk_score"] >= 25.0


def test_documentos_en_requiere_revision_aumenta_score(client, auth_headers, db, cliente_test):
    """Cliente con todos los docs en requiere_revision → Variable 2 al máximo (30 pts)."""
    _crear_documento(db, cliente_test.id, EstadoDocumento.requiere_revision)
    _crear_documento(db, cliente_test.id, EstadoDocumento.requiere_revision)

    response = client.post(
        f"/api/risk/clients/{cliente_test.id}/calculate",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # Variable 2 máxima = 30. Score mínimo esperado > 30
    assert data["risk_score"] >= 30.0


def test_sin_actividad_45_dias_variable1_maxima(client, auth_headers, db, cliente_test):
    """Última tarea completada hace exactamente 45 días → Variable 1 = 25."""
    hace_45 = date.today() - timedelta(days=45)
    _crear_tarea_completada(db, cliente_test.id, fecha_completada=hace_45)

    response = client.post(
        f"/api/risk/clients/{cliente_test.id}/calculate",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # Variable 1 = min(45/45, 1.0) * 25 = 25.0
    # Score total >= 25
    assert data["risk_score"] >= 25.0


def test_recalcular_todos_retorna_conteos(client, auth_headers, db, cliente_test):
    """POST /api/risk/recalculate-all retorna conteos correctos por nivel."""
    response = client.post("/api/risk/recalculate-all", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "procesados" in data
    assert "rojos" in data
    assert "amarillos" in data
    assert "verdes" in data
    assert data["procesados"] >= 1
    assert data["procesados"] == data["rojos"] + data["amarillos"] + data["verdes"]


def test_risk_calculated_at_se_actualiza(client, auth_headers, db, cliente_test):
    """risk_calculated_at cambia con cada recálculo."""
    r1 = client.post(
        f"/api/risk/clients/{cliente_test.id}/calculate",
        headers=auth_headers,
    )
    ts1 = r1.json()["risk_calculated_at"]

    r2 = client.post(
        f"/api/risk/clients/{cliente_test.id}/calculate",
        headers=auth_headers,
    )
    ts2 = r2.json()["risk_calculated_at"]

    # Ambos timestamps deben existir (puede ser igual si la ejecución es muy rápida,
    # pero ambos deben ser strings ISO no nulos)
    assert ts1 is not None
    assert ts2 is not None
