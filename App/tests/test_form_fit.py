"""Formularios que caben en la pantalla de un portatil.

Tres cosas, comprobadas midiendo y no leyendo el codigo:

1. El formulario de fatiga pedia 967 px de alto y el de rotary 850. En un
   portatil la fila de 'Guardar' quedaba debajo del borde de la pantalla, sin
   forma de llegar a ella. Ahora solo se desplaza el cuerpo: el titulo y los
   botones quedan fijos.
2. Con Fusion la lista desplegable ignoraba maxVisibleItems y crecia con el
   catalogo: la de clientes media 516 px.
3. La rueda sobre un combo o una fecha sin foco cambiaba su valor. Dentro de un
   formulario desplazable, eso era cambiar el Test Rig al bajar por el.

Corre con la plataforma nativa: con 'offscreen' las fuentes no resuelven y las
medidas no son las de la app.
"""

from harness import Report, make_context, qt_app

import time

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionComboBox

from app.models import QUASI, TORSION
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.dialogs.rotary_dialog import RotaryDialog
from app.ui.dialogs.work_order_dialog import WorkOrderDialog
from app.ui.widgets.common import (
    MAX_VISIBLE_ITEMS,
    SCREEN_MARGIN,
    combo_value,
    fit_dialog_to_screen,
    set_combo_value,
)

report = Report("Formularios en pantallas chicas")
app = qt_app()
context = make_context()

# Estas pruebas cambian campos y luego cierran el formulario. Sin esto, la
# pregunta de 'cambios sin guardar' abriria un cuadro modal y la prueba se
# quedaria colgada esperando a que alguien lo cerrara.
from app.ui.dialogs import form_guard

form_guard.confirm_discard = lambda _parent: True

# Un portatil de 1366x768 con la barra de tareas deja unos 728 px de alto; un
# 1920x1080 al 150 % de escala, unos 680. Se simula el peor de los dos.
PANTALLA_CHICA = 680
# Lo minimo que puede exigir un formulario para caber en el portatil de 768.
TOPE_MINIMO = 768 - 40 - SCREEN_MARGIN


def esperar(segundos: float = 0.3) -> None:
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        app.processEvents()


