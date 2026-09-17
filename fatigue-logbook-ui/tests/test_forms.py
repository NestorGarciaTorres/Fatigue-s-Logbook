"""Los formularios de captura, medidos en una pantalla de portatil.

Lo que se comprueba no es que se vean bien, sino que **se pueda guardar**:

1. El boton de guardar queda dentro de la ventana en una pantalla de 768 px.
   Es el fallo concreto que llevo a partir el formulario en cuerpo desplazable
   y pie fijo -- Fatiga pedia 967 px de alto y el boton caia debajo del borde.
2. El cuerpo se desplaza y el boton **no** esta dentro de esa zona.
3. La ventana no pide mas ancho del que tiene un portatil.
4. Los avisos de lo que falta marcan el campo donde se captura cada dato, no
   solo lo enumeran.
5. Cancelar un formulario recien abierto no pregunta nada: lo que trae el
   registro no es un cambio del usuario.

Corre con la plataforma nativa: hay que medir widgets de verdad.
"""

from __future__ import annotations

import harness  # noqa: F401  (deja sys.path listo)
from harness import Report

from app.models import ONGOING
from app.services import maintenance
from theme.tokens import LIGHT

# La pantalla que se simula y el tope de ancho, los mismos que el proyecto
# original: un portatil de 1366 x 768.
LAPTOP_HEIGHT = 768
LAPTOP_WIDTH = 1326


def _sample_visibility(dialog) -> tuple[int, int, int]:
    """(enteras, asomando, fuera) de las tarjetas de pieza, sin desplazar."""
    vp = dialog.scroll.viewport()
    enteras = asomando = 0
    for caja in dialog.sample_boxes:
        arriba = caja.mapTo(vp, caja.rect().topLeft()).y()
        abajo = caja.mapTo(vp, caja.rect().bottomLeft()).y()
        if arriba >= -1 and abajo <= vp.height() + 1:
            enteras += 1
        elif abajo > 0 and arriba < vp.height():
            asomando += 1
    return enteras, asomando, len(dialog.sample_boxes) - enteras - asomando


def _within(dialog, widget) -> bool:
    """Si el widget queda dentro del alto de la ventana."""
    abajo = widget.mapTo(dialog, widget.rect().bottomLeft()).y()
    return abajo <= dialog.height()


def _check_form(report: Report, app, nombre: str, dialogo,
                espera_guardar: bool = True) -> None:
    dialogo.show()
    harness.settle(app, 25)

    boton = dialogo.save_button
    if espera_guardar:
        report.check(
            f"[{nombre}] el botón de guardar queda dentro de la ventana",
            boton.isVisible() and _within(dialogo, boton),
            f"ventana {dialogo.width()}x{dialogo.height()} px, botón abajo en "
            f"{boton.mapTo(dialogo, boton.rect().bottomLeft()).y()} px",
        )
        report.check(
            f"[{nombre}] el botón de guardar NO está en la zona que se desplaza",
            not dialogo.scroll.isAncestorOf(boton),
            "el pie queda fijo aunque el cuerpo se desplace",
        )
    else:
        report.check(f"[{nombre}] en consulta no se ofrece guardar",
                     not boton.isVisible(), "botón oculto")

    report.check(
        f"[{nombre}] cabe a lo ancho de un portátil",
        dialogo.minimumSizeHint().width() <= LAPTOP_WIDTH,
        f"{dialogo.minimumSizeHint().width()} px  (tope {LAPTOP_WIDTH})",
    )
    report.check(
        f"[{nombre}] no pasa del alto de la pantalla",
        dialogo.height() <= LAPTOP_HEIGHT,
        f"{dialogo.height()} px  (pantalla {LAPTOP_HEIGHT})",
    )
    report.check(
        f"[{nombre}] recién abierto no tiene cambios sin guardar",
        not dialogo.has_unsaved_changes(),
        "cancelar no pregunta nada",
    )
    dialogo.close()


