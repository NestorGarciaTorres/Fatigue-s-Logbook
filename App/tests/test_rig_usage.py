"""Piezas terminadas por banco, y ocupacion.

Dos preguntas que las dos pantallas que las muestran calculaban por separado, y
no daban lo mismo: la de rigs cruzaba (nombre, tipo) sobre Fatiga y Rotary, y
la tarjeta del dashboard solo Fatiga y por nombre. Ahora las dos llaman al
mismo servicio, y esta suite lo comprueba con datos armados a mano --donde se
sabe la respuesta-- y contra la base real.
"""

import time
from datetime import date

from harness import Report, database_copy

from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.context import AppContext
from app.models import (
    FINISHED,
    ONGOING,
    FatigueSample,
    FatigueTest,
    GenericTest,
    Rig,
    RotarySample,
    RotaryTest,
)
from app.services import rig_usage
from app.ui import theme

report = Report("Piezas por banco y ocupación")

# ======================================================================
report.section("1. Con datos armados, donde se sabe la respuesta")

CATALOGO = [
    Rig("A-1", "fatigue"), Rig("A-2", "fatigue"),
    Rig("I-25", "rotary"), Rig("I-25", "torsion"), Rig("I-25", "quasi"),
]
claves = rig_usage.catalog_keys(CATALOGO)

cerrada = FatigueTest(
    test_batch="242314STF01", test_status=FINISHED, qty_samples=4,
    start_date=date(2026, 1, 1), end_date=date(2026, 2, 1),
    samples=[
        FatigueSample(rig="A-1", result="Falla", cycles=100),
        FatigueSample(rig="A-1", result="S/Falla", cycles=200),
        FatigueSample(rig="A-2", result="Falla", cycles=300),
        # Pieza cerrada sin banco anotado: cuenta como pieza, pero no se le
        # puede atribuir banco. Es el caso de casi toda la historia previa.
        FatigueSample(result="Falla", cycles=400),
    ] + [FatigueSample() for _ in range(5)],
)
abierta = FatigueTest(
    test_batch="242314STF02", test_status=ONGOING, qty_samples=2,
    start_date=date(2026, 3, 1),
    samples=[FatigueSample(rig="A-1", cycles=10),
             FatigueSample(rig="A-2", cycles=20)]
            + [FatigueSample() for _ in range(7)],
)

piezas = rig_usage.finished_pieces([cerrada, abierta], [], {})
report.note(f"por banco: {piezas.by_rig}")
report.check("cuenta las piezas de la prueba cerrada",
             piezas.by_rig.get(("A-1", "fatigue")) == 2
             and piezas.by_rig.get(("A-2", "fatigue")) == 1,
             str(piezas.by_rig))
report.check("la prueba en curso no entra en la cuenta",
             piezas.total == 4, f"total {piezas.total}")
report.check("una pieza sin banco cuenta como pieza pero no se atribuye",
             piezas.attributed == 3 and piezas.total == 4,
             f"{piezas.attributed} de {piezas.total}")
report.check("y eso se puede decir en pantalla",
             abs(piezas.coverage - 0.75) < 1e-9, f"{piezas.coverage:.2f}")

rotary_cerrada = RotaryTest(
    test_batch="242314SRF01", test_status=FINISHED, test_rig="I-25",
    qty_samples=3, start_date=date(2026, 1, 1), end_date=date(2026, 2, 1),
    samples=[RotarySample(revs=10, status="Falla"),
             RotarySample(revs=20, status="Falla"),
             RotarySample(revs=30, status="S/Falla")]
            + [RotarySample() for _ in range(6)],
)
generic = {
    "torsion": [GenericTest(test_batch="242314SST01", test_rig="I-25",
                            qty_samples=5, test_date=date(2026, 1, 5))],
    "quasi": [GenericTest(test_batch="242314SQF01", test_rig="I-25",
                          qty_samples=7, test_date=date(2026, 1, 6))],
}
mezcla = rig_usage.finished_pieces([], [rotary_cerrada], generic)
report.note(f"tres bancos que se llaman igual: {mezcla.by_rig}")
report.check("Rotary suma sus piezas usadas",
             mezcla.by_rig.get(("I-25", "rotary")) == 3, str(mezcla.by_rig))
report.check("Torsión y Quasi suman las piezas declaradas",
             mezcla.by_rig.get(("I-25", "torsion")) == 5
             and mezcla.by_rig.get(("I-25", "quasi")) == 7, str(mezcla.by_rig))
report.check("los tres I-25 no se mezclan entre si",
             len([k for k in mezcla.by_rig if k[0] == "I-25"]) == 3,
             str(sorted(mezcla.by_rig)))

# ======================================================================
report.section("2. Ocupación: la misma cuenta para las dos pantallas")

ocupados, fuera = rig_usage.occupancy([abierta], [], claves)
report.check("una prueba en curso ocupa los bancos de sus piezas",
             set(ocupados) == {("A-1", "fatigue"), ("A-2", "fatigue")},
             str(sorted(ocupados)))

repetida = FatigueTest(
    test_batch="242314STF03", test_status=ONGOING, qty_samples=2,
    start_date=date(2026, 3, 1),
    samples=[FatigueSample(rig="A-1", cycles=1),
             FatigueSample(rig="A-1", cycles=2)]
            + [FatigueSample() for _ in range(7)],
)
ocupados, _ = rig_usage.occupancy([repetida], [], claves)
report.check("un banco no lista dos veces la misma prueba",
             len(ocupados[("A-1", "fatigue")]) == 1,
             f"{len(ocupados[('A-1', 'fatigue')])} pruebas listadas")

