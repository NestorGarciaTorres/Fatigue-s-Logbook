"""Verifica los niveles 2 y 3."""

from harness import (
    Report, database_copy, empty_database, make_context, offscreen,
    qt_app, settle,
)


import os
import sys
from datetime import date, timedelta

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.context import AppContext
from app.models import ONGOING
from app.services import duration
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.models.table_models import DAYS_HEADER
from app.ui.pages.rigs_page import RigCard

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

# ======================================================================
print("=== 5. Columna Dias con semaforo ===")
window.show_page("fatigue")
tab = window.pages["fatigue"].ongoing
model = tab.table.source_model()
proxy = tab.table.model()

check("existe la columna Dias", DAYS_HEADER in model.headers,
      f"columna {model.days_column}")

thresholds = model.thresholds
print(f"     umbrales: atencion >{thresholds.warning}, "
      f"revisar >={thresholds.critical}, calibrado={thresholds.calibrated}")
check("los umbrales salen del historial", thresholds.calibrated)
check("p75 y p95 razonables",
      5 <= thresholds.warning <= 20 and 20 <= thresholds.critical <= 60,
      f"{thresholds.warning}/{thresholds.critical}")

column = model.days_column
rows = []
for row in range(proxy.rowCount()):
    index = proxy.index(row, column)
    rows.append((
        proxy.index(row, 1).data(),
        index.data(),
        index.data(Qt.ItemDataRole.ForegroundRole),
    ))

print("     batch          dias   color")
levels = {theme.SUCCESS: "verde", theme.WARNING: "ambar", theme.DANGER: "rojo"}
for batch, days, color in rows:
    name = levels.get(QColor(color).name().upper(), str(color))
    print(f"     {batch:<14} {days:>5}   {name}")

criticals = [r for r in rows if QColor(r[2]).name().upper() == theme.DANGER]
check("las pruebas viejas salen en rojo", len(criticals) >= 2,
      f"{len(criticals)} en rojo")
check("las recientes salen en verde",
      any(QColor(r[2]).name().upper() == theme.SUCCESS for r in rows))

# Alineacion y orden numerico
check("Dias alineada a la derecha",
      proxy.index(0, column).data(Qt.ItemDataRole.TextAlignmentRole)
      == int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))

# Pestana de finalizadas: duracion, sin semaforo
finished = window.pages["fatigue"].finished
finished.refresh()
fmodel = finished.table.source_model()
fproxy = finished.table.model()
fcolumn = fmodel.days_column
colors = {
    QColor(fproxy.index(r, fcolumn).data(Qt.ItemDataRole.ForegroundRole)).name().upper()
    for r in range(min(50, fproxy.rowCount()))
}
check("finalizadas: duracion sin semaforo", colors == {theme.SUCCESS},
      f"colores vistos: {colors}")

record = fmodel.record_at(0)
expected = duration.elapsed(record.start_date, record.end_date)
check("finalizadas: la duracion es fin - inicio",
      fproxy.index(0, fcolumn).data() == str(expected),
      f"tabla {fproxy.index(0, fcolumn).data()}, calculado {expected}")

# ======================================================================
print("\n=== 6. Ocupacion de rigs ===")
window.show_page("rigs")
page = window.pages["rigs"]
cards = [
    page.grid.itemAt(i).widget() for i in range(page.grid.count())
    if isinstance(page.grid.itemAt(i).widget(), RigCard)
]
check("hay una tarjeta por rig del catalogo",
      len(cards) == len(context.catalogs.rigs()),
      f"{len(cards)} tarjetas / {len(context.catalogs.rigs())} rigs")

busy = [c for c in cards if c.occupants]
free = [c for c in cards if not c.occupants]
print(f"     ocupados: {sorted(c.rig.name for c in busy)}")
print(f"     libres:   {sorted(c.rig.name for c in free)}")
check("hay rigs ocupados y libres", busy and free,
      f"{len(busy)} ocupados, {len(free)} libres")
names = [c.rig.name for c in busy]
check("un rig no se ocupa por su homonimo de otro tipo",
      len(names) == len(set(names)), f"repetidos: {names}")
check("las tarjetas coinciden con las tarjetas resumen",
      page.card_busy.value_label.text() == str(len(busy))
      and page.card_free.value_label.text() == str(len(free)))
check("avisa de los valores fuera de catalogo", page.notice.isVisibleTo(page),
      page.notice.text()[:70])

