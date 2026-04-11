"""
Router para el builder de automatizaciones Python visuales.
Permite crear, editar y generar código Python desde un grafo de nodos estilo n8n.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import require_rol, solo_dueno
from database import get_db
from schemas.automatizacion_python import (
    AutomatizacionPythonCreate,
    AutomatizacionPythonResponse,
    AutomatizacionPythonUpdate,
    ConfigurarInputsRequest,
    GenerarDesdeDescripcionRequest,
    InputRequeridoPendiente,
)
from services import automatizacion_python_service

router = APIRouter(prefix="/api/automatizaciones-python", tags=["Automatizaciones Python"])


@router.post("/desde-descripcion", response_model=AutomatizacionPythonResponse, status_code=201)
async def generar_desde_descripcion(
    data: GenerarDesdeDescripcionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """
    Usa IA para generar un grafo de nodos Python a partir de una descripción textual.
    El resultado queda en estado 'borrador' listo para editar en el canvas.
    """
    return await automatizacion_python_service.generar_grafo_desde_descripcion(
        db=db,
        descripcion=data.descripcion,
        nombre=data.nombre,
        empleado_id=current_user.get("empleado_id"),
    )


@router.post("/", response_model=AutomatizacionPythonResponse, status_code=201)
def crear_automatizacion_python(
    data: AutomatizacionPythonCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """Crea una automatización Python vacía o con nodos/conexiones predefinidas."""
    return automatizacion_python_service.crear_automatizacion_python(
        db=db,
        data=data,
        empleado_id=current_user.get("empleado_id"),
    )


@router.get("/", response_model=list[AutomatizacionPythonResponse])
def listar_automatizaciones_python(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Lista todas las automatizaciones Python no archivadas."""
    return automatizacion_python_service.listar_automatizaciones_python(db)


@router.get("/{auto_id}", response_model=AutomatizacionPythonResponse)
def obtener_automatizacion_python(
    auto_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Retorna la automatización completa con nodos, conexiones y código generado."""
    return automatizacion_python_service.obtener_automatizacion_python(db, auto_id)


@router.put("/{auto_id}", response_model=AutomatizacionPythonResponse)
def actualizar_automatizacion_python(
    auto_id: int,
    data: AutomatizacionPythonUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """
    Actualiza nombre, descripción, estado, nodos o conexiones.
    Llamado por el canvas visual cada vez que el usuario mueve o edita un nodo.
    """
    return automatizacion_python_service.actualizar_automatizacion_python(db, auto_id, data)


@router.post("/{auto_id}/generar-codigo", response_model=AutomatizacionPythonResponse)
async def generar_codigo(
    auto_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """
    Genera código Python ejecutable a partir del grafo de nodos actual.
    El código incorpora los inputs_configurados del usuario.
    """
    return await automatizacion_python_service.generar_codigo_python(db, auto_id)


@router.get("/{auto_id}/inputs-requeridos", response_model=list[InputRequeridoPendiente])
def obtener_inputs_requeridos(
    auto_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """
    Retorna los inputs pendientes de configurar en los nodos.
    El frontend muestra un formulario por nodo con los campos faltantes.
    """
    pendientes = automatizacion_python_service.obtener_inputs_requeridos(db, auto_id)
    return [
        InputRequeridoPendiente(
            node_id=p["node_id"],
            node_name=p["node_name"],
            node_type=p["node_type"],
            campos=p["campos"],
        )
        for p in pendientes
    ]


@router.patch("/{auto_id}/configurar-inputs", response_model=AutomatizacionPythonResponse)
def configurar_inputs(
    auto_id: int,
    data: ConfigurarInputsRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """
    Guarda los valores de inputs provistos por el usuario para los nodos.
    Body: { "inputs": { "node_id": { "campo": "valor" } } }
    """
    return automatizacion_python_service.aplicar_inputs(db, auto_id, data.inputs)
