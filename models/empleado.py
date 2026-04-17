import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class RolEmpleado(str, enum.Enum):
    dueno = "dueno"
    contador = "contador"
    administrativo = "administrativo"
    rrhh = "rrhh"


class Empleado(Base):
    __tablename__ = "empleados"
    __table_args__ = (UniqueConstraint("email", "studio_id", name="uq_empleados_email_studio"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[RolEmpleado] = mapped_column(Enum(RolEmpleado), nullable=False)
    capacidad_horas_mes: Mapped[int] = mapped_column(Integer, default=160, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
