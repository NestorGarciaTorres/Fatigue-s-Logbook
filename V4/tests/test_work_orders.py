"""Verifica el flujo completo: Work Order -> Comenzar prueba -> registro."""

from harness import (
    Report, database_copy, empty_database, make_context, offscreen,
    qt_app, settle,
)


import sys
from datetime import date
from pathlib import Path


from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from app.config import AppConfig
from app.context import AppContext
from app.models import (
    ONGOING, WO_PENDING, WO_STARTED, Requester, WorkOrder,
)
from app.ui import theme
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.widgets.common import combo_value
from app.ui.dialogs.rotary_dialog import RotaryDialog
from app.ui.dialogs.work_order_dialog import WorkOrderDialog
from app.ui.main_window import MainWindow
from app.ui.pages.settings_page import RequestersTab

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
print("migraciones:", context.prepare() or "ninguna pendiente")

# ======================================================================
print("\n=== 1. Catalogo de solicitantes ===")
# Sobre una base recien creada, no sobre la copia: la copia ya trae los
# solicitantes que el usuario dio de alta, y comprobar ahi que "nace vacio"
# mediria el uso real en vez de lo que hace la migracion.
import tempfile
_nueva = Path(tempfile.mkdtemp()) / "nueva.db"
_limpio = AppContext(AppConfig(database_path=str(_nueva), auto_backup=False))
_limpio.prepare()
check("nace vacio, sin nombres inventados",
      _limpio.catalogs.requesters() == [],
      str(_limpio.catalogs.requesters()))

for nombre in ("Ana Torres", "Luis Gomez"):
    if nombre not in context.catalogs.requesters():
        context.catalogs.save_requester(Requester(name=nombre))
check("se pueden dar de alta",
      {"Ana Torres", "Luis Gomez"} <= set(context.catalogs.requesters()),
      str(context.catalogs.requesters()))

# ======================================================================
print("\n=== 2. Alta de una Work Order ===")
repo = context.work_orders
orden = WorkOrder(
    test_type="fatigue", test_batch="990001STF01", customer="AUDI",
    qty_samples=3, requester="Ana Torres", comments="urgente",
)
wo_id = repo.create(orden, AUTHOR)
guardada = repo.get(wo_id)
check("se guarda y se relee",
      (guardada.test_batch, guardada.customer, guardada.qty_samples,
       guardada.requester) == ("990001STF01", "AUDI", 3, "Ana Torres"),
      str(guardada))
check("nace pendiente", guardada.status == WO_PENDING, guardada.status)
check("sin prueba enlazada todavia", guardada.started_test_id is None)
check("guarda la fecha de creacion", guardada.created_at == date.today(),
      str(guardada.created_at))
check("una WO de fatiga se puede comenzar", guardada.can_start)

torsion_wo = WorkOrder(test_type="torsion", test_batch="990002STO01",
                       customer="AUDI", qty_samples=2, requester="Luis Gomez")
torsion_id = repo.create(torsion_wo, AUTHOR)
check("una WO de torsion NO se puede comenzar todavia",
      not repo.get(torsion_id).can_start)

check("el alta queda en el historial",
      any(e.action == "created" for e in context.audit.for_record(
          "work_orders", wo_id)))

# ======================================================================
print("\n=== 3. El formulario se abre con los datos de la orden ===")
dialog = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                       work_order=guardada)
check("trae el Test Batch", dialog.batch.text() == "990001STF01",
      dialog.batch.text())
check("trae el cliente", dialog.customer.currentText() == "AUDI",
      dialog.customer.currentText())
check("trae el numero de piezas", dialog.qty.currentText() == "3",
      dialog.qty.currentText())
check("trae los comentarios", dialog.comments.text() == "urgente",
      dialog.comments.text())
check("la fecha de inicio queda en hoy, para que el usuario la ajuste",
      dialog.start_date.date().toPython() == date.today(),
      str(dialog.start_date.date().toPython()))
check("las piezas quedan vacias, las llena quien corre la prueba",
      all(not c.text() for c in dialog.cycles)
      and all(not combo_value(r) for r in dialog.rigs)
      and all(not combo_value(m) for m in dialog.failure_modes))