# Un rig ocupado no debe listar la misma prueba dos veces
for card in busy:
    batches = [r.test_batch for r, _, _ in card.occupants]
    if len(batches) != len(set(batches)):
        check(f"{card.rig.name}: sin pruebas repetidas", False, str(batches))
        break
else:
    check("ningun rig repite la misma prueba", True)

# ======================================================================
print("\n=== 7. Leyenda ===")
legend = tab.legend
captions = [label.text() for label in legend.days_labels]
check("la leyenda describe los umbrales", all(captions), str(captions))
check("coincide con los umbrales del modelo",
      captions[0] == f"hasta {thresholds.warning}"
      and captions[2] == f"{thresholds.critical} o mas", str(captions))

# ======================================================================
print("\n=== 9. Chips de filtros activos ===")
chips_widget = tab.active_filters
check("sin filtros no se muestran", not chips_widget.isVisibleTo(tab))

tab.filters.search.setText("STF")
tab.filters.customer.setCurrentText("TOYOTA")
app.processEvents()
chip_texts = [
    chips_widget._layout.itemAt(i).widget().text()
    for i in range(chips_widget._layout.count() - 1)
]
print(f"     chips: {chip_texts}")
check("aparece un chip por filtro", len(chip_texts) == 2, str(chip_texts))
check("los chips nombran el filtro",
      any("Texto" in t for t in chip_texts)
      and any("Cliente" in t for t in chip_texts))

before = tab.table.row_count()
chips_widget.removed.emit("search")
app.processEvents()
check("quitar un chip libera solo ese filtro",
      tab.filters.search.text() == ""
      and tab.filters.customer.currentText() == "TOYOTA")
check("la tabla se actualiza", tab.table.row_count() >= before)
tab.filters.clear()
app.processEvents()
check("limpiar todo esconde los chips", not chips_widget.isVisibleTo(tab))

# ======================================================================
print("\n=== 8. Las nueve piezas siempre a la vista ===")
from app.ui.dialogs.fatigue_dialog import FatigueDialog

# Historia de esta comprobación: primero medía el atenuado por hoja de estilos
# y pasaba en vacío (un campo sin texto no cambia de color, así que con una
# pieza declarada se seguían viendo los 27 campos). Luego midió el ocultado de
# las sobrantes. Ahora las nueve se muestran siempre y lo único condicional es
# la marca ámbar de las capturadas por encima de lo declarado.
record = context.fatigue.list(ONGOING)[0]
dialog = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                       test=record)
declared = int(dialog.qty.currentText())
used = sum(1 for s in record.samples
           if s.rig != "--" or s.cycles or s.failure_mode)
visible = [b.number for b in dialog.sample_boxes if b.isVisibleTo(dialog)]
print(f"     piezas declaradas: {declared}, con datos: {used}, "
      f"visibles: {visible}")
check("se ven las nueve piezas", visible == list(range(1, 10)), str(visible))
check("las ranuras vacias abren en blanco, no con 0",
      all(dialog.cycles[i].text() == "" for i in range(used, 9)),
      str([dialog.cycles[i].text() for i in range(9)]))
check("no se marca ninguna pieza dentro de lo declarado",
      all("de mas" not in b.title() for b in dialog.sample_boxes[:declared]))

dialog.qty.setCurrentText("9")
app.processEvents()
check("con nueve declaradas no queda ninguna marcada",
      all("de mas" not in b.title() for b in dialog.sample_boxes))

# ======================================================================
print("\n=== 10. Dashboard ===")
# Esta seccion comprobaba la grafica de 'Uso por Test Rig' (barras
# horizontales, una categoria por rig). El usuario pidio retirarla, asi que lo
# que queda por comprobar es que ya no este y que las otras sigan en pie.
window.show_page("dashboard")
dash = window.pages["dashboard"]
vistas = [dash.grid.itemAt(i).widget() for i in range(dash.grid.count())]
titulos = [v.chart().title() for v in vistas]
print(f"     graficas: {titulos}")
check("la grafica de uso por rig ya no existe",
      not hasattr(dash, "_usage_by_rig")
      and not any("Test Rig" in t for t in titulos), str(titulos))
check("quedan las otras tres", len(vistas) == 3, str(len(vistas)))
check("todas traen datos",
      all(v.chart().series() for v in vistas),
      str([len(v.chart().series()) for v in vistas]))

app.quit()
print("\n" + "=" * 62)
if failures:
    print(f"FALLARON {len(failures)}:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("TODAS LAS COMPROBACIONES PASARON")
