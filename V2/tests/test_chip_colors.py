"""Verifica que los resultados de pieza pierdan el color y que quepan 9 chips."""

from harness import (
    Report, database_copy, empty_database, make_context, offscreen,
    qt_app, settle,
)


import sys
from datetime import date
from pathlib import Path


from PySide6.QtCore import QRect
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from app.config import AppConfig
from app.context import AppContext
from app.models import ONGOING, FatigueSample, FatigueTest, RotarySample, RotaryTest
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.models.table_models import FatigueTableModel, RotaryTableModel
from app.ui.widgets import sample_chips
from app.ui.widgets.legend import Legend
from app.ui.widgets.sample_chips import (
    CHIPS_ROLE, RIG, STATUS, UNKNOWN, chip_font, strip_width,
)

COPY = database_copy()
failures = []
AUTHOR = ("verificador", "PC-PRUEBA")


def check(label, condition, detail=""):
    print(("OK    " if condition else "FALLO ") + label +
          (f"   {detail}" if detail else ""))
    if not condition:
        failures.append(label)


app = QApplication(sys.argv)
theme.apply(app)
context = AppContext(AppConfig(database_path=str(COPY), auto_backup=False))
context.prepare()

# ======================================================================
print("=== 1. Los resultados de pieza ya no llevan color ===")
check("no queda funcion de color por estado",
      not hasattr(sample_chips, "status_color")
      and not hasattr(sample_chips, "STATUS_COLORS"))

from app.services import catalogs as catalogs_module
check("no queda el diccionario de tonos reservados",
      not hasattr(catalogs_module, "STATUS_RESERVED")
      and not hasattr(catalogs_module, "conflicting_status"))

# Una prueba con las tres cosas: banco, resultado y valor desconocido.
mixta = FatigueTest(
    test_batch="999910STF01", customer="AUDI", start_date=date(2026, 8, 10),
    qty_samples=9,
    samples=[
        FatigueSample(rig="I-02-1", cycles=1_000),
        FatigueSample(rig="Falla", cycles=2_000),
        FatigueSample(rig="S/Falla", cycles=3_000),
        FatigueSample(rig="Susp", cycles=4_000),
        FatigueSample(rig="XX-9", cycles=5_000),
        FatigueSample(rig="I-02-1", cycles=6_000),
        FatigueSample(rig="Falla", cycles=7_000),
        FatigueSample(rig="I-02-1", cycles=8_000),
        FatigueSample(rig="Falla", cycles=999_999),
    ],
)
mixta_id = context.fatigue.create(mixta, AUTHOR)

model = FatigueTableModel(context.catalogs, show_end_date=False, compact=True)
model.set_records(context.fatigue.list(ONGOING))
row = next(i for i, r in enumerate(model.records()) if r.id == mixta_id)
chips = model.data(model.index(row, model.chips_column), CHIPS_ROLE)

for chip, esperado in zip(chips, ["banco", "Falla", "S/Falla", "Susp"]):
    print(f"      {esperado:<8} kind={chip.kind:<8} color={chip.color!r}")

check("Falla no tiene color", chips[1].color is None, repr(chips[1].color))
check("S/Falla no tiene color", chips[2].color is None, repr(chips[2].color))
check("Susp no tiene color", chips[3].color is None, repr(chips[3].color))
check("el banco si conserva su color", chips[0].color is not None,
      repr(chips[0].color))
check("los resultados siguen siendo pastilla (se distinguen por forma)",
      [c.kind for c in chips[1:4]] == [STATUS, STATUS, STATUS],
      str([c.kind for c in chips[1:4]]))
check("el banco sigue siendo cuadrado", chips[0].kind == RIG)
check("un valor fuera de catalogo queda sin clasificar",
      chips[4].kind == UNKNOWN, chips[4].kind)

# Celdas de la vista completa
full = FatigueTableModel(context.catalogs, show_end_date=False, compact=False)
full.set_records(context.fatigue.list(ONGOING))
check("la celda de un resultado no se pinta",
      full.cell_color("Falla") is None and full.cell_color("S/Falla") is None
      and full.cell_color("Susp") is None,
      f"{full.cell_color('Falla')}, {full.cell_color('S/Falla')}")
check("la celda de un banco si se pinta",
      full.cell_color("I-02-1") is not None)

# Rotary
rot = RotaryTest(test_batch="999911SRF01", customer="AUDI",
                 start_date=date(2026, 8, 11), qty_samples=2, test_rig="I-25",
                 samples=[RotarySample(revs=10, status="Falla"),
                          RotarySample(revs=20, status="S/Falla")]
                         + [RotarySample() for _ in range(7)])
