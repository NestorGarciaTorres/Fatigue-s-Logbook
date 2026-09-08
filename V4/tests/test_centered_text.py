"""Comprueba que el texto de los formularios va centrado."""

from harness import (
    Report, database_copy, empty_database, make_context, offscreen,
    qt_app, settle,
)


import sys
from pathlib import Path


from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDateEdit, QDialog, QLineEdit,
)

from app.config import AppConfig
from app.context import AppContext
from app.models import ONGOING, TORSION
from app.ui import theme
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.dialogs.rotary_dialog import RotaryDialog
from app.ui.dialogs.work_order_dialog import WorkOrderDialog
from app.ui.widgets.common import CenteredComboBox

COPY = database_copy()
failures = []


def check(label, condition, detail=""):
    print(("OK    " if condition else "FALLO ") + label +
          (f"   {detail}" if detail else ""))
    if not condition:
        failures.append(label)


app = QApplication(sys.argv)
theme.apply(app)
context = AppContext(AppConfig(database_path=str(COPY), auto_backup=False))
context.prepare()


def campos(dialog):
    """Todos los campos de captura del dialogo."""
    return (dialog.findChildren(QLineEdit)
            + dialog.findChildren(QComboBox)
            + dialog.findChildren(QDateEdit))


def centro_del_texto(widget) -> float | None:
    """Fraccion horizontal donde cae el texto dibujado: 0 izquierda, 1 derecha.

    Se mide sobre el pixel real en vez de fiarse de la propiedad: el texto de
    un combo cerrado no lo dibuja ningun QLineEdit, asi que setAlignment no
    dice nada de el.
    """
    widget.resize(240, 34)
    widget.ensurePolished()
    for _ in range(2):                 # el primer render del proceso sale vacio
        pixmap = QPixmap(widget.size())
        pixmap.fill()
        widget.render(pixmap)
    image = pixmap.toImage()

    # Se ignoran los 26 px de la derecha: ahi va la flecha del combo.
    util = image.width() - 26
    fondo = image.pixelColor(2, 2).name()
    columnas = [
        x for x in range(4, util)
        if any(image.pixelColor(x, y).name() != fondo
               for y in range(6, image.height() - 6))
    ]
    if not columnas:
        return None
    return ((min(columnas) + max(columnas)) / 2) / util


# ======================================================================
print("=== 1. Los combos cerrados dibujan su texto centrado ===")
dialog = FatigueDialog(context.fatigue, context.catalogs, context.audit)
dialog.customer.setCurrentIndex(0)
dialog.rigs[0].setCurrentIndex(0)

for nombre, widget in (("Cliente", dialog.customer),
                       ("No. de piezas", dialog.qty),
                       ("Tiene Work Order", dialog.wo),
                       ("Pieza 1", dialog.rigs[0])):
    fraccion = centro_del_texto(widget)
    print(f"      {nombre:<18} texto centrado en {fraccion:.2f}"
          if fraccion is not None else f"      {nombre:<18} sin texto")
    check(f"'{nombre}' centrado",
          fraccion is not None and 0.40 <= fraccion <= 0.60,
          f"{fraccion:.2f}" if fraccion is not None else "sin texto")

check("siguen siendo listas cerradas",
      not dialog.customer.isEditable() and not dialog.qty.isEditable()
      and not dialog.rigs[0].isEditable())
check("son CenteredComboBox",
      all(isinstance(w, CenteredComboBox)
          for w in (dialog.customer, dialog.qty, dialog.wo, dialog.rigs[0])))

# ======================================================================
print("\n=== 2. Fechas y cajas de texto ===")
for nombre, widget in (("Inicio de prueba", dialog.start_date),
                       ("Fin de prueba", dialog.end_date)):
    alineacion = widget.lineEdit().alignment()
    check(f"'{nombre}' centrado",
          bool(alineacion & Qt.AlignmentFlag.AlignHCenter), str(alineacion))

for nombre, widget in (("Test Batch", dialog.batch),
                       ("Comentarios", dialog.comments),
                       ("Ciclos 1", dialog.cycles[0])):
    check(f"'{nombre}' centrado",
          bool(widget.alignment() & Qt.AlignmentFlag.AlignHCenter),
          str(widget.alignment()))

# ======================================================================
print("\n=== 3. Ningun campo queda alineado a la izquierda ===")
dialogos = {
    "Fatiga (nuevo)": dialog,
    "Fatiga (edicion)": FatigueDialog(
        context.fatigue, context.catalogs, context.audit,
        test=context.fatigue.list(ONGOING)[0]),
    "Rotary": RotaryDialog(context.rotary, context.catalogs, context.audit),
    "Torsion": GenericDialog(context.torsion, context.catalogs, context.audit,
                             TORSION),
    "Work Order": WorkOrderDialog(context.work_orders, context.catalogs),
}

for nombre, dlg in dialogos.items():
    sueltos = []
    for widget in campos(dlg):
        if isinstance(widget, QDateEdit):
            ok = bool(widget.lineEdit().alignment()
                      & Qt.AlignmentFlag.AlignHCenter)
        elif isinstance(widget, QComboBox):
            # El QLineEdit interno de un QDateEdit ya se conto arriba.
            ok = isinstance(widget, CenteredComboBox)
        elif widget.parent() is not None and isinstance(
                widget.parent(), (QDateEdit, QComboBox)):
            continue
        else:
            ok = bool(widget.alignment() & Qt.AlignmentFlag.AlignHCenter)
        if not ok:
            sueltos.append(f"{type(widget).__name__}({widget.objectName()})")
    print(f"      {nombre:<18} {len(campos(dlg))} campos, "
          f"{len(sueltos)} sin centrar")
    check(f"{nombre}: todos los campos centrados", not sueltos, str(sueltos))

# ======================================================================
print("\n=== 4. La lista desplegada tambien va centrada ===")
combo = dialog.customer
combo.showPopup()
app.processEvents()
alineaciones = {
    combo.itemData(i, Qt.ItemDataRole.TextAlignmentRole)
    for i in range(combo.count())
}
combo.hidePopup()
check("cada opcion lleva alineacion centrada",
      alineaciones == {Qt.AlignmentFlag.AlignCenter}, str(alineaciones))

app.quit()
print("\n" + "=" * 62)
if failures:
    print(f"FALLARON {len(failures)}:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("TODAS LAS COMPROBACIONES PASARON")
