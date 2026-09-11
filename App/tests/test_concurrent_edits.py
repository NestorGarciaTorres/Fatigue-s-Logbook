"""Que ningun dato se pierda sin que nadie lo note.

Tres agujeros, cada uno con su comprobacion:

1. Cambiar de base desde Ajustes dejaba Torsion y Quasi leyendo y guardando en
   la base anterior: guardaban su repositorio al crearse.
2. Dos equipos editando el mismo registro: guardar escribia el registro entero
   y el ultimo en guardar pisaba al otro sin aviso. Ahora lo que cambio solo
   uno se combina, y se pregunta cuando los dos cambiaron el mismo campo.
3. Cancelar o cerrar un formulario con cambios los tiraba sin preguntar.

Los cuadros de pregunta se sustituyen por respuestas preparadas: un modal
abierto en una prueba la deja colgada.
"""

from harness import Report, database_copy, make_context, offscreen, qt_app

offscreen()

import tempfile
from copy import deepcopy
from datetime import date
from pathlib import Path

from PySide6.QtWidgets import QDialog, QMessageBox

import app.config as config_module
from app.db.connection import Database
from app.db.repositories import (
    KEEP_MINE,
    KEEP_THEIRS,
    EditConflict,
    RecordDeleted,
)
from app.models import (
    EMPTY_RIG,
    ONGOING,
    QUASI,
    SAMPLE_SLOTS,
    TORSION,
    WO_STARTED,
    FatigueSample,
    FatigueTest,
    GenericTest,
    RotarySample,
    RotaryTest,
    WorkOrder,
)
from app.ui.dialogs import form_guard
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.dialogs.rotary_dialog import RotaryDialog
from app.ui.dialogs.work_order_dialog import WorkOrderDialog
from app.ui.main_window import MainWindow

YO = ("ana", "PC-LAB-1")
OTRO = ("luis", "PC-LAB-2")

report = Report("Ningún dato se pierde sin aviso")
app = qt_app()
context = make_context()


def _sin_modales(*args, **_kwargs):
    """Cualquier aviso que no se esperaba falla en vez de colgar la prueba."""
    raise AssertionError(f"se abrio un cuadro modal inesperado: {args[1:3]}")


QMessageBox.warning = _sin_modales
QMessageBox.critical = _sin_modales
QMessageBox.information = _sin_modales


class Respuestas:
    """Contesta por el usuario y anota que se le pregunto."""

    def __init__(self):
        self.conflictos: list[tuple[EditConflict, list[str]]] = []
        self.eleccion = None
        self.descartes = 0
        self.descartar = True
        self.borrados: list[RecordDeleted] = []

    def conflicto(self, _parent, conflict, audit):
        self.conflictos.append(
            (conflict, form_guard.describe_conflict(conflict, audit))
        )
        return self.eleccion

    def descarte(self, _parent):
        self.descartes += 1
        return self.descartar

    def borrado(self, _parent, error):
        self.borrados.append(error)


respuestas = Respuestas()
form_guard.ask_conflict = respuestas.conflicto
form_guard.confirm_discard = respuestas.descarte
form_guard.warn_deleted = respuestas.borrado

_consecutivo = [0]


def lote(tipo: str) -> str:
    """Un Test Batch nuevo con una clave que el catalogo si acepta.

    Con una clave inventada, guardar desde el formulario abre el aviso de
    'Datos incompletos' y la prueba se cuelga.
    """
    _consecutivo[0] += 1
    return f"{998000 + _consecutivo[0]}{context.catalogs.codes(tipo)[0]}01"


def fatiga_nueva() -> FatigueTest:
    prueba = FatigueTest(
        test_batch=lote("fatigue"), customer="AUDI",
        start_date=date(2026, 9, 1), qty_samples=2, test_status=ONGOING,
        samples=[FatigueSample(rig=EMPTY_RIG, cycles=100),
                 FatigueSample(rig=EMPTY_RIG, cycles=200)]
                + [FatigueSample() for _ in range(SAMPLE_SLOTS - 2)],
    )
    return context.fatigue.get(context.fatigue.create(prueba, YO))


