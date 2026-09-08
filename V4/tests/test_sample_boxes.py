"""Verifica el recuadro por pieza y el ocultado de las piezas sobrantes."""

from harness import (
    Report, database_copy, empty_database, make_context, offscreen,
    qt_app, settle,
)


import sys
from datetime import date
from pathlib import Path


from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.context import AppContext
from app.models import FatigueSample, FatigueTest, RotarySample, RotaryTest
from app.ui import theme
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.dialogs.rotary_dialog import RotaryDialog

COPY = database_copy()
failures = []


def check(label, condition, detail=""):
    print(("OK    " if condition else "FALLO ") + label +
          (f"   {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def visibles(dialog):
    return [b.number for b in dialog.sample_boxes if b.isVisibleTo(dialog)]


app = QApplication(sys.argv)
theme.apply(app)
context = AppContext(AppConfig(database_path=str(COPY), auto_backup=False))
context.prepare()

# ======================================================================
print("=== 1. Cada pieza es un recuadro propio ===")
dialog = FatigueDialog(context.fatigue, context.catalogs, context.audit)
check("hay 9 recuadros", len(dialog.sample_boxes) == 9)
check("cada uno lleva el numero de pieza en el titulo",
      [b.title() for b in dialog.sample_boxes]
      == [f"Pieza {i}" for i in range(1, 10)],
      str([b.title() for b in dialog.sample_boxes][:3]))
check("los tres campos de la pieza 1 estan dentro de su recuadro",
      all(w.parent() is dialog.sample_boxes[0]
          for w in (dialog.rigs[0], dialog.cycles[0], dialog.failure_modes[0])))
check("y no mezclados con los de la pieza 2",
      dialog.rigs[1].parent() is dialog.sample_boxes[1])

# ======================================================================
print("\n=== 2. Solo se ven las piezas declaradas ===")
for declaradas in ("1", "4", "9", "2"):
    dialog.qty.setCurrentText(declaradas)
    app.processEvents()
    check(f"con {declaradas} declarada(s) se siguen viendo las 9 piezas",
          visibles(dialog) == list(range(1, 10)), str(visibles(dialog)))

check("no queda ninguna casilla de 'mostrar todas'",
      not hasattr(dialog, "show_all_samples"))

# ======================================================================
print("\n=== 3. La ventana no cambia de alto al cambiar el numero ===")
dialog.show()
for _ in range(5):
    app.processEvents()


def alto_con(piezas):
    dialog.qty.setCurrentText(str(piezas))
    for _ in range(5):
        app.processEvents()
    return dialog.height()


una = alto_con(1)
nueve = alto_con(9)
print(f"      alto con 1 pieza: {una} px, con 9: {nueve} px")
check("el alto es el mismo con 1 que con 9 piezas", una == nueve,
      f"{una} vs {nueve}")
dialog.close()

# ======================================================================
print("\n=== 4. Piezas capturadas por encima de lo declarado ===")
# El caso real de los registros heredados: qty_samples dice 1, pero hay datos
# en las piezas 2 y 3.
sobrante = FatigueTest(
    test_batch="999904STF01", customer="AUDI", start_date=date(2026, 8, 4),
    qty_samples=1,
    samples=[
        FatigueSample(rig="I-02-1", cycles=100),
        FatigueSample(rig="Falla", cycles=200),
        FatigueSample(cycles=300),
    ] + [FatigueSample() for _ in range(6)],
)
sobrante_id = context.fatigue.create(sobrante, ("verificador", "PC-PRUEBA"))
cargado = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                        test=context.fatigue.get(sobrante_id))
app.processEvents()
print(f"      declara 1 pieza, visibles: {visibles(cargado)}")
check("se ven las 9 piezas aunque solo se declare una",
      visibles(cargado) == list(range(1, 10)), str(visibles(cargado)))
check("las sobrantes con datos se marcan",
      [b.number for b in cargado.sample_boxes if "de mas" in b.title()] == [2, 3],
      str([b.title() for b in cargado.sample_boxes[:4]]))
check("la pieza 1, dentro de lo declarado, no se marca",
      "de mas" not in cargado.sample_boxes[0].title())
check("el grupo avisa en su titulo",
      "por encima" in cargado.samples_group.title(),
      cargado.samples_group.title())
check("las sobrantes traen explicacion al pasar el cursor",
      "número declarado" in cargado.sample_boxes[1].toolTip(),
      cargado.sample_boxes[1].toolTip())
check("guardar no pierde los datos de las piezas sobrantes",
      [s.cycles for s in cargado._collect().samples[:3]] == [100, 200, 300],
      str([s.cycles for s in cargado._collect().samples[:3]]))

# Al subir el numero declarado dejan de ser sobrantes.
cargado.qty.setCurrentText("3")
app.processEvents()
check("subir el numero quita la marca",
      all("de mas" not in b.title() for b in cargado.sample_boxes),
      str([b.title() for b in cargado.sample_boxes[:3]]))
check("y limpia el aviso del grupo",
      cargado.samples_group.title() == "Datos de las muestras",
      cargado.samples_group.title())

# ======================================================================
print("\n=== 5. Rotary se comporta igual ===")
rotary = RotaryTest(
    test_batch="999905SRF01", customer="AUDI", start_date=date(2026, 8, 5),
    qty_samples=1, test_rig="I-25",
    samples=[RotarySample(revs=10, status="Falla"),
             RotarySample(revs=20, status="S/Falla")]
            + [RotarySample() for _ in range(7)],
)
rotary_id = context.rotary.create(rotary, ("verificador", "PC-PRUEBA"))
rdialog = RotaryDialog(context.rotary, context.catalogs, context.audit,
                       test=context.rotary.get(rotary_id))
app.processEvents()
check("Rotary: 9 recuadros", len(rdialog.sample_boxes) == 9)
check("Rotary: muestra las 9 piezas", visibles(rdialog) == list(range(1, 10)),
      str(visibles(rdialog)))
check("Rotary: marca la sobrante",
      "de mas" in rdialog.sample_boxes[1].title(),
      rdialog.sample_boxes[1].title())
rdialog.qty.setCurrentText("5")
app.processEvents()
check("Rotary: subir a 5 quita la marca",
      all("de mas" not in b.title() for b in rdialog.sample_boxes))

# ======================================================================
print("\n=== 5b. Datos generales repartidos en columnas ===")


def celda(grid, widget):
    """(fila, columna) que ocupa un campo dentro de la rejilla."""
    index = grid.indexOf(widget)
    fila, columna, _, _ = grid.getItemPosition(index)
    return fila, columna


nuevo = FatigueDialog(context.fatigue, context.catalogs, context.audit)
grid = nuevo.samples_group.parent().findChild(type(nuevo.layout()))
general = nuevo.batch.parentWidget().layout()

posiciones = {
    "Test Batch": celda(general, nuevo.batch),
    "Cliente": celda(general, nuevo.customer),
    "Inicio": celda(general, nuevo.start_date),
    "No. de piezas": celda(general, nuevo.qty),
    "Work Order": celda(general, nuevo.wo),
    "Fin": celda(general, nuevo.end_date),
    "Comentarios": celda(general, nuevo.comments),
}
for nombre, (fila, columna) in posiciones.items():
    print(f"      {nombre:<15} fila {fila}, columna {columna}")

filas = {fila for fila, _ in posiciones.values()}
columnas = {columna for _, columna in posiciones.values()}
check("los datos generales ya no van en una sola columna",
      len(columnas) > 1, str(sorted(columnas)))
check("caben en tres filas en vez de siete", len(filas) == 3, str(sorted(filas)))
check("la primera fila lleva tres campos distintos",
      len({c for f, c in posiciones.values() if f == 0}) == 3)
check("comentarios ocupa su propia fila",
      posiciones["Comentarios"][0] == 2)

alto_general = nuevo.batch.parentWidget().sizeHint().height()
print(f"      alto de 'Datos generales': {alto_general} px")
check("el bloque de datos generales es mas bajo que las 7 filas de antes",
      alto_general < 200, f"{alto_general} px")

# ======================================================================
print("\n=== 6. Se sigue viendo (los recuadros dibujan su borde) ===")
nueve_dialog = FatigueDialog(context.fatigue, context.catalogs, context.audit)
nueve_dialog.qty.setCurrentText("9")
nueve_dialog.show()
for _ in range(5):
    app.processEvents()
shot = nueve_dialog.grab()
colores = {shot.toImage().pixelColor(x, y).name()
           for x in range(0, shot.width(), 7)
           for y in range(360, min(shot.height(), 560), 7)}
print(f"      colores distintos en la zona de muestras: {len(colores)}")
check("la zona de muestras no sale en blanco", len(colores) > 3, str(len(colores)))
nueve_dialog.close()

app.quit()
print("\n" + "=" * 62)
if failures:
    print(f"FALLARON {len(failures)}:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("TODAS LAS COMPROBACIONES PASARON")