rot_id = context.rotary.create(rot, AUTHOR)
rmodel = RotaryTableModel(context.catalogs, compact=True)
rmodel.set_records(context.rotary.list())
rrow = next(i for i, r in enumerate(rmodel.records()) if r.id == rot_id)
rchips = rmodel.data(rmodel.index(rrow, rmodel.chips_column), CHIPS_ROLE)
check("Rotary: sus estatus tampoco llevan color",
      all(c.color is None for c in rchips), str([c.color for c in rchips]))
check("Rotary: siguen dibujandose como pastilla",
      all(c.kind == STATUS for c in rchips), str([c.kind for c in rchips]))

legend = Legend()
check("la leyenda se construye sin color de resultado", legend is not None)

# ======================================================================
print("\n=== 2. La columna 'Muestras' cabe 9 chips ===")
window = MainWindow(context)
window.show_page("fatigue")
window.resize(1900, 1000)
window.show()
for _ in range(8):
    app.processEvents()

tab = window.pages["fatigue"].ongoing
table = tab.table
source = table.source_model()
proxy = table.model()
column = source.chips_column

metrics = QFontMetrics(chip_font(table.font()))
reservado = strip_width(metrics)
ancho = table.columnWidth(column)
print(f"      ancho reservado {reservado} px, ancho real {ancho} px")
check("la columna mide lo que piden 9 chips", ancho == reservado,
      f"{ancho} vs {reservado}")

caben = (ancho - sample_chips.MARGIN * 2 + sample_chips.CHIP_GAP) // (
    sample_chips.chip_width(metrics) + sample_chips.CHIP_GAP)
check("caben 9 chips", caben >= 9, f"caben {caben}")

option = QStyleOptionViewItem()
option.font = table.font()
delegado = table.itemDelegateForColumn(column)
anchos = {delegado.sizeHint(option, proxy.index(r, column)).width()
          for r in range(proxy.rowCount())}
check("el ancho no depende de los datos de la fila", len(anchos) == 1,
      str(anchos))

# Ninguna fila se corta
cortadas = []
for r in range(proxy.rowCount()):
    n = len(proxy.index(r, column).data(CHIPS_ROLE) or [])
    if n > caben:
        cortadas.append((r, n))
maximo = max((len(proxy.index(r, column).data(CHIPS_ROLE) or [])
              for r in range(proxy.rowCount())), default=0)
print(f"      maximo de chips en una fila: {maximo}")
check("hay al menos una fila de 9 piezas para probarlo", maximo == 9, str(maximo))
check("ninguna fila se corta", not cortadas, str(cortadas))

# --- se dibujan de verdad los nueve ---
# No se cuentan "bandas": un chip sin relleno deja dos bordes y su texto, asi
# que el conteo de franjas no equivale al de chips. Se comprueba pieza por
# pieza que en el rectangulo donde debe caer cada una hay algo dibujado.
from PySide6.QtGui import QPainter

fila9 = next(r for r in range(proxy.rowCount())
             if len(proxy.index(r, column).data(CHIPS_ROLE) or []) == 9)
alto = table.rowHeight(fila9) or 30
option.rect = QRect(0, 0, ancho, alto)
option.font = table.font()

lienzo = QPixmap(option.rect.size())
lienzo.fill()
painter = QPainter(lienzo)
painter.setFont(table.font())
delegado.paint(painter, option, proxy.index(fila9, column))
painter.end()

imagen = lienzo.toImage()
fondo = imagen.pixelColor(1, 1).name()
paso = sample_chips.chip_width(metrics) + sample_chips.CHIP_GAP

dibujadas = []
for pieza in range(9):
    inicio = sample_chips.MARGIN + pieza * paso
    fin = inicio + sample_chips.chip_width(metrics)
    pintado = any(
        imagen.pixelColor(x, y).name() != fondo
        for x in range(inicio, min(fin, imagen.width()))
        for y in range(imagen.height())
    )
    if pintado:
        dibujadas.append(pieza + 1)

print(f"      piezas con algo dibujado en su sitio: {dibujadas}")
check("se dibujan las nueve muestras, no cinco",
      dibujadas == list(range(1, 10)), str(dibujadas))
check("la novena cae dentro de la columna, sin recorte",
      sample_chips.MARGIN + 8 * paso + sample_chips.chip_width(metrics)
      <= ancho - sample_chips.MARGIN,
      f"la novena termina en "
      f"{sample_chips.MARGIN + 8 * paso + sample_chips.chip_width(metrics)} px "
      f"de {ancho}")

window.close()
app.quit()
print("\n" + "=" * 62)
if failures:
    print(f"FALLARON {len(failures)}:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("TODAS LAS COMPROBACIONES PASARON")
