"""
Seed inicial — crea los datos mínimos para que el sistema funcione:
  - Studio (id=1)
  - StudioConfig (id=1)
  - Empleado dueño
  - Usuario admin
"""
from dotenv import load_dotenv
load_dotenv()

from database import engine
from sqlalchemy.orm import Session
from auth import hash_password

EMAIL    = "steffanfelipe@gmail.com"
PASSWORD = "nueva_contraseña"
NOMBRE   = "Felipe"
STUDIO   = "Mi Estudio Contable"

with Session(engine) as db:

    # 1. Studio
    from models.studio import Studio
    studio = db.query(Studio).first()
    if not studio:
        studio = Studio(nombre=STUDIO)
        db.add(studio)
        db.commit()
        db.refresh(studio)
        print(f"Studio creado: {studio.nombre} (id={studio.id})")
    else:
        print(f"Studio ya existe: {studio.nombre} (id={studio.id})")

    # 2. StudioConfig
    from models.studio_config import StudioConfig
    config = db.query(StudioConfig).first()
    if not config:
        config = StudioConfig()
        db.add(config)
        db.commit()
        print("StudioConfig creado.")
    else:
        print("StudioConfig ya existe.")

    # 3. Empleado dueño
    from models.empleado import Empleado, RolEmpleado
    empleado = db.query(Empleado).filter(Empleado.email == EMAIL).first()
    if not empleado:
        empleado = Empleado(nombre=NOMBRE, email=EMAIL, rol=RolEmpleado.dueno, activo=True)
        db.add(empleado)
        db.commit()
        db.refresh(empleado)
        print(f"Empleado creado: {empleado.nombre} rol=dueno (id={empleado.id})")
    else:
        if str(empleado.rol) != "dueno" and empleado.rol != RolEmpleado.dueno:
            empleado.rol = RolEmpleado.dueno
            db.commit()
            print(f"Empleado actualizado a rol=dueno (id={empleado.id})")
        else:
            print(f"Empleado ya existe: {empleado.nombre} rol={empleado.rol} (id={empleado.id})")

    # 4. Usuario
    from models.usuario import Usuario
    usuario = db.query(Usuario).filter(Usuario.email == EMAIL).first()
    if not usuario:
        usuario = Usuario(email=EMAIL, nombre=NOMBRE, password_hash=hash_password(PASSWORD))
        db.add(usuario)
        db.commit()
        print(f"Usuario creado: {usuario.email}")
    else:
        print(f"Usuario ya existe: {usuario.email}")

print("\nListo. Credenciales:")
print(f"  Email:    {EMAIL}")
print(f"  Password: {PASSWORD}")