def _silence_dialogs() -> None:
    """Contesta sin abrir cuadros modales.

    Una prueba que cambia campos y despues cierra el formulario **tiene** que
    sustituir estas funciones: si no, ``reject()`` abre el cuadro de 'cambios
    sin guardar' y la suite se queda esperando a que alguien lo conteste. Por
    eso son funciones de modulo y no metodos -- estan pensadas justo para poder
    sustituirlas.

    Se descubrio otra vez aqui: la suite imprimia sus 37 comprobaciones y el
    proceso no terminaba nunca, colgando de paso a ``run_all.py``.
    """
    from app.ui.dialogs import form_guard

    form_guard.confirm_discard = lambda parent: True        # descartar
    form_guard.ask_conflict = lambda parent, conflict, audit: None
    form_guard.warn_deleted = lambda parent, error: None


def main() -> int:
    report = Report("Formularios de captura")
    app = harness.qt_app(LIGHT)
    _silence_dialogs()
    context = harness.make_context()

    from dialogs.cycles import CyclesDialog
    from dialogs.fatigue import FatigueDialog
    from dialogs.generic import GenericDialog
    from dialogs.rotary import RotaryDialog
    from dialogs.work_order import WorkOrderDialog

    abiertas = context.fatigue.list(ONGOING)
    cerradas = context.fatigue.list("Finished")
    rotary = context.rotary.list()
    torsion = context.torsion.list()

    report.check("hay datos con los que medir",
                 bool(abiertas and cerradas and rotary and torsion),
                 f"{len(abiertas)} fatiga abiertas, {len(rotary)} rotary, "
                 f"{len(torsion)} torsión")
    if not (abiertas and cerradas and rotary and torsion):
        harness.shutdown(app)
        return report.finish()

    abiertos = context.maintenance.open_records()
    prueba = abiertas[0]
    detenidas = {slot: registro
                 for (test_id, slot), registro
                 in maintenance.paused_slots(abiertos).items()
                 if test_id == prueba.id}

    def fatiga(**extra):
        d = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                          unavailable_rigs=maintenance.rigs_in_maintenance(
                              abiertos), **extra)
        # Se vuelve a ajustar simulando el portatil: la maquina que corre esto
        # tiene un monitor grande.
        d.finish_setup(available_height=LAPTOP_HEIGHT)
        return d

    report.section("Fatiga: nueve piezas de cuatro campos")
    _check_form(report, app, "Fatiga · edición",
                fatiga(test=prueba, paused=detenidas))
    _check_form(report, app, "Fatiga · consulta",
                fatiga(test=cerradas[0], read_only=True),
                espera_guardar=False)

    report.section("Las demás bitácoras")
    rot = RotaryDialog(context.rotary, context.catalogs, context.audit,
                       test=rotary[0])
    rot.finish_setup(available_height=LAPTOP_HEIGHT)
    _check_form(report, app, "Rotary", rot)

    from app.models import TORSION

    gen = GenericDialog(context.torsion, context.catalogs, context.audit,
                        TORSION, test=torsion[0])
    gen.finish_setup(available_height=LAPTOP_HEIGHT)
    _check_form(report, app, "Torsión", gen)

    wo = WorkOrderDialog(context.work_orders, context.catalogs)
    wo.finish_setup(available_height=LAPTOP_HEIGHT)
    _check_form(report, app, "Work Order", wo)

    ciclos = CyclesDialog(context.fatigue, prueba, paused=detenidas)
    ciclos.finish_setup(available_height=LAPTOP_HEIGHT)
    _check_form(report, app, "Capturar ciclos", ciclos)

    report.section("El formulario abre con seis piezas exactas")
    # Seis y no cinco ni "seis y media": lo normal en un test batch son seis
    # piezas, y una tercera fila asomando por abajo se lee como un corte
    # accidental en vez de como "hay mas, desplaza". Se midio: estimando el
    # alto con sizeHint() la fila sobrante asomaba 72 px.
    #
    # Aqui **no** se simula el portatil. En una pantalla de 768 px dos filas no
    # caben y el formulario recorta, que es lo correcto; lo que se comprueba es
    # el tamano con el que nace cuando hay sitio.
    seis_fatiga = FatigueDialog(context.fatigue, context.catalogs,
                                context.audit, test=prueba, paused=detenidas)
    seis_rotary = RotaryDialog(context.rotary, context.catalogs,
                               context.audit, test=rotary[0])
    for nombre, dialogo in (("Fatiga", seis_fatiga), ("Rotary", seis_rotary)):
        dialogo.show()
        harness.settle(app, 25)
        enteras, asomando, fuera = _sample_visibility(dialogo)
        report.check(
            f"[{nombre}] se ven seis tarjetas enteras",
            enteras == 6,
            f"{enteras} enteras, {asomando} asomando, {fuera} fuera",
        )
        report.check(
            f"[{nombre}] ninguna cuarta fila asoma por abajo",
            asomando == 0,
            "el corte cae en el hueco entre filas",
        )
        report.check(
            f"[{nombre}] las tres restantes se alcanzan desplazando",
            fuera == 3 and dialogo.scroll.verticalScrollBar().maximum() > 0,
            f"{fuera} fuera del área, barra hasta "
            f"{dialogo.scroll.verticalScrollBar().maximum()} px",
        )
        dialogo.mark_clean()
        dialogo.close()

    report.section("Fatiga abre por filas, no entera")
    # Las nueve piezas siguen en el formulario; lo que cambia es con cuantas
    # nace la ventana. Sin esto pedia 967 px de alto.
    completo = fatiga(test=prueba, paused=detenidas)
    completo.show()
    harness.settle(app, 25)
    report.check(
        "las nueve piezas siguen en el formulario",
        len(completo.sample_boxes) == 9,
        f"{len(completo.sample_boxes)} recuadros de pieza",
    )
    report.check(
        "el cuerpo es más alto que la ventana, así que hay algo que desplazar",
        completo.body.sizeHint().height() > completo.scroll.viewport().height(),
        f"cuerpo {completo.body.sizeHint().height()} px, "
        f"ventana del área {completo.scroll.viewport().height()} px",
    )

    report.section("Lo que falta se marca sobre su campo")
    # Se vacia el resultado de la primera pieza y se pide finalizar: el aviso
    # tiene que marcar ese campo concreto, no solo enumerarlo.
    from components import fields

    fields.set_combo_value(completo.results[0], None)
    completo.cycles[0].clear()
    completo._finish()
    marcados = completo.invalid_widgets()
    report.check(
        "finalizar sin datos marca los campos que faltan",
        completo.results[0] in marcados or completo.cycles[0] in marcados,
        f"{len(marcados)} campos marcados",
    )
    report.check(
        "y los enumera en el aviso de arriba",
        bool(completo.issue_text()),
        (completo.issue_text().splitlines() or ["sin texto"])[0][:70],
    )
    report.check(
        "el aviso vive fuera del área que se desplaza",
        not completo.scroll.isAncestorOf(completo._banner),
        "se lee aunque el campo marcado esté abajo del todo",
    )
    completo.close()

    report.section("Las piezas que sobran se apagan, no se ocultan")
    corto = fatiga(test=prueba, paused=detenidas)
    fields.set_combo_value(corto.qty, "2")
    corto._update_sample_slots()
    apagadas = [c for c in corto.sample_boxes if not c.is_active()]
    report.check(
        "declarando 2 piezas, las de más quedan apagadas",
        bool(apagadas),
        f"{len(apagadas)} de {len(corto.sample_boxes)} apagadas",
    )
    report.check(
        "pero siguen a la vista",
        all(not c.isHidden() for c in corto.sample_boxes),
        "ninguna se oculta",
    )
    corto.close()

    harness.shutdown(app)
    return report.finish()


if __name__ == "__main__":
    raise SystemExit(main())