def rueda(widget, hacia_abajo: bool = True) -> None:
    """Un paso de rueda sobre el centro del widget, como lo manda el raton.

    Qt solo pasa al padre la rueda **real** que nadie acepto; la que se manda
    con sendEvent no sube (medido: el combo la ignora y la barra no se movia,
    y enviada al viewport del area si desplazaba 60 px). Aqui se sube a mano,
    igual que hace Qt con la del raton, hasta que alguien la acepte.
    """
    delta = QPoint(0, -120 if hacia_abajo else 120)
    destino = widget
    while destino is not None:
        centro = destino.rect().center()
        evento = QWheelEvent(
            QPointF(centro), QPointF(destino.mapToGlobal(centro)),
            QPoint(0, 0), delta, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(destino, evento)
        if evento.isAccepted() or destino.isWindow():
            return
        destino = destino.parentWidget()


def hueco(dialogo) -> int:
    """Pixeles vacios entre el ultimo bloque de datos y el borde del area.

    Mide lo que se ve, no el calculo: el ultimo bloque antes del stretch del
    cuerpo, contra el alto visible del area.
    """
    cuerpo = dialogo.body.layout()
    ultimo = cuerpo.itemAt(cuerpo.count() - 2).widget()
    fondo = ultimo.mapTo(dialogo.body, QPoint(0, 0)).y() + ultimo.height()
    return dialogo.scroll.viewport().height() - fondo


def nuevo(nombre: str):
    """Formulario de alta, con las nueve piezas capturables."""
    if nombre == "Fatiga":
        dialogo = FatigueDialog(context.fatigue, context.catalogs, context.audit)
    else:
        dialogo = RotaryDialog(context.rotary, context.catalogs, context.audit)
    # Con una sola pieza declarada las otras ocho estan apagadas, y un widget
    # deshabilitado no recibe la rueda: la prueba no probaria nada.
    set_combo_value(dialogo.qty, "9")
    return dialogo


for nombre in ("Fatiga", "Rotary"):
    # ==================================================================
    report.section(f"{nombre}: los botones no quedan fuera de la pantalla")

    dialogo = nuevo(nombre)
    report.check("el minimo que exige cabe en un portatil de 768",
                 dialogo.minimumSizeHint().height() <= TOPE_MINIMO,
                 f"{dialogo.minimumSizeHint().height()} px de minimo, "
                 f"tope {TOPE_MINIMO} (antes: 967 fatiga, 850 rotary)")
    report.check("los datos van dentro del area desplazable",
                 dialogo.scroll.isAncestorOf(dialogo.samples_group))
    report.check("y el boton de guardar fuera de ella",
                 not dialogo.scroll.isAncestorOf(dialogo.save_button))

    fit_dialog_to_screen(dialogo, dialogo.scroll, dialogo.body,
                         available_height=PANTALLA_CHICA)
    dialogo.show()
    esperar(0.4)

    report.check("en la pantalla chica el formulario no pasa de su alto",
                 dialogo.height() <= PANTALLA_CHICA - SCREEN_MARGIN,
                 f"{dialogo.height()} px de {PANTALLA_CHICA - SCREEN_MARGIN}")
    boton = dialogo.save_button
    abajo = boton.mapTo(dialogo, QPoint(0, 0)).y() + boton.height()
    report.check("el boton de guardar se ve entero dentro del formulario",
                 boton.isVisible() and abajo <= dialogo.height(),
                 f"termina en {abajo} px, el formulario mide "
                 f"{dialogo.height()}")
    barra = dialogo.scroll.verticalScrollBar()
    report.check("lo que no cabe se alcanza desplazando",
                 barra.maximum() > 0, f"{barra.maximum()} px por desplazar")

    # --- la rueda ---------------------------------------------------------
    dialogo.batch.setFocus()
    esperar(0.2)
    barra.setValue(0)
    ultimo = dialogo.failure_modes[8]
    antes = ultimo.currentIndex()
    rueda(ultimo)
    esperar(0.1)
    report.check("la rueda sobre un combo sin foco no cambia su valor",
                 ultimo.currentIndex() == antes,
                 f"indice {antes} -> {ultimo.currentIndex()}")
    report.check("y desplaza el formulario",
                 barra.value() > 0, f"barra en {barra.value()}")

    fecha = dialogo.start_date
    dia = fecha.date()
    rueda(fecha)
    esperar(0.1)
    report.check("la rueda sobre una fecha sin foco tampoco la cambia",
                 fecha.date() == dia,
                 f"{dia.toString('dd/MM/yyyy')} -> "
                 f"{fecha.date().toString('dd/MM/yyyy')}")

    # Con foco la rueda sigue eligiendo, como antes: solo se quito el cambio
    # que nadie pidio. Si el sistema no le da el foco a la ventana de prueba,
    # no hay nada que medir y se dice.
    ultimo.setFocus()
    esperar(0.2)
    if ultimo.hasFocus():
        valor = combo_value(ultimo)
        rueda(ultimo)
        esperar(0.1)
        report.check("con foco, la rueda sigue cambiando el valor",
                     combo_value(ultimo) != valor,
                     f"{valor!r} -> {combo_value(ultimo)!r}")
    else:
        report.note("la ventana no recibio el foco: no se mide la rueda con foco")

    dialogo.close()
    esperar(0.1)

    # --- pantalla grande ------------------------------------------------
    # En un monitor donde cabe, el formulario no cambia: se abre entero y sin
    # barra. La barra solo aparece donde hace falta.
    grande = nuevo(nombre)
    disponible = grande.screen().availableGeometry().height()
    grande.show()
    esperar(0.4)
    if grande.height() < disponible - SCREEN_MARGIN:
        report.check("en una pantalla donde cabe, se ve entero y sin barra",
                     grande.scroll.verticalScrollBar().maximum() == 0,
                     f"{grande.height()} px, barra de "
                     f"{grande.scroll.verticalScrollBar().maximum()} px")
        report.check("y sin hueco entre los datos y los botones",
                     hueco(grande) == 0, f"{hueco(grande)} px vacios")
    else:
        report.note(f"esta pantalla ({disponible} px) no da para verlo entero")
    grande.close()
    esperar(0.1)


# Los formularios cortos: Work Order, Torsion y Quasi. Caben en cualquier
# portatil, pero con la escala de Windows alta o una pantalla baja el boton de
# guardar tambien quedaria fuera, asi que siguen la misma estructura.
CORTOS = (
    ("Work Order",
     lambda: WorkOrderDialog(context.work_orders, context.catalogs)),
    ("Torsion",
     lambda: GenericDialog(context.torsion, context.catalogs, context.audit,
                           TORSION)),
    ("Quasi",
     lambda: GenericDialog(context.quasi, context.catalogs, context.audit,
                           QUASI)),
)

for nombre, fabrica in CORTOS:
    # ==================================================================
    report.section(f"{nombre}: la misma estructura")

    corto = fabrica()
    report.check("los datos van dentro del area desplazable",
                 corto.scroll.isAncestorOf(corto.batch))
    report.check("y el boton de guardar fuera de ella",
                 not corto.scroll.isAncestorOf(corto.save_button))
    report.check("el minimo que exige cabe en un portatil de 768",
                 corto.minimumSizeHint().height() <= TOPE_MINIMO,
                 f"{corto.minimumSizeHint().height()} px de minimo, "
                 f"tope {TOPE_MINIMO}")
    corto.show()
    esperar(0.4)
    disponible = corto.screen().availableGeometry().height()
    if corto.height() < disponible - SCREEN_MARGIN:
        report.check("en una pantalla donde cabe, se ve entero y sin barra",
                     corto.scroll.verticalScrollBar().maximum() == 0,
                     f"{corto.height()} px, barra de "
                     f"{corto.scroll.verticalScrollBar().maximum()} px")
        # Paso en la Work Order: con el suelo fijo de 220 px, sus 189 px de
        # datos nacian con 31 px vacios encima de los botones.
        report.check("y sin hueco entre los datos y los botones",
                     hueco(corto) == 0, f"{hueco(corto)} px vacios")
    corto.close()
    esperar(0.1)

    # Una pantalla que no le da su alto -- escala de Windows alta, por
    # ejemplo --: se simula la mas baja con la que todavia puede abrirse.
    baja = fabrica()
    fit_dialog_to_screen(baja, baja.scroll, baja.body,
                         available_height=baja.minimumSizeHint().height()
                         + SCREEN_MARGIN)
    baja.show()
    esperar(0.4)
    boton = baja.save_button
    abajo = boton.mapTo(baja, QPoint(0, 0)).y() + boton.height()
    report.check("a su alto minimo, el boton de guardar se ve entero",
                 boton.isVisible() and abajo <= baja.height(),
                 f"termina en {abajo} px, el formulario mide {baja.height()}")
    barra = baja.scroll.verticalScrollBar()
    if baja.body.sizeHint().height() > baja.scroll.viewport().height():
        report.check("y lo que no cabe se alcanza desplazando",
                     barra.maximum() > 0, f"{barra.maximum()} px por desplazar")
    else:
        report.note("a su alto minimo cabe entero: no hay barra que medir")

    baja.batch.setFocus()
    esperar(0.2)
    antes = baja.requester.currentIndex()
    rueda(baja.requester)
    esperar(0.1)
    report.check("la rueda sobre un combo sin foco no cambia su valor",
                 baja.requester.currentIndex() == antes,
                 f"indice {antes} -> {baja.requester.currentIndex()}")

    # La Work Order no lleva fecha; Torsion y Quasi si.
    fecha = getattr(baja, "test_date", None)
    if fecha is not None:
        dia = fecha.date()
        rueda(fecha)
        esperar(0.1)
        report.check("la rueda sobre una fecha sin foco tampoco la cambia",
                     fecha.date() == dia,
                     f"{dia.toString('dd/MM/yyyy')} -> "
                     f"{fecha.date().toString('dd/MM/yyyy')}")
    baja.close()
    esperar(0.1)


# ======================================================================
report.section("Las listas desplegables tienen tope")

dialogo = nuevo("Fatiga")
dialogo.show()
esperar(0.4)

clientes = dialogo.customer
opcion = QStyleOptionComboBox()
clientes.initStyleOption(opcion)
report.check("la lista se abre debajo del campo, no centrada sobre el",
             clientes.style().styleHint(QStyle.StyleHint.SH_ComboBox_Popup,
                                        opcion, clientes) == 0)

clientes.showPopup()
esperar(0.4)
vista = clientes.view()
fila = vista.sizeHintForRow(0)
visibles = vista.viewport().height() / max(1, fila)
report.check(f"la lista abierta no pasa de {MAX_VISIBLE_ITEMS} filas",
             visibles <= MAX_VISIBLE_ITEMS + 0.5,
             f"{clientes.count()} clientes, lista de "
             f"{vista.window().height()} px, {visibles:.1f} filas a la vista "
             f"(antes 516 px)")
if clientes.count() > MAX_VISIBLE_ITEMS:
    report.check("y el resto se alcanza con su barra",
                 vista.verticalScrollBar().isVisible())
report.check("las filas no quedan apretadas", fila >= 26, f"{fila} px")
clientes.hidePopup()
dialogo.close()
esperar(0.1)

raise SystemExit(report.finish())