def rotary_nueva() -> RotaryTest:
    prueba = RotaryTest(
        test_batch=lote("rotary"), customer="AUDI",
        start_date=date(2026, 9, 1), qty_samples=1, test_rig=EMPTY_RIG,
        samples=[RotarySample(revs=10, status="Falla")]
                + [RotarySample() for _ in range(SAMPLE_SLOTS - 1)],
    )
    return context.rotary.get(context.rotary.create(prueba, YO))


def torsion_nueva() -> GenericTest:
    prueba = GenericTest(test_batch=lote("torsion"), customer="AUDI",
                         test_date=date(2026, 9, 1), qty_samples=1)
    return context.torsion.get(context.torsion.create(prueba, YO))


def orden_nueva() -> WorkOrder:
    orden = WorkOrder(test_type="fatigue", test_batch=lote("fatigue"),
                      customer="AUDI", qty_samples=1, requester="Ana")
    return context.work_orders.get(context.work_orders.create(orden, YO))


# ======================================================================
report.section("1. Cambiar de base no deja pantallas en la anterior")

# reload_database guarda la ruta nueva en settings.json. Contra el de verdad,
# la prueba dejaria la app apuntando a una copia temporal: se redirige.
ajustes_reales = config_module.SETTINGS_FILE


def leer_ajustes():
    return (ajustes_reales.read_text(encoding="utf-8")
            if ajustes_reales.exists() else None)


antes_ajustes = leer_ajustes()
config_module.SETTINGS_FILE = (
    Path(tempfile.mkdtemp(prefix="bitacora_ajustes_")) / "settings.json"
)
try:
    window = MainWindow(context)
    otra_base = database_copy()
    # Un registro que solo existe en la base nueva: si Torsion lo ve, esta
    # leyendo de ella.
    marca = make_context(otra_base).torsion
    solo_nueva = marca.create(
        GenericTest(test_batch=lote("torsion"), customer="AUDI",
                    test_date=date(2026, 9, 10), qty_samples=1), YO)

    context.reload_database(str(otra_base))
    window.show_page("torsion")
    torsion = window.pages["torsion"]

    report.check("Torsión lee de la base nueva",
                 any(r.id == solo_nueva for r in torsion._records),
                 f"{len(torsion._records)} registros")
    report.check("y guarda en ella: su repositorio es el del contexto",
                 torsion.repository is context.torsion)
    report.check("Quasi también",
                 window.pages["quasi"].repository is context.quasi)

    # Barrido de todas las pantallas: ninguna guarda un repositorio o una base
    # que no sea la actual. Asi, la proxima pantalla que caiga en lo mismo
    # tambien sale aqui.
    viejas = []
    for clave, pagina in window.pages.items():
        for nombre, valor in vars(pagina).items():
            base = valor if isinstance(valor, Database) else getattr(
                valor, "db", None)
            if isinstance(base, Database) and base.path != context.database.path:
                viejas.append(f"{clave}.{nombre}")
    report.check("ninguna pantalla se queda con la base anterior",
                 not viejas, str(viejas))
finally:
    config_module.SETTINGS_FILE = ajustes_reales

report.check("y el settings.json real no se tocó",
             leer_ajustes() == antes_ajustes)


# ======================================================================
report.section("2. Dos equipos, campos distintos: se combinan solos")

abierta = fatiga_nueva()                    # lo que cargo mi formulario
suyo = deepcopy(abierta)
suyo.samples[0].cycles = 150
context.fatigue.update(suyo, OTRO)          # el otro equipo guarda primero

mio = deepcopy(abierta)
mio.samples[1].result = "S/Falla"
context.fatigue.update(mio, YO, base=abierta)

final = context.fatigue.get(abierta.id)
report.check("mi cambio se guarda", final.samples[1].result == "S/Falla",
             final.samples[1].result)
report.check("y el del otro equipo no se pisa",
             final.samples[0].cycles == 150,
             f"ciclos pieza 1: {final.samples[0].cycles} (antes volvia a 100)")
mias = [e.field for e in context.audit.for_record("fatigue_tests", abierta.id)
        if e.changed_by == "ana" and e.action == "updated"]
