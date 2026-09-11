"""Suspender una pieza, y lo que se exige para cerrar la prueba.

Tres cosas que van juntas:

1. Mientras la prueba corre, el Test Rig se puede dejar en blanco -- una pieza
   suspendida sale del banco y vuelve despues.
2. Las piezas por encima de la cantidad declarada se apagan; solo se captura en
   las que la prueba dice tener.
3. Al finalizar se exige todo lo declarado, y nada de lo que sobra.

Y que el historial lo cuente de forma legible, que es lo que hace util un
registro de auditoria.
"""

from harness import Report, make_context, offscreen, qt_app, settle

offscreen()

from datetime import date

from app.models import (
    EMPTY_RIG,
    FINISHED,
    ONGOING,
    SAMPLE_SLOTS,
    SUSPENDED_RESULT,
    FatigueSample,
    FatigueTest,
    RotarySample,
    RotaryTest,
)
from app.services import validation
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.dialogs.history_dialog import field_label, value_label
from app.ui.dialogs.rotary_dialog import RotaryDialog
from app.ui.widgets.common import combo_value

AUTHOR = ("verificador", "PC-PRUEBA")
report = Report("Suspension de piezas y cierre completo")

app = qt_app()
context = make_context()


def new_dialog(test=None, read_only=False):
    return FatigueDialog(context.fatigue, context.catalogs, context.audit,
                         test=test, read_only=read_only)


def _rejects(dialog, damage) -> bool:
    """Estropea un dato de lo recogido y comprueba que el cierre lo frena."""
    test = dialog._collect()
    damage(test)
    try:
        general, samples = dialog._completeness_fields(test)
        validation.validate_complete_for_finish(general, samples)
    except validation.ValidationError:
        return True
    return False


# ======================================================================
report.section("1. El Test Rig se puede volver a dejar en blanco")

dialog = new_dialog()
rig = dialog.rigs[0]
report.check("el combo abre vacio", combo_value(rig) == "", repr(combo_value(rig)))
report.check("la opcion de vaciar es la primera", rig.itemData(0) == "",
             rig.itemText(0))

bancos = context.catalogs.rig_names("fatigue")
rig.setCurrentIndex(rig.findText(bancos[0]))
report.check("se elige un banco", combo_value(rig) == bancos[0], combo_value(rig))

# Esto es lo que antes no se podia: un QComboBox cerrado no tiene forma de
# volver a "sin seleccion" una vez elegido algo.
rig.setCurrentIndex(0)
report.check("y se puede volver a vaciar desde la propia lista",
             combo_value(rig) == "", repr(combo_value(rig)))
report.check("el catalogo completo sigue disponible",
             [rig.itemText(i) for i in range(1, rig.count())] == bancos)

report.check("resultado y modo de falla tambien se vacian",
             combo_value(dialog.results[0]) == ""
             and combo_value(dialog.failure_modes[0]) == "")


def elegir(combo, texto) -> None:
    """Elige una opcion como lo hace el usuario, con su senal 'activated'."""
    indice = combo.findText(texto)
    combo.setCurrentIndex(indice)
    combo.activated.emit(indice)


# Marcar 'Susp' saca la pieza del banco sin que haya que borrarlo a mano. Es
# como se captura una suspension --fuera de banco y anotada 'Susp'-- y de eso
# depende que la tabla, el reporte y la ocupacion de rigs la reconozcan.
elegir(rig, bancos[0])
elegir(dialog.results[0], SUSPENDED_RESULT)
report.check("elegir 'Susp' vacia el Test Rig de esa pieza",
             combo_value(rig) == "", repr(combo_value(rig)))
report.check("y el resultado se queda puesto",
             combo_value(dialog.results[0]) == SUSPENDED_RESULT)

# Los demas resultados no tocan el banco: una pieza que fallo o que aguanto si
# corrio en algun sitio, y ahi es donde acabo.
elegir(dialog.rigs[1], bancos[0])
elegir(dialog.results[1], "Falla")
report.check("un resultado que no es 'Susp' deja el banco donde estaba",
             combo_value(dialog.rigs[1]) == bancos[0],
             combo_value(dialog.rigs[1]))
