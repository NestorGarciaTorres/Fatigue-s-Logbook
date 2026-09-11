"""Capturar con menos clics y sin adivinar que falta.

Tres ayudas, cada una con su comprobacion:

1. Guardar o finalizar con datos que faltan abria un cuadro con el primer
   error; se cerraba, se corregia y aparecia el siguiente. Ahora se marcan
   todos a la vez, cada uno sobre su campo, con un aviso bajo el titulo.
2. Anotar ciclos pedia abrir el registro completo y buscar la pieza. 'Capturar
   ciclos' ensenia solo los ciclos, y solo deja capturar las piezas que corren.
3. Al mover una pieza detenida por mantenimiento se tomaba como fecha el dia de
   guardar. Ahora se captura el dia en que de verdad paso al otro banco.
"""

from harness import Report, make_context, offscreen, qt_app

offscreen()

from copy import deepcopy
from datetime import date, timedelta

from PySide6.QtCore import QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QMessageBox

import app.ui.pages.fatigue_page as pagina_fatiga
from app.models import (
    EMPTY_RIG,
    FINISHED,
    ONGOING,
    SAMPLE_SLOTS,
    SUSPENDED_RESULT,
    TORSION,
    FatigueSample,
    FatigueTest,
    RigMaintenance,
    RotarySample,
    RotaryTest,
)
from app.services import maintenance
from app.ui import theme
from app.ui.dialogs import form_guard
from app.ui.dialogs.cycles_dialog import CyclesDialog
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.dialogs.rotary_dialog import RotaryDialog
from app.ui.dialogs.work_order_dialog import WorkOrderDialog
from app.ui.widgets.common import fit_dialog_to_screen, set_combo_value

YO = ("ana", "PC-LAB-1")
OTRO = ("luis", "PC-LAB-2")

report = Report("Ayudas de captura")
app = qt_app()
context = make_context()


def _sin_modales(*args, **_kwargs):
    """Un cuadro que no se esperaba falla en vez de dejar la prueba colgada.

    Es justo lo que esta suite comprueba: que validar ya no abre cuadros.
    """
    raise AssertionError(f"se abrio un cuadro modal: {args[1:3]}")


QMessageBox.warning = _sin_modales
QMessageBox.critical = _sin_modales
QMessageBox.information = _sin_modales
form_guard.confirm_discard = lambda _parent: True

bancos = context.catalogs.rig_names("fatigue")
_consecutivo = [0]


def lote(tipo: str) -> str:
    """Un Test Batch nuevo con una clave que el catalogo si acepta."""
    _consecutivo[0] += 1
    return f"{997000 + _consecutivo[0]}{context.catalogs.codes(tipo)[0]}01"


def fatiga(qty: int, samples: list[FatigueSample]) -> FatigueTest:
    prueba = FatigueTest(
        test_batch=lote("fatigue"), customer="AUDI",
        # Un mes atras: los dias detenida se recortan a la vida de la prueba,
        # y una prueba que empezara despues del mantenimiento no los veria.
        start_date=date.today() - timedelta(days=30),
        qty_samples=qty, test_status=ONGOING,
        samples=samples
        + [FatigueSample() for _ in range(SAMPLE_SLOTS - len(samples))],
    )
    return context.fatigue.get(context.fatigue.create(prueba, YO))


def rojo(widget) -> int:
    """Pixeles del rojo de 'revisar' en el campo: los del borde marcado."""
    imagen = widget.grab().toImage()
    objetivo = QColor(theme.DANGER).rgb()
    return sum(1 for x in range(imagen.width()) for y in range(imagen.height())
               if imagen.pixel(x, y) == objetivo)


# ======================================================================
report.section("1. Guardar marca todo lo que falta, sobre su campo")

nuevo = FatigueDialog(context.fatigue, context.catalogs, context.audit)
nuevo.show()
app.processEvents()
nuevo.grab()                       # el primer grab del proceso sale en blanco
limpio = rojo(nuevo.batch)

nuevo._save()
app.processEvents()
report.check("guardar sin datos no abre ningún cuadro ni guarda",
             nuevo.created_id is None and nuevo.isVisible())
report.check("marca a la vez los dos campos que faltan",
             nuevo.invalid_widgets() == [nuevo.customer, nuevo.batch],
             str([type(w).__name__ for w in nuevo.invalid_widgets()]))
marcado = rojo(nuevo.batch)
report.check("el campo marcado se dibuja con borde rojo",
             marcado > limpio + nuevo.batch.width(),
             f"{limpio} -> {marcado} px del rojo de revisar")
report.check("el aviso de arriba dice cuántos y cuáles",
             nuevo._banner.isVisible() and "2 campos" in nuevo.issue_text()
             and "Cliente" in nuevo.issue_text()
             and "Test Batch" in nuevo.issue_text(), nuevo.issue_text())
