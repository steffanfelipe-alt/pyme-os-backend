import csv
import io
import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from models.cliente import Cliente, TipoPersona
from services import documento_service

logger = logging.getLogger("pymeos")
from models.empleado import Empleado
from models.tarea import EstadoTarea, Tarea
from models.vencimiento import EstadoVencimiento, Vencimiento
from schemas.cliente import (
    ClienteCreate,
    ClienteResumen,
    ClienteUpdate,
    EstadoAlerta,
    FichaClienteResponse,
)

UMBRAL_AMARILLO_DIAS = 7


def _calcular_estado_alerta(
    proximo_vencimiento: Optional[date],
    tiene_vencidos: bool,
    tareas_pendientes: int,
) -> EstadoAlerta:
    if proximo_vencimiento is None and tareas_pendientes == 0:
        return EstadoAlerta.sin_datos
    if tiene_vencidos:
        return EstadoAlerta.rojo
    if proximo_vencimiento is not None:
        dias = (proximo_vencimiento - date.today()).days
        if dias <= UMBRAL_AMARILLO_DIAS:
            return EstadoAlerta.amarillo
    return EstadoAlerta.verde


def crear_cliente(db: Session, data: ClienteCreate, studio_id: int) -> Cliente:
    from validaciones import validar_cuit

    if not validar_cuit(data.cuit_cuil):
        raise HTTPException(status_code=422, detail="CUIT/CUIL inválido — el dígito verificador no es correcto")

    existente = db.query(Cliente).filter(
        Cliente.cuit_cuil == data.cuit_cuil, Cliente.studio_id == studio_id
    ).first()
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un cliente con ese CUIT/CUIL")

    if data.contador_asignado_id is not None:
        empleado = db.query(Empleado).filter(
            Empleado.id == data.contador_asignado_id,
            Empleado.studio_id == studio_id,
            Empleado.activo == True,
        ).first()
        if not empleado:
            raise HTTPException(status_code=404, detail="Empleado no encontrado o inactivo")

    cliente = Cliente(**data.model_dump(), studio_id=studio_id)
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


def listar_clientes(
    db: Session,
    studio_id: int,
    skip: int = 0,
    limit: int = 20,
    tipo_persona: Optional[TipoPersona] = None,
    activo: Optional[bool] = True,
    busqueda: Optional[str] = None,
    contador_asignado_id: Optional[int] = None,
    estado_alerta: Optional[EstadoAlerta] = None,
) -> list[ClienteResumen]:
    # Subquery: próximo vencimiento pendiente por cliente
    sq_proximo = (
        select(
            Vencimiento.cliente_id,
            func.min(Vencimiento.fecha_vencimiento).label("proximo_vencimiento"),
        )
        .where(Vencimiento.estado == EstadoVencimiento.pendiente)
        .group_by(Vencimiento.cliente_id)
        .subquery()
    )

    # Subquery: tiene vencimientos vencidos
    sq_vencidos = (
        select(Vencimiento.cliente_id)
        .where(Vencimiento.estado == EstadoVencimiento.vencido)
        .distinct()
        .subquery()
    )

    # Subquery: tareas pendientes/en_progreso por cliente
    sq_tareas = (
        select(
            Tarea.cliente_id,
            func.count(Tarea.id).label("tareas_pendientes"),
        )
        .where(
            and_(
                Tarea.estado.in_([EstadoTarea.pendiente, EstadoTarea.en_progreso]),
                Tarea.activo == True,
            )
        )
        .group_by(Tarea.cliente_id)
        .subquery()
    )

    # Subquery: última actividad (max updated_at entre tareas y vencimientos)
    sq_act_tareas = (
        select(Tarea.cliente_id, func.max(Tarea.updated_at).label("ultima"))
        .group_by(Tarea.cliente_id)
        .subquery()
    )
    sq_act_venc = (
        select(Vencimiento.cliente_id, func.max(Vencimiento.updated_at).label("ultima"))
        .group_by(Vencimiento.cliente_id)
        .subquery()
    )

    query = db.query(Cliente).outerjoin(
        sq_proximo, Cliente.id == sq_proximo.c.cliente_id
    ).outerjoin(
        sq_vencidos, Cliente.id == sq_vencidos.c.cliente_id
    ).outerjoin(
        sq_tareas, Cliente.id == sq_tareas.c.cliente_id
    ).outerjoin(
        sq_act_tareas, Cliente.id == sq_act_tareas.c.cliente_id
    ).outerjoin(
        sq_act_venc, Cliente.id == sq_act_venc.c.cliente_id
    )

    query = query.filter(Cliente.studio_id == studio_id)
    if activo is not None:
        query = query.filter(Cliente.activo == activo)
    if tipo_persona is not None:
        query = query.filter(Cliente.tipo_persona == tipo_persona)
    if contador_asignado_id is not None:
        query = query.filter(Cliente.contador_asignado_id == contador_asignado_id)
    if busqueda is not None:
        like = f"%{busqueda}%"
        query = query.filter(
            Cliente.nombre.ilike(like) | Cliente.cuit_cuil.ilike(like)
        )

    rows = query.add_columns(
        sq_proximo.c.proximo_vencimiento,
        sq_vencidos.c.cliente_id.label("tiene_vencidos"),
        func.coalesce(sq_tareas.c.tareas_pendientes, 0).label("tareas_pendientes"),
        func.greatest(sq_act_tareas.c.ultima, sq_act_venc.c.ultima).label("ultima_actividad"),
    ).offset(skip).limit(limit).all()

    resultados = []
    for row in rows:
        cliente = row[0]
        proximo = row[1]
        tiene_vencidos = row[2] is not None
        tareas_pendientes = row[3] or 0
        ultima_actividad = row[4]

        alerta = _calcular_estado_alerta(proximo, tiene_vencidos, tareas_pendientes)

        if estado_alerta is not None and alerta != estado_alerta:
            continue

        resultados.append(ClienteResumen(
            id=cliente.id,
            tipo_persona=cliente.tipo_persona,
            nombre=cliente.nombre,
            cuit_cuil=cliente.cuit_cuil,
            condicion_fiscal=cliente.condicion_fiscal,
            contador_asignado_id=cliente.contador_asignado_id,
            activo=cliente.activo,
            proximo_vencimiento=proximo,
            tareas_pendientes=tareas_pendientes,
            ultima_actividad=ultima_actividad,
            estado_alerta=alerta,
        ))

    return resultados