report.check("el historial me atribuye solo lo que cambié",
             mias == ["result2"], str(mias))

igual = fatiga_nueva()
suyo = deepcopy(igual)
suyo.samples[0].cycles = 300
context.fatigue.update(suyo, OTRO)
mio = deepcopy(igual)
mio.samples[0].cycles = 300
context.fatigue.update(mio, YO, base=igual)
report.check("si los dos pusieron lo mismo, no hay nada que preguntar",
             context.fatigue.get(igual.id).samples[0].cycles == 300)

for nombre, crear, repositorio, suyo_cambia, mio_cambia, comprobar in (
    ("Rotary", rotary_nueva, lambda: context.rotary,
     lambda r: setattr(r.samples[0], "revs", 20),
     lambda r: setattr(r, "comments", "revisada"),
     lambda f: f.samples[0].revs == 20 and f.comments == "revisada"),
    ("Torsión", torsion_nueva, lambda: context.torsion,
     lambda r: setattr(r, "qty_samples", 3),
     lambda r: setattr(r, "comments", "revisada"),
     lambda f: f.qty_samples == 3 and f.comments == "revisada"),
):
    abierta = crear()
    suyo = deepcopy(abierta)
    suyo_cambia(suyo)
    repositorio().update(suyo, OTRO)
    mio = deepcopy(abierta)
    mio_cambia(mio)
    repositorio().update(mio, YO, base=abierta)
    report.check(f"{nombre}: también se combina",
                 comprobar(repositorio().get(abierta.id)))

# La Work Order es donde mas duele: otro equipo la comienza mientras yo le
# corrijo los comentarios, y guardar la orden entera la devolvia a Pendiente.
orden = orden_nueva()
prueba_id = context.fatigue.create(
    FatigueTest(test_batch=orden.test_batch, customer="AUDI",
                start_date=date(2026, 9, 1), qty_samples=1,
                samples=[FatigueSample() for _ in range(SAMPLE_SLOTS)]), OTRO)
context.work_orders.mark_started(orden.id, prueba_id, OTRO)
mia = deepcopy(orden)
mia.comments = "urgente"
context.work_orders.update(mia, YO, base=orden)
guardada = context.work_orders.get(orden.id)
report.check("Work Order: corregirla no deshace que otro equipo la comenzó",
             guardada.status == WO_STARTED
             and guardada.started_test_id == prueba_id
             and guardada.comments == "urgente",
             f"{guardada.status}, registro {guardada.started_test_id}, "
             f"{guardada.comments!r}")


# ======================================================================
report.section("3. Dos equipos, el mismo campo: se pregunta")

abierta = fatiga_nueva()
suyo = deepcopy(abierta)
suyo.samples[0].cycles = 180
suyo.comments = "revisada"
context.fatigue.update(suyo, OTRO)

mio = deepcopy(abierta)
mio.samples[0].cycles = 150
mio.samples[1].cycles = 250
try:
    context.fatigue.update(mio, YO, base=abierta)
    conflicto = None
except EditConflict as error:
    conflicto = error

report.check("guardar avisa del campo que cambiaron los dos",
             conflicto is not None and list(conflicto.fields) == ["cycles1"],
             str(conflicto.fields if conflicto else None))
report.check("con lo que había, lo mío y lo guardado",
             conflicto is not None
             and conflicto.fields["cycles1"] == (100, 150, 180),
             str(conflicto.fields.get("cycles1") if conflicto else None))
tras = context.fatigue.get(abierta.id)
report.check("y no guarda nada mientras no se decida",
             tras.samples[0].cycles == 180 and tras.samples[1].cycles == 200,
             f"{tras.samples[0].cycles}, {tras.samples[1].cycles}")

context.fatigue.update(mio, YO, base=abierta, on_conflict=KEEP_MINE)
con_mios = context.fatigue.get(abierta.id)
report.check("'guardar los míos' deja mi valor en el campo disputado",
             con_mios.samples[0].cycles == 150, str(con_mios.samples[0].cycles))
