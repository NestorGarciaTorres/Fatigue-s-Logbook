"""Las reglas de color de la tabla, medidas.

El problema que dio origen a esto: la fila seleccionada y el encabezado eran
el mismo #5DADE2 -- el mismo valor, no dos parecidos -- y al ser un azul claro
mataba todo lo que llevaba encima. El semaforo de Dias caia a 1.05:1 y los
once colores de rig del catalogo bajaban de 3:1.

Un color "se ve bien" no es comprobable; el contraste y la distancia en Lab
si. Aqui se fijan los umbrales para que nadie los rompa sin enterarse.
"""

import math

from harness import Report, make_context, qt_app, settle

from app.db.migrations import (
    _M010_MIN_DISTANCE,
    _M010_MIN_SEPARATION,
    _M010_RESERVED,
    _M010_ROW_BACKGROUNDS,
)
from app.services.catalogs import DEFAULT_PALETTE
from app.ui import theme
from app.ui.models.table_models import DAYS_COLORS
from app.ui.widgets.record_table import SELECTION_BAR

report = Report("Colores de la tabla")


def rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def luminance(color):
    total = 0.0
    for channel, weight in zip(rgb(color), (0.2126, 0.7152, 0.0722)):
        c = channel / 255
        total += weight * (
            c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        )
    return total