report.check("y no toca las piezas vecinas",
             combo_value(dialog.rigs[2]) == "")

# Un registro viejo puede traer banco y 'Susp' a la vez. Abrirlo no debe
# borrarle nada: por eso el vaciado escucha 'activated', que solo se dispara
# cuando elige el usuario, y no el cambio de indice, que tambien salta al
# cargar el formulario.
heredado = FatigueTest(
    test_batch="999862STF01", customer="AUDI", start_date=date(2026, 8, 1),
    qty_samples=1,
    samples=[FatigueSample(rig=bancos[0], result=SUSPENDED_RESULT, cycles=500)]
            + [FatigueSample() for _ in range(SAMPLE_SLOTS - 1)],
)
abierto = new_dialog(test=heredado)
report.check("abrir un registro con banco y 'Susp' no le borra el banco",
             combo_value(abierto.rigs[0]) == bancos[0],
             combo_value(abierto.rigs[0]))

# ======================================================================
report.section("2. Vaciar el banco se guarda y no confunde con capturado")

corriendo = FatigueTest(
    test_batch="999861STF01", customer="AUDI", start_date=date(2026, 8, 1),
    qty_samples=2, test_status=ONGOING,
    samples=[FatigueSample(rig=bancos[0], cycles=1000),
             FatigueSample(rig=bancos[1], cycles=2000)]
            + [FatigueSample() for _ in range(7)],
)
test_id = context.fatigue.create(corriendo, AUTHOR)

editar = new_dialog(test=context.fatigue.get(test_id))
report.check("al abrir trae el banco capturado",
             combo_value(editar.rigs[0]) == bancos[0])

editar.rigs[0].setCurrentIndex(0)                     # la pieza se suspende
recogido = editar._collect()
report.check("una pieza sin banco se recoge como vacia",
             recogido.samples[0].rig == EMPTY_RIG, recogido.samples[0].rig)
report.check("y conserva sus ciclos y su pieza vecina",
             recogido.samples[0].cycles == 1000
             and recogido.samples[1].rig == bancos[1])

context.fatigue.update(recogido, AUTHOR)
guardado = context.fatigue.get(test_id)
report.check("la base guarda la pieza sin banco",
             guardado.samples[0].rig == EMPTY_RIG, guardado.samples[0].rig)
report.check("los ciclos siguen ahi", guardado.samples[0].cycles == 1000)

# La caja no debe darse por capturada solo porque el combo muestre la etiqueta
# '(vacio)': es texto visible, pero no es un valor.
vacio = new_dialog()
report.check("una pieza recien abierta no cuenta como capturada",
             not vacio.sample_boxes[0].has_data())

# ======================================================================
report.section("3. El historial lo cuenta en cristiano")

entradas = context.audit.for_record("fatigue_tests", test_id)
rig_change = next((e for e in entradas if e.field == "test_rig1"), None)
report.check("queda registrado que la pieza salio del banco",
             rig_change is not None)
if rig_change:
    report.check("el campo se lee como pieza y dato",
                 field_label(rig_change.field) == "Pieza 1  -  Test Rig",
                 field_label(rig_change.field))
    report.check("el valor anterior es el banco",
                 value_label(rig_change.field, rig_change.old_value) == bancos[0],
                 value_label(rig_change.field, rig_change.old_value))
    report.check("y el nuevo se lee '(vacío)', no '--'",
                 value_label(rig_change.field, rig_change.new_value) == "(vacío)",
                 repr(value_label(rig_change.field, rig_change.new_value)))

report.check("los codigos de estatus tambien se traducen",
             value_label("test_status", "Ongoing") == "En curso"
             and value_label("test_status", "Finished") == "Finalizada")
report.check("y la bandera de Work Order",
             value_label("wo_status", "1") == "Si"
             and value_label("wo_status", "0") == "No")
report.check("las columnas de siempre conservan su nombre legible",
             field_label("qty_samples") == "No. de piezas"
             and field_label("cycles7") == "Pieza 7  -  Ciclos"
             and field_label("failure_mode3") == "Pieza 3  -  Modo de falla")
report.check("un campo desconocido no se pierde ni revienta",
             field_label("columna_rara") == "columna_rara")