report.check("y respeta lo demás que guardó el otro equipo",
             con_mios.comments == "revisada"
             and con_mios.samples[1].cycles == 250,
             f"{con_mios.comments!r}, {con_mios.samples[1].cycles}")

abierta = fatiga_nueva()
suyo = deepcopy(abierta)
suyo.samples[0].cycles = 180
context.fatigue.update(suyo, OTRO)
mio = deepcopy(abierta)
mio.samples[0].cycles = 150
mio.samples[1].cycles = 250
context.fatigue.update(mio, YO, base=abierta, on_conflict=KEEP_THEIRS)
con_suyos = context.fatigue.get(abierta.id)
report.check("'dejar los guardados' conserva el valor del otro equipo",
             con_suyos.samples[0].cycles == 180,
             str(con_suyos.samples[0].cycles))
report.check("y guarda el resto de mis cambios",
             con_suyos.samples[1].cycles == 250,
             str(con_suyos.samples[1].cycles))

borrada = torsion_nueva()
context.torsion.delete(borrada.id, OTRO)
mia = deepcopy(borrada)
mia.comments = "x"
try:
    context.torsion.update(mia, YO, base=borrada)
    eliminado = False
except RecordDeleted:
    eliminado = True
report.check("si otro equipo lo eliminó, avisa en vez de guardar en el vacío",
             eliminado)

# Sin punto de partida se guarda tal cual, como siempre: lo usan los scripts y
# las pruebas que escriben directo.
directa = fatiga_nueva()
suyo = deepcopy(directa)
suyo.samples[0].cycles = 180
context.fatigue.update(suyo, OTRO)
context.fatigue.update(directa, YO)
report.check("sin 'base', update escribe el registro entero como antes",
             context.fatigue.get(directa.id).samples[0].cycles == 100)


# ======================================================================
report.section("4. El formulario combina al guardar")

abierta = fatiga_nueva()
dialogo = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                        test=abierta)
suyo = deepcopy(abierta)
suyo.samples[0].cycles = 150
context.fatigue.update(suyo, OTRO)
dialogo.cycles[1].setText("260")
dialogo._save()
final = context.fatigue.get(abierta.id)
report.check("guardar desde el formulario no pisa lo del otro equipo",
             final.samples[0].cycles == 150 and final.samples[1].cycles == 260,
             f"{final.samples[0].cycles}, {final.samples[1].cycles}")
report.check("sin preguntar nada: no tocaron el mismo campo",
             not respuestas.conflictos)
report.check("y el formulario se cierra como siempre",
             dialogo.result() == QDialog.DialogCode.Accepted)

abierta = fatiga_nueva()
dialogo = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                        test=abierta)
suyo = deepcopy(abierta)
suyo.samples[0].cycles = 180
context.fatigue.update(suyo, OTRO)
dialogo.cycles[0].setText("150")

respuestas.eleccion = None
dialogo._save()
report.check("si los dos cambiaron el mismo campo, pregunta",
             len(respuestas.conflictos) == 1, str(len(respuestas.conflictos)))
lineas = respuestas.conflictos[0][1] if respuestas.conflictos else []
report.check("y dice qué campo, los dos valores y quién lo guardó",
             len(lineas) == 1 and "Pieza 1" in lineas[0]
             and "Ciclos" in lineas[0] and "150" in lineas[0]
             and "180" in lineas[0] and "luis" in lineas[0], str(lineas))
report.check("'volver al formulario' no guarda nada",
             context.fatigue.get(abierta.id).samples[0].cycles == 180)
report.check("y deja el formulario abierto",
             dialogo.result() != QDialog.DialogCode.Accepted)

respuestas.eleccion = KEEP_MINE
dialogo._save()
report.check("'guardar los míos' guarda y cierra",
             context.fatigue.get(abierta.id).samples[0].cycles == 150
             and dialogo.result() == QDialog.DialogCode.Accepted)

orden = orden_nueva()
dialogo = WorkOrderDialog(context.work_orders, context.catalogs, order=orden)
prueba_id = context.fatigue.create(
    FatigueTest(test_batch=orden.test_batch, customer="AUDI",
                start_date=date(2026, 9, 1), qty_samples=1,
                samples=[FatigueSample() for _ in range(SAMPLE_SLOTS)]), OTRO)
