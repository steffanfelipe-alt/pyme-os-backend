from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.rentabilidad import RentabilidadMensual
from models.studio_config import StudioConfig
from models.tarea import EstadoTarea, Tarea


def _parse_periodo(periodo: str) -> tuple[date, date]:
    """Devuelve (primer_dia, ultimo_dia) del mes YYYY-MM."""
    import calendar
    if len(periodo) != 7 or periodo[4] != "-":
        raise HTTPException(status_code=400, detail="Formato de período inválido. Usar YYYY-MM.")
    try:
        anio, mes = int(periodo[:4]), int(periodo[5:7])
        if mes < 1 or mes > 12:
            raise ValueError()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de período inválido. Usar YYYY-MM.")
    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])
    return primer_dia, ultimo_dia


def calcular_rentabilidad_periodo(db: Session, periodo: str, studio_id: int) -> list[dict]:
    """
    Calcula y persiste snapshots de rentabilidad para todos los clientes activos.
    Sobreescribe snapshots existentes del mismo período.
    """
    primer_dia, ultimo_dia = _parse_periodo(periodo)

    clientes = db.query(Cliente).filter(Cliente.activo == True, Cliente.studio_id == studio_id).all()
    resultados = []

    # Tarifa del estudio para calcular margen
    studio_config = db.query(StudioConfig).first()
    tarifa_hora = float(studio_config.tarifa_hora_pesos) if studio_config and studio_config.tarifa_hora_pesos else None

    for cliente in clientes:
        tareas = db.query(Tarea).filter(
            Tarea.cliente_id == cliente.id,
            Tarea.estado == EstadoTarea.completada,
            Tarea.activo == True,
            Tarea.fecha_completada >= primer_dia,
            Tarea.fecha_completada <= ultimo_dia,
        ).all()

        tareas_completadas = len(tareas)
        tareas_demoradas = sum(
            1 for t in tareas
            if t.fecha_completada and t.fecha_limite
            and t.fecha_completada > t.fecha_limite
        )

        # Sumar horas reales; fallback a horas_estimadas si horas_reales es null
        horas_reales_total = sum(
            (t.horas_reales if t.horas_reales is not None else (t.horas_estimadas or 0.0))
            for t in tareas
        )
        horas_estimadas_total = sum(
            (t.horas_estimadas or 0.0) for t in tareas
        )

        honorario = float(cliente.honorarios_mensuales) if cliente.honorarios_mensuales else None
        honorario_configurado = honorario is not None

        rentabilidad_hora = None
        if honorario_configurado and honorario > 0 and horas_reales_total > 0:
            rentabilidad_hora = round(honorario / horas_reales_total, 2)

        # Margen y costo estimado
        costo_estimado = None
        profit_margin_percentage = None
        if tarifa_hora is not None and horas_reales_total > 0:
            costo_estimado = round(horas_reales_total * tarifa_hora, 2)
            if honorario_configurado and honorario > 0:
                profit_margin_percentage = round(((honorario - costo_estimado) / honorario) * 100, 2)

        # Sobreescribir snapshot existente si ya existe para este cliente+periodo
        snapshot = db.query(RentabilidadMensual).filter(
            RentabilidadMensual.cliente_id == cliente.id,
            RentabilidadMensual.periodo == periodo,
            RentabilidadMensual.studio_id == studio_id,
        ).first()

        if snapshot:
            snapshot.honorario = honorario or 0.0
            snapshot.horas_reales = horas_reales_total
            snapshot.horas_estimadas = horas_estimadas_total if horas_estimadas_total > 0 else None
            snapshot.rentabilidad_hora = rentabilidad_hora
            snapshot.tareas_completadas = tareas_completadas
            snapshot.tareas_demoradas = tareas_demoradas
            snapshot.costo_estimado = costo_estimado
            snapshot.profit_margin_percentage = profit_margin_percentage
        else:
            snapshot = RentabilidadMensual(
                studio_id=studio_id,
                cliente_id=cliente.id,
                periodo=periodo,
                honorario=honorario or 0.0,
                horas_reales=horas_reales_total,
                horas_estimadas=horas_estimadas_total if horas_estimadas_total > 0 else None,
                rentabilidad_hora=rentabilidad_hora,
                tareas_completadas=tareas_completadas,
                tareas_demoradas=tareas_demoradas,
                costo_estimado=costo_estimado,
                profit_margin_percentage=profit_margin_percentage,
            )
            db.add(snapshot)

        # Calcular trend comparando con período anterior
        prev_anio, prev_mes = (int(periodo[:4]), int(periodo[5:7]))
        if prev_mes == 1:
            prev_periodo = f"{prev_anio - 1}-12"
        else:
            prev_periodo = f"{prev_anio}-{prev_mes - 1:02d}"

        prev_snap = db.query(RentabilidadMensual).filter(
            RentabilidadMensual.cliente_id == cliente.id,
            RentabilidadMensual.periodo == prev_periodo,
            RentabilidadMensual.studio_id == studio_id,
        ).first()

        trend = None
        if prev_snap and prev_snap.profit_margin_percentage is not None and profit_margin_percentage is not None:
            diff = profit_margin_percentage - prev_snap.profit_margin_percentage
            trend = "sube" if diff > 5 else ("baja" if diff < -5 else "estable")

        resultados.append({
            "cliente_id": cliente.id,
            "nombre": cliente.nombre,
            "periodo": periodo,
            "honorario": honorario,
            "honorario_configurado": honorario_configurado,
            "horas_reales": round(horas_reales_total, 2),
            "horas_estimadas": round(horas_estimadas_total, 2) if horas_estimadas_total > 0 else None,
            "rentabilidad_hora": rentabilidad_hora,
            "costo_estimado": costo_estimado,
            "profit_margin_percentage": profit_margin_percentage,
            "trend": trend,
            "tareas_completadas": tareas_completadas,
            "tareas_demoradas": tareas_demoradas,
        })

    db.commit()

    # Ordenar: con rentabilidad primero (ascendente = menos rentable primero),
    # sin honorario al final
    resultados.sort(key=lambda x: (
        x["rentabilidad_hora"] is None,
        x["rentabilidad_hora"] if x["rentabilidad_hora"] is not None else 0,
    ))
    return resultados


