"""Verifica que los resultados de pieza pierdan el color y que quepan 9 chips."""

from harness import (
    Report, database_copy, empty_database, make_context, offscreen,
    qt_app, settle,
)


import sys
from datetime import date
from pathlib import Path


import math

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QStyleOptionViewItem

from app.config import AppConfig
from app.context import AppContext
from app.models import ONGOING, FatigueSample, FatigueTest, RotarySample, RotaryTest
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.models.table_models import (
    RIG_COLOR_ROLE, FatigueTableModel, RotaryTableModel,
)
from app.ui.widgets import sample_chips
from app.ui.widgets.legend import Legend
from app.ui.widgets.sample_chips import (
    CHIPS_ROLE, DONE, RIG, STATUS, SUSPENDED, SUSPENDED_COLOR, UNKNOWN,
    SampleChipsDelegate, chip_font, strip_width,
)


def _lin(channel):
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _contrast(one, other):
    a, b = (sum(w * _lin(v) for v, w in zip(_rgb(c), (0.2126, 0.7152, 0.0722)))
            for c in (one, other))
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _lab(color):
    r, g, b = (_lin(v) for v in _rgb(color))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    pivot = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = pivot(x), pivot(y), pivot(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _dE(one, other):
    return math.dist(_lab(one), _lab(other))

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
    # Desde la migracion 008 el banco y el resultado son campos distintos.
    # Antes convivian en test_rigN y por eso una pieza no podia decir a la vez
    # donde corrio y como acabo.
    samples=[
        FatigueSample(rig="I-02-1", cycles=1_000),
        FatigueSample(result="Falla", cycles=2_000),
        FatigueSample(result="S/Falla", cycles=3_000),
        FatigueSample(result="Susp", cycles=4_000),
        FatigueSample(rig="XX-9", cycles=5_000),
        FatigueSample(rig="I-02-1", result="Falla", cycles=6_000),
        FatigueSample(result="Falla", cycles=7_000),
        FatigueSample(rig="I-02-1", cycles=8_000),
        FatigueSample(result="Falla", cycles=999_999),
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
check("el banco si conserva su color", chips[0].color is not None,
      repr(chips[0].color))
check("los resultados siguen siendo pastilla (se distinguen por forma)",
      [c.kind for c in chips[1:3]] == [STATUS, STATUS],
      str([c.kind for c in chips[1:3]]))
# 'Susp' es la excepcion entre los resultados: no cierra nada. Una pieza
# marcada asi, sin banco y con ciclos, esta suspendida --y asi se captura en
# la practica: se vacia el Test Rig y se anota 'Susp'--.
check("Susp con ciclos y sin banco cuenta como suspendida",
      chips[3].kind == SUSPENDED and chips[3].color == SUSPENDED_COLOR,
      f"{chips[3].kind} {chips[3].color!r}")
check("y el tooltip no repite el resultado",
      "suspendida, fuera de banco" in chips[3].tooltip
      and "Susp  ·" not in chips[3].tooltip, chips[3].tooltip)
check("el banco sigue siendo cuadrado", chips[0].kind == RIG)
check("un valor fuera de catalogo queda sin clasificar",
      chips[4].kind == UNKNOWN, chips[4].kind)
# Una pieza con banco y resultado se pinta con el color del banco: la forma
# solo importa cuando no hay banco del que tirar.
check("banco + resultado manda el color del banco",
      chips[5].kind == RIG and chips[5].color == chips[0].color,
      f"{chips[5].kind} {chips[5].color!r}")
check("el tooltip de esa pieza dice ambas cosas",
      "banco I-02-1" in chips[5].tooltip and "Falla" in chips[5].tooltip,
      chips[5].tooltip)

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
print("\n=== 1b. La pieza suspendida se pone naranja ===")
# Una pieza que estaba corriendo puede salir del banco y volver despues. El
# rastro que deja es un hueco: ciclos acumulados, sin banco y sin resultado.
# Sin marca, ese hueco se ve igual que una ranura que nadie uso.
suspendida = FatigueTest(
    test_batch="999912STF01", customer="AUDI", start_date=date(2026, 8, 12),
    qty_samples=4,
    samples=[
        FatigueSample(rig="I-02-1", cycles=1_000),   # corriendo
        FatigueSample(rig="", cycles=2_000),         # retirada del banco
        FatigueSample(result="Falla", cycles=3_000),  # termino, sin banco
        FatigueSample(rig="", cycles=None),          # ranura sin usar
    ] + [FatigueSample() for _ in range(5)],
)
susp_id = context.fatigue.create(suspendida, AUTHOR)

model.set_records(context.fatigue.list(ONGOING))
srow = next(i for i, r in enumerate(model.records()) if r.id == susp_id)
record = model.record_at(srow)
schips = model.data(model.index(srow, model.chips_column), CHIPS_ROLE)

# La base no distingue: el campo vaciado vuelve como "--", igual que una
# ranura que nadie toco. Lo que separa una cosa de la otra son los ciclos.
check("se reconoce la suspension aunque la base guarde '--'",
      record.samples[1].is_suspended and record.samples[3].rig
      == record.samples[1].rig,
      f"rig guardado: {record.samples[1].rig!r}")
check("la ranura sin usar no genera chip", len(schips) == 3, str(len(schips)))
for chip in schips:
    print(f"      kind={chip.kind:<10} color={chip.color!r}  {chip.tooltip}")

check("la suspendida sale naranja",
      schips[1].color == SUSPENDED_COLOR, repr(schips[1].color))
check("y con su propia clase de chip", schips[1].kind == SUSPENDED,
      schips[1].kind)
check("el tooltip dice por que",
      "suspendida, fuera de banco" in schips[1].tooltip, schips[1].tooltip)
check("la que sigue en banco conserva el color del banco",
      schips[0].kind == RIG and schips[0].color != SUSPENDED_COLOR,
      f"{schips[0].kind} {schips[0].color!r}")
check("una pieza que ya fallo no se marca como suspendida",
      schips[2].kind == STATUS and schips[2].color is None,
      f"{schips[2].kind} {schips[2].color!r}")

# El naranja dice 'fuera de banco'; en una prueba cerrada eso no significa
# nada, ahi lo que falta es dato historico y no una pieza esperando volver.
cerrada = FatigueTest(**{**vars(record), "test_status": "Finished"})
cerrado_model = FatigueTableModel(context.catalogs, show_end_date=True,
                                  compact=True)
cerrado_model.set_records([cerrada])
cchips = cerrado_model.data(
    cerrado_model.index(0, cerrado_model.chips_column), CHIPS_ROLE)
check("una prueba finalizada no marca suspensiones",
      all(c.color != SUSPENDED_COLOR for c in cchips),
      str([c.kind for c in cchips]))

# --- vista de columnas completas -------------------------------------
# Ahi no hay chip: la celda de Test Rig sale vacia, y vacia se ve igual que
# una ranura que nadie uso. Se pinta la celda.
full.set_records(context.fatigue.list(ONGOING))
frow = next(i for i, r in enumerate(full.records()) if r.id == susp_id)
rig_columns = sorted(full.rig_columns)
fondo = [full.data(full.index(frow, rig_columns[s]),
                   Qt.ItemDataRole.BackgroundRole) for s in range(4)]
print(f"      fondos de las cuatro primeras celdas de rig: "
      f"{[c.name() if c else None for c in fondo]}")
check("la celda de la suspendida se pinta naranja",
      fondo[1] is not None and fondo[1].name().upper()
      == SUSPENDED_COLOR.upper(),
      str(fondo[1]))
check("la celda de la ranura sin usar se queda sin pintar",
      fondo[3] is None, str(fondo[3]))
check("la celda de un banco sigue con su color",
      fondo[0] is not None and fondo[0].name().upper()
      != SUSPENDED_COLOR.upper(), str(fondo[0]))
check("la celda naranja explica lo que es",
      "Suspendida" in (full.data(full.index(frow, rig_columns[1]),
                                 Qt.ItemDataRole.ToolTipRole) or ""),
      str(full.data(full.index(frow, rig_columns[1]),
                    Qt.ItemDataRole.ToolTipRole)))

# --- Rotary ----------------------------------------------------------
# Aqui el banco es de la prueba entera: al vaciarlo se suspende todo lo que
# siguiera corriendo, y solo eso.
rot_susp = RotaryTest(
    test_batch="999913SRF01", customer="AUDI", start_date=date(2026, 8, 13),
    qty_samples=3, test_rig="",
    samples=[RotarySample(revs=100),                        # corria
             RotarySample(revs=200, status="Falla"),        # ya termino
             RotarySample(revs=300)]                        # corria
            + [RotarySample() for _ in range(6)],
)
rsusp_id = context.rotary.create(rot_susp, AUTHOR)
rmodel.set_records(context.rotary.list())
srrow = next(i for i, r in enumerate(rmodel.records()) if r.id == rsusp_id)
rschips = rmodel.data(rmodel.index(srrow, rmodel.chips_column), CHIPS_ROLE)
print(f"      Rotary: {[(c.kind, c.color) for c in rschips]}")
check("Rotary: las piezas que corrian salen naranjas",
      [c.color for c in rschips] == [SUSPENDED_COLOR, None, SUSPENDED_COLOR],
      str([c.color for c in rschips]))
check("Rotary: la que ya tiene estatus no se toca",
      rschips[1].kind == STATUS, rschips[1].kind)
# La celda del Rotary Rig ya no se pinta entera: la dibuja RigChipDelegate
# como un chip, y el color viaja por su propio rol. Con 400 filas del mismo
# banco, el relleno completo era un bloque de color que no distinguia nada.
check("Rotary: el color del Rotary Rig va por el rol del chip",
      (rmodel.data(rmodel.index(srrow, min(rmodel.rig_columns)),
                   RIG_COLOR_ROLE) or "").upper() == SUSPENDED_COLOR.upper(),
      str(rmodel.data(rmodel.index(srrow, min(rmodel.rig_columns)),
                      RIG_COLOR_ROLE)))
check("Rotary: y la celda ya no se pinta entera",
      rmodel.data(rmodel.index(srrow, min(rmodel.rig_columns)),
                  Qt.ItemDataRole.BackgroundRole) is None)

vacia = RotaryTest(test_batch="999914SRF01", customer="AUDI",
                   start_date=date(2026, 8, 14), qty_samples=2, test_rig="")
check("Rotary: una prueba a medio capturar no es una suspension",
      not vacia.is_suspended)

# --- el color elegido no puede confundirse con un banco ---------------
from app.db.migrations import _M010_MIN_DISTANCE, _M010_RESERVED
check("el naranja esta reservado en la migracion 010",
      SUSPENDED_COLOR.upper() in {c.upper() for c in _M010_RESERVED},
      SUSPENDED_COLOR)
cercanos = [(r.name, r.color, round(_dE(SUSPENDED_COLOR, r.color), 1))
            for r in context.catalogs.rigs()
            if _dE(SUSPENDED_COLOR, r.color) < _M010_MIN_DISTANCE]
check("ningun banco del catalogo se le parece", not cercanos, str(cercanos))
flojos = {n: round(_contrast(SUSPENDED_COLOR, f), 2)
          for n, f in (("fila", theme.ROW), ("alterna", theme.ROW_ALT),
                       ("seleccion", theme.SELECTION))}
print(f"      contraste del naranja sobre las filas: {flojos}")
check("se ve sobre las tres clases de fila",
      all(v >= 3 for v in flojos.values()), str(flojos))

# --- y se dibuja de verdad -------------------------------------------
option_s = QStyleOptionViewItem()
option_s.font = QApplication.font()
option_s.rect = QRect(0, 0, 200, 28)
lienzo_s = QPixmap(option_s.rect.size())
lienzo_s.fill()
pintor = QPainter(lienzo_s)
SampleChipsDelegate().paint(pintor, option_s,
                            model.index(srow, model.chips_column))
pintor.end()
imagen_s = lienzo_s.toImage()
paso_s = sample_chips.chip_width(QFontMetrics(chip_font(option_s.font)))
centro = sample_chips.MARGIN + paso_s + sample_chips.CHIP_GAP + paso_s // 2
naranjas = {imagen_s.pixelColor(centro, y).name().upper()
            for y in range(imagen_s.height())}
check("el segundo chip esta pintado de naranja",
      SUSPENDED_COLOR.upper() in naranjas, str(sorted(naranjas)))

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

print()
print("=== 8. La pieza declarada por completo pierde el color del banco ===")

# El color del banco significa "esta corriendo aqui ahora". Una pieza que ya
# tiene banco, ciclos, resultado y --si fallo-- modo de falla, termino: no
# ocupa el banco, y por eso el chip se queda sin color.
banco_prueba = context.catalogs.rig_names("fatigue")[0]
modo = (context.catalogs.failure_modes() or ["Aflojamiento"])[0]

casos = FatigueTest(
    test_batch="992001STF01", customer="AUDI", start_date=date.today(),
    qty_samples=5, test_status=ONGOING,
    samples=[
        FatigueSample(rig=banco_prueba, cycles=1000),
        FatigueSample(rig=banco_prueba, cycles=2000, result="Falla",
                      failure_mode=modo),
        FatigueSample(rig=banco_prueba, cycles=3000, result="Falla"),
        FatigueSample(rig=banco_prueba, cycles=4000, result="S/Falla"),
        FatigueSample(cycles=5000, result="Falla", failure_mode=modo),
    ] + [FatigueSample() for _ in range(4)],
)
modelo_casos = FatigueTableModel(context.catalogs, show_end_date=False)
modelo_casos.set_records([casos])
chips_casos = modelo_casos.chips(casos)

check("la pieza que sigue corriendo conserva el color de su banco",
      chips_casos[0].kind == RIG and bool(chips_casos[0].color),
      f"{chips_casos[0].kind} / {chips_casos[0].color}")
check("la declarada por completo se queda sin color",
      chips_casos[1].kind == DONE and chips_casos[1].color is None,
      f"{chips_casos[1].kind} / {chips_casos[1].color}")
check("y su tooltip dice que termino",
      "terminada" in chips_casos[1].tooltip, chips_casos[1].tooltip)

# El modo de falla solo se le exige a la que fallo: es la misma regla que el
# cierre de una prueba. Sin esto una 'S/Falla' se quedaria con el color del
# banco para siempre, porque nunca va a tener modo.
check("a la que fallo y no tiene modo aun, no se le quita el color",
      chips_casos[2].kind == RIG, chips_casos[2].kind)
check("pero una 'S/Falla' no necesita modo para darse por terminada",
      chips_casos[3].kind == DONE, chips_casos[3].kind)
check("y sin banco sigue siendo una pastilla de resultado",
      chips_casos[4].kind == STATUS, chips_casos[4].kind)


def _centro(kind, color):
    """El pixel del centro del chip: con relleno es el color, sin el la fila."""
    imagen = QPixmap(44, 20)
    imagen.fill(QColor(theme.ROW))
    pintor = QPainter(imagen)
    sample_chips.paint_chip_shape(pintor, QRectF(0, 0, 44, 20), kind, color)
    pintor.end()
    return QColor(imagen.toImage().pixel(22, 10)).name().upper()


check("el chip terminado no lleva relleno",
      _centro(DONE, None) == theme.ROW.upper(),
      f"{_centro(DONE, None)} en el centro, la fila es {theme.ROW}")
check("y el del banco si", _centro(RIG, "#FAAA82") == "#FAAA82",
      _centro(RIG, "#FAAA82"))


def _borde(kind):
    """El pixel de arriba: el contorno."""
    imagen = QPixmap(44, 20)
    imagen.fill(QColor(theme.ROW))
    pintor = QPainter(imagen)
    sample_chips.paint_chip_shape(pintor, QRectF(0, 0, 44, 20), kind, None)
    pintor.end()
    return QColor(imagen.toImage().pixel(22, 0)).name().upper()


# Terminada y a-medias van las dos sin relleno pero significan lo contrario,
# asi que el contorno tiene que separarlas.
check("terminada y a-medias no llevan el mismo contorno",
      _borde(DONE) != _borde(UNKNOWN),
      f"terminada {_borde(DONE)}, a medias {_borde(UNKNOWN)}")

# Y la vista de columnas completas sigue la misma regla: las dos vistas
# ensenian lo mismo, asi que no pueden decir cosas distintas de la misma pieza.
completa = FatigueTableModel(context.catalogs, show_end_date=False,
                             compact=False)
completa.set_records([casos])
colores_celda = [
    completa.index(0, completa._first_sample + i * 4).data(RIG_COLOR_ROLE)
    for i in range(4)
]
check("en columnas completas, la celda de la que corre lleva color",
      bool(colores_celda[0]), str(colores_celda[0]))
check("la de la pieza terminada no",
      colores_celda[1] is None, str(colores_celda[1]))
check("la que aun no tiene modo si",
      bool(colores_celda[2]), str(colores_celda[2]))
check("y la 'S/Falla' terminada tampoco",
      colores_celda[3] is None, str(colores_celda[3]))
check("las dos vistas coinciden pieza por pieza",
      [c.color is None for c in chips_casos[:4]]
      == [c is None for c in colores_celda],
      f"chips {[c.color for c in chips_casos[:4]]} / celdas {colores_celda}")
check("la celda sin color explica por que",
      "Terminada" in (completa.tooltip(casos, completa._first_sample + 4) or ""),
      str(completa.tooltip(casos, completa._first_sample + 4)))

leyenda = Legend(show_days=True, show_wo=True, show_maintenance=True)
rotulos = [w.text() for w in leyenda.findChildren(QLabel)]
check("la leyenda nombra el chip terminado",
      any("terminada" in t for t in rotulos),
      str([t for t in rotulos if t][:8]))

window.close()
app.quit()
print("\n" + "=" * 62)
if failures:
    print(f"FALLARON {len(failures)}:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("TODAS LAS COMPROBACIONES PASARON")