check("el titulo dice que viene de una WO",
      "Comenzar prueba" in dialog.windowTitle(), dialog.windowTitle())
check("las 9 piezas siguen a la vista",
      all(b.isVisibleTo(dialog) for b in dialog.sample_boxes))

# ======================================================================
print("\n=== 4. Guardar crea el registro y marca la orden ===")
dialog.rigs[0].setCurrentText("I-02-1")
dialog.cycles[0].setText("50000")
dialog.failure_modes[0].setCurrentText("Fractura")
dialog._save()

check("el formulario expone el id creado", dialog.created_id is not None,
      str(dialog.created_id))
creado = context.fatigue.get(dialog.created_id)
check("el registro entra a 'En curso'", creado.test_status == ONGOING,
      creado.test_status)
check("conserva los datos de la orden",
      (creado.test_batch, creado.customer, creado.qty_samples)
      == ("990001STF01", "AUDI", 3), str(creado.test_batch))
check("conserva lo capturado en la pieza 1",
      (creado.samples[0].rig, creado.samples[0].cycles,
       creado.samples[0].failure_mode) == ("I-02-1", 50000, "Fractura"),
      str(creado.samples[0]))

repo.mark_started(wo_id, dialog.created_id, AUTHOR)
marcada = repo.get(wo_id)
check("la orden queda comenzada", marcada.status == WO_STARTED, marcada.status)
check("y enlazada al registro", marcada.started_test_id == dialog.created_id,
      str(marcada.started_test_id))
check("una orden comenzada ya no se puede comenzar otra vez",
      not marcada.can_start)
check("el cambio queda en el historial",
      any(e.action == "started" for e in context.audit.for_record(
          "work_orders", wo_id)))

# ======================================================================
print("\n=== 5. Cancelar el formulario deja la orden pendiente ===")
otra = WorkOrder(test_type="rotary", test_batch="990003SRF01", customer="AUDI",
                 qty_samples=2, requester="Luis Gomez")
otra_id = repo.create(otra, AUTHOR)
cancelado = RotaryDialog(context.rotary, context.catalogs, context.audit,
                         work_order=repo.get(otra_id))
cancelado.reject()
check("sin guardar, no hay registro creado", cancelado.created_id is None)
check("la orden sigue pendiente", repo.get(otra_id).status == WO_PENDING,
      repo.get(otra_id).status)

# Ahora si, Rotary completo
rdialog = RotaryDialog(context.rotary, context.catalogs, context.audit,
                       work_order=repo.get(otra_id))
check("Rotary tambien precarga", rdialog.batch.text() == "990003SRF01",
      rdialog.batch.text())
rdialog.revs[0].setText("1200")
rdialog.statuses[0].setCurrentText("Falla")
rdialog._save()
check("Rotary crea el registro", rdialog.created_id is not None)
repo.mark_started(otra_id, rdialog.created_id, AUTHOR)
check("y la orden de Rotary queda comenzada",
      repo.get(otra_id).status == WO_STARTED)

# ======================================================================
print("\n=== 6. Validaciones de la Work Order ===")
wdialog = WorkOrderDialog(repo, context.catalogs)
items = [wdialog.test_type.itemText(i) for i in range(wdialog.test_type.count())]
check("ofrece los cuatro tipos de prueba", len(items) == 4, str(items))
req_items = [wdialog.requester.itemText(i)
             for i in range(wdialog.requester.count())]
check("el requester sale del catalogo",
      req_items == context.catalogs.requesters(), str(req_items))
check("el requester es lista cerrada", not wdialog.requester.isEditable())
qty_items = [wdialog.qty.itemText(i) for i in range(wdialog.qty.count())]
check("piezas 1 al 9", qty_items == [str(i) for i in range(1, 10)])

check("no admite un batch repetido en otra WO",
      repo.batch_exists("990001STF01"))
check("y sabe distinguir la propia al editar",
      not repo.batch_exists("990001STF01", exclude_id=wo_id))