context.work_orders.mark_started(orden.id, prueba_id, OTRO)
dialogo.comments.setText("urgente")
dialogo._save()
guardada = context.work_orders.get(orden.id)
report.check("Work Order desde su formulario: sigue comenzada",
             guardada.status == WO_STARTED and guardada.comments == "urgente",
             f"{guardada.status}, {guardada.comments!r}")

borrada = torsion_nueva()
dialogo = GenericDialog(context.torsion, context.catalogs, context.audit,
                        TORSION, test=borrada)
context.torsion.delete(borrada.id, OTRO)
dialogo.comments.setText("x")
dialogo._save()
report.check("registro eliminado en otro equipo: lo avisa",
             len(respuestas.borrados) == 1)
report.check("y el formulario sigue abierto con lo capturado",
             dialogo.result() != QDialog.DialogCode.Accepted
             and dialogo.comments.text() == "x")


# ======================================================================
report.section("5. Cancelar pregunta solo si hay cambios")

FORMULARIOS = (
    ("Fatiga",
     lambda: FatigueDialog(context.fatigue, context.catalogs, context.audit,
                           test=fatiga_nueva()),
     lambda d: d.cycles[0].setText("999")),
    ("Rotary",
     lambda: RotaryDialog(context.rotary, context.catalogs, context.audit,
                          test=rotary_nueva()),
     lambda d: d.revs[0].setText("999")),
    ("Torsión",
     lambda: GenericDialog(context.torsion, context.catalogs, context.audit,
                           TORSION, test=torsion_nueva()),
     lambda d: d.comments.setText("otra cosa")),
    ("Work Order",
     lambda: WorkOrderDialog(context.work_orders, context.catalogs,
                             order=orden_nueva()),
     lambda d: d.comments.setText("otra cosa")),
)

for nombre, abrir, cambiar in FORMULARIOS:
    respuestas.descartes = 0
    respuestas.descartar = True
    limpio = abrir()
    limpio.show()
    app.processEvents()
    limpio.reject()
    report.check(f"{nombre}: recién abierto, cancelar cierra sin preguntar",
                 respuestas.descartes == 0 and not limpio.isVisible(),
                 f"{respuestas.descartes} preguntas")

    sucio = abrir()
    sucio.show()
    app.processEvents()
    cambiar(sucio)
    respuestas.descartar = False
    sucio.reject()
    report.check(f"{nombre}: con cambios, pregunta antes de cerrar",
                 respuestas.descartes == 1, f"{respuestas.descartes} preguntas")
    report.check(f"{nombre}: 'seguir editando' deja lo capturado a la vista",
                 sucio.isVisible() and sucio.has_unsaved_changes())

    respuestas.descartar = True
    sucio.close()
    app.processEvents()
    report.check(f"{nombre}: la X de la ventana pregunta igual y descarta",
                 respuestas.descartes == 2 and not sucio.isVisible(),
                 f"{respuestas.descartes} preguntas")

respuestas.descartes = 0
vuelta = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                       test=fatiga_nueva())
original = vuelta.cycles[0].text()
vuelta.cycles[0].setText("999")
vuelta.cycles[0].setText(original)
report.check("cambiar un campo y dejarlo como estaba no cuenta como cambio",
             not vuelta.has_unsaved_changes())

orden = orden_nueva()
precargado = GenericDialog(context.quasi, context.catalogs, context.audit,
                           QUASI, work_order=orden)
precargado.show()
app.processEvents()
precargado.reject()
report.check("lo que trae la Work Order al comenzar no cuenta como cambio",
             respuestas.descartes == 0 and not precargado.isVisible())

consulta = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                         test=fatiga_nueva(), read_only=True)
consulta.show()
app.processEvents()
consulta.cycles[0].setText("1")
consulta.reject()
report.check("un registro abierto solo para consulta no pregunta",
             respuestas.descartes == 0 and not consulta.isVisible())

raise SystemExit(report.finish())
