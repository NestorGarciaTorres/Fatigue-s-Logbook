"""Verifica las cuatro mejoras del nivel 1."""

from harness import (
    Report, database_copy, empty_database, make_context, offscreen,
    qt_app, settle,
)


import os
import sys
from datetime import date
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"


from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.context import AppContext
from app.models import ONGOING
from app.services.filtering import TestFilters
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.models.table_models import CENTER, LEFT, RIGHT, SORT_ROLE
from app.ui.widgets.sample_chips import CHIPS_ROLE, compact_number

failures = []


def check(label, condition, detail=""):
    print(("OK   " if condition else "FALLO ") + label +
          (f"   {detail}" if detail else ""))
    if not condition:
        failures.append(label)


app = QApplication(sys.argv)
theme.apply(app)

# Contra una COPIA, nunca contra la base real: prepare() aplica
# migraciones, y correr esta prueba dejaba migrada la base de
# produccion antes de que nadie hubiera sacado un respaldo.
context = AppContext(AppConfig(database_path=str(database_copy()), auto_backup=False))
context.prepare()
window = MainWindow(context)
window.show_page("fatigue")
tab = window.pages["fatigue"].ongoing
table = tab.table
model = table.source_model()

print("=== 1. Vista compacta ===")
check("columnas reducidas de 28 a 11",
      len(model.headers) == 11, f"{len(model.headers)}: {model.headers}")
check("existe la columna de chips",
      model.chips_column is not None and
      model.headers[model.chips_column] == "Muestras")

proxy = table.model()
row0 = proxy.index(0, model.chips_column)
chips = row0.data(CHIPS_ROLE)
check("la fila trae chips", bool(chips), f"{len(chips or [])} chips")
if chips:
    print(f"     etiquetas: {[c.label for c in chips]}")
    print(f"     colores:   {[c.color for c in chips]}")
    print(f"     tooltip 1: {chips[0].tooltip}")
    check("los chips tienen color de rig",
          any(c.color for c in chips))

check("el delegado esta puesto en la columna de chips",
      table.itemDelegateForColumn(model.chips_column) is not None)
check("orden por total de ciclos",
      row0.data(SORT_ROLE) == table.selected_record().total_cycles
      if table.selected_record() else True)

print("\n=== Numeros compactos ===")
for value, expected in [(None, "--"), (0, "0"), (8084, "8.1K"),
                        (450_000, "450K"), (8_100_000, "8.1M"),
                        (2_000_000, "2M"), (999_999, "1M")]:
    got = compact_number(value)
    check(f"compact_number({value}) = {expected}", got == expected, f"dio {got}")

print("\n=== Conmutador a vista completa ===")
tab.view_toggle.setChecked(True)
# 37 = 10 columnas fijas + 9 muestras x 3 (rig, ciclos y modo de falla).
check("vuelve a 37 columnas", len(model.headers) == 37,
      f"{len(model.headers)}")
check("el texto del boton cambia",
      tab.view_toggle.text() == "Ver vista compacta", tab.view_toggle.text())
check("sin columna de chips en vista completa", model.chips_column is None)
tab.view_toggle.setChecked(False)
check("regresa a compacta", len(model.headers) == 11)

print("\n=== 2. Alineacion por tipo de dato ===")
headers = model.headers
cases = {
    "Dias": RIGHT,
    "ID": RIGHT, "Test Batch": LEFT, "Cliente": LEFT, "Inicio": CENTER,
    "Piezas": RIGHT, "Comentarios": LEFT, "Total ciclos": RIGHT,
    "WO": CENTER, "Estatus": LEFT,
}
for name, expected in cases.items():
    column = headers.index(name)
    got = proxy.index(0, column).data(Qt.ItemDataRole.TextAlignmentRole)
    check(f"'{name}' alineada correctamente", got == int(expected),
          f"dio {got}, esperaba {int(expected)}")

print("\n=== 3. Anchos estables al filtrar ===")
widths_before = [table.columnWidth(c) for c in range(len(headers))]
tab.filters.search.setText("STF")
app.processEvents()
widths_after = [table.columnWidth(c) for c in range(len(headers))]
check("las columnas no cambian de ancho al escribir",
      widths_before == widths_after,
      f"antes {widths_before[:4]} / despues {widths_after[:4]}")

tab.filters.search.setText("2")
app.processEvents()
check("tampoco al seguir escribiendo",
      [table.columnWidth(c) for c in range(len(headers))] == widths_before)

print("\n=== 4. Estado vacio ===")
tab.filters.search.setText("ZZZZZZ-no-existe")
app.processEvents()
check("no quedan filas", table.row_count() == 0)
check("el mensaje de vacio es visible",
      tab.table._empty.isVisibleTo(tab.table.viewport()))
check("dice que es por los filtros",
      "filtros" in tab.table._empty.message.text().lower(),
      tab.table._empty.message.text())
check("ofrece limpiar filtros",
      tab.table._empty.button.isVisibleTo(tab.table._empty))

tab.table._empty.button.click()
app.processEvents()
# Contra el conteo real, no contra un 10 fijo: la base crece segun se usa la
# app y una prueba nueva hacia fallar esto sin que nada estuviera mal.
en_curso = len(context.fatigue.list(ONGOING))
check("el boton limpia los filtros y vuelven las filas",
      table.row_count() == en_curso,
      f"{table.row_count()} filas, {en_curso} en curso")
check("el mensaje se oculta",
      not tab.table._empty.isVisibleTo(tab.table.viewport()))

print("\n=== Rotary ===")
window.show_page("rotary")
rotary = window.pages["rotary"]
rmodel = rotary.table.source_model()
check("rotary compacta: 12 columnas", len(rmodel.headers) == 12,
      f"{len(rmodel.headers)}")
rchips = rotary.table.model().index(0, rmodel.chips_column).data(CHIPS_ROLE)
check("rotary trae chips", bool(rchips), f"{len(rchips or [])}")
if rchips:
    print(f"     etiquetas: {[c.label for c in rchips]}")
    print(f"     colores:   {[c.color for c in rchips]}")
    # Los resultados de pieza perdieron el color a peticion del usuario: ahora
    # se distinguen por la forma del chip, no por el tono.
    check("los chips de rotary no llevan color",
          all(c.color is None for c in rchips),
          str([c.color for c in rchips]))
    check("y se dibujan como pastilla",
          all(c.kind in ("status", "unknown") for c in rchips),
          str([c.kind for c in rchips]))

print("\n=== Torsion/Quasi intactas ===")
window.show_page("torsion")
tmodel = window.pages["torsion"].table.source_model()
check("torsion sigue con 7 columnas", len(tmodel.headers) == 7)

app.quit()
print("\n" + "=" * 62)
if failures:
    print(f"FALLARON {len(failures)}:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("TODAS LAS COMPROBACIONES PASARON")
