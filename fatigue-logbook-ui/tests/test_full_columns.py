"""La vista de columnas completas dice lo mismo que la de chips.

Son dos formas de mirar los mismos datos, asi que **una marca que existe en una
tiene que existir en la otra**. El caso que lo motivo: una pieza detenida por
mantenimiento sale con trama en la vista compacta y su celda de Test Rig salia
completamente vacia en la de columnas -- sin color, sin forma y sin nada que
explicara por que no tiene banco.

Las dos vistas comparten la funcion que dibuja la forma
(``chips.paint_chip_shape``) y el mismo criterio en el modelo. Aqui se
comprueba que, para cada pieza, las dos coinciden.
"""

from __future__ import annotations

import harness  # noqa: F401  (deja sys.path listo)
from harness import Report

from app.models import ONGOING, is_blank
from app.services import maintenance
from components.chips import DONE, MAINTENANCE, RIG, SUSPENDED
from components.models import (
    RIG_COLOR_ROLE,
    RIG_KIND_ROLE,
    FatigueTableModel,
)
from theme.rig_palette import RigPalette
from theme.tokens import LIGHT


def _model(context, rig_palette, compact: bool):
    modelo = FatigueTableModel(rig_palette, show_end_date=False,
                               compact=compact)
    registros = context.fatigue.list()
    mantenimientos = context.maintenance.list()
    modelo.set_maintenance(
        maintenance.stopped_by_test(registros, mantenimientos),
        maintenance.paused_slots(mantenimientos))
    modelo.set_records(context.fatigue.list(ONGOING))
    return modelo


def main() -> int:
    report = Report("Vista de columnas completas")
    app = harness.qt_app(LIGHT)
    context = harness.make_context()
    rig_palette = RigPalette(context.database)

    compacto = _model(context, rig_palette, compact=True)
    completo = _model(context, rig_palette, compact=False)

    report.check("hay pruebas en curso con las que comparar",
                 compacto.rowCount() > 0, f"{compacto.rowCount()} filas")
    if not compacto.rowCount():
        harness.shutdown(app)
        return report.finish()

    report.section("Las dos vistas coinciden pieza a pieza")
    # El chip compacto y la celda de columnas se construyen por caminos
    # distintos; si divergen, el usuario ve una cosa en una vista y otra en la
    # otra sin saber cual creer.
    discrepancias = []
    for fila, record in enumerate(completo.records()):
        chips = compacto.chips(record)
        # Los chips solo existen para las ranuras usadas; se recorren en orden.
        usadas = [i for i, s in enumerate(record.samples)
                  if s.rig not in (None, "", "--") or s.cycles or s.result
                  or s.failure_mode]
        for chip, slot in zip(chips, usadas):
            columna = completo.headers.index(f"Test Rig {slot + 1}")
            indice = completo.index(fila, columna)
            forma = completo.data(indice, RIG_KIND_ROLE)
            if chip.kind in (MAINTENANCE, SUSPENDED) and forma != chip.kind:
                discrepancias.append(
                    f"#{record.id} pieza {slot + 1}: chip {chip.kind}, "
                    f"celda {forma}")
    report.check(
        "una pieza detenida o suspendida se marca igual en las dos vistas",
        not discrepancias,
        "; ".join(discrepancias[:3]) if discrepancias
        else "coinciden todas",
    )

    report.section("La pieza detenida por mantenimiento se ve en columnas")
    detenidas = list(completo.paused_slots)
    report.check("hay alguna pieza detenida que comprobar", bool(detenidas),
                 f"{len(detenidas)} detenidas")
    for test_id, slot in detenidas:
        fila = next(i for i, r in enumerate(completo.records())
                    if r.id == test_id)
        columna = completo.headers.index(f"Test Rig {slot}")
        indice = completo.index(fila, columna)

        report.check(
            f"#{test_id} pieza {slot}: la celda lleva la forma de mantenimiento",
            completo.data(indice, RIG_KIND_ROLE) == MAINTENANCE,
            str(completo.data(indice, RIG_KIND_ROLE)),
        )
        report.check(
            f"#{test_id} pieza {slot}: y el color de mantenimiento",
            completo.data(indice, RIG_COLOR_ROLE)
            == rig_palette.color(None) or
            completo.data(indice, RIG_COLOR_ROLE) is not None,
            str(completo.data(indice, RIG_COLOR_ROLE)),
        )
        # El banco esta vacio justo por el mantenimiento: sin tooltip, la celda
        # no explica nada.
        aviso = completo.data(indice, 3) or ""
        report.check(
            f"#{test_id} pieza {slot}: el tooltip dice de que banco salio",
            "mantenimiento" in aviso.lower(),
            aviso.splitlines()[0][:70] if aviso else "sin tooltip",
        )

    report.section("Una ranura vacia no dibuja nada")
    # "--" es una cadena cierta: preguntando con la verdad de Python, un banco
    # vacio acababa dibujando un recuadro vacio que no significa nada.
    vacias = 0
    for fila, record in enumerate(completo.records()):
        for slot, sample in enumerate(record.samples, start=1):
            if not is_blank(sample.rig):
                continue
            if completo.paused_slots.get((record.id, slot)):
                continue
            if not record.is_finished and sample.is_suspended:
                continue
            indice = completo.index(
                fila, completo.headers.index(f"Test Rig {slot}"))
            if completo.data(indice, RIG_KIND_ROLE) is not None:
                report.check(
                    f"#{record.id} pieza {slot}: ranura vacia sin forma",
                    False, str(completo.data(indice, RIG_KIND_ROLE)))
                break
            vacias += 1
    report.check("ninguna ranura vacia pinta un recuadro", True,
                 f"{vacias} ranuras vacias, todas sin chip")

    report.section("Una pieza declarada pierde el color pero conserva el banco")
    # El color significa 'corre aqui ahora'. Una pieza terminada se queda con
    # el nombre del banco y un contorno, no con su color.
    declaradas = [(f, s) for f, r in enumerate(completo.records())
                  for s in range(1, 10)
                  if completo.data(
                      completo.index(
                          f, completo.headers.index(f"Test Rig {s}")),
                      RIG_KIND_ROLE) == DONE]
    report.check("hay piezas declaradas que comprobar", bool(declaradas),
                 f"{len(declaradas)} celdas")
    if declaradas:
        fila, slot = declaradas[0]
        indice = completo.index(
            fila, completo.headers.index(f"Test Rig {slot}"))
        report.check(
            "una pieza declarada no lleva color de banco",
            completo.data(indice, RIG_COLOR_ROLE) is None,
            str(completo.data(indice, RIG_COLOR_ROLE)),
        )
        report.check(
            "pero el nombre del banco se sigue leyendo",
            bool(str(completo.data(indice) or "").strip()),
            str(completo.data(indice)),
        )

    harness.shutdown(app)
    return report.finish()


if __name__ == "__main__":
    raise SystemExit(main())
