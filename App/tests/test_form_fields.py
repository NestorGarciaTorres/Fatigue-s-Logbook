"""Verifica los cuatro puntos pedidos."""

from harness import (
    Report, database_copy, empty_database, make_context, offscreen,
    qt_app, settle,
)


import os
import sys
from collections import Counter
from datetime import date

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.context import AppContext
from app.models import ONGOING
from app.ui import theme
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.main_window import MainWindow
from app.ui.widgets.sample_chips import CHIPS_ROLE, RADIUS, RIG, STATUS

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
applied = context.prepare()
if applied:
    print(f"Migraciones aplicadas: {applied}\n")

window = MainWindow(context)

# ======================================================================
print("=== 1. El color es solo de los bancos ===")
# Esta seccion comprobaba que ningun color de rig se confundiera con el de un
# resultado. Ya no aplica: los resultados perdieron el color, asi que no hay
# tonos reservados que respetar. Lo que se comprueba ahora es que los bancos
# conserven el suyo y que la forma sea lo que separa banco de resultado.
rigs = context.catalog_repository.rigs(active_only=False)
for rig in rigs:
    print(f"     {rig.name:<10} {rig.test_type:<9} {rig.color}")
check("todos los rigs tienen un color asignado",
      all(r.color and r.color.startswith("#") for r in rigs),
      str([r.color for r in rigs if not (r.color or "").startswith("#")]))

colors = [r.color.upper() for r in rigs]
duplicated = [c for c, n in Counter(colors).items() if n > 1]
print(f"     colores repetidos entre rigs: {duplicated or 'ninguno'}")

check("no quedan tonos reservados para los resultados",
      not hasattr(__import__("app.services.catalogs", fromlist=["x"]),
                  "STATUS_RESERVED"))

# La forma es ahora el unico canal que separa banco de resultado.
check("banco y resultado tienen radios distintos",
      RADIUS[RIG] != RADIUS[STATUS],
      f"rig={RADIUS[RIG]}, status={RADIUS[STATUS]}")

window.show_page("fatigue")
tab = window.pages["fatigue"].ongoing
model = tab.table.source_model()
proxy = tab.table.model()
kinds = Counter()
for row in range(proxy.rowCount()):
    for chip in proxy.index(row, model.chips_column).data(CHIPS_ROLE) or []:
        kinds[chip.kind] += 1
print(f"     chips por tipo: {dict(kinds)}")
check("los chips se clasifican en banco y resultado",
      kinds.get(STATUS, 0) > 0 and kinds.get(RIG, 0) > 0, str(dict(kinds)))

# ======================================================================
print("\n=== 2. Combos de pieza: banco y resultado, cada uno el suyo ===")
# Hasta la migracion 008 los rigs y los estatus compartian un solo combo,
# separados por una linea en blanco. Ahora son dos campos distintos, asi que
# ninguno de los dos debe traer valores del otro.
dialog = FatigueDialog(context.fatigue, context.catalogs, context.audit)
rig_combo = dialog.rigs[0]
result_combo = dialog.results[0]
rig_items = [rig_combo.itemText(i) for i in range(rig_combo.count())]
result_items = [result_combo.itemText(i) for i in range(result_combo.count())]
rig_names = context.catalogs.rig_names("fatigue")
statuses = context.catalogs.sample_statuses()
print(f"     bancos:     {rig_items}")
print(f"     resultados: {result_items}")
check("el combo de banco trae todos los rigs de fatiga",
      all(r in rig_items for r in rig_names), str(rig_names))
check("el combo de banco no trae estatus",
      not any(s in rig_items for s in statuses), str(rig_items))
check("el combo de resultado trae los 3 estatus",
      all(s in result_items for s in statuses), str(statuses))
check("el combo de resultado no trae bancos",
      not any(r in result_items for r in rig_names), str(result_items))
check("ninguno lleva ya el separador en blanco",
      "" not in rig_items and "" not in result_items)
check("ninguno es editable",
      not rig_combo.isEditable() and not result_combo.isEditable())

# ======================================================================
print("\n=== 3 y 4. Cliente y No. de piezas como dropdowns ===")
check("Cliente es un dropdown cerrado",
      not dialog.customer.isEditable() and dialog.customer.count() > 0,
      f"{dialog.customer.count()} clientes")
qty_items = [dialog.qty.itemText(i) for i in range(dialog.qty.count())]
check("No. de piezas: 1 al 9", qty_items == [str(i) for i in range(1, 10)],
      str(qty_items))
check("No. de piezas no es editable", not dialog.qty.isEditable())

generic = GenericDialog(context.torsion, context.catalogs, context.audit,
                        __import__("app.models", fromlist=["TORSION"]).TORSION)
check("Torsion: Cliente tambien es dropdown cerrado",
      not generic.customer.isEditable() and generic.customer.count() > 0)
check("Torsion: Test Rig es dropdown cerrado",
      not generic.rig.isEditable())

# --- la flecha se dibuja ---------------------------------------------
# El primer render() del proceso siempre sale en blanco, sea cual sea el
# widget: hay que calentar con uno de descarte antes de medir.
from PySide6.QtWidgets import QComboBox as _WarmUp
_scratch = _WarmUp()
_scratch.addItems(["x"])
_scratch.resize(180, 34)
_scratch.ensurePolished()
_warm = QPixmap(_scratch.size())
_scratch.render(_warm)

def _measure(widget):
    widget.resize(180, 34)
    widget.ensurePolished()
    pixmap = QPixmap(widget.size())
    pixmap.fill()
    widget.render(pixmap)
    image = pixmap.toImage()
    return len({
        image.pixelColor(x, y).name()
        for x in range(image.width() - 24, image.width() - 4)
        for y in range(8, image.height() - 8)
    })


def arrow_colors(widget):
    # El primer render() de un hijo de un dialogo que nunca se mostro sale en
    # blanco. Se mide de nuevo si eso pasa.
    result = _measure(widget)
    return result if result > 1 else _measure(widget)

customer_arrow = arrow_colors(dialog.customer)
check("el combo de Cliente dibuja su flecha", customer_arrow > 1,
      f"{customer_arrow} colores")
check("el combo de piezas dibuja su flecha", arrow_colors(dialog.qty) > 1)
check("el selector de fecha dibuja su flecha",
      arrow_colors(dialog.start_date) > 1)

# ======================================================================
print("\n=== 5. Fecha por omision y date picker ===")
check("nuevo registro abre con la fecha de hoy",
      dialog.start_date.date().toPython() == date.today(),
      str(dialog.start_date.date().toPython()))
check("tiene calendario emergente", dialog.start_date.calendarPopup())
check("formato dd/MM/yyyy", dialog.start_date.displayFormat() == "dd/MM/yyyy",
      dialog.start_date.displayFormat())
check("Torsion tambien abre en hoy",
      generic.test_date.date().toPython() == date.today())
check("Torsion tiene calendario", generic.test_date.calendarPopup())

# --- no se pierden valores heredados ---------------------------------
print("\n=== Valores heredados fuera del catalogo ===")
record = context.fatigue.list(ONGOING)[0]
loaded = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                       test=record)
collected = loaded._collect()
check("editar no pierde el cliente",
      collected.customer == record.customer,
      f"{collected.customer} vs {record.customer}")
check("editar no pierde los valores de pieza",
      [s.rig for s in collected.samples] == [s.rig for s in record.samples],
      str([s.rig for s in collected.samples][:3]))

app.quit()
print("\n" + "=" * 62)
if failures:
    print(f"FALLARON {len(failures)}:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("TODAS LAS COMPROBACIONES PASARON")