# ======================================================================
report.section("4. Los campos se habilitan segun la cantidad de piezas")

form = new_dialog()
form.qty.setCurrentText("6")
settle(app)
activas = [i + 1 for i, b in enumerate(form.sample_boxes) if b.is_active()]
report.check("con 6 piezas se habilitan de la 1 a la 6",
             activas == [1, 2, 3, 4, 5, 6], str(activas))
report.check("los campos de la pieza 7 quedan deshabilitados",
             not form.rigs[6].isEnabled() and not form.cycles[6].isEnabled()
             and not form.failure_modes[6].isEnabled())
report.check("los de la 6 siguen activos",
             form.rigs[5].isEnabled() and form.cycles[5].isEnabled())

form.qty.setCurrentText("9")
settle(app)
report.check("subir la cantidad las vuelve a habilitar",
             all(b.is_active() for b in form.sample_boxes))

form.qty.setCurrentText("1")
settle(app)
report.check("bajarla las apaga otra vez",
             [i + 1 for i, b in enumerate(form.sample_boxes) if b.is_active()]
             == [1])

# Un registro antiguo con piezas por encima de lo declarado: se queda
# encendido, o no habria forma de corregirlo.
descuadrado = FatigueTest(
    test_batch="999862STF02", customer="AUDI", start_date=date(2026, 8, 2),
    qty_samples=2, test_status=ONGOING,
    samples=[FatigueSample(rig=bancos[0], cycles=10),
             FatigueSample(rig=bancos[0], cycles=20),
             FatigueSample(rig=bancos[0], cycles=30)]
            + [FatigueSample() for _ in range(6)],
)
raro_id = context.fatigue.create(descuadrado, AUTHOR)
raro = new_dialog(test=context.fatigue.get(raro_id))
settle(app)
report.check("la pieza de mas se queda editable para poder arreglarla",
             raro.sample_boxes[2].is_active() and raro.rigs[2].isEnabled())
report.check("y se marca como 'de mas'",
             "de mas" in raro.sample_boxes[2].title(),
             raro.sample_boxes[2].title())
report.check("el titulo del grupo lo dice",
             "por encima" in raro.samples_group.title(),
             raro.samples_group.title())
report.check("la pieza 4, vacia y fuera de rango, si se apaga",
             not raro.sample_boxes[3].is_active())

# Al borrar sus datos, la pieza de mas se apaga sola.
raro.rigs[2].setCurrentIndex(0)
raro.cycles[2].clear()
settle(app)
report.check("borrar los datos de la pieza de mas la apaga",
             not raro.sample_boxes[2].is_active()
             and "de mas" not in raro.sample_boxes[2].title(),
             raro.sample_boxes[2].title())

# ======================================================================
report.section("5. Al finalizar se exige lo declarado, y solo eso")

report.check("el modo de falla solo se pide a la pieza que fallo",
             validation.requires_failure_mode("Falla")
             and not validation.requires_failure_mode("S/Falla")
             and not validation.requires_failure_mode("Susp")
             and not validation.requires_failure_mode(""))

incompleta = FatigueTest(
    test_batch="999863STF03", customer="AUDI", start_date=date(2026, 8, 3),
    qty_samples=3, test_status=ONGOING,
    samples=[FatigueSample(rig=bancos[0], result="Falla", cycles=100,
                           failure_mode="Fisura"),
             FatigueSample(rig=bancos[1], cycles=200),      # sin resultado
             FatigueSample()]                                # vacia del todo
            + [FatigueSample() for _ in range(6)],
)
incompleta_id = context.fatigue.create(incompleta, AUTHOR)
cerrar = new_dialog(test=context.fatigue.get(incompleta_id))
general, muestras = cerrar._completeness_fields(cerrar._collect())

report.check("solo se revisan las piezas declaradas",
             [n for n, _ in muestras] == [1, 2, 3], str([n for n, _ in muestras]))
report.check("a la pieza que fallo se le pide el modo",
             "Modo de falla" in dict(muestras)[1])
report.check("a la que no tiene resultado, no",
             "Modo de falla" not in dict(muestras)[2])

fallo = None
try:
    validation.validate_complete_for_finish(general, muestras)
except validation.ValidationError as error:
    fallo = str(error)