def obtener_cliente(db: Session, cliente_id: int, studio_id: int) -> Cliente:
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.studio_id == studio_id
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return cliente


def actualizar_cliente(db: Session, cliente_id: int, data: ClienteUpdate, studio_id: int) -> Cliente:
    cliente = obtener_cliente(db, cliente_id, studio_id)
    cambios = data.model_dump(exclude_unset=True)

    if "cuit_cuil" in cambios:
        existente = (
            db.query(Cliente)
            .filter(
                Cliente.cuit_cuil == cambios["cuit_cuil"],
                Cliente.studio_id == studio_id,
                Cliente.id != cliente_id,
            )
            .first()
        )
        if existente:
            raise HTTPException(status_code=409, detail="Ya existe un cliente con ese CUIT/CUIL")

    for campo, valor in cambios.items():
        setattr(cliente, campo, valor)

    db.commit()
    db.refresh(cliente)
    return cliente


def eliminar_cliente(db: Session, cliente_id: int, studio_id: int) -> None:
    cliente = obtener_cliente(db, cliente_id, studio_id)
    cliente.activo = False
    cliente.fecha_baja = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()


async def importar_desde_csv(db: Session, file: UploadFile, studio_id: int) -> dict:
    """
    Importa clientes desde un CSV.
    Columnas requeridas: tipo_persona, nombre, cuit_cuil, condicion_fiscal
    Columnas opcionales: email, telefono, telefono_whatsapp, email_notificaciones,
                         acepta_notificaciones, contador_asignado_id, notas
    Devuelve: {"creados": N, "errores": [{"fila": N, "razon": "..."}]}
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un CSV (.csv)")

    contenido = await file.read()
    try:
        texto = contenido.decode("utf-8-sig")  # utf-8-sig elimina BOM de Excel
    except UnicodeDecodeError:
        texto = contenido.decode("latin-1")

    reader = csv.DictReader(io.StringIO(texto))
    requeridas = {"tipo_persona", "nombre", "cuit_cuil", "condicion_fiscal"}
    if not requeridas.issubset(set(reader.fieldnames or [])):
        faltantes = requeridas - set(reader.fieldnames or [])
        raise HTTPException(
            status_code=400,
            detail=f"Columnas requeridas faltantes: {', '.join(sorted(faltantes))}",
        )

    creados = 0
    errores = []

    for num_fila, row in enumerate(reader, start=2):  # 2 porque fila 1 es el header
        # Normalizar: strip de espacios
        row = {k.strip(): (v.strip() if v else "") for k, v in row.items()}

        try:
            data = ClienteCreate(
                tipo_persona=row["tipo_persona"],
                nombre=row["nombre"],
                cuit_cuil=row["cuit_cuil"],
                condicion_fiscal=row["condicion_fiscal"],
                email=row.get("email") or None,
                telefono=row.get("telefono") or None,
                telefono_whatsapp=row.get("telefono_whatsapp") or None,
                email_notificaciones=row.get("email_notificaciones") or None,
                acepta_notificaciones=row.get("acepta_notificaciones", "true").lower() != "false",
                contador_asignado_id=int(row["contador_asignado_id"]) if row.get("contador_asignado_id") else None,
                notas=row.get("notas") or None,
            )
        except (ValidationError, ValueError) as e:
            errores.append({"fila": num_fila, "razon": str(e)})
            continue

        try:
            crear_cliente(db, data, studio_id)
            creados += 1
        except HTTPException as e:
            errores.append({"fila": num_fila, "razon": e.detail})

    logger.info("Importación CSV — %d creados, %d errores", creados, len(errores))
    return {"creados": creados, "errores": errores}


def obtener_ficha_cliente(db: Session, cliente_id: int, studio_id: int) -> FichaClienteResponse:
    from schemas.cliente import ClienteResponse, ContadorInfo, TareaFicha, VencimientoFicha

    cliente = obtener_cliente(db, cliente_id, studio_id)

    # Contador principal
    contador_principal = None
    if cliente.contador_asignado_id:
        emp = db.query(Empleado).filter(Empleado.id == cliente.contador_asignado_id).first()
        if emp:
            contador_principal = ContadorInfo.model_validate(emp)

    # Vencimientos: auto-actualizar estado vencido antes de mostrar
    hoy = date.today()
    vencimientos_db = db.query(Vencimiento).filter(Vencimiento.cliente_id == cliente_id).all()
    for v in vencimientos_db:
        if v.estado == EstadoVencimiento.pendiente and v.fecha_vencimiento < hoy:
            v.estado = EstadoVencimiento.vencido
    db.commit()

    proximos = [
        VencimientoFicha(
            id=v.id, tipo=v.tipo.value, descripcion=v.descripcion,
            fecha_vencimiento=v.fecha_vencimiento, fecha_cumplimiento=v.fecha_cumplimiento,
            estado=v.estado.value, dias_para_vencer=(v.fecha_vencimiento - hoy).days,
        )
        for v in vencimientos_db if v.estado == EstadoVencimiento.pendiente
    ]
    proximos.sort(key=lambda x: x.fecha_vencimiento)

    vencidos = [
        VencimientoFicha(
            id=v.id, tipo=v.tipo.value, descripcion=v.descripcion,
            fecha_vencimiento=v.fecha_vencimiento, fecha_cumplimiento=v.fecha_cumplimiento,
            estado=v.estado.value, dias_para_vencer=(v.fecha_vencimiento - hoy).days,
        )
        for v in vencimientos_db if v.estado == EstadoVencimiento.vencido
    ]

    # Tareas
    tareas_db = db.query(Tarea).filter(Tarea.cliente_id == cliente_id, Tarea.activo == True).all()

    activas = [
        TareaFicha(
            id=t.id, titulo=t.titulo, tipo=t.tipo.value, prioridad=t.prioridad.value,
            estado=t.estado.value, fecha_limite=t.fecha_limite,
            horas_estimadas=t.horas_estimadas, empleado_id=t.empleado_id,
        )
        for t in tareas_db
        if t.estado in (EstadoTarea.pendiente, EstadoTarea.en_progreso)
    ]

    completadas_recientes = sorted(
        [
            TareaFicha(
                id=t.id, titulo=t.titulo, tipo=t.tipo.value, prioridad=t.prioridad.value,
                estado=t.estado.value, fecha_limite=t.fecha_limite,
                horas_estimadas=t.horas_estimadas, empleado_id=t.empleado_id,
            )
            for t in tareas_db if t.estado == EstadoTarea.completada
        ],
        key=lambda x: x.id,
        reverse=True,
    )[:5]

    # Participantes con tareas activas
    empleado_ids = {t.empleado_id for t in tareas_db
                    if t.empleado_id and t.estado in (EstadoTarea.pendiente, EstadoTarea.en_progreso)}
    participantes = []
    for eid in empleado_ids:
        emp = db.query(Empleado).filter(Empleado.id == eid).first()
        if emp:
            participantes.append(ContadorInfo.model_validate(emp))

    # Estado alerta global
    tiene_vencidos = len(vencidos) > 0
    proximo_date = proximos[0].fecha_vencimiento if proximos else None
    alerta = _calcular_estado_alerta(proximo_date, tiene_vencidos, len(activas))

    documentos = documento_service.listar_documentos(db, cliente_id)

    # ── Nuevos campos del spec Ficha del Cliente ──────────────────────────────
    # Alertas activas
    from models.alerta import AlertaVencimiento
    alertas_db = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.cliente_id == cliente_id,
        AlertaVencimiento.resuelta_at.is_(None),
        AlertaVencimiento.ignorada_at.is_(None),
    ).order_by(AlertaVencimiento.created_at.desc()).limit(5).all()
    alertas_activas = [
        {
            "id": a.id,
            "tipo": a.tipo or "vencimiento",
            "mensaje": a.mensaje,
            "severidad": a.nivel,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alertas_db
    ]

    # Abono y historial de cobros
    abono_data = None
    historial_cobros = []
    try:
        from models.abono import Abono, Cobro
        abono = db.query(Abono).filter(
            Abono.cliente_id == cliente_id, Abono.activo == True
        ).first()
        if abono:
            cobros = db.query(Cobro).filter(
                Cobro.abono_id == abono.id,
            ).order_by(Cobro.created_at.desc()).limit(7).all()
            cobro_actual = cobros[0] if cobros else None
            abono_data = {
                "id": abono.id,
                "monto": float(abono.monto or 0),
                "estado": abono.estado.value if hasattr(abono.estado, "value") else str(abono.estado),
                "cobro_actual": {
                    "id": cobro_actual.id,
                    "periodo": getattr(cobro_actual, "periodo", ""),
                    "estado": cobro_actual.estado.value if hasattr(cobro_actual.estado, "value") else str(cobro_actual.estado),
                    "fecha_vencimiento": cobro_actual.fecha_vencimiento.isoformat() if getattr(cobro_actual, "fecha_vencimiento", None) else None,
                } if cobro_actual else None,
            }
            historial_cobros = [
                {
                    "periodo": getattr(c, "periodo", ""),
                    "monto": float(c.monto or 0),
                    "estado": c.estado.value if hasattr(c.estado, "value") else str(c.estado),
                    "fecha_cobro": c.fecha_cobro.isoformat() if getattr(c, "fecha_cobro", None) else None,
                }
                for c in cobros
            ]
    except Exception:
        pass

    # Portal
    portal_data = None
    try:
        from models.portal_usuario import PortalUsuario
        from models.portal_notificacion import PortalNotificacion
        pu = db.query(PortalUsuario).filter(PortalUsuario.cliente_id == cliente_id).first()
        if pu:
            tareas_portal = db.query(Tarea).filter(
                Tarea.cliente_id == cliente_id,
                Tarea.activo == True,
                Tarea.estado.in_([EstadoTarea.pendiente, EstadoTarea.en_progreso]),
            ).count()
            notifs_pendientes = db.query(PortalNotificacion).filter(
                PortalNotificacion.cliente_id == cliente_id,
                PortalNotificacion.leida == False,
            ).count()
            portal_data = {
                "usuario_activo": pu.activo,
                "email_portal": pu.email,
                "tareas_portal_pendientes": tareas_portal,
                "notificaciones_pendientes": notifs_pendientes,
                "ultimo_acceso": pu.ultimo_acceso.isoformat() if pu.ultimo_acceso else None,
            }
    except Exception:
        pass

    # Resumen ejecutivo
    cobro_estado = "sin_abono"
    if abono_data and abono_data.get("cobro_actual"):
        cobro_estado = abono_data["cobro_actual"].get("estado", "sin_abono")

    resumen = {
        "score_riesgo": getattr(cliente, "score_riesgo", None),
        "alertas_activas": len(alertas_activas),
        "vencimientos_proximos_7_dias": sum(1 for v in proximos if 0 <= v.dias_para_vencer <= 7),
        "tareas_pendientes": len(activas),
        "cobro_estado": cobro_estado,
        "honorario_base": float(getattr(cliente, "honorario_base", 0) or 0),
    }

    # Notas del cliente
    notas = getattr(cliente, "notas", None)

    return FichaClienteResponse(
        cliente=ClienteResponse.model_validate(cliente),
        contador_principal=contador_principal,
        participantes_tareas=participantes,
        vencimientos={"proximos": proximos, "vencidos": vencidos},
        tareas={"activas": activas, "completadas_recientes": completadas_recientes},
        estado_alerta=alerta,
        documentos=documentos,
        resumen=resumen,
        alertas_activas=alertas_activas,
        abono=abono_data,
        historial_cobros=historial_cobros,
        portal=portal_data,
        notas=notas,
    )
