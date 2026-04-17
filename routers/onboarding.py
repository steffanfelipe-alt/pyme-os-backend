"""
Módulo de Onboarding — spec completo.
Registro de estudio, activación, wizard 5 pasos, CSV import, vencimientos sugeridos.
"""
import csv
import io
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Header
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from auth import create_access_token, hash_password
from auth_dependencies import get_studio_id, require_rol, solo_dueno
from database import get_db
from models.cliente import Cliente
from models.empleado import Empleado, RolEmpleado
from models.onboarding_pasos import OnboardingPasos
from models.studio import Studio
from models.vencimiento_sugerido import VencimientoSugerido

logger = logging.getLogger("pymeos")

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class RegistroRequest(BaseModel):
    nombre_estudio: str
    email: str
    password: str
    nombre_responsable: str


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_or_create_pasos(db: Session, studio_id: int) -> OnboardingPasos:
    pasos = db.query(OnboardingPasos).filter(OnboardingPasos.studio_id == studio_id).first()
    if not pasos:
        pasos = OnboardingPasos(studio_id=studio_id)
        db.add(pasos)
        db.commit()
        db.refresh(pasos)
    return pasos


def _calcular_porcentaje(pasos: OnboardingPasos) -> int:
    completados = sum([
        pasos.paso1_completado,
        pasos.paso2_completado,
        pasos.paso3_completado,
        pasos.paso4_completado,
        pasos.paso5_completado,
    ])
    return int(completados / 5 * 100)


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/estado")
def estado_onboarding(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Estado actual del onboarding: paso, checklist, % completado."""
    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    pasos = _get_or_create_pasos(db, studio_id)
    porcentaje = _calcular_porcentaje(pasos)
    return {
        "paso_actual": studio.onboarding_paso_actual if studio else 1,
        "completado": (studio.onboarding_completado if studio else False),
        "porcentaje": porcentaje,
        "pasos": [
            {"numero": 1, "titulo": "Configurar el estudio", "completado": pasos.paso1_completado},
            {"numero": 2, "titulo": "Cargar equipo", "completado": pasos.paso2_completado},
            {"numero": 3, "titulo": "Cargar clientes", "completado": pasos.paso3_completado},
            {"numero": 4, "titulo": "Confirmar vencimientos", "completado": pasos.paso4_completado},
            {"numero": 5, "titulo": "Conectar notificaciones", "completado": pasos.paso5_completado},
        ],
    }


@router.patch("/paso/{numero}/completar")
def completar_paso(
    numero: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Marca un paso como completado y avanza el paso actual."""
    if numero < 1 or numero > 5:
        raise HTTPException(status_code=400, detail="Paso inválido (1-5)")
    pasos = _get_or_create_pasos(db, studio_id)
    setattr(pasos, f"paso{numero}_completado", True)

    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    if studio:
        if studio.onboarding_paso_actual <= numero:
            studio.onboarding_paso_actual = min(numero + 1, 5)
        # Si completó el paso 5, marcar onboarding como terminado
        if numero == 5:
            studio.onboarding_completado = True

    db.commit()
    return {"ok": True, "paso_completado": numero}


# Alias POST /onboarding/completar-paso — usado por el frontend del wizard
_NOMBRE_A_NUMERO = {
    "estudio_configurado": 1,
    "equipo_configurado": 2,
    "clientes_importados": 3,
    "vencimientos_configurados": 4,
    "notificaciones_configuradas": 5,
}


class CompletarPasoBody(BaseModel):
    paso: str  # e.g. "estudio_configurado"


@router.post("/completar-paso")
def completar_paso_alias(
    body: CompletarPasoBody,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Alias amigable: recibe el nombre del paso y delega a la lógica existente."""
    numero = _NOMBRE_A_NUMERO.get(body.paso)
    if not numero:
        raise HTTPException(status_code=400, detail=f"Paso desconocido: '{body.paso}'")
    pasos = _get_or_create_pasos(db, studio_id)
    setattr(pasos, f"paso{numero}_completado", True)
    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    if studio:
        if studio.onboarding_paso_actual <= numero:
            studio.onboarding_paso_actual = min(numero + 1, 5)
        if numero == 5:
            studio.onboarding_completado = True
    db.commit()
    return {"ok": True, "paso_completado": body.paso}


@router.get("/siguientes-pasos")
def siguientes_pasos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Pasos pendientes post-onboarding ordenados por prioridad de valor."""
    studio = db.query(Studio).filter(Studio.id == studio_id).first()
    if not studio:
        return {"pasos_pendientes": []}

    pendientes = []

    # 1. Completar categorías fiscales faltantes
    clientes_sin_cat = db.query(Cliente).filter(
        Cliente.studio_id == studio_id,
        Cliente.requiere_categoria == True,
        Cliente.activo == True,
    ).count()
    if clientes_sin_cat > 0:
        pendientes.append({
            "id": "completar_categorias_clientes",
            "titulo": "Completar categorías fiscales",
            "descripcion": f"{clientes_sin_cat} cliente(s) sin categoría fiscal. Necesaria para sugerir vencimientos automáticamente.",
            "accion": "Completar ahora",
            "ruta": "/clientes",
            "completado": False,
        })

    # 2. Conectar Telegram
    if not studio.telegram_configurado:
        pendientes.append({
            "id": "conectar_telegram",
            "titulo": "Conectar Telegram",
            "descripcion": "Recibí alertas de vencimientos y clientes en riesgo directo en tu celular.",
            "accion": "Conectar ahora",
            "ruta": "/configuracion/integraciones",
            "completado": False,
        })

    # 3. Conectar email de alertas
    if not studio.email_configurado:
        pendientes.append({
            "id": "conectar_email_alertas",
            "titulo": "Configurar email de alertas",
            "descripcion": "Canal de respaldo para recibir resúmenes y alertas críticas.",
            "accion": "Configurar",
            "ruta": "/configuracion/integraciones",
            "completado": False,
        })

    # 4. Crear primera tarea
    from models.tarea import Tarea
    tiene_tareas = db.query(Tarea).filter(Tarea.studio_id == studio_id).first() is not None
    if not tiene_tareas:
        pendientes.append({
            "id": "crear_primera_tarea",
            "titulo": "Crear tu primera tarea",
            "descripcion": "Organizá el trabajo del estudio con el módulo de tareas.",
            "accion": "Ir a tareas",
            "ruta": "/tareas",
            "completado": False,
        })

    # 5. Activar portal del cliente
    if not studio.portal_habilitado:
        pendientes.append({
            "id": "activar_portal_cliente",
            "titulo": "Activar el portal del cliente",
            "descripcion": "Permitir que tus clientes suban documentación y vean sus vencimientos.",
            "accion": "Activar",
            "ruta": "/configuracion/portal",
            "completado": False,
        })

    # 6. Configurar abonos
    from models.abono import Abono
    tiene_abonos = db.query(Abono).filter(Abono.studio_id == studio_id).first() is not None
    if not tiene_abonos:
        pendientes.append({
            "id": "configurar_abonos",
            "titulo": "Configurar honorarios y abonos",
            "descripcion": "Activá el módulo de cobranza para generar cobros automáticos.",
            "accion": "Configurar",
            "ruta": "/configuracion/honorarios",
            "completado": False,
        })

    # 7. Invitar empleado
    tiene_empleados = db.query(Empleado).filter(
        Empleado.studio_id == studio_id,
        Empleado.activo == True,
        Empleado.rol != RolEmpleado.dueno,
    ).first() is not None
    if not tiene_empleados:
        pendientes.append({
            "id": "invitar_empleado",
            "titulo": "Agregar un empleado",
            "descripcion": "Sumá a tu equipo y asignales clientes y tareas.",
            "accion": "Agregar",
            "ruta": "/configuracion/equipo",
            "completado": False,
        })

    return {"pasos_pendientes": pendientes}


# ─── CSV Import ───────────────────────────────────────────────────────────────

@router.post("/importar-empleados")
async def importar_empleados_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Importa empleados desde CSV. Columnas: nombre (req), email, rol."""
    contenido = await file.read()
    texto = contenido.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(texto))

    importados = 0
    saltados = 0
    errores = []

    ROLES_VALIDOS = {r.value for r in RolEmpleado}

    for i, fila in enumerate(reader, start=2):
        nombre = (fila.get("nombre") or "").strip()
        if not nombre:
            errores.append(f"Fila {i}: nombre vacío — saltada")
            continue

        email = (fila.get("email") or "").strip().lower()
        rol_raw = (fila.get("rol") or "").strip().lower()
        rol = rol_raw if rol_raw in ROLES_VALIDOS else "contador"

        # Verificar duplicado
        if email:
            existente = db.query(Empleado).filter(
                Empleado.studio_id == studio_id,
                Empleado.email == email,
            ).first()
            if existente:
                saltados += 1
                continue

        emp = Empleado(
            studio_id=studio_id,
            nombre=nombre,
            email=email or f"sin_email_{i}@placeholder.local",
            rol=RolEmpleado(rol),
        )
        db.add(emp)
        importados += 1

    db.commit()
    return {"importados": importados, "saltados": saltados, "errores": errores}


@router.post("/importar-clientes")
async def importar_clientes_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Importa clientes desde CSV. Columnas: nombre (req), cuit (req), categoria_fiscal, email, telefono."""
    contenido = await file.read()
    texto = contenido.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(texto))

    CATEGORIAS_VALIDAS = {"monotributista", "responsable_inscripto", "sociedad", "empleador", "otro"}

    importados = 0
    saltados = 0
    sin_categoria = 0
    vencimientos_sugeridos = 0
    errores = []

    for i, fila in enumerate(reader, start=2):
        nombre = (fila.get("nombre") or "").strip()
        cuit = (fila.get("cuit") or "").strip().replace("-", "")
        if not nombre or not cuit:
            errores.append(f"Fila {i}: nombre o cuit vacío — saltada")
            continue

        # Verificar duplicado por CUIT
        existente = db.query(Cliente).filter(
            Cliente.studio_id == studio_id,
            Cliente.cuit == cuit,
        ).first()
        if existente:
            saltados += 1
            continue

        cat_raw = (fila.get("categoria_fiscal") or "").strip().lower()
        categoria = cat_raw if cat_raw in CATEGORIAS_VALIDAS else None
        requiere_cat = categoria is None

        if requiere_cat:
            sin_categoria += 1

        from models.cliente import TipoCliente, TipoPersona
        cliente = Cliente(
            studio_id=studio_id,
            nombre=nombre,
            cuit=cuit,
            email=(fila.get("email") or "").strip() or None,
            telefono=(fila.get("telefono") or "").strip() or None,
            requiere_categoria=requiere_cat,
        )
        if categoria:
            try:
                cliente.categoria_fiscal = categoria
            except Exception:
                pass
        db.add(cliente)
        db.flush()

        if categoria and not requiere_cat:
            n = _sugerir_vencimientos(db, studio_id, cliente.id, categoria, cuit)
            vencimientos_sugeridos += n

        importados += 1

    db.commit()
    return {
        "importados": importados,
        "saltados": saltados,
        "sin_categoria": sin_categoria,
        "vencimientos_sugeridos": vencimientos_sugeridos,
        "errores": errores,
    }


# ─── Vencimientos sugeridos ───────────────────────────────────────────────────

def _sugerir_vencimientos(
    db: Session, studio_id: int, cliente_id: int, categoria: str, cuit: str = ""
) -> int:
    """Genera sugerencias de vencimientos para el período actual según categoría fiscal."""
    hoy = date.today()
    periodo = hoy.strftime("%Y-%m")
    generados = 0

    # Determinar terminación del CUIT para IVA/Ganancias
    terminacion = cuit[-1] if cuit and cuit[-1].isdigit() else "0"
    fecha_iva = _fecha_iva_por_cuit(hoy.year, hoy.month, terminacion)

    obligaciones = _obligaciones_por_categoria(categoria, hoy, fecha_iva, periodo)

    for ob in obligaciones:
        existente = db.query(VencimientoSugerido).filter(
            VencimientoSugerido.cliente_id == cliente_id,
            VencimientoSugerido.tipo_obligacion == ob["tipo"],
            VencimientoSugerido.periodo == periodo,
            VencimientoSugerido.estado == "pendiente_confirmacion",
        ).first()
        if existente:
            continue

        vs = VencimientoSugerido(
            studio_id=studio_id,
            cliente_id=cliente_id,
            tipo_obligacion=ob["tipo"],
            periodo=periodo,
            fecha_vencimiento_estimada=ob["fecha"],
            fecha_es_estimada=ob.get("estimada", False),
            nota_verificacion=ob.get("nota"),
        )
        db.add(vs)
        generados += 1

    return generados


def _fecha_iva_por_cuit(year: int, month: int, terminacion: str) -> date:
    """Calcula fecha de vencimiento IVA según terminación del CUIT."""
    DIA_POR_TERMINACION = {
        "0": 12, "1": 12, "2": 13, "3": 13,
        "4": 14, "5": 14, "6": 15, "7": 15,
        "8": 16, "9": 16,
    }
    # mes siguiente
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    dia = DIA_POR_TERMINACION.get(terminacion, 20)
    try:
        return date(next_year, next_month, dia)
    except ValueError:
        return date(next_year, next_month, 20)


def _obligaciones_por_categoria(
    categoria: str, hoy: date, fecha_iva: date, periodo: str
) -> list[dict]:
    """Retorna lista de obligaciones según categoría fiscal."""
    year, month = hoy.year, hoy.month
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    obligaciones = []

    if categoria == "monotributista":
        obligaciones.append({
            "tipo": "Monotributo",
            "fecha": date(year, month, 20),
            "estimada": False,
        })

    elif categoria in ("responsable_inscripto", "sociedad"):
        obligaciones.append({
            "tipo": "IVA",
            "fecha": fecha_iva,
            "estimada": fecha_iva == date(next_year, next_month, 20),
            "nota": "Fecha estimada — verificar en AFIP según terminación de CUIT" if fecha_iva == date(next_year, next_month, 20) else None,
        })
        obligaciones.append({
            "tipo": "Ganancias anticipos",
            "fecha": fecha_iva,
            "estimada": True,
            "nota": "Fecha estimada — verificar en AFIP según terminación de CUIT",
        })
        try:
            obligaciones.append({
                "tipo": "IIBB",
                "fecha": date(next_year, next_month, 15),
                "estimada": True,
                "nota": "Fecha estimada — verificar en organismo provincial",
            })
        except ValueError:
            pass

    elif categoria == "empleador":
        try:
            obligaciones.append({
                "tipo": "F931 cargas sociales",
                "fecha": date(next_year, next_month, 10),
                "estimada": False,
            })
        except ValueError:
            pass

    return obligaciones


@router.post("/sugerir-vencimientos/{cliente_id}")
def sugerir_vencimientos_endpoint(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
    studio_id: int = Depends(get_studio_id),
):
    """Genera sugerencias de vencimientos para un cliente específico."""
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.studio_id == studio_id
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    cat = getattr(cliente, "categoria_fiscal", None)
    if cat is None:
        return {"sin_configurar": True, "mensaje": "Cliente sin categoría fiscal"}
    if hasattr(cat, "value"):
        cat = cat.value

    cuit = getattr(cliente, "cuit", "") or ""
    n = _sugerir_vencimientos(db, studio_id, cliente_id, str(cat), cuit)
    db.commit()
    return {"sugerencias_creadas": n}


@router.get("/vencimientos-sugeridos")
def listar_sugeridos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
    studio_id: int = Depends(get_studio_id),
):
    """Lista todos los vencimientos sugeridos pendientes de confirmación."""
    sugeridos = db.query(VencimientoSugerido).filter(
        VencimientoSugerido.studio_id == studio_id,
        VencimientoSugerido.estado == "pendiente_confirmacion",
    ).order_by(VencimientoSugerido.cliente_id, VencimientoSugerido.fecha_vencimiento_estimada).all()

    cliente_ids = {s.cliente_id for s in sugeridos}
    clientes_map = {
        c.id: c
        for c in db.query(Cliente).filter(Cliente.id.in_(cliente_ids)).all()
    } if cliente_ids else {}

    resultado = {}
    for s in sugeridos:
        cliente = clientes_map.get(s.cliente_id)
        cat = getattr(cliente, "categoria_fiscal", None)
        if hasattr(cat, "value"):
            cat = cat.value
        key = s.cliente_id
        if key not in resultado:
            resultado[key] = {
                "cliente_id": s.cliente_id,
                "cliente_nombre": cliente.nombre if cliente else "",
                "categoria_fiscal": str(cat) if cat else "",
                "sugerencias": [],
            }
        resultado[key]["sugerencias"].append({
            "id": s.id,
            "tipo_obligacion": s.tipo_obligacion,
            "periodo": s.periodo,
            "fecha_vencimiento_estimada": s.fecha_vencimiento_estimada.isoformat(),
            "fecha_es_estimada": s.fecha_es_estimada,
            "nota_verificacion": s.nota_verificacion,
            "estado": s.estado,
        })

    return list(resultado.values())


