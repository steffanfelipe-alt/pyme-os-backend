"""
Tests del módulo de emails entrantes.
Gmail API y Claude API se mockean con respuestas fijas.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from models.cliente import Cliente, CondicionFiscal, TipoPersona
from models.email_entrante import EmailEntrante
from models.empleado import Empleado, RolEmpleado


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _crear_empleado(db, nombre: str, email: str, rol: RolEmpleado) -> Empleado:
    e = Empleado(nombre=nombre, email=email, rol=rol, activo=True)
    db.add(e)
    db.flush()
    return e


def _crear_cliente(db, nombre: str, cuit: str, contador_id: int | None = None) -> Cliente:
    c = Cliente(
        tipo_persona=TipoPersona.juridica,
        nombre=nombre,
        cuit_cuil=cuit,
        condicion_fiscal=CondicionFiscal.responsable_inscripto,
        activo=True,
        contador_asignado_id=contador_id,
    )
    db.add(c)
    db.flush()
    return c


def _crear_email(db, **kwargs) -> EmailEntrante:
    defaults = dict(
        remitente="cliente@ejemplo.com",
        asunto="Consulta",
        cuerpo_texto="Hola",
        fecha_recibido=datetime(2026, 4, 1, 10, 0),
        estado="no_leido",
        requiere_respuesta=False,
        requiere_revision_manual=False,
        tiene_adjuntos=False,
    )
    defaults.update(kwargs)
    email = EmailEntrante(**defaults)
    db.add(email)
    db.commit()
    db.refresh(email)
    return email


# ---------------------------------------------------------------------------
# test_clasificacion_email_cliente
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clasificacion_email_cliente(db):
    """Email de un cliente conocido: se clasifica y se asigna a su contador."""
    from unittest.mock import AsyncMock
    from services.email_clasificador import clasificar_email
    from services.email_router_service import procesar_email_entrante

    contador = _crear_empleado(db, "Contador", "cnt@estudio.com", RolEmpleado.contador)
    cliente = _crear_cliente(db, "García SA", "20-11111111-1", contador.id)
    db.commit()

    with patch("services.email_clasificador.anthropic.AsyncAnthropic") as mock_anthropic:
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text='{"categoria":"consulta_fiscal","urgencia":"media","resumen":"El cliente pregunta sobre IVA.","remitente_tipo":"cliente_registrado","requiere_respuesta":true,"borrador_respuesta":"Estimado cliente...","cliente_cuit":"20-11111111-1","confianza":0.9}')]
        mock_anthropic.return_value.messages.create = AsyncMock(return_value=mock_msg)

        resultado = await clasificar_email(
            remitente="garcia@empresa.com",
            asunto="Consulta IVA",
            cuerpo="Quisiera saber sobre IVA",
            clientes_registrados=[{"nombre": "García SA", "cuit_cuil": "20-11111111-1"}],
        )

    assert resultado["categoria"] == "consulta_fiscal"
    assert resultado["cliente_cuit"] == "20-11111111-1"
    assert resultado["requiere_revision_manual"] is False  # confianza alta, urgencia media

    # Routing
    email = _crear_email(db, remitente="garcia@empresa.com")
    procesar_email_entrante(email, resultado, db)
    db.commit()

    assert email.asignado_a == contador.id
    assert email.cliente_id == cliente.id
    assert email.categoria == "consulta_fiscal"


# ---------------------------------------------------------------------------
# test_clasificacion_postulacion
# ---------------------------------------------------------------------------

def test_clasificacion_postulacion(db):
    """Email con CV se clasifica como postulacion_laboral y va a RRHH."""
    from services.email_router_service import determinar_destinatario

    rrhh_emp = _crear_empleado(db, "RRHH Test", "rrhh@estudio.com", RolEmpleado.rrhh)
    db.commit()

    clasificacion = {
        "categoria": "postulacion_laboral",
        "urgencia": "baja",
        "cliente_cuit": None,
    }

    destinatario_id = determinar_destinatario(clasificacion, db)
    assert destinatario_id == rrhh_emp.id


# ---------------------------------------------------------------------------
# test_urgencia_alta_notifica_dueno
# ---------------------------------------------------------------------------

def test_urgencia_alta_notifica_dueno(db):
    """Email urgente llega al destinatario correcto Y se crea copia para el dueño."""
    from services.email_router_service import procesar_email_entrante

    dueno = _crear_empleado(db, "Dueño", "dueno@estudio.com", RolEmpleado.dueno)
    contador = _crear_empleado(db, "Contador2", "cnt2@estudio.com", RolEmpleado.contador)
    cliente = _crear_cliente(db, "Urgente SA", "20-22222222-2", contador.id)
    db.commit()

    clasificacion = {
        "categoria": "consulta_fiscal",
        "urgencia": "alta",
        "resumen": "Urgente.",
        "remitente_tipo": "cliente_registrado",
        "requiere_respuesta": True,
        "borrador_respuesta": "...",
        "cliente_cuit": "20-22222222-2",
        "confianza": 0.85,
        "requiere_revision_manual": True,
        "motivo_revision": "urgencia_alta",
    }

    email = _crear_email(db, remitente="urgente@empresa.com")
    procesar_email_entrante(email, clasificacion, db)
    db.commit()

    # El email principal va al contador
    assert email.asignado_a == contador.id

    # Se creó una copia para el dueño
    copia = db.query(EmailEntrante).filter(
        EmailEntrante.asignado_a == dueno.id,
        EmailEntrante.remitente == "urgente@empresa.com",
    ).first()
    assert copia is not None
    assert "URGENTE" in copia.asunto


# ---------------------------------------------------------------------------
# test_contador_no_ve_emails_de_otro_contador
# ---------------------------------------------------------------------------

def test_contador_no_ve_emails_de_otro_contador(client, db, token_contador):
    """Filtro de bandeja por rol: contador solo ve sus emails asignados."""
    from jose import jwt
    import os
    payload = jwt.decode(token_contador, os.environ["SECRET_KEY"], algorithms=["HS256"])
    mi_empleado_id = payload["empleado_id"]

    otro = _crear_empleado(db, "Otro Contador", "otro3@estudio.com", RolEmpleado.contador)
    db.commit()

    # Email asignado al contador logueado
    _crear_email(db, remitente="mio@test.com", asunto="Para mí", asignado_a=mi_empleado_id)
    # Email asignado al otro
    _crear_email(db, remitente="otro@test.com", asunto="Para otro", asignado_a=otro.id)
    # Email sin asignar
    _crear_email(db, remitente="nadie@test.com", asunto="General")

    resp = client.get("/api/emails", headers=_headers(token_contador))
    assert resp.status_code == 200
    asuntos = {e["asunto"] for e in resp.json()}
    assert "Para mí" in asuntos
    assert "Para otro" not in asuntos
    assert "General" not in asuntos


# ---------------------------------------------------------------------------
# test_rrhh_solo_ve_postulaciones
# ---------------------------------------------------------------------------

def test_rrhh_solo_ve_postulaciones(client, db, token_rrhh):
    """RRHH solo ve emails de categorías: postulacion_laboral, solicitud_licencia, consulta_interna."""
    _crear_email(db, remitente="cv@test.com", asunto="CV", categoria="postulacion_laboral", urgencia="baja")
    _crear_email(db, remitente="lic@test.com", asunto="Licencia", categoria="solicitud_licencia", urgencia="baja")
    _crear_email(db, remitente="iva@test.com", asunto="IVA", categoria="consulta_fiscal", urgencia="media")

    resp = client.get("/api/emails", headers=_headers(token_rrhh))
    assert resp.status_code == 200
    asuntos = {e["asunto"] for e in resp.json()}
    assert "CV" in asuntos
    assert "Licencia" in asuntos
    assert "IVA" not in asuntos


# ---------------------------------------------------------------------------
# test_borrador_aprobado_marca_enviado
# ---------------------------------------------------------------------------

def test_borrador_aprobado_marca_enviado(client, db, token_dueno):
    """Aprobar borrador actualiza estado a respondido."""
    email = _crear_email(
        db,
        remitente="cliente@test.com",
        asunto="Consulta",
        requiere_respuesta=True,
        borrador_respuesta="Estimado cliente, le respondemos...",
        requiere_revision_manual=False,
    )

    with patch("routers.emails._enviar_respuesta_via_gmail"):
        resp = client.post(f"/api/emails/{email.id}/aprobar-respuesta", headers=_headers(token_dueno))

    assert resp.status_code == 200
    db.refresh(email)
    assert email.estado == "respondido"
    assert email.borrador_aprobado is True
    assert email.respuesta_enviada_at is not None


# ---------------------------------------------------------------------------
# test_email_sin_match_va_a_bandeja_general
# ---------------------------------------------------------------------------

def test_email_sin_match_va_a_bandeja_general(db):
    """Email de remitente desconocido queda sin asignar (asignado_a=None)."""
    from services.email_router_service import determinar_destinatario

    clasificacion = {
        "categoria": "otro",
        "urgencia": "baja",
        "cliente_cuit": None,
    }

    destinatario_id = determinar_destinatario(clasificacion, db)
    assert destinatario_id is None


# ---------------------------------------------------------------------------
# test_revision_manual_bloquea_aprobacion
# ---------------------------------------------------------------------------

def test_revision_manual_bloquea_aprobacion(client, db, token_dueno):
    """Email con requiere_revision_manual=True no puede ser aprobado directamente."""
    email = _crear_email(
        db,
        remitente="urgente@test.com",
        asunto="Urgente",
        requiere_respuesta=True,
        borrador_respuesta="Borrador...",
        requiere_revision_manual=True,
        motivo_revision="urgencia_alta",
    )

    resp = client.post(f"/api/emails/{email.id}/aprobar-respuesta", headers=_headers(token_dueno))
    assert resp.status_code == 400
    assert "revisión manual" in resp.json()["detail"].lower()


def test_editar_respuesta_omite_bloqueo_revision(client, db, token_dueno):
    """Con editar-respuesta se puede enviar incluso con requiere_revision_manual=True."""
    email = _crear_email(
        db,
        remitente="urgente2@test.com",
        asunto="Urgente2",
        requiere_respuesta=True,
        borrador_respuesta="Borrador...",
        requiere_revision_manual=True,
        motivo_revision="urgencia_alta",
    )

    with patch("routers.emails._enviar_respuesta_via_gmail"):
        resp = client.post(
            f"/api/emails/{email.id}/editar-respuesta",
            json={"texto": "Respuesta revisada y aprobada por humano"},
            headers=_headers(token_dueno),
        )

    assert resp.status_code == 200
    db.refresh(email)
    assert email.estado == "respondido"
    assert email.requiere_revision_manual is False
