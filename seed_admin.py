from dotenv import load_dotenv
load_dotenv()

from database import engine
from sqlalchemy.orm import Session
from auth import hash_password
from models.empleado import Empleado, RolEmpleado
from models.usuario import Usuario

EMAIL = "steffanfelipe@gmail.com"
PASSWORD = "nueva_contraseña"
NOMBRE = "Felipe"

with Session(engine) as db:
    # Crear empleado si no existe
    empleado = db.query(Empleado).filter(Empleado.email == EMAIL).first()
    if not empleado:
        empleado = Empleado(nombre=NOMBRE, email=EMAIL, rol=RolEmpleado.contador, activo=True)
        db.add(empleado)
        db.commit()
        db.refresh(empleado)
        print(f"Empleado creado: {empleado.nombre} (id={empleado.id})")
    else:
        print(f"Empleado ya existe: {empleado.nombre} (id={empleado.id})")

    # Crear usuario si no existe
    usuario = db.query(Usuario).filter(Usuario.email == EMAIL).first()
    if not usuario:
        usuario = Usuario(email=EMAIL, nombre=NOMBRE, password_hash=hash_password(PASSWORD))
        db.add(usuario)
        db.commit()
        print(f"Usuario creado: {usuario.email}")
    else:
        print(f"Usuario ya existe: {usuario.email}")

print("Listo. Podés loguearte con:", EMAIL, "/", PASSWORD)
