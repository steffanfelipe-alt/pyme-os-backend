import logging
from calendar import monthrange
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.cliente import Cliente, CondicionFiscal
from models.empleado import Empleado  # noqa: F401 — necesario para resolver FK cliente→empleados
from models.plantilla_vencimiento import PlantillaVencimiento, RecurrenciaPlantilla
from models.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from schemas.plantilla_vencimiento import PlantillaCreate, PlantillaUpdate

logger = logging.getLogger("pymeos")


def _calcular_dia(plantilla: PlantillaVencimiento, cuit_cuil: str) -> int:
    if plantilla.mapa_digito_dia:
        clean = cuit_cuil.replace("-", "").replace(" ", "")
        ultimo_digito = clean[-1]
        return int(plantilla.mapa_digito_dia.get(ultimo_digito, plantilla.dia_vencimiento))
    return plantilla.dia_vencimiento


def _fecha_segura(año: int, mes: int, dia: int) -> date:
    """Clamp el día al último día del mes si excede."""
    max_dia = monthrange(año, mes)[1]
    return date(año, mes, min(dia, max_dia))


def _descripcion(template: str, mes: int, año: int) -> str:
    meses = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
    }
    return template.replace("{mes}", meses[mes]).replace("{año}", str(año))


# --- CRUD ---

def crear_plantilla(db: Session, data: PlantillaCreate, studio_id: int) -> PlantillaVencimiento:
    plantilla = PlantillaVencimiento(**data.model_dump(), studio_id=studio_id)
    db.add(plantilla)
    db.commit()
    db.refresh(plantilla)
    return plantilla


def listar_plantillas(
    db: Session,
    condicion_fiscal: Optional[CondicionFiscal] = None,
    activo: Optional[bool] = True,
    studio_id: int = None,
) -> list[PlantillaVencimiento]:
    query = db.query(PlantillaVencimiento)
    if studio_id is not None:
        query = query.filter(PlantillaVencimiento.studio_id == studio_id)
    if condicion_fiscal is not None:
        query = query.filter(PlantillaVencimiento.condicion_fiscal == condicion_fiscal)
    if activo is not None:
        query = query.filter(PlantillaVencimiento.activo == activo)
    return query.all()


def obtener_plantilla(db: Session, plantilla_id: int, studio_id: int = None) -> PlantillaVencimiento:
    filtros = [PlantillaVencimiento.id == plantilla_id]
    if studio_id is not None:
        filtros.append(PlantillaVencimiento.studio_id == studio_id)
    p = db.query(PlantillaVencimiento).filter(*filtros).first()
    if not p:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return p


def actualizar_plantilla(db: Session, plantilla_id: int, data: PlantillaUpdate, studio_id: int = None) -> PlantillaVencimiento:
    plantilla = obtener_plantilla(db, plantilla_id, studio_id)
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(plantilla, campo, valor)
    db.commit()
    db.refresh(plantilla)
    return plantilla


def eliminar_plantilla(db: Session, plantilla_id: int, studio_id: int = None) -> None:
    plantilla = obtener_plantilla(db, plantilla_id, studio_id)
    plantilla.activo = False
    db.commit()


# --- Generación de vencimientos ---

def aplicar_plantillas_a_cliente(db: Session, cliente_id: int, studio_id: int) -> dict:
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.studio_id == studio_id, Cliente.activo == True
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    plantillas = db.query(PlantillaVencimiento).filter(
        PlantillaVencimiento.condicion_fiscal == cliente.condicion_fiscal,
        PlantillaVencimiento.activo == True,
    ).all()

    if not plantillas:
        raise HTTPException(
            status_code=404,
            detail=f"No hay plantillas activas para condición fiscal: {cliente.condicion_fiscal.value}",
        )

    hoy = date.today()
    generados = 0

    for plantilla in plantillas:
        dia = _calcular_dia(plantilla, cliente.cuit_cuil)

        if plantilla.recurrencia == RecurrenciaPlantilla.mensual:
            for i in range(13):  # iterar 13 para asegurarnos 12 futuros incluso si el mes actual ya pasó
                mes_offset = hoy.month - 1 + i
                año = hoy.year + mes_offset // 12
                mes = mes_offset % 12 + 1
                fecha = _fecha_segura(año, mes, dia)
                if fecha < hoy:
                    continue
                descripcion = _descripcion(plantilla.descripcion_template, mes, año)
                _crear_vencimiento_si_no_existe(db, cliente_id, plantilla, fecha, descripcion, studio_id)
                generados += 1

        elif plantilla.recurrencia == RecurrenciaPlantilla.bimestral:
            for i in range(7):
                mes_offset = hoy.month - 1 + (i * 2)
                año = hoy.year + mes_offset // 12
                mes = mes_offset % 12 + 1
                fecha = _fecha_segura(año, mes, dia)
                if fecha < hoy:
                    continue
                descripcion = _descripcion(plantilla.descripcion_template, mes, año)
                _crear_vencimiento_si_no_existe(db, cliente_id, plantilla, fecha, descripcion, studio_id)
                generados += 1

        elif plantilla.recurrencia == RecurrenciaPlantilla.cuatrimestral:
            for i in range(4):
                mes_offset = hoy.month - 1 + (i * 4)
                año = hoy.year + mes_offset // 12
                mes = mes_offset % 12 + 1
                fecha = _fecha_segura(año, mes, dia)
                if fecha < hoy:
                    continue
                descripcion = _descripcion(plantilla.descripcion_template, mes, año)
                _crear_vencimiento_si_no_existe(db, cliente_id, plantilla, fecha, descripcion, studio_id)
                generados += 1

        elif plantilla.recurrencia == RecurrenciaPlantilla.anual:
            mes = plantilla.mes_inicio or hoy.month
            año = hoy.year if hoy.month <= mes else hoy.year + 1
            fecha = _fecha_segura(año, mes, dia)
            if fecha >= hoy:
                descripcion = _descripcion(plantilla.descripcion_template, mes, año)
                _crear_vencimiento_si_no_existe(db, cliente_id, plantilla, fecha, descripcion, studio_id)
                generados += 1

    cliente.plantilla_aplicada = True
    db.commit()

    logger.info("Plantillas aplicadas al cliente %d — %d vencimientos generados", cliente_id, generados)
    return {"cliente_id": cliente_id, "vencimientos_generados": generados}


