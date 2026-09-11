"""Comprueba que la columna de muestras muestre TODOS los chips de cada fila."""

from harness import (
    Report, database_copy, empty_database, make_context, offscreen,
    qt_app, settle,
)


import os
import sys
from collections import Counter

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from app.config import AppConfig
from app.context import AppContext
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.widgets.sample_chips import (
    CHIP_GAP, MARGIN, CHIPS_ROLE, chip_font, chip_width, compact_number,
)

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

print("=== Etiquetas: maximo 4 caracteres ===")
for value, expected in [(None, "--"), (0, "0"), (845, "845"),
                        (8_084, "8.1K"), (45_000, "45K"), (450_000, "450K"),
                        (8_100_000, "8.1M"), (647_487_325, "647M")]:
    got = compact_number(value)
    check(f"compact_number({value}) = {expected}", got == expected, f"dio {got}")

longest = max(
    (compact_number(v) for v in
     [0, 999, 1000, 9999, 99_999, 999_999, 9_999_999, 999_999_999,
      2_000_000_000]),
    key=len,
)
check("ninguna etiqueta pasa de 4 caracteres", len(longest) <= 4,
      f"la mas larga es '{longest}'")

window.show_page("fatigue")

for name in ("ongoing", "finished"):
    tab = getattr(window.pages["fatigue"], name)
    tab.refresh()
    model = tab.table.source_model()
    proxy = tab.table.model()
    column = model.chips_column

    option = QStyleOptionViewItem()
    option.initFrom(tab.table)
    width = chip_width(QFontMetrics(chip_font(option.font)))
    available = tab.table.columnWidth(column)

    # Cuantos chips caben realmente con la logica de paint().
    def drawn(count):
        x = MARGIN
        for position in range(count):
            if x + width > available - MARGIN:
                return position
            x += width + CHIP_GAP
        return count

    counts = Counter()
    truncated = 0
    worst = 0
    for row in range(proxy.rowCount()):
        chips = proxy.index(row, column).data(CHIPS_ROLE) or []
        counts[len(chips)] += 1
        worst = max(worst, len(chips))
        if drawn(len(chips)) < len(chips):
            truncated += 1

    print(f"\n--- fatiga: {name} ({proxy.rowCount()} filas) ---")
    print(f"  chips por fila: {dict(sorted(counts.items()))}")
    print(f"  ancho de chip: {width} px   ancho de columna: {available} px")
    check(f"{name}: ninguna fila se recorta", truncated == 0,
          f"{truncated} filas recortadas (max {worst} chips)")

# Rotary
window.show_page("rotary")
page = window.pages["rotary"]
model = page.table.source_model()
proxy = page.table.model()
column = model.chips_column
option = QStyleOptionViewItem()
option.initFrom(page.table)
width = chip_width(QFontMetrics(chip_font(option.font)))
available = page.table.columnWidth(column)
worst = max(
    (len(proxy.index(r, column).data(CHIPS_ROLE) or [])
     for r in range(proxy.rowCount())), default=0)
needed = MARGIN * 2 + worst * width + max(worst - 1, 0) * CHIP_GAP
print(f"\n--- rotary ({proxy.rowCount()} filas) ---")
print(f"  maximo {worst} chips, necesita {needed} px, tiene {available} px")
check("rotary: la columna alcanza", available >= needed)

# El resto de columnas sigue con su tope.
window.show_page("fatigue")
tab = window.pages["fatigue"].finished
tab.refresh()
model = tab.table.source_model()
others = [
    tab.table.columnWidth(c)
    for c in range(len(model.headers)) if c != model.chips_column
]
check("las demas columnas siguen topadas a 240", max(others) <= 240,
      f"la mas ancha mide {max(others)}")

app.quit()
print("\n" + "=" * 62)
if failures:
    print(f"FALLARON {len(failures)}:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("TODAS LAS COMPROBACIONES PASARON")
