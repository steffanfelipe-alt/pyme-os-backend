from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models.cliente import Cliente


def require_rol(*roles: str):
    """Dependencia que valida que el usuario tenga uno de los roles permitidos."""
    def checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("rol") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rol requerido: {roles}. Rol actual: {current_user.get('rol')}",
            )
        return current_user

    return checker


def solo_dueno(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("rol") != "dueno":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el dueño del estudio puede realizar esta acción",
        )
    return current_user


def filtrar_clientes_por_rol(current_user: dict, query):
    """Aplica filtro de tenant sobre una query de Cliente según el rol del usuario."""
    if current_user.get("rol") == "contador":
        empleado_id = current_user.get("empleado_id")
        query = query.filter(Cliente.contador_asignado_id == empleado_id)
    return query


def verificar_acceso_cliente(current_user: dict, cliente_id: int, db: Session) -> None:
    """Para rol contador: lanza 403 si el cliente no está asignado a él."""
    if current_user.get("rol") != "contador":
        return
    empleado_id = current_user.get("empleado_id")
    cliente = (
        db.query(Cliente)
        .filter(Cliente.id == cliente_id, Cliente.contador_asignado_id == empleado_id)
        .first()
    )
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene acceso a este cliente",
        )