# ======================================================================
print("\n=== 7. La pantalla y los botones ===")
window = MainWindow(context)
check("hay pagina de Work Orders", "work_orders" in window.pages)
window.show_page("work_orders")
page = window.pages["work_orders"]
page.status_filter.setCurrentText("Todas")
page.refresh()
print(f"      ordenes en la lista: {len(page._orders)}")
check("lista las ordenes creadas aqui", len(page._orders) >= 3,
      str(len(page._orders)))

acciones = {}
for row, order in enumerate(page._orders):
    widget = page.table.cellWidget(row, page.ACTION_COLUMN)
    acciones[order.test_batch] = (
        type(widget).__name__,
        widget.isEnabled() if isinstance(widget, QPushButton) else None,
    )
for batch, info in acciones.items():
    print(f"      {batch}: {info}")

# Donde no hay accion no se pone un boton apagado, sino una nota.
check("la WO de torsion no ofrece boton, sino una nota",
      acciones["990002STO01"][0] == "QLabel",
      str(acciones["990002STO01"]))
nota = next(page.table.cellWidget(r, page.ACTION_COLUMN)
            for r, o in enumerate(page._orders)
            if o.test_batch == "990002STO01")
check("la nota explica donde dar de alta esa prueba",
      "bitácora de Torsión" in nota.toolTip(), nota.toolTip())
check("las comenzadas ya no muestran boton",
      acciones["990001STF01"][0] == "QLabel", str(acciones["990001STF01"]))

page.status_filter.setCurrentText(WO_PENDING + "s")
page.refresh()
check("el filtro de pendientes deja fuera las ya comenzadas",
      "990002STO01" in [o.test_batch for o in page._orders]
      and "990001STF01" not in [o.test_batch for o in page._orders],
      str([o.test_batch for o in page._orders]))

# --- ya no hay 'Nuevo registro' en Fatiga ni Rotary ---
fatiga = window.pages["fatigue"]
check("Fatiga ya no tiene boton de alta directa",
      not hasattr(fatiga.ongoing, "new_button"))
check("ni el metodo que lo abria", not hasattr(fatiga.ongoing, "open_new"))
rotary = window.pages["rotary"]
check("Rotary tampoco", not hasattr(rotary, "new_button")
      and not hasattr(rotary, "open_new"))
check("pero Torsion conserva el suyo",
      hasattr(window.pages["torsion"], "new_button"))
check("y Quasi tambien", hasattr(window.pages["quasi"], "new_button"))
check("Fatiga conserva el boton de exportar",
      hasattr(fatiga.ongoing, "export_button"))

# --- el registro creado aparece en la bitacora ---
window.show_page("fatigue")
batches = [t.test_batch for t in context.fatigue.list(ONGOING)]
check("el registro creado desde la WO esta en 'En curso'",
      "990001STF01" in batches)

# ======================================================================
print("\n=== 8. Ajustes -> Solicitantes ===")
tab = RequestersTab(context)
tab.refresh()
nombres = [tab.table.item(r, 0).text() for r in range(tab.table.rowCount())]
check("lista a los solicitantes",
      {"Ana Torres", "Luis Gomez"} <= set(nombres), str(nombres))
usos = {tab.table.item(r, 0).text(): tab.table.item(r, 2).text()
        for r in range(tab.table.rowCount())}
print(f"      Work Orders por solicitante: {usos}")
# Las ordenes que crea esta prueba: 1 de Ana, 2 de Luis. La copia puede traer
# mas, asi que se comprueba el conteo del repositorio, no un total absoluto.
check("cuenta las ordenes de cada uno",
      usos["Ana Torres"] == str(context.work_orders.requester_usage("Ana Torres"))
      and usos["Luis Gomez"] == str(
          context.work_orders.requester_usage("Luis Gomez")),
      str(usos))
check("el conteo del repositorio ve las ordenes creadas aqui",
      context.work_orders.requester_usage("Ana Torres") >= 1
      and context.work_orders.requester_usage("Luis Gomez") >= 2,
      f"Ana={context.work_orders.requester_usage('Ana Torres')}, "
      f"Luis={context.work_orders.requester_usage('Luis Gomez')}")

app.quit()
print("\n" + "=" * 64)
if failures:
    print(f"FALLARON {len(failures)}:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("TODAS LAS COMPROBACIONES PASARON")