report.check("no deja cerrar con piezas a medias", fallo is not None)
if fallo:
    print("      " + fallo.replace("\n", "\n      "))
    report.check("nombra la pieza 2 y lo que le falta",
                 "Pieza 2" in fallo and "Resultado" in fallo)
    report.check("nombra la pieza 3 completa",
                 "Pieza 3" in fallo and "Test Rig" in fallo and "Ciclos" in fallo)
    report.check("no se queja de las piezas 4 a 9",
                 not any(f"Pieza {n}" in fallo for n in range(4, 10)))
    report.check("la pieza 1, completa, no aparece", "Pieza 1" not in fallo)

# Completa: ya no protesta.
completa = context.fatigue.get(incompleta_id)
completa.samples[1] = FatigueSample(rig=bancos[1], result="S/Falla", cycles=200)
completa.samples[2] = FatigueSample(rig=bancos[0], result="Falla", cycles=300,
                                    failure_mode="Fractura")
listo = new_dialog(test=completa)
general, muestras = listo._completeness_fields(listo._collect())
try:
    validation.validate_complete_for_finish(general, muestras)
    report.check("con las 3 piezas llenas si deja cerrar", True)
except validation.ValidationError as error:
    report.check("con las 3 piezas llenas si deja cerrar", False, str(error))

report.check("una pieza sin banco tampoco pasa el cierre",
             _rejects(listo, lambda t: setattr(t.samples[0], "rig", EMPTY_RIG)))
report.check("ni una sin ciclos",
             _rejects(listo, lambda t: setattr(t.samples[0], "cycles", None)))
report.check("ni una que fallo sin modo de falla",
             _rejects(listo, lambda t: setattr(t.samples[0], "failure_mode", "")))
report.check("ni un cliente vacio",
             _rejects(listo, lambda t: setattr(t, "customer", "")))

# ======================================================================
report.section("6. Rotary lleva las mismas reglas")

rot_dialog = RotaryDialog(context.rotary, context.catalogs, context.audit)
report.check("el Rotary Rig se puede vaciar",
             rot_dialog.rig.itemData(0) == "" and combo_value(rot_dialog.rig) == "")
rot_dialog.qty.setCurrentText("4")
settle(app)
report.check("las piezas se habilitan por cantidad",
             [i + 1 for i, b in enumerate(rot_dialog.sample_boxes) if b.is_active()]
             == [1, 2, 3, 4])

rot = RotaryTest(
    test_batch="999864SRF04", customer="AUDI", start_date=date(2026, 8, 4),
    qty_samples=2, test_status=ONGOING,
    test_rig=context.catalogs.rig_names("rotary")[0],
    samples=[RotarySample(revs=10, status="Falla"), RotarySample()]
            + [RotarySample() for _ in range(7)],
)
rot_id = context.rotary.create(rot, AUTHOR)
rot_edit = RotaryDialog(context.rotary, context.catalogs, context.audit,
                        test=context.rotary.get(rot_id))
general, muestras = rot_edit._completeness_fields(rot_edit._collect())
rot_fallo = None
try:
    validation.validate_complete_for_finish(general, muestras)
except validation.ValidationError as error:
    rot_fallo = str(error)
report.check("Rotary tampoco cierra a medias", rot_fallo is not None)
if rot_fallo:
    report.check("le falta el modo a la pieza que fallo",
                 "Pieza 1" in rot_fallo and "Modo de falla" in rot_fallo,
                 rot_fallo.splitlines()[2] if len(rot_fallo.splitlines()) > 2
                 else rot_fallo)
    report.check("y la pieza 2 entera", "Pieza 2" in rot_fallo)

# ======================================================================
report.section("7. En consulta no se habilita nada")

finalizada = context.fatigue.get(incompleta_id)
finalizada.test_status = FINISHED
consulta = new_dialog(test=finalizada, read_only=True)
settle(app)
report.check("una prueba abierta en consulta queda toda apagada",
             not any(b.is_active() for b in consulta.sample_boxes))
report.check("ni los campos ni el guardar",
             not consulta.rigs[0].isEnabled()
             and not consulta.save_button.isVisible())

raise SystemExit(report.finish())