report.check("cada campo explica su problema al pasar el cursor",
             "Test Batch" in nuevo.batch.toolTip(), nuevo.batch.toolTip())
report.check("y el foco queda en el primero",
             nuevo.focusWidget() is nuevo.customer)

lote_guardado = lote("fatigue")
nuevo.batch.setText(lote_guardado)
report.check("corregir un campo le quita la marca en ese momento",
             nuevo.batch not in nuevo.invalid_widgets()
             and rojo(nuevo.batch) <= limpio,
             f"{rojo(nuevo.batch)} px rojos")
report.check("y el aviso se actualiza solo", "1 campo" in nuevo.issue_text(),
             nuevo.issue_text())
set_combo_value(nuevo.customer, "AUDI")
report.check("corregido todo, el aviso desaparece",
             not nuevo.invalid_widgets() and not nuevo._banner.isVisible())
nuevo._save()
report.check("y entonces guarda", nuevo.created_id is not None)

formato = FatigueDialog(context.fatigue, context.catalogs, context.audit)
formato.batch.setText("12345")
set_combo_value(formato.customer, "AUDI")
formato._save()
report.check("un Test Batch con formato inválido se marca con la explicación",
             formato.invalid_widgets() == [formato.batch]
             and "formato" in formato.batch.toolTip(), formato.batch.toolTip())

repetido = FatigueDialog(context.fatigue, context.catalogs, context.audit)
repetido.batch.setText(lote_guardado)
set_combo_value(repetido.customer, "AUDI")
repetido._save()
report.check("uno repetido también, diciendo que ya existe",
             repetido.invalid_widgets() == [repetido.batch]
             and "Ya existe" in repetido.batch.toolTip(),
             repetido.batch.toolTip())

banco = bancos[0]
incompleta = fatiga(2, [FatigueSample(rig=banco, cycles=1000), FatigueSample()])
dialogo = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                        test=incompleta)
dialogo.show()
app.processEvents()
dialogo._finish()
marcados = dialogo.invalid_widgets()
report.check("finalizar marca cada dato que falta, en su pieza",
             marcados == [dialogo.results[0], dialogo.rigs[1],
                          dialogo.results[1], dialogo.cycles[1]],
             f"{len(marcados)} marcados")
report.check("no le pide modo de falla a una pieza que no falló",
             dialogo.failure_modes[0] not in marcados)
report.check("ni toca las piezas por encima de las declaradas",
             all(w not in marcados for w in (dialogo.rigs[2], dialogo.cycles[2])))
report.check("el aviso dice que es para finalizar",
             "finalizar" in dialogo.issue_text(), dialogo.issue_text())
report.check("y la prueba sigue en curso",
             context.fatigue.get(incompleta.id).test_status == ONGOING)

casi = fatiga(9, [FatigueSample(rig=banco, cycles=1000, result="S/Falla")
                  for _ in range(8)])
larga = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                      test=casi)
fit_dialog_to_screen(larga, larga.scroll, larga.body, available_height=680)
larga.show()
app.processEvents()
larga.scroll.verticalScrollBar().setValue(0)
larga._finish()
app.processEvents()
report.check("lleva la vista hasta el primer campo marcado aunque esté abajo",
             larga.invalid_widgets()[:1] == [larga.rigs[8]]
             and larga.scroll.verticalScrollBar().value() > 0,
             f"barra en {larga.scroll.verticalScrollBar().value()}")

vacia = fatiga(9, [])
muchos = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                       test=vacia)
muchos._finish()
report.check("con muchos faltantes el aviso resume en vez de crecer sin fin",
             len(muchos.invalid_widgets()) == 27
             and "y 21 más" in muchos.issue_text(),
             f"{len(muchos.invalid_widgets())} marcados")

for nombre, formulario in (
    ("Rotary", RotaryDialog(context.rotary, context.catalogs, context.audit)),
    ("Torsión", GenericDialog(context.torsion, context.catalogs,
                              context.audit, TORSION)),
):
    formulario._save()
    report.check(f"{nombre}: marca Cliente y Test Batch sin abrir cuadros",
                 formulario.invalid_widgets()
                 == [formulario.customer, formulario.batch],
                 f"{len(formulario.invalid_widgets())} marcados")

orden = WorkOrderDialog(context.work_orders, context.catalogs)
orden._save()
report.check("Work Order: marca también el solicitante",
             orden.invalid_widgets()
             == [orden.customer, orden.batch, orden.requester],
             f"{len(orden.invalid_widgets())} marcados")