@router.post("/vencimientos-sugeridos/confirmar")
def confirmar_sugeridos(
    ids: list[int],
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
    studio_id: int = Depends(get_studio_id),
):
    """Confirma una lista de sugerencias, creando los vencimientos reales."""
    from models.vencimiento import Vencimiento, TipoVencimiento, EstadoVencimiento

    confirmados = 0
    for sugerido_id in ids:
        s = db.query(VencimientoSugerido).filter(
            VencimientoSugerido.id == sugerido_id,
            VencimientoSugerido.studio_id == studio_id,
        ).first()
        if not s or s.estado != "pendiente_confirmacion":
            continue

        # Crear vencimiento real
        try:
            tipo = TipoVencimiento(s.tipo_obligacion)
        except ValueError:
            tipo = TipoVencimiento.otro if hasattr(TipoVencimiento, "otro") else list(TipoVencimiento)[0]

        venc = Vencimiento(
            studio_id=studio_id,
            cliente_id=s.cliente_id,
            tipo=tipo,
            descripcion=f"{s.tipo_obligacion} — {s.periodo}",
            fecha_vencimiento=s.fecha_vencimiento_estimada,
            estado=EstadoVencimiento.pendiente,
        )
        db.add(venc)
        s.estado = "confirmado"
        confirmados += 1

    db.commit()
    return {"confirmados": confirmados}


@router.delete("/vencimientos-sugeridos/{sugerido_id}")
def descartar_sugerido(
    sugerido_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
    studio_id: int = Depends(get_studio_id),
):
    s = db.query(VencimientoSugerido).filter(
        VencimientoSugerido.id == sugerido_id,
        VencimientoSugerido.studio_id == studio_id,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada")
    s.estado = "descartado"
    db.commit()
    return {"ok": True}
