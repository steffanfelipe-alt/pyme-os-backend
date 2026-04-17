import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class EstadoSolicitud(str, enum.Enum):
    pendiente = "pendiente"
    enviada = "enviada"
    recibida = "recibida"
    vencida = "vencida"


class SolicitudDocumentoAuto(Base):
    __tablename__ = "solicitudes_documentos_auto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, index=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    vencimiento_id: Mapped[int] = mapped_column(Integer, ForeignKey("vencimientos.id"), nullable=False)
    tipo_documento: Mapped[str] = mapped_column(String(50), nullable=False)
    estado: Mapped[EstadoSolicitud] = mapped_column(
        Enum(EstadoSolicitud), default=EstadoSolicitud.pendiente, nullable=False
    )
    canal: Mapped[str | None] = mapped_column(String(20), nullable=True)  # email | telegram | portal
    enviada_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