rotary = context.rotary.get(context.rotary.create(
    RotaryTest(test_batch=lote("rotary"), customer="AUDI",
               start_date=date(2026, 9, 1), qty_samples=1, test_rig=EMPTY_RIG,
               samples=[RotarySample(revs=10)]
               + [RotarySample() for _ in range(SAMPLE_SLOTS - 1)]), YO))
rdialogo = RotaryDialog(context.rotary, context.catalogs, context.audit,
                        test=rotary)
rdialogo._finish()
report.check("Rotary: finalizar marca el banco y el estatus que faltan",
             rdialogo.invalid_widgets() == [rdialogo.rig, rdialogo.statuses[0]],
             f"{len(rdialogo.invalid_widgets())} marcados")


# ======================================================================
report.section("2. Capturar ciclos sin abrir el registro")

abiertos = maintenance.open_by_rig(context.maintenance.open_records())
libres = [n for n in bancos if (n, "fatigue") not in abiertos]
CORRE, TERMINO, PARADO, PARADO_2, DESTINO, QUIETO = libres[:6]


def rig_id(nombre: str) -> int:
    return next(r for r in context.catalogs.rigs("fatigue") if r.name == nombre).id


def parar(nombre: str, test_id: int, inicio: date) -> int:
    return context.maintenance.start(
        RigMaintenance(rig_name=nombre, test_type="fatigue",
                       rig_id=rig_id(nombre), start_date=inicio,
                       created_by="verificador"),
        [m for m in maintenance.affected_samples(
            nombre, "fatigue", context.fatigue.list(ONGOING))
         if m.record_id == test_id],
        YO,
    )


def detenidas_de(test_id: int) -> dict:
    return {slot: registro for (tid, slot), registro
            in maintenance.paused_slots(context.maintenance.open_records()).items()
            if tid == test_id}


mezcla = fatiga(5, [
    FatigueSample(rig=CORRE, cycles=1000),
    FatigueSample(rig=TERMINO, cycles=2000, result="Falla",
                  failure_mode="Fisura"),
    FatigueSample(rig=EMPTY_RIG, cycles=3000, result=SUSPENDED_RESULT),
    FatigueSample(rig=PARADO, cycles=4000),
    FatigueSample(rig=CORRE),
])
parar(PARADO, mezcla.id, date.today() - timedelta(days=2))
mezcla = context.fatigue.get(mezcla.id)

ciclos = CyclesDialog(context.fatigue, mezcla, paused=detenidas_de(mezcla.id))
report.check("lista las piezas declaradas",
             sorted(ciclos.fields) == [1, 2, 3, 4, 5], str(sorted(ciclos.fields)))
report.check("solo deja capturar las que están corriendo en un banco",
             ciclos.editable_pieces() == [1, 5], str(ciclos.editable_pieces()))
report.check("y dice por qué las demás no",
             "terminada" in ciclos.states[2]
             and "suspendida" in ciclos.states[3]
             and "mantenimiento" in ciclos.states[4], str(ciclos.states))
report.check("trae la lectura anterior lista para sobrescribir",
             ciclos.fields[1].text() == "1000", ciclos.fields[1].text())

ciclos.fields[1].setText("900")
report.check("una lectura menor que la anterior se avisa",
             "menor" in ciclos.notes[1].text(), ciclos.notes[1].text())
ciclos.fields[1].setText("1500")
report.check("y el aviso se quita al corregirla", ciclos.notes[1].text() == "")
ciclos.fields[5].setText("250")

suya = deepcopy(mezcla)
suya.comments = "leída por la tarde"
context.fatigue.update(suya, OTRO)          # otro equipo, con el cuadro abierto
ciclos._save()
guardada = context.fatigue.get(mezcla.id)
report.check("guarda los ciclos capturados",
             guardada.samples[0].cycles == 1500
             and guardada.samples[4].cycles == 250,
             f"{guardada.samples[0].cycles}, {guardada.samples[4].cycles}")
report.check("sin tocar las demás piezas",
             [s.cycles for s in guardada.samples[1:4]] == [2000, 3000, 4000],
             str([s.cycles for s in guardada.samples[1:4]]))
report.check("ni lo que otro equipo guardó mientras tanto",
             guardada.comments == "leída por la tarde", guardada.comments)
report.check("y cierra el cuadro",
             ciclos.result() == QDialog.DialogCode.Accepted
             and ciclos.changed == [1, 5], str(ciclos.changed))

vacio = CyclesDialog(context.fatigue, guardada,
                     paused=detenidas_de(guardada.id))
vacio.fields[1].setText("")
vacio._save()
report.check("un campo vacío conserva la lectura anterior",
             context.fatigue.get(guardada.id).samples[0].cycles == 1500
             and vacio.changed == [])

