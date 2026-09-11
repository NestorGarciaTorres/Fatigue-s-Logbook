"""Mantenimiento de bancos: cual esta parado, desde cuando y a quien frena.

Un mantenimiento es un **intervalo**, no una bandera en el rig. De ahi salen
las tres cosas que la app necesita saber, y ninguna se puede responder con un
"este banco esta en mantenimiento" a secas:

- **Que piezas estan detenidas ahora.** Al entrar el banco en mantenimiento
  las piezas que corrian en el salen de ahi, y su estatus deja de ser una
  suspension cualquiera: estan paradas por el banco, no por la prueba.
- **Cuanto tiempo lleva parada una prueba.** Es lo que se descuenta de los
  dias en curso: una prueba de 40 dias de los que 12 fueron mantenimiento
  lleva 28 dias de ensayo, y el semaforo no tiene por que ponerse rojo por un
  paro que no es suyo.
- **Cuanto ha estado fuera de servicio cada banco.**

Los intervalos se **unen**, no se suman. Una prueba con dos piezas en dos
bancos distintos, parados los dos la misma semana, estuvo detenida una semana
y no dos.
"""

from __future__ import annotations

from datetime import date

from app.models import MAINTAINED_TEST_TYPES, MaintenanceSample, RigMaintenance

# La clave de un banco es (nombre, tipo de ensayo), igual que en rig_usage:
# hay un I-25 en Torsion, otro en Quasi y otro en Rotary.
RigKey = tuple[str, str]

FATIGUE_TABLE = "fatigue_tests"


# --------------------------------------------------------------------------
# Intervalos
# --------------------------------------------------------------------------