def contrast(one, other):
    a, b = luminance(one), luminance(other)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def lab(color):
    values = []
    for channel in rgb(color):
        c = channel / 255
        values.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = values
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    pivot = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = pivot(x), pivot(y), pivot(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def dE(one, other):
    return math.dist(lab(one), lab(other))


FONDOS = {"fila": theme.ROW, "franja alterna": theme.ROW_ALT,
          "seleccion": theme.SELECTION}

# ======================================================================
report.section("1. Cada estado de fila tiene su color")

estados = {"fila": theme.ROW, "alterna": theme.ROW_ALT,
           "seleccion": theme.SELECTION, "encabezado": theme.HEADER_BG}
for nombre, color in estados.items():
    print(f"      {nombre:<12} {color}")

report.check("la seleccion ya no es el color del encabezado",
             theme.SELECTION != theme.HEADER_BG)
report.check("y ninguno de los dos es PRIMARY",
             theme.SELECTION != theme.PRIMARY and theme.HEADER_BG != theme.PRIMARY)

pares = [(a, b) for i, (a, _) in enumerate(estados.items())
         for b, _ in list(estados.items())[i + 1:]]
peor = min((dE(estados[a], estados[b]), a, b) for a, b in pares)
report.check("los cuatro estados se distinguen entre si (dE >= 7)",
             peor[0] >= 7, f"el par mas cercano: {peor[1]}/{peor[2]} dE {peor[0]:.1f}")

report.check("la franja alterna se nota mas que antes",
             dE(theme.ROW, theme.ROW_ALT) >= 9,
             f"dE {dE(theme.ROW, theme.ROW_ALT):.1f}  (antes 5.7)")
report.check("la seleccion se separa claramente de una fila normal",
             dE(theme.SELECTION, theme.ROW) >= 15,
             f"dE {dE(theme.SELECTION, theme.ROW):.1f}")
report.check("el rotulo del encabezado se lee (AA)",
             contrast(theme.PRIMARY, theme.HEADER_BG) >= 4.5,
             f"{contrast(theme.PRIMARY, theme.HEADER_BG):.2f} : 1")

# ======================================================================
report.section("2. La seleccion deja legible lo que lleva encima")

for nombre, color in (("texto", theme.TEXT), *DAYS_COLORS.items()):
    valor = contrast(color, theme.SELECTION)
    print(f"      {str(nombre):<10} sobre la seleccion: {valor:5.2f} : 1")

report.check("el texto sobre la seleccion cumple AA",
             contrast(theme.TEXT, theme.SELECTION) >= 4.5,
             f"{contrast(theme.TEXT, theme.SELECTION):.2f} : 1")
report.check("el semaforo sobrevive a la seleccion",
             all(contrast(c, theme.SELECTION) >= 3
                 for c in DAYS_COLORS.values()),
             str({k: round(contrast(v, theme.SELECTION), 2)
                  for k, v in DAYS_COLORS.items()}))
report.check("la barra de acento marca la fila sin repintarla",
             SELECTION_BAR >= 2, f"{SELECTION_BAR} px")

# ======================================================================
report.section("3. La paleta de rigs")

report.check("hay al menos un color por rig del catalogo",
             len(DEFAULT_PALETTE) >= 16, f"{len(DEFAULT_PALETTE)} colores")
report.check("sin repetidos", len(set(DEFAULT_PALETTE)) == len(DEFAULT_PALETTE))

flojos = [
    (c, nombre, round(contrast(c, fondo), 2))
    for c in DEFAULT_PALETTE
    for nombre, fondo in FONDOS.items()
    if contrast(c, fondo) < 3
]
report.check("todos se leen sobre los TRES fondos de fila", not flojos, str(flojos[:4]))
print(f"      contraste minimo: "
      f"{min(contrast(c, f) for c in DEFAULT_PALETTE for f in FONDOS.values()):.2f}")

choques = [
    (c, r) for c in DEFAULT_PALETTE for r in _M010_RESERVED
    if dE(c, r) < _M010_MIN_DISTANCE
]
report.check("ninguno choca con un color de la interfaz", not choques, str(choques[:3]))
report.check("PRIMARY ya no es un color de rig",
             theme.PRIMARY.upper() not in {c.upper() for c in DEFAULT_PALETTE})

vecinos = min(
    (dE(a, b), a, b)
    for i, a in enumerate(DEFAULT_PALETTE) for b in DEFAULT_PALETTE[i + 1:]
)
report.check("dos rigs no se confunden entre si",
             vecinos[0] >= _M010_MIN_SEPARATION,
             f"el par mas cercano: {vecinos[1]} y {vecinos[2]}, dE {vecinos[0]:.1f}")

# ======================================================================
report.section("4. Sobre el catalogo real, ya migrado")

app = qt_app()
context = make_context()
rigs = context.catalogs.rigs()
colores = [r.color for r in rigs]

report.check("hay rigs que comprobar", bool(rigs), f"{len(rigs)} rigs")
report.check("cada rig tiene un color distinto",
             len(set(colores)) == len(colores),
             f"{len(set(colores))} colores para {len(colores)} rigs")

malos = [
    (r.name, r.color, nombre, round(contrast(r.color, fondo), 2))
    for r in rigs for nombre, fondo in FONDOS.items()
    if contrast(r.color, fondo) < 3
]
report.check("ningun chip se pierde en ninguna fila", not malos, str(malos[:3]))

cerca = [
    (a.name, b.name, round(dE(a.color, b.color), 1))
    for i, a in enumerate(rigs) for b in rigs[i + 1:]
    if dE(a.color, b.color) < _M010_MIN_SEPARATION
]
report.check("ningun par de rigs comparte tono", not cerca, str(cerca[:3]))

reservados = [
    (r.name, r.color, res) for r in rigs for res in _M010_RESERVED
    if dE(r.color, res) < _M010_MIN_DISTANCE
]
report.check("ningun rig usa un color de la interfaz", not reservados,
             str(reservados[:3]))
print(f"      contraste minimo real: "
      f"{min(contrast(r.color, f) for r in rigs for f in FONDOS.values()):.2f}")

# ======================================================================
report.section("5. La barra de seleccion se pinta de verdad")

from app.ui.main_window import MainWindow

window = MainWindow(context)
window.show_page("fatigue")
window.resize(1500, 560)
window.show()
tab = window.pages["fatigue"].ongoing
settle(app, 30)
tab.table.selectRow(1)
settle(app, 20)
tab.table.grab()          # el primer render de un proceso Qt sale en blanco
settle(app, 10)

imagen = tab.table.viewport().grab().toImage()
fila = tab.table.visualRect(tab.table.model().index(1, 0))
otra = tab.table.visualRect(tab.table.model().index(0, 0))

barra = [imagen.pixelColor(x, fila.center().y()).name().upper()
         for x in range(SELECTION_BAR)]
sin_barra = [imagen.pixelColor(x, otra.center().y()).name().upper()
             for x in range(SELECTION_BAR)]
print(f"      fila seleccionada: {barra}")
print(f"      fila normal:       {sin_barra}")

report.check("la fila seleccionada lleva su barra en PRIMARY",
             set(barra) == {theme.PRIMARY.upper()}, str(barra))
report.check("una fila normal no la lleva",
             theme.PRIMARY.upper() not in sin_barra, str(sin_barra))
report.check("el relleno de la seleccion es el color nuevo",
             imagen.pixelColor(SELECTION_BAR + 2,
                               fila.center().y()).name().upper()
             == theme.SELECTION.upper(),
             imagen.pixelColor(SELECTION_BAR + 2, fila.center().y()).name())

raise SystemExit(report.finish())