terminada = fatiga(1, [FatigueSample(rig=CORRE, cycles=10, result="S/Falla")])
# En una variable: un cuadro sin padre ni referencia lo destruye PySide en la
# misma linea, y leer su boton despues falla con 'already deleted'.
sin_piezas = CyclesDialog(context.fatigue, terminada)
report.check("si ninguna pieza corre, no ofrece guardar",
             not sin_piezas.save_button.isEnabled())

en_curso = pagina_fatiga.FatigueTab(context, ONGOING)
en_curso.refresh()
report.check("la bitácora en curso ofrece 'Capturar ciclos'",
             en_curso.cycles_button.isVisibleTo(en_curso))
en_curso.table.clearSelection()
report.check("apagado mientras no hay fila seleccionada",
             not en_curso.cycles_button.isEnabled())
fila = next(i for i, r in enumerate(en_curso.table.visible_records())
            if r.id == mezcla.id)
en_curso.table.selectRow(fila)
report.check("se enciende al seleccionar una prueba",
             en_curso.cycles_button.isEnabled())
report.check("y está también en el menú del botón derecho",
             "Capturar ciclos" in en_curso.table.menu_action_texts(),
             str(en_curso.table.menu_action_texts()))


class CuadroEspia:
    """Sustituye a la captura: anota con que se abrio, sin abrir nada modal."""

    abiertos: list = []

    def __init__(self, repository, record, paused=None, parent=None):
        CuadroEspia.abiertos.append((record, paused))

    def exec(self):
        return 0


original = pagina_fatiga.CyclesDialog
pagina_fatiga.CyclesDialog = CuadroEspia
try:
    en_curso.cycles_button.click()
finally:
    pagina_fatiga.CyclesDialog = original
report.check("el botón la abre con la prueba seleccionada y sus piezas detenidas",
             len(CuadroEspia.abiertos) == 1
             and CuadroEspia.abiertos[0][0].id == mezcla.id
             and set(CuadroEspia.abiertos[0][1]) == {4},
             str([(r.id, sorted(p)) for r, p in CuadroEspia.abiertos]))

finalizadas = pagina_fatiga.FatigueTab(context, FINISHED)
finalizadas.refresh()
report.check("en finalizadas no se ofrece: esas pruebas ya no avanzan",
             not finalizadas.cycles_button.isVisibleTo(finalizadas)
             and "Capturar ciclos" not in finalizadas.table.menu_action_texts())


# ======================================================================
report.section("3. El día real en que se movió una pieza detenida")

inicio = date.today() - timedelta(days=5)
movible = fatiga(1, [FatigueSample(rig=PARADO_2, cycles=100)])
paro = parar(PARADO_2, movible.id, inicio)
movible = context.fatigue.get(movible.id)

form = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                     test=movible, paused=detenidas_de(movible.id))
fecha = form.moved_dates.get(1)
report.check("la pieza detenida trae 'Movida el'", fecha is not None)
report.check("oculta mientras la pieza no tiene otro banco",
             not form.sample_boxes[0].is_row_visible(fecha))
set_combo_value(form.rigs[0], DESTINO)
report.check("aparece al asignarle otro banco",
             form.sample_boxes[0].is_row_visible(fecha))
report.check("no admite fechas antes del inicio del mantenimiento",
             fecha.minimumDate().toPython() == inicio,
             str(fecha.minimumDate().toPython()))
report.check("ni fechas futuras",
             fecha.maximumDate().toPython() == date.today(),
             str(fecha.maximumDate().toPython()))

movida = date.today() - timedelta(days=2)
fecha.setDate(QDate(movida))
form._save()
apunte = next(m for m in context.maintenance.get(paro).samples
              if m.record_id == movible.id)
report.check("se guarda el día capturado, no el de guardar",
             apunte.released_date == movida, str(apunte.released_date))
dias = maintenance.stopped_days(context.fatigue.get(movible.id),
                                context.maintenance.list())
report.check("y la prueba cuenta detenida solo hasta ese día",
             dias == (movida - inicio).days,
             f"{dias} días (hasta hoy serían {(date.today() - inicio).days})")

quieta = fatiga(1, [FatigueSample(rig=QUIETO, cycles=100)])
paro_quieta = parar(QUIETO, quieta.id, inicio)
quieta = context.fatigue.get(quieta.id)
espera = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                       test=quieta, paused=detenidas_de(quieta.id))
espera.comments.setText("sigue esperando su banco")
espera._save()
apunte_quieta = next(m for m in context.maintenance.get(paro_quieta).samples
                     if m.record_id == quieta.id)
report.check("sin otro banco, guardar no la da por movida",
             apunte_quieta.released_date is None and espera.moved_on() == {},
             str(apunte_quieta.released_date))

raise SystemExit(report.finish())
