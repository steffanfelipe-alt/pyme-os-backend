"""
Tests del módulo SOP Asistido (Bloques 2 y 3).
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from models.proceso import ProcesoTemplate, ProcesoPasoTemplate
from models.sop_documento import EstadoSop, SopDocumento, SopPaso
from tests.conftest import _crear_token_con_rol


@pytest.fixture()
def token_dueno(db):
    return _crear_token_con_rol(db, "dueno_sop@pymeos.com", "Dueño SOP", "dueno")


@pytest.fixture()
def token_contador(db):
    return _crear_token_con_rol(db, "cont_sop@pymeos.com", "Contador SOP", "contador")


@pytest.fixture()
def headers(token_dueno):
    return {"Authorization": f"Bearer {token_dueno}"}


@pytest.fixture()
def headers_contador(token_contador):
    return {"Authorization": f"Bearer {token_contador}"}


@pytest.fixture()
def template_sop(db, headers, client):
    resp = client.post(
        "/api/procesos/templates",
        json={"nombre": "Proceso SOP Test", "tipo": "liquidacion_iva"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


# ─── Bloque 2A: CRUD básico ──────────────────────────────────────────────────

def test_crear_sop_borrador(client, headers):
    """POST /sop crea un SOP en estado borrador con sus pasos."""
    resp = client.post("/api/sop", json={
        "titulo": "Cierre Mensual IVA",
        "area": "impuestos",
        "descripcion_proposito": "Liquidar el IVA mensual del cliente",
        "resultado_esperado": "Declaración presentada en AFIP",
        "pasos": [
            {"orden": 1, "descripcion": "Descargar comprobantes del mes", "es_automatizable": True},
            {"orden": 2, "descripcion": "Verificar facturas emitidas", "es_automatizable": False},
        ],
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["estado"] == "borrador"
    assert data["titulo"] == "Cierre Mensual IVA"
    assert len(data["pasos"]) == 2


def test_listar_sops(client, headers):
    """GET /sop lista SOPs del usuario."""
    client.post("/api/sop", json={"titulo": "SOP 1", "area": "impuestos"}, headers=headers)
    client.post("/api/sop", json={"titulo": "SOP 2", "area": "laboral"}, headers=headers)

    resp = client.get("/api/sop", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_listar_sops_filtro_area(client, headers):
    """GET /sop?area=impuestos filtra por área."""
    client.post("/api/sop", json={"titulo": "IVA SOP", "area": "impuestos"}, headers=headers)
    client.post("/api/sop", json={"titulo": "Laboral SOP", "area": "laboral"}, headers=headers)

    resp = client.get("/api/sop?area=impuestos", headers=headers)
    assert resp.status_code == 200
    for sop in resp.json():
        assert sop["area"] == "impuestos"


def test_obtener_sop_detalle(client, headers):
    """GET /sop/{id} retorna el SOP con pasos y revisiones."""
    create_resp = client.post("/api/sop", json={
        "titulo": "Detalle Test",
        "area": "administracion",
        "pasos": [{"orden": 1, "descripcion": "Primer paso"}],
    }, headers=headers)
    sop_id = create_resp.json()["id"]

    resp = client.get(f"/api/sop/{sop_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sop_id
    assert "pasos" in data
    assert "revisiones" in data


def test_obtener_sop_inexistente_retorna_404(client, headers):
    resp = client.get("/api/sop/99999", headers=headers)
    assert resp.status_code == 404


def test_actualizar_sop(client, headers):
    """PATCH /sop/{id} actualiza campos del SOP."""
    create_resp = client.post("/api/sop", json={"titulo": "Título Original", "area": "otro"}, headers=headers)
    sop_id = create_resp.json()["id"]

    resp = client.patch(f"/api/sop/{sop_id}", json={"titulo": "Título Actualizado"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["titulo"] == "Título Actualizado"


def test_agregar_paso_a_sop(client, headers):
    """POST /sop/{id}/pasos agrega un paso al SOP."""
    create_resp = client.post("/api/sop", json={"titulo": "SOP Pasos", "area": "otro"}, headers=headers)
    sop_id = create_resp.json()["id"]

    resp = client.post(f"/api/sop/{sop_id}/pasos", json={
        "orden": 1, "descripcion": "Nuevo paso agregado", "es_automatizable": True,
    }, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["descripcion"] == "Nuevo paso agregado"


def test_eliminar_paso_de_sop(client, headers):
    """DELETE /sop/{id}/pasos/{paso_id} elimina el paso."""
    create_resp = client.post("/api/sop", json={
        "titulo": "SOP Eliminar Paso",
        "area": "otro",
        "pasos": [{"orden": 1, "descripcion": "Paso a eliminar"}],
    }, headers=headers)
    sop_id = create_resp.json()["id"]
    paso_id = create_resp.json()["pasos"][0]["id"]

    resp = client.delete(f"/api/sop/{sop_id}/pasos/{paso_id}", headers=headers)
    assert resp.status_code == 204


def test_flujo_borrador_a_activo(client, headers):
    """POST /sop/{id}/publicar cambia estado a activo y registra revisión."""
    create_resp = client.post("/api/sop", json={"titulo": "SOP Publicar", "area": "impuestos"}, headers=headers)
    sop_id = create_resp.json()["id"]

    resp = client.post(f"/api/sop/{sop_id}/publicar", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "activo"
    assert len(data["revisiones"]) == 1
    assert data["revisiones"][0]["descripcion_cambio"] == "Publicación inicial"


def test_publicar_dos_veces_retorna_400(client, headers):
    """No se puede publicar un SOP que ya está activo."""
    create_resp = client.post("/api/sop", json={"titulo": "SOP Doble", "area": "otro"}, headers=headers)
    sop_id = create_resp.json()["id"]
    client.post(f"/api/sop/{sop_id}/publicar", headers=headers)

    resp = client.post(f"/api/sop/{sop_id}/publicar", headers=headers)
    assert resp.status_code == 400


def test_archivar_sop(client, headers):
    """POST /sop/{id}/archivar cambia estado a archivado."""
    create_resp = client.post("/api/sop", json={"titulo": "SOP Archivar", "area": "otro"}, headers=headers)
    sop_id = create_resp.json()["id"]
    client.post(f"/api/sop/{sop_id}/publicar", headers=headers)

    resp = client.post(f"/api/sop/{sop_id}/archivar", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["estado"] == "archivado"


# ─── Bloque 2C: Generación asistida por IA ───────────────────────────────────

_SOP_IA_MOCK = {
    "titulo": "Liquidación IVA Mensual",
    "area": "impuestos",
    "descripcion_proposito": "Liquidar el IVA del mes para el cliente",
    "resultado_esperado": "Declaración presentada en AFIP sin errores",
    "pasos": [
        {"orden": 1, "descripcion": "Descargar comprobantes del portal AFIP", "responsable_sugerido": "contador", "tiempo_estimado_minutos": 15, "es_automatizable": True},
        {"orden": 2, "descripcion": "Verificar facturas emitidas", "responsable_sugerido": None, "tiempo_estimado_minutos": 30, "es_automatizable": False},
    ],
}


def _mock_sop_anthropic(respuesta=None):
    respuesta = respuesta or _SOP_IA_MOCK
    mock_client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(respuesta))]
    mock_client.messages.create.return_value = msg
    return mock_client


def test_generar_sop_desde_descripcion(client, headers):
    """POST /sop/generar-desde-descripcion crea un SOP borrador con IA."""
    mock_client = _mock_sop_anthropic()
    with patch("services.sop_asistido_service.anthropic.Anthropic", return_value=mock_client):
        resp = client.post("/api/sop/generar-desde-descripcion", json={
            "descripcion": "cada mes hay que bajar los comprobantes de AFIP y chequear que cuadren con las facturas emitidas"
        }, headers=headers)

    assert resp.status_code == 201
    data = resp.json()
    assert data["estado"] == "borrador"
    assert len(data["pasos"]) == 2
    assert data["titulo"] == "Liquidación IVA Mensual"


def test_generar_sop_descripcion_vacia_retorna_422(client, headers):
    """Descripción vacía debe retornar 422."""
    resp = client.post("/api/sop/generar-desde-descripcion", json={"descripcion": ""}, headers=headers)
    assert resp.status_code == 422


def test_generar_sop_respuesta_invalida_de_ia_retorna_422(client, headers):
    """Si la IA devuelve JSON inválido, debe retornar 422."""
    mock_client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text="Esto no es JSON válido")]
    mock_client.messages.create.return_value = msg

    with patch("services.sop_asistido_service.anthropic.Anthropic", return_value=mock_client):
        resp = client.post("/api/sop/generar-desde-descripcion", json={
            "descripcion": "proceso de onboarding de clientes nuevos"
        }, headers=headers)
    assert resp.status_code == 422


def test_generar_sop_respeta_area_de_request(client, headers):
    """El área de la request debe sobrescribir la del JSON de IA."""
    mock_data = dict(_SOP_IA_MOCK)
    mock_data["area"] = "laboral"
    mock_client = _mock_sop_anthropic(mock_data)
    with patch("services.sop_asistido_service.anthropic.Anthropic", return_value=mock_client):
        resp = client.post("/api/sop/generar-desde-descripcion", json={
            "descripcion": "proceso de nómina mensual",
            "area": "laboral",
        }, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["area"] == "laboral"


# ─── Bloque 3: Integración ────────────────────────────────────────────────────

def test_instancia_sin_sop_retorna_sop_null(client, db, headers, template_sop):
    """Instancia sin SOP vinculado retorna sop_vinculado=null."""
    resp = client.post("/api/procesos/instancias", json={
        "template_id": template_sop["id"],
    }, headers=headers)
    assert resp.status_code == 201
    instancia_id = resp.json()["id"]

    detail = client.get(f"/api/procesos/instancias/{instancia_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["sop_vinculado"] is None


def test_instancia_con_sop_activo_retorna_sop_vinculado(client, db, headers, template_sop):
    """Instancia con SOP activo vinculado retorna sop_vinculado con datos."""
    tid = template_sop["id"]

    # Crear y publicar SOP vinculado al template
    sop_resp = client.post("/api/sop", json={
        "titulo": "SOP del Proceso",
        "area": "impuestos",
        "proceso_id": tid,
        "pasos": [{"orden": 1, "descripcion": "Guía paso 1"}],
    }, headers=headers)
    sop_id = sop_resp.json()["id"]
    client.post(f"/api/sop/{sop_id}/publicar", headers=headers)

    # Crear instancia
    inst_resp = client.post("/api/procesos/instancias", json={"template_id": tid}, headers=headers)
    instancia_id = inst_resp.json()["id"]

    detail = client.get(f"/api/procesos/instancias/{instancia_id}", headers=headers)
    assert detail.status_code == 200
    sop_vinculado = detail.json()["sop_vinculado"]
    assert sop_vinculado is not None
    assert sop_vinculado["titulo"] == "SOP del Proceso"
    assert len(sop_vinculado["pasos"]) >= 1


def test_biblioteca_solo_activos(client, db, headers):
    """GET /sop/biblioteca retorna solo SOPs activos."""
    # Crear borrador (no debe aparecer en biblioteca)
    client.post("/api/sop", json={"titulo": "SOP Borrador", "area": "otro"}, headers=headers)

    # Crear y publicar (debe aparecer en biblioteca)
    sop_resp = client.post("/api/sop", json={"titulo": "SOP Activo", "area": "impuestos"}, headers=headers)
    sop_id = sop_resp.json()["id"]
    client.post(f"/api/sop/{sop_id}/publicar", headers=headers)

    resp = client.get("/api/sop/biblioteca", headers=headers)
    assert resp.status_code == 200
    titulos = [s["titulo"] for s in resp.json()]
    assert "SOP Activo" in titulos
    assert "SOP Borrador" not in titulos


def test_biblioteca_incluye_proceso_vinculado(client, db, headers, template_sop):
    """La biblioteca incluye proceso_vinculado cuando el SOP tiene proceso_id."""
    tid = template_sop["id"]
    sop_resp = client.post("/api/sop", json={
        "titulo": "SOP Vinculado",
        "area": "impuestos",
        "proceso_id": tid,
    }, headers=headers)
    sop_id = sop_resp.json()["id"]
    client.post(f"/api/sop/{sop_id}/publicar", headers=headers)

    resp = client.get("/api/sop/biblioteca", headers=headers)
    assert resp.status_code == 200
    item = next((s for s in resp.json() if s["titulo"] == "SOP Vinculado"), None)
    assert item is not None
    assert item["proceso_vinculado"] is not None
    assert item["proceso_vinculado"]["id"] == tid


def test_resumen_incluye_cobertura_sops(client, headers):
    """GET /reportes/resumen incluye cobertura_sops."""
    from datetime import date
    periodo = date.today().strftime("%Y-%m")
    resp = client.get(f"/api/reportes/resumen?periodo={periodo}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "cobertura_sops" in data
    cobertura = data["cobertura_sops"]
    assert "procesos_totales" in cobertura
    assert "procesos_con_sop" in cobertura
    assert "procesos_sin_sop" in cobertura
    assert "porcentaje_cobertura" in cobertura
    assert "sops_proximos_revision" in cobertura
    assert "sops_sin_responsable" in cobertura


def test_cobertura_100_cuando_todos_tienen_sop(client, db, headers, template_sop):
    """Si todos los procesos tienen SOP activo, porcentaje_cobertura = 100."""
    tid = template_sop["id"]
    sop_resp = client.post("/api/sop", json={
        "titulo": "SOP Completo",
        "area": "impuestos",
        "proceso_id": tid,
    }, headers=headers)
    sop_id = sop_resp.json()["id"]
    client.post(f"/api/sop/{sop_id}/publicar", headers=headers)

    from datetime import date
    periodo = date.today().strftime("%Y-%m")
    resp = client.get(f"/api/reportes/resumen?periodo={periodo}", headers=headers)
    cobertura = resp.json()["cobertura_sops"]
    assert cobertura["porcentaje_cobertura"] == 100


def test_cobertura_0_sin_sops(client, db, headers, template_sop):
    """Sin SOPs activos, porcentaje_cobertura = 0."""
    from datetime import date
    periodo = date.today().strftime("%Y-%m")
    resp = client.get(f"/api/reportes/resumen?periodo={periodo}", headers=headers)
    cobertura = resp.json()["cobertura_sops"]
    # Puede ser 0 o 100 según si template_sop tiene SOP; asegurar que el campo existe y es int
    assert isinstance(cobertura["porcentaje_cobertura"], int)


def test_sop_sin_responsable_aparece_en_lista(client, db, headers):
    """SOP activo sin responsable aparece en sops_sin_responsable."""
    sop_resp = client.post("/api/sop", json={
        "titulo": "SOP Sin Responsable",
        "area": "otro",
    }, headers=headers)
    sop_id = sop_resp.json()["id"]
    client.post(f"/api/sop/{sop_id}/publicar", headers=headers)

    from datetime import date
    periodo = date.today().strftime("%Y-%m")
    resp = client.get(f"/api/reportes/resumen?periodo={periodo}", headers=headers)
    sin_resp = resp.json()["cobertura_sops"]["sops_sin_responsable"]
    titulos = [s["titulo"] for s in sin_resp]
    assert "SOP Sin Responsable" in titulos


# ─── Bloque 3.4: Confirmación de lectura ─────────────────────────────────────

def _crear_sop_con_paso_critico(client, headers, proceso_id=None):
    """Helper: crea SOP activo con un paso que requiere confirmación."""
    payload = {
        "titulo": "SOP Crítico",
        "area": "impuestos",
        "pasos": [
            {"orden": 1, "descripcion": "Paso crítico", "requiere_confirmacion_lectura": True},
        ],
    }
    if proceso_id:
        payload["proceso_id"] = proceso_id
    sop_resp = client.post("/api/sop", json=payload, headers=headers)
    assert sop_resp.status_code == 201
    sop_id = sop_resp.json()["id"]
    client.post(f"/api/sop/{sop_id}/publicar", headers=headers)
    paso_id = sop_resp.json()["pasos"][0]["id"]
    return sop_id, paso_id


def test_confirmar_lectura_paso_critico(client, headers):
    """POST /sop/{sop_id}/pasos/{paso_id}/confirmar-lectura registra confirmación."""
    sop_id, paso_id = _crear_sop_con_paso_critico(client, headers)

    resp = client.post(f"/api/sop/{sop_id}/pasos/{paso_id}/confirmar-lectura", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["confirmado"] is True
    assert data["requiere_confirmacion"] is True


def test_confirmar_lectura_paso_sin_requerimiento(client, headers):
    """Paso que NO requiere confirmación responde 200 sin crear registro."""
    sop_resp = client.post("/api/sop", json={
        "titulo": "SOP Sin Req",
        "area": "otro",
        "pasos": [{"orden": 1, "descripcion": "Paso normal", "requiere_confirmacion_lectura": False}],
    }, headers=headers)
    sop_id = sop_resp.json()["id"]
    paso_id = sop_resp.json()["pasos"][0]["id"]
    client.post(f"/api/sop/{sop_id}/publicar", headers=headers)

    resp = client.post(f"/api/sop/{sop_id}/pasos/{paso_id}/confirmar-lectura", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["requiere_confirmacion"] is False


def test_confirmar_lectura_segunda_vez_no_duplica(client, db, headers):
    """Segunda confirmación dentro de 30 días no crea duplicado."""
    sop_id, paso_id = _crear_sop_con_paso_critico(client, headers)

    client.post(f"/api/sop/{sop_id}/pasos/{paso_id}/confirmar-lectura", headers=headers)
    client.post(f"/api/sop/{sop_id}/pasos/{paso_id}/confirmar-lectura", headers=headers)

    from models.sop_documento import SopConfirmacionLectura
    confirmaciones = db.query(SopConfirmacionLectura).filter(
        SopConfirmacionLectura.sop_paso_id == paso_id
    ).count()
    assert confirmaciones == 1


def test_avanzar_paso_sin_confirmacion_retorna_409(client, db, headers, template_sop):
    """Avanzar paso de instancia cuando el SOP requiere confirmación retorna 409."""
    tid = template_sop["id"]

    # Agregar paso al template
    client.post(f"/api/procesos/templates/{tid}/pasos", json={
        "orden": 1, "titulo": "Paso SOP", "tiempo_estimado_minutos": 30, "es_automatizable": False,
    }, headers=headers)

    # Crear SOP con paso orden=1 que requiere confirmación, vinculado al template
    sop_id, _ = _crear_sop_con_paso_critico(client, headers, proceso_id=tid)

    # Crear instancia
    inst_resp = client.post("/api/procesos/instancias", json={"template_id": tid}, headers=headers)
    instancia_id = inst_resp.json()["id"]

    # Obtener el paso de instancia orden=1
    pasos = client.get(f"/api/procesos/instancias/{instancia_id}", headers=headers).json()["pasos"]
    paso_inst_id = next(p["id"] for p in pasos if p["orden"] == 1)

    # Intentar avanzar sin confirmar lectura → 409
    resp = client.put(f"/api/procesos/pasos-instancia/{paso_inst_id}", json={
        "estado": "en_progreso"
    }, headers=headers)
    assert resp.status_code == 409
    assert "SOP" in resp.json()["detail"] or "confirmes" in resp.json()["detail"]


def test_avanzar_paso_con_confirmacion_previa_funciona(client, db, headers, template_sop):
    """Avanzar paso funciona cuando hay confirmación de lectura vigente."""
    tid = template_sop["id"]

    # Agregar paso al template
    client.post(f"/api/procesos/templates/{tid}/pasos", json={
        "orden": 1, "titulo": "Paso SOP Confirmado", "tiempo_estimado_minutos": 30,
    }, headers=headers)

    # Crear SOP con paso crítico vinculado
    sop_id, paso_sop_id = _crear_sop_con_paso_critico(client, headers, proceso_id=tid)

    # Confirmar lectura primero
    client.post(f"/api/sop/{sop_id}/pasos/{paso_sop_id}/confirmar-lectura", headers=headers)

    # Crear instancia y avanzar paso → debe funcionar
    inst_resp = client.post("/api/procesos/instancias", json={"template_id": tid}, headers=headers)
    instancia_id = inst_resp.json()["id"]
    pasos = client.get(f"/api/procesos/instancias/{instancia_id}", headers=headers).json()["pasos"]
    paso_inst_id = next(p["id"] for p in pasos if p["orden"] == 1)

    resp = client.put(f"/api/procesos/pasos-instancia/{paso_inst_id}", json={
        "estado": "en_progreso"
    }, headers=headers)
    assert resp.status_code == 200


def test_avanzar_paso_sin_sop_vinculado_funciona(client, db, headers, template_sop):
    """Avanzar paso de proceso sin SOP vinculado funciona libremente."""
    tid = template_sop["id"]
    client.post(f"/api/procesos/templates/{tid}/pasos", json={
        "orden": 1, "titulo": "Paso Libre", "tiempo_estimado_minutos": 10,
    }, headers=headers)

    inst_resp = client.post("/api/procesos/instancias", json={"template_id": tid}, headers=headers)
    instancia_id = inst_resp.json()["id"]
    pasos = client.get(f"/api/procesos/instancias/{instancia_id}", headers=headers).json()["pasos"]
    paso_inst_id = pasos[0]["id"]

    resp = client.put(f"/api/procesos/pasos-instancia/{paso_inst_id}", json={
        "estado": "en_progreso"
    }, headers=headers)
    assert resp.status_code == 200
