"""Que una pieza apagada se vea apagada, medido en pixeles.

Esta suite existe por un tropiezo anterior: las piezas sobrantes se
"atenuaban" con ``color:`` sobre campos vacios --que no tienen texto que
colorear-- y una prueba lo daba por bueno porque comprobaba que se hubiera
llamado a la funcion, no que algo cambiara en pantalla.

Aqui se compara la tinta de una pieza capturable contra la de una apagada, en
el mismo formulario y sobre los mismos campos. Corre con la plataforma nativa:
con 'offscreen' las fuentes no resuelven.
"""

from harness import Report, make_context, qt_app, settle

from datetime import date

from PySide6.QtGui import QColor

from app.models import ONGOING, FatigueSample, FatigueTest
from app.ui import theme
from app.ui.dialogs.fatigue_dialog import FatigueDialog

AUTHOR = ("verificador", "PC-PRUEBA")
report = Report("Campos deshabilitados")

app = qt_app()
context = make_context()
bancos = context.catalogs.rig_names("fatigue")

test = FatigueTest(
    test_batch="999871STF01", customer="AUDI", start_date=date(2026, 8, 5),
    qty_samples=3, test_status=ONGOING,
    samples=[FatigueSample(rig=bancos[0], result="Falla", cycles=1000,
                           failure_mode="Fisura")]
            + [FatigueSample() for _ in range(8)],
)
test_id = context.fatigue.create(test, AUTHOR)

dialog = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                       test=context.fatigue.get(test_id))
dialog.show()
settle(app, 30)
# El primer render de un proceso Qt sale en blanco: se descarta.
dialog.grab()
settle(app, 10)

report.section("1. El estado es el que se espera")
report.check("la pieza 3 esta activa (dentro de las declaradas)",
             dialog.sample_boxes[2].is_active())
report.check("la pieza 4 esta apagada (fuera de las declaradas)",
             not dialog.sample_boxes[3].is_active())
report.check("y sus campos tambien",
             not dialog.rigs[3].isEnabled()
             and not dialog.cycles[3].isEnabled()
             and not dialog.failure_modes[3].isEnabled())


def ink(widget) -> QColor:
    """El pixel mas claro del campo: el texto sobre el fondo oscuro."""
    image = widget.grab().toImage()
    best = None
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            value = color.lightness()
            if best is None or value > best[0]:
                best = (value, color)
    return best[1]


def fill(widget) -> QColor:
    """El relleno del campo: el pixel del centro, lejos del borde."""
    image = widget.grab().toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2)


report.section("2. Los combos apagados se pintan mas apagados")
# Ambos muestran la misma etiqueta '(sin banco)': si el texto se dibujara
# igual, estas dos medidas serian identicas.
activo = ink(dialog.rigs[2])
apagado = ink(dialog.rigs[3])
print(f"      Test Rig pieza 3 (activa):  {activo.name()}  "
      f"claridad {activo.lightness()}")
print(f"      Test Rig pieza 4 (apagada): {apagado.name()}  "
      f"claridad {apagado.lightness()}")

report.check("los dos combos dicen lo mismo",
             dialog.rigs[2].currentText() == dialog.rigs[3].currentText(),
             dialog.rigs[2].currentText())
report.check("el apagado se dibuja mas oscuro que el activo",
             apagado.lightness() < activo.lightness(),
             f"{apagado.lightness()} vs {activo.lightness()}")
report.check("y la diferencia se nota a simple vista (>25)",
             activo.lightness() - apagado.lightness() > 25,
             str(activo.lightness() - apagado.lightness()))

mode_activo = ink(dialog.failure_modes[2])
mode_apagado = ink(dialog.failure_modes[3])
report.check("el combo de modo de falla se comporta igual",
             mode_apagado.lightness() < mode_activo.lightness(),
             f"{mode_apagado.lightness()} vs {mode_activo.lightness()}")

report.section("3. Y las cajas de ciclos")
# Aqui no sirve medir el pixel mas claro: las dos cajas estan vacias y el mas
# claro acaba siendo el borde. Lo que distingue una caja vacia apagada de una
# capturable es el relleno, asi que se mide el centro.
fill_activo = fill(dialog.cycles[2])
fill_apagado = fill(dialog.cycles[3])
print(f"      Ciclos activa,  relleno {fill_activo.name()}")
print(f"      Ciclos apagada, relleno {fill_apagado.name()}")
report.check("la caja vacia apagada tiene relleno mas oscuro",
             fill_apagado.lightness() < fill_activo.lightness(),
             f"{fill_apagado.lightness()} vs {fill_activo.lightness()}")
report.check("y su borde tambien se apaga",
             ink(dialog.cycles[3]).lightness() < ink(dialog.cycles[2]).lightness(),
             f"{ink(dialog.cycles[3]).name()} vs {ink(dialog.cycles[2]).name()}")

# Con texto dentro, la caja apagada tambien tiene que leerse mas apagada.
dialog.cycles[2].setText("12345")
dialog.qty.setCurrentText("4")          # habilita la 4 para poder escribirle
settle(app, 10)
dialog.cycles[3].setText("12345")
dialog.qty.setCurrentText("3")          # y la vuelve a apagar, ya con dato
settle(app, 10)
report.check("la pieza 4 con dato se queda encendida y marcada 'de mas'",
             dialog.sample_boxes[3].is_active()
             and "de mas" in dialog.sample_boxes[3].title(),
             dialog.sample_boxes[3].title())
dialog.cycles[3].clear()
settle(app, 10)
report.check("al borrarlo vuelve a apagarse",
             not dialog.sample_boxes[3].is_active())

report.section("4. Los rotulos del recuadro tambien cambian")
report.check("el titulo de la pieza apagada no es el mismo color",
             dialog.sample_boxes[3].styleSheet() != "",
             repr(dialog.sample_boxes[3].styleSheet()[:40]))
report.check("el de la activa no lleva estilo especial",
             dialog.sample_boxes[2].styleSheet() == "",
             repr(dialog.sample_boxes[2].styleSheet()))
report.check("el color apagado del tema es mas oscuro que el atenuado",
             QColor(theme.TEXT_DISABLED).lightness()
             < QColor(theme.TEXT_MUTED).lightness(),
             f"{theme.TEXT_DISABLED} vs {theme.TEXT_MUTED}")

report.section("5. Subir la cantidad devuelve el brillo")
dialog.qty.setCurrentText("9")
settle(app, 20)
report.check("la pieza 4 vuelve a estar activa",
             dialog.sample_boxes[3].is_active() and dialog.rigs[3].isEnabled())
report.check("y se vuelve a pintar como la 3",
             ink(dialog.rigs[3]).lightness() >= activo.lightness() - 5,
             f"{ink(dialog.rigs[3]).lightness()} vs {activo.lightness()}")

raise SystemExit(report.finish())
