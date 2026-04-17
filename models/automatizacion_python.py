"""
Modelo para el builder de automatizaciones Python visuales.
Cada instancia representa un flujo tipo n8n pero cuyo backend es Python.
El grafo se almacena como JSON de nodos + conexiones; el servicio genera
código Python ejecutable a partir de él.
"""
import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func, JSON
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class EstadoAutomatizacionPython(str, enum.Enum):
    borrador = "borrador"
    activo = "activo"
    archivado = "archivado"


class AutomatizacionPython(Base):
    __tablename__ = "automatizaciones_python"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_por_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("empleados.id"), nullable=True)
    estado: Mapped[EstadoAutomatizacionPython] = mapped_column(
        Enum(EstadoAutomatizacionPython),
        default=EstadoAutomatizacionPython.borrador,
        nullable=False,
    )

    # Grafo del flujo visual
    # Cada nodo: { id, type, name, position: {x, y}, config: {}, required_inputs: [{campo, label, tipo}] }
    nodos: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # Cada conexión: { from_node: str, to_node: str, label: str|null }
    conexiones: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # Código Python generado a partir del grafo
    codigo_generado: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Valores provistos por el usuario para los required_inputs de cada nodo
    # Estructura: { "node_id": { "campo": "valor" } }
    inputs_configurados: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
