"""F1 + F2 — Gestión de abonos y cobros con alertas de cobranza."""
from calendar import monthrange
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.abono import Abono, Cobro, EstadoCobro, PeriodicidadAbono
from models.cliente import Cliente


# ── helpers periodicidad ──────────────────────────────────────────────────────

_MESES_PERIODO = {
    PeriodicidadAbono.mensual: 1,
    PeriodicidadAbono.bimestral: 2,
    PeriodicidadAbono.trimestral: 3,
    PeriodicidadAbono.semestral: 6,
    PeriodicidadAbono.anual: 12,
}


def _proximo_cobro(desde: date, periodicidad: PeriodicidadAbono) -> date:
    """Avanza n meses con aritmética de calendario correcta (clamp al último día del mes)."""
    n = _MESES_PERIODO[periodicidad]
    month = desde.month - 1 + n
    year = desde.year + month // 12
    month = month % 12 + 1
    day = min(desde.day, monthrange(year, month)[1])
    return date(year, month, day)


# ── Abonos CRUD ───────────────────────────────────────────────────────────────

def crear_abono(db: Session, studio_id: int, data: dict) -> Abono:
    cliente = db.query(Cliente).filter(
        Cliente.id == data["cliente_id"], Cliente.studio_id == studio_id
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    fecha_inicio = data.get("fecha_inicio", date.today())
    periodicidad = PeriodicidadAbono(data.get("periodicidad", "mensual"))

    abono = Abono(
        studio_id=studio_id,
        cliente_id=data["cliente_id"],
        concepto=data["concepto"],
        monto=data["monto"],
        periodicidad=periodicidad,
        fecha_inicio=fecha_inicio,
        fecha_proximo_cobro=_proximo_cobro(fecha_inicio, periodicidad),
        activo=data.get("activo", True),
        notas=data.get("notas"),
    )
    db.add(abono)
    db.commit()
    db.refresh(abono)

    # Generar primer cobro pendiente
    _generar_cobro(db, abono)

    return abono


def _generar_cobro(db: Session, abono: Abono) -> Cobro:
    cobro = Cobro(
        studio_id=abono.studio_id,
        abono_id=abono.id,
        fecha_cobro=abono.fecha_proximo_cobro or abono.fecha_inicio,
        monto=float(abono.monto),
        estado=EstadoCobro.pendiente,
    )
    db.add(cobro)
    db.commit()
    db.refresh(cobro)
    return cobro


def listar_abonos(db: Session, studio_id: int, cliente_id: int | None = None) -> list[Abono]:
    q = db.query(Abono).filter(Abono.studio_id == studio_id)
    if cliente_id is not None:
        q = q.filter(Abono.cliente_id == cliente_id)
    return q.order_by(Abono.created_at.desc()).all()


def obtener_abono(db: Session, abono_id: int, studio_id: int) -> Abono:
    abono = db.query(Abono).filter(
        Abono.id == abono_id, Abono.studio_id == studio_id
    ).first()
    if not abono:
        raise HTTPException(status_code=404, detail="Abono no encontrado")
    return abono


def actualizar_abono(db: Session, abono_id: int, studio_id: int, data: dict) -> Abono:
    abono = obtener_abono(db, abono_id, studio_id)
    for k, v in data.items():
        if v is not None and hasattr(abono, k):
            setattr(abono, k, v)
    db.commit()
    db.refresh(abono)
    return abono


def eliminar_abono(db: Session, abono_id: int, studio_id: int) -> None:
    abono = obtener_abono(db, abono_id, studio_id)
    db.delete(abono)
    db.commit()


# ── Cobros ────────────────────────────────────────────────────────────────────

def listar_cobros(db: Session, studio_id: int, abono_id: int | None = None, estado: EstadoCobro | None = None) -> list[Cobro]:
    q = db.query(Cobro).filter(Cobro.studio_id == studio_id)
    if abono_id is not None:
        q = q.filter(Cobro.abono_id == abono_id)
    if estado is not None:
        q = q.filter(Cobro.estado == estado)
    return q.order_by(Cobro.fecha_cobro.desc()).all()


def registrar_cobro_pagado(db: Session, cobro_id: int, studio_id: int, notas: str | None = None) -> Cobro:
    """Marca un cobro como cobrado y genera el siguiente cobro pendiente."""
    cobro = db.query(Cobro).filter(
        Cobro.id == cobro_id, Cobro.studio_id == studio_id
    ).first()
    if not cobro:
        raise HTTPException(status_code=404, detail="Cobro no encontrado")

    cobro.estado = EstadoCobro.cobrado
    if notas:
        cobro.notas = notas
    db.commit()
    db.refresh(cobro)

    # Generar siguiente cobro si el abono sigue activo
    abono = db.query(Abono).filter(Abono.id == cobro.abono_id).first()
    if abono and abono.activo:
        siguiente = _proximo_cobro(cobro.fecha_cobro, abono.periodicidad)
        abono.fecha_proximo_cobro = siguiente
        db.commit()
        _generar_cobro(db, abono)

    return cobro


# ── F2 — Alertas de cobranza ──────────────────────────────────────────────────

def evaluar_cobros_vencidos(db: Session, studio_id: int | None = None) -> list[dict]:
    """
    Marca como vencidos los cobros cuya fecha_cobro ya pasó y siguen pendientes.
    Retorna lista de cobros marcados para log/notificación.
    """
    hoy = date.today()
    q = db.query(Cobro).filter(
        Cobro.estado == EstadoCobro.pendiente,
        Cobro.fecha_cobro < hoy,
    )
    if studio_id is not None:
        q = q.filter(Cobro.studio_id == studio_id)

    vencidos = q.all()
    resultado = []
    for cobro in vencidos:
        cobro.estado = EstadoCobro.vencido
        resultado.append({
            "cobro_id": cobro.id,
            "abono_id": cobro.abono_id,
            "studio_id": cobro.studio_id,
            "fecha_cobro": cobro.fecha_cobro.isoformat(),
            "monto": float(cobro.monto),
        })
    db.commit()
    return resultado


def resumen_cobros(db: Session, studio_id: int) -> dict:
    """Resumen de cobros por estado para el studio."""
    cobros = db.query(Cobro).filter(Cobro.studio_id == studio_id).all()
    return {
        "pendientes": sum(1 for c in cobros if c.estado == EstadoCobro.pendiente),
        "cobrados": sum(1 for c in cobros if c.estado == EstadoCobro.cobrado),
        "vencidos": sum(1 for c in cobros if c.estado == EstadoCobro.vencido),
        "monto_pendiente": sum(float(c.monto) for c in cobros if c.estado == EstadoCobro.pendiente),
        "monto_vencido": sum(float(c.monto) for c in cobros if c.estado == EstadoCobro.vencido),
    }
