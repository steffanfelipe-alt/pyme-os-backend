import os

# CRÍTICO: setear env vars ANTES de importar cualquier módulo del proyecto
# load_dotenv() en database.py no sobrescribe vars que ya existen en el entorno
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-supersecret-key-for-pytest-only")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from auth import create_access_token, hash_password
from models.studio import Studio
from models.usuario import Usuario
from models.cliente import Cliente, TipoPersona, CondicionFiscal
from models.empleado import Empleado, RolEmpleado
from models.vencimiento import Vencimiento, TipoVencimiento, EstadoVencimiento
from datetime import date

SQLALCHEMY_TEST_URL = "sqlite://"  # in-memory: no locking, aislado por proceso

engine_test = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # todas las conexiones comparten la misma DB in-memory
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine_test,
    expire_on_commit=False,  # evita lazy-load fallido entre fixtures
)


# Registrar funciones PostgreSQL-específicas en SQLite
from sqlalchemy import event

@event.listens_for(engine_test, "connect")
def registrar_funciones_sqlite(dbapi_connection, connection_record):
    def greatest(*args):
        valores = [a for a in args if a is not None]
        return max(valores) if valores else None
    dbapi_connection.create_function("greatest", -1, greatest)


@pytest.fixture(scope="session", autouse=True)
def crear_tablas():
    """Crea todas las tablas al inicio de la sesión de tests."""
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture(autouse=True)
def limpiar_db():
    """Limpia todas las filas antes de cada test para aislar estado."""
    with engine_test.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


@pytest.fixture()
def db(limpiar_db):
    """Sesión de base de datos para cada test. Depende de limpiar_db para garantizar orden."""
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    """Cliente HTTP de test con la DB inyectada."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _get_or_create_studio(db) -> int:
    """Obtiene o crea el studio por defecto (id=1) para tests."""
    studio = db.query(Studio).first()
    if not studio:
        studio = Studio(nombre="Studio Test")
        db.add(studio)
        db.flush()
    return studio.id


def _crear_token_con_rol(db, email: str, nombre: str, rol: str) -> str:
    """Helper: crea Usuario + Empleado vinculados y retorna JWT con rol y empleado_id."""
    studio_id = _get_or_create_studio(db)

    usuario = Usuario(
        email=email,
        password_hash=hash_password("password123"),
        nombre=nombre,
        studio_id=studio_id,
    )
    db.add(usuario)
    db.flush()

    empleado = Empleado(
        nombre=nombre,
        email=email,
        rol=RolEmpleado(rol),
        activo=True,
        studio_id=studio_id,
    )
    db.add(empleado)
    db.commit()
    db.refresh(usuario)
    db.refresh(empleado)

    return create_access_token({
        "sub": str(usuario.id),
        "email": usuario.email,
        "rol": rol,
        "empleado_id": empleado.id,
        "studio_id": studio_id,
    })


@pytest.fixture()
def token(db):
    """Token con rol dueno — acceso total. Mantiene compatibilidad con tests existentes."""
    return _crear_token_con_rol(db, "dueno@pymeos.com", "Dueño Test", "dueno")


@pytest.fixture()
def auth_headers(token):
    """Headers de autenticación listos para usar en requests."""
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def token_dueno(db):
    return _crear_token_con_rol(db, "dueno2@pymeos.com", "Dueño", "dueno")


@pytest.fixture()
def token_contador(db):
    return _crear_token_con_rol(db, "contador@pymeos.com", "Contador Test", "contador")


@pytest.fixture()
def token_administrativo(db):
    return _crear_token_con_rol(db, "admin@pymeos.com", "Admin Test", "administrativo")


@pytest.fixture()
def token_rrhh(db):
    return _crear_token_con_rol(db, "rrhh@pymeos.com", "RRHH Test", "rrhh")


@pytest.fixture()
def cliente_test(db):
    """Cliente de prueba persistido en la DB."""
    studio_id = _get_or_create_studio(db)
    cliente = Cliente(
        studio_id=studio_id,
        tipo_persona=TipoPersona.juridica,
        nombre="Martínez SRL",
        cuit_cuil="20-12345678-6",  # CUIT con dígito verificador válido
        condicion_fiscal=CondicionFiscal.responsable_inscripto,
        activo=True,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@pytest.fixture()
def empleado_test(db):
    """Empleado de prueba persistido en la DB."""
    studio_id = _get_or_create_studio(db)
    empleado = Empleado(
        nombre="Lucas García",
        email="lucas@estudio.com",
        rol=RolEmpleado.contador,
        activo=True,
        studio_id=studio_id,
    )
    db.add(empleado)
    db.commit()
    db.refresh(empleado)
    return empleado


@pytest.fixture()
def vencimiento_test(db, cliente_test):
    """Vencimiento IVA de prueba para el cliente_test."""
    vencimiento = Vencimiento(
        studio_id=cliente_test.studio_id,
        cliente_id=cliente_test.id,
        tipo=TipoVencimiento.iva,
        descripcion="IVA Marzo 2026",
        fecha_vencimiento=date(2026, 3, 21),
        estado=EstadoVencimiento.pendiente,
    )
    db.add(vencimiento)
    db.commit()
    db.refresh(vencimiento)
    return vencimiento
