"""Schemas Pydantic para el builder de automatizaciones Python visuales."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from models.automatizacion_python import EstadoAutomatizacionPython


# ─── Node / Edge schemas (validación de estructura JSON) ─────────────────────

class InputRequerido(BaseModel):
    campo: str
    label: str
    tipo: str = "text"  # text | password | url | number | select
    opciones: Optional[list[str]] = None  # para tipo select


class NodoPython(BaseModel):
    id: str
    type: str  # trigger | http_request | transform | filter | notify | code | delay | condition
    name: str
    position: dict  # { x: int, y: int }
    config: dict = {}
    required_inputs: list[InputRequerido] = []


class ConexionPython(BaseModel):
    from_node: str
    to_node: str
    label: Optional[str] = None


# ─── Request / Response schemas ───────────────────────────────────────────────

class AutomatizacionPythonCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    nodos: Optional[list[dict]] = None
    conexiones: Optional[list[dict]] = None


class AutomatizacionPythonUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    estado: Optional[EstadoAutomatizacionPython] = None
    nodos: Optional[list[dict]] = None
    conexiones: Optional[list[dict]] = None


class AutomatizacionPythonResponse(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str]
    creado_por_id: Optional[int]
    estado: EstadoAutomatizacionPython
    nodos: Optional[list[dict]]
    conexiones: Optional[list[dict]]
    codigo_generado: Optional[str]
    inputs_configurados: Optional[dict]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConfigurarInputsRequest(BaseModel):
    """Body para PATCH /configurar-inputs. Estructura: { node_id: { campo: valor } }"""
    inputs: dict[str, dict[str, Any]]


class GenerarDesdeDescripcionRequest(BaseModel):
    descripcion: str
    nombre: Optional[str] = None


class InputRequeridoPendiente(BaseModel):
    node_id: str
    node_name: str
    node_type: str
    campos: list[InputRequerido]