def listar_rentabilidad(db: Session, periodo: str, studio_id: int) -> list[dict]:
    """
    Retorna snapshots del período ordenados por rentabilidad_hora ascendente.
    Clientes sin honorario configurado aparecen al final.
    """
    _parse_periodo(periodo)  # validar formato

    snapshots = (
        db.query(RentabilidadMensual, Cliente)
        .join(Cliente, RentabilidadMensual.cliente_id == Cliente.id)
        .filter(
            RentabilidadMensual.periodo == periodo,
            RentabilidadMensual.studio_id == studio_id,
            Cliente.activo == True,
        )
        .all()
    )

    resultado = []
    for snap, cliente in snapshots:
        honorario_configurado = snap.honorario > 0
        resultado.append({
            "cliente_id": cliente.id,
            "nombre": cliente.nombre,
            "periodo": periodo,
            "honorario": snap.honorario if honorario_configurado else None,
            "honorario_configurado": honorario_configurado,
            "horas_reales": snap.horas_reales,
            "horas_estimadas": snap.horas_estimadas,
            "rentabilidad_hora": snap.rentabilidad_hora,
            "costo_estimado": snap.costo_estimado,
            "profit_margin_percentage": snap.profit_margin_percentage,
            "tareas_completadas": snap.tareas_completadas,
            "tareas_demoradas": snap.tareas_demoradas,
        })

    resultado.sort(key=lambda x: (
        x["rentabilidad_hora"] is None,
        x["rentabilidad_hora"] if x["rentabilidad_hora"] is not None else 0,
    ))
    return resultado


def historial_cliente(db: Session, cliente_id: int, meses: int = 12, studio_id: int = None) -> list[dict]:
    """Últimos N snapshots de un cliente, ordenados por período descendente."""
    filtros = [Cliente.id == cliente_id, Cliente.activo == True]
    if studio_id is not None:
        filtros.append(Cliente.studio_id == studio_id)
    cliente = db.query(Cliente).filter(*filtros).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    snap_filtros = [RentabilidadMensual.cliente_id == cliente_id]
    if studio_id is not None:
        snap_filtros.append(RentabilidadMensual.studio_id == studio_id)
    snapshots = (
        db.query(RentabilidadMensual)
        .filter(*snap_filtros)
        .order_by(RentabilidadMensual.periodo.desc())
        .limit(meses)
        .all()
    )

    return [
        {
            "periodo": s.periodo,
            "honorario": s.honorario,
            "horas_reales": s.horas_reales,
            "horas_estimadas": s.horas_estimadas,
            "rentabilidad_hora": s.rentabilidad_hora,
            "tareas_completadas": s.tareas_completadas,
            "tareas_demoradas": s.tareas_demoradas,
        }
        for s in snapshots
    ]