def _crear_vencimiento_si_no_existe(
    db: Session,
    cliente_id: int,
    plantilla: PlantillaVencimiento,
    fecha: date,
    descripcion: str,
    studio_id: int,
) -> None:
    existente = db.query(Vencimiento).filter(
        Vencimiento.cliente_id == cliente_id,
        Vencimiento.studio_id == studio_id,
        Vencimiento.tipo == plantilla.tipo,
        Vencimiento.fecha_vencimiento == fecha,
    ).first()
    if not existente:
        venc = Vencimiento(
            studio_id=studio_id,
            cliente_id=cliente_id,
            tipo=plantilla.tipo,
            descripcion=descripcion,
            fecha_vencimiento=fecha,
            estado=EstadoVencimiento.pendiente,
        )
        db.add(venc)


# --- Seed de plantillas por defecto ---

PLANTILLAS_DEFAULT = [
    {
        "condicion_fiscal": CondicionFiscal.monotributista,
        "tipo": TipoVencimiento.monotributo,
        "descripcion_template": "Cuota Monotributo {mes} {año}",
        "dia_vencimiento": 7,
        "mapa_digito_dia": {
            "0": 7, "1": 7, "2": 8, "3": 8,
            "4": 9, "5": 9, "6": 10, "7": 10, "8": 11, "9": 11,
        },
        "recurrencia": RecurrenciaPlantilla.mensual,
        "mes_inicio": None,
    },
    {
        "condicion_fiscal": CondicionFiscal.responsable_inscripto,
        "tipo": TipoVencimiento.iva,
        "descripcion_template": "IVA {mes} {año}",
        "dia_vencimiento": 18,
        "mapa_digito_dia": {
            "0": 18, "1": 18, "2": 19, "3": 19,
            "4": 20, "5": 20, "6": 21, "7": 21, "8": 22, "9": 22,
        },
        "recurrencia": RecurrenciaPlantilla.mensual,
        "mes_inicio": None,
    },
    {
        "condicion_fiscal": CondicionFiscal.responsable_inscripto,
        "tipo": TipoVencimiento.ganancias,
        "descripcion_template": "Ganancias {año}",
        "dia_vencimiento": 13,
        "mapa_digito_dia": {
            "0": 13, "1": 13, "2": 14, "3": 14,
            "4": 15, "5": 15, "6": 16, "7": 16, "8": 17, "9": 17,
        },
        "recurrencia": RecurrenciaPlantilla.anual,
        "mes_inicio": 6,
    },
    {
        "condicion_fiscal": CondicionFiscal.responsable_inscripto,
        "tipo": TipoVencimiento.iibb,
        "descripcion_template": "IIBB {mes} {año}",
        "dia_vencimiento": 15,
        "mapa_digito_dia": None,
        "recurrencia": RecurrenciaPlantilla.mensual,
        "mes_inicio": None,
    },
    {
        "condicion_fiscal": CondicionFiscal.relacion_de_dependencia,
        "tipo": TipoVencimiento.sueldos_cargas,
        "descripcion_template": "Sueldos y Cargas {mes} {año}",
        "dia_vencimiento": 10,
        "mapa_digito_dia": None,
        "recurrencia": RecurrenciaPlantilla.mensual,
        "mes_inicio": None,
    },
    {
        "condicion_fiscal": CondicionFiscal.autonomos,
        "tipo": TipoVencimiento.autonomos,
        "descripcion_template": "Aportes Autónomos {mes} {año}",
        "dia_vencimiento": 3,
        "mapa_digito_dia": {
            "0": 3, "1": 3, "2": 4, "3": 4,
            "4": 5, "5": 5, "6": 6, "7": 6, "8": 7, "9": 7,
        },
        "recurrencia": RecurrenciaPlantilla.mensual,
        "mes_inicio": None,
    },
]


def seed_plantillas_default(db: Session) -> None:
    cantidad = db.query(PlantillaVencimiento).count()
    if cantidad > 0:
        return
    for datos in PLANTILLAS_DEFAULT:
        db.add(PlantillaVencimiento(**datos))
    db.commit()
    logger.info("Plantillas por defecto cargadas (%d)", len(PLANTILLAS_DEFAULT))