intrusa = FatigueTest(
    test_batch="242314STF04", test_status=ONGOING, qty_samples=1,
    start_date=date(2026, 3, 1),
    samples=[FatigueSample(rig="NO-EXISTE", cycles=1)]
            + [FatigueSample() for _ in range(8)],
)
ocupados, fuera = rig_usage.occupancy([intrusa], [], claves)
report.check("un banco fuera del catálogo se reporta aparte",
             not ocupados and fuera == {"NO-EXISTE": 1}, str(dict(fuera)))

rot_abierta = RotaryTest(
    test_batch="242314SRF02", test_status=ONGOING, test_rig="I-25",
    qty_samples=1, start_date=date(2026, 3, 1),
    samples=[RotarySample(revs=5)] + [RotarySample() for _ in range(8)],
)
ocupados, _ = rig_usage.occupancy([], [rot_abierta], claves)
report.check("Rotary ocupa su banco, y solo el suyo",
             set(ocupados) == {("I-25", "rotary")}, str(sorted(ocupados)))

suspendida = RotaryTest(
    test_batch="242314SRF03", test_status=ONGOING, test_rig="",
    qty_samples=1, start_date=date(2026, 3, 1),
    samples=[RotarySample(revs=5)] + [RotarySample() for _ in range(8)],
)
ocupados, _ = rig_usage.occupancy([], [suspendida], claves)
report.check("una prueba fuera de banco no ocupa nada", not ocupados,
             str(sorted(ocupados)))

# ======================================================================
report.section("3. Sobre la base real, en las dos pantallas")

app = QApplication([])
theme.apply(app)
context = AppContext(AppConfig(database_path=str(database_copy()),
                               auto_backup=False))
context.prepare()

from app.ui.main_window import MainWindow

window = MainWindow(context)
window.start()


def settle(segundos: float = 0.8) -> None:
    fin = time.time() + segundos
    while time.time() < fin:
        app.processEvents()


settle(0.4)
window.show_page("rigs")
settle()
rigs_page = window.pages["rigs"]
window.show_page("dashboard")
settle(1.2)
dash = window.pages["dashboard"]

ocupados_pagina = rigs_page.card_busy.value_label.text()
ocupados_dash = dash.card_rigs.value_label.text()
report.note(f"rigs ocupados: pantalla de rigs {ocupados_pagina}, "
            f"dashboard {ocupados_dash}")
report.check("las dos pantallas dicen lo mismo",
             ocupados_pagina == ocupados_dash,
             f"{ocupados_pagina} vs {ocupados_dash}")

# El panel: un renglon por banco del catalogo.
rigs = context.catalogs.rigs()
filas = dash.rig_usage.rows.rowCount()
report.check("hay un renglón por banco del catálogo", filas == len(rigs),
             f"{filas} renglones para {len(rigs)} bancos")

# Y lo que dice el panel es lo que dice el servicio, con el mismo rango.
from app.services import filtering

rango = dash._range_filter()
esperado = rig_usage.finished_pieces(
    filtering.apply(context.fatigue.list(), rango),
    filtering.apply(context.rotary.list(), rango),
    {"torsion": filtering.apply(context.torsion.list(), rango),
     "quasi": filtering.apply(context.quasi.list(), rango)},
)
report.note(f"atribuidas {esperado.attributed:,} de {esperado.total:,} "
            f"({esperado.coverage:.0%})")
report.check("el subtítulo dice cuántas piezas tienen banco anotado",
             f"{esperado.attributed:,}" in dash.rig_usage.subtitle.text()
             and f"{esperado.total:,}" in dash.rig_usage.subtitle.text(),
             dash.rig_usage.subtitle.text())
report.check("la tarjeta de piezas cuadra con el panel",
             dash.card_samples.value_label.text() == f"{esperado.total:,}",
             f"{dash.card_samples.value_label.text()} vs {esperado.total:,}")

# Nada de lo que cuenta el panel viene de una prueba abierta.
abiertas = [t for t in context.fatigue.list(ONGOING)]
piezas_abiertas = sum(
    1 for t in abiertas for s in t.samples
    if s.rig and s.rig != "--"
)
solo_cerradas = rig_usage.finished_pieces(
    context.fatigue.list(), [], {}
)
report.check("hay piezas en curso que deben quedar fuera",
             piezas_abiertas > 0, f"{piezas_abiertas} piezas en bancos ahora")
report.check("y el conteo solo mira pruebas cerradas",
             solo_cerradas.total
             == sum(1 for t in context.fatigue.list()
                    if t.test_status == FINISHED
                    for s in t.samples
                    if s.cycles or s.result or s.failure_mode
                    or (s.rig and s.rig != "--")),
             f"{solo_cerradas.total} piezas")

if esperado.attributed < esperado.total:
    report.check("y avisa de las piezas que no se pueden atribuir",
                 dash.rig_usage.note.isVisibleTo(dash.rig_usage)
                 and "sin dejar anotado el banco" in dash.rig_usage.note.text(),
                 dash.rig_usage.note.text()[:70])

window.close()
app.quit()
raise SystemExit(report.finish())