def _merge(intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """Une los intervalos que se solapan o se tocan."""
    ordered = sorted(i for i in intervals if i[0] <= i[1])
    merged: list[tuple[date, date]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def _clip(
    interval: tuple[date, date], window: tuple[date, date]
) -> tuple[date, date] | None:
    """La parte del intervalo que cae dentro de la ventana, si queda algo."""
    start = max(interval[0], window[0])
    end = min(interval[1], window[1])
    return (start, end) if start < end else None


def _span(record: RigMaintenance, reference: date) -> tuple[date, date] | None:
    """El periodo que cubre un mantenimiento. Uno abierto llega hasta hoy."""
    if record.start_date is None:
        return None
    return (record.start_date, record.end_date or reference)


def _total(intervals: list[tuple[date, date]]) -> int:
    """Dias que cubren los intervalos ya unidos.

    Se mide ``(fin - inicio).days``, como el resto de duraciones de la app: un
    mantenimiento que empieza y acaba el mismo dia no descuenta nada, igual
    que una prueba abierta y cerrada el mismo dia dura cero dias.
    """
    return sum((end - start).days for start, end in intervals)


# --------------------------------------------------------------------------
# Estado actual
# --------------------------------------------------------------------------

def open_by_rig(records: list[RigMaintenance]) -> dict[RigKey, RigMaintenance]:
    """Los mantenimientos abiertos, por banco.

    Si un banco tuviera dos abiertos --no deberia, la pantalla no lo permite--
    se queda el mas reciente, que es el que describe el estado de hoy.
    """
    abiertos: dict[RigKey, RigMaintenance] = {}
    for record in records:
        if not record.is_open:
            continue
        previo = abiertos.get(record.key)
        if previo is None or _newer(record, previo):
            abiertos[record.key] = record
    return abiertos


def rigs_in_maintenance(
    records: list[RigMaintenance], test_type: str = "fatigue"
) -> set[str]:
    """Nombres de los bancos de ese tipo que hoy estan fuera de servicio.

    Es lo que el formulario quita de las opciones de Test Rig: poner una pieza
    en un banco parado es capturar algo que no puede estar pasando.
    """
    return {nombre for (nombre, tipo) in open_by_rig(records)
            if tipo == test_type}


def _newer(one: RigMaintenance, other: RigMaintenance) -> bool:
    if one.start_date and other.start_date and one.start_date != other.start_date:
        return one.start_date > other.start_date
    return (one.id or 0) > (other.id or 0)


def paused_slots(
    records: list[RigMaintenance], table: str = FATIGUE_TABLE
) -> dict[tuple[int, int], RigMaintenance]:
    """Piezas detenidas ahora mismo: ``(id de prueba, pieza) -> mantenimiento``.

    Solo de los mantenimientos abiertos y de las piezas que no se han repuesto:
    una pieza que volvio a su banco antes de que el mantenimiento cerrara ya no
    esta detenida.
    """
    detenidas: dict[tuple[int, int], RigMaintenance] = {}
    for record in records:
        if not record.is_open:
            continue
        for sample in record.samples:
            # Ni la repuesta ni la que se llevaron a otro banco: las dos ya
            # estan corriendo, aunque el mantenimiento siga abierto.
            if not sample.is_held or sample.table_name != table:
                continue
            detenidas[(sample.record_id, sample.slot)] = record
    return detenidas


def affected_samples(
    rig_name: str, test_type: str, ongoing_tests: list
) -> list[MaintenanceSample]:
    """Piezas que hay que sacar del banco al ponerlo en mantenimiento.

    Solo las que **siguen corriendo**: una pieza con resultado ya anotado
    termino ahi, y su banco es el dato de donde corrio. Vaciarselo perderia esa
    informacion para siempre a cambio de nada -- esa pieza no esta esperando a
    que el banco vuelva.

    Un banco de una bitacora que todavia no maneja mantenimiento no saca
    ninguna pieza: el periodo se registra igual y mide el tiempo fuera de
    servicio, pero no toca registros de una bitacora cuyas reglas no estan
    decididas.
    """
    if test_type not in MAINTAINED_TEST_TYPES:
        return []

    afectadas: list[MaintenanceSample] = []
    for test in ongoing_tests:
        for slot, sample in enumerate(test.samples, start=1):
            if sample.rig != rig_name or sample.result:
                continue
            afectadas.append(
                MaintenanceSample(
                    record_id=test.id,
                    slot=slot,
                    rig_name=rig_name,
                    table_name=FATIGUE_TABLE,
                    test_batch=test.test_batch,
                )
            )
    return afectadas


# --------------------------------------------------------------------------
# Tiempo medido
# --------------------------------------------------------------------------

def stopped_days(
    test, records: list[RigMaintenance], reference: date | None = None
) -> int:
    """Dias que esta prueba estuvo detenida por mantenimiento de algun banco.

    Solo cuenta lo que cae dentro de la vida de la prueba: un banco que estuvo
    parado antes de que la prueba empezara no la detuvo.
    """
    if test.id is None or test.start_date is None:
        return 0

    today = reference or date.today()
    window = (test.start_date, getattr(test, "end_date", None) or today)
    if window[1] <= window[0]:
        return 0

    intervals: list[tuple[date, date]] = []
    for record in records:
        propias = [smp for smp in record.samples
                   if smp.record_id == test.id
                   and smp.table_name == FATIGUE_TABLE]
        if not propias:
            continue
        span = _span(record, today)
        if span is None:
            continue
        # Un intervalo por pieza, no por mantenimiento: la que se llevaron a
        # otro banco dejo de estar detenida ese dia, aunque el suyo siguiera
        # parado. Los intervalos se unen despues, asi que dos piezas paradas a
        # la vez siguen contando una sola vez.
        for sample in propias:
            fin = span[1]
            if sample.released_date and sample.released_date < fin:
                fin = sample.released_date
            clipped = _clip((span[0], fin), window)
            if clipped:
                intervals.append(clipped)

    return _total(_merge(intervals))


def stopped_by_test(
    tests: list, records: list[RigMaintenance], reference: date | None = None
) -> dict[int, int]:
    """``id de prueba -> dias detenida``. Solo las que tienen algun paro.

    Se calcula de una vez para todas: la tabla lo consulta por fila y una
    busqueda por fila sobre la lista de mantenimientos seria cuadratica.
    """
    if not records:
        return {}

    today = reference or date.today()
    afectadas = {s.record_id for r in records for s in r.samples}
    detenidas: dict[int, int] = {}
    for test in tests:
        if test.id not in afectadas:
            continue
        days = stopped_days(test, records, today)
        if days:
            detenidas[test.id] = days
    return detenidas


def downtime_by_rig(
    records: list[RigMaintenance],
    reference: date | None = None,
    window: tuple[date | None, date | None] | None = None,
) -> dict[RigKey, int]:
    """Dias fuera de servicio de cada banco, uniendo sus periodos.

    ``window`` recorta a un rango de fechas, para las pantallas que filtran por
    periodo: lo que cuenta ahi no es lo que el banco estuvo parado en total,
    sino lo que estuvo parado **dentro** del rango que se esta mirando.
    """
    today = reference or date.today()
    desde, hasta = window or (None, None)

    por_banco: dict[RigKey, list[tuple[date, date]]] = {}
    for record in records:
        span = _span(record, today)
        if span is None:
            continue
        if desde or hasta:
            span = _clip(span, (desde or date.min, hasta or date.max))
            if span is None:
                continue
        por_banco.setdefault(record.key, []).append(span)

    return {
        key: _total(_merge(spans)) for key, spans in por_banco.items()
    }


def overlapping(
    records: list[RigMaintenance],
    desde: date | None = None,
    hasta: date | None = None,
    reference: date | None = None,
) -> list[RigMaintenance]:
    """Los periodos que tocan la ventana, del mas reciente al mas antiguo.

    Un mantenimiento cuenta para un rango si **se solapa** con el, no si empezo
    dentro: uno que arranco en julio y sigue abierto es lo que tiene parado el
    banco hoy, y dejarlo fuera del periodo que se mira seria esconder
    justamente el que importa.
    """
    today = reference or date.today()
    dentro = []
    for record in records:
        span = _span(record, today)
        if span is None:
            continue
        if desde and span[1] < desde:
            continue
        if hasta and span[0] > hasta:
            continue
        dentro.append(record)

    return sorted(
        dentro,
        key=lambda r: (r.start_date or date.min, r.id or 0),
        reverse=True,
    )
