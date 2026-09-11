"""Verifica escrituras con auditoria (paso 12) y el arranque de la interfaz.

La UI se construye con QT_QPA_PLATFORM=offscreen: se instancian todas las
paginas y dialogos de verdad, pero sin abrir ventanas.
"""

from harness import (
    Report, database_copy, empty_database, make_context, offscreen,
    qt_app, settle,
)


import os
import sys
from datetime import date
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"


COPY = database_copy()

from app.config import AppConfig
from app.context import AppContext
from app.models import FINISHED, ONGOING, FatigueSample, FatigueTest

failures = []


def check(label, condition, detail=""):
    print(("OK   " if condition else "FALLO ") + label +
          (f"   {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def verify_writes():
    print("=== Escrituras y auditoria ===")
    config = AppConfig(database_path=str(COPY), auto_backup=False)
    context = AppContext(config)
    context.prepare()

    author = ("verificador", "PC-PRUEBA")
    repo = context.fatigue

    test = FatigueTest(
        test_batch="999999STF01",
        customer="AUDI",
        start_date=date(2026, 8, 1),
        qty_samples=2,
        comments="registro de prueba",
        wo_status=True,
        test_status=ONGOING,
        samples=[FatigueSample() for _ in range(9)],
    )
    test.samples[0] = FatigueSample(rig="I-02-1", cycles=1000)
    test.samples[1] = FatigueSample(rig="T-7228", cycles=2000)

    new_id = repo.create(test, author)
    check("alta crea el registro", new_id is not None, f"id {new_id}")

    saved = repo.get(new_id)
    check("los datos vuelven igual",
          saved.test_batch == "999999STF01"
          and saved.customer == "AUDI"
          and saved.start_date == date(2026, 8, 1)
          and saved.total_cycles == 3000,
          f"ciclos={saved.total_cycles}")

    entries = context.audit.for_record("fatigue_tests", new_id)
    check("el alta quedo en el historial",
          any(e.action == "created" for e in entries))

    # --- edicion ---------------------------------------------------------
    saved.customer = "BMW"
    saved.samples[0].cycles = 5000
    repo.update(saved, author)

    entries = context.audit.for_record("fatigue_tests", new_id)
    changed = {e.field for e in entries if e.action == "updated"}
    check("la edicion registra solo los campos que cambiaron",
          changed == {"customer", "cycles1"}, f"campos: {sorted(changed)}")

    updated = repo.get(new_id)
    check("la edicion se guardo",
          updated.customer == "BMW" and updated.samples[0].cycles == 5000)

    # --- cierre y reapertura ---------------------------------------------
    repo.close(new_id, date(2026, 8, 20), author)
    closed = repo.get(new_id)
    check("cierre marca Finished y fecha",
          closed.test_status == FINISHED
          and closed.end_date == date(2026, 8, 20))

    repo.reopen(new_id, author)
    check("reapertura vuelve a Ongoing",
          repo.get(new_id).test_status == ONGOING)

    entries = context.audit.for_record("fatigue_tests", new_id)
    actions = {e.action for e in entries}
    check("historial completo",
          {"created", "updated", "closed", "reopened"} <= actions,
          f"acciones: {sorted(actions)}")

    users = {e.changed_by for e in entries}
    check("el autor quedo registrado", users == {"verificador"}, str(users))

    # --- limpieza --------------------------------------------------------
    with context.database.write() as conn:
        conn.execute("DELETE FROM fatigue_tests WHERE id = ?", (new_id,))
        conn.execute("DELETE FROM audit_log WHERE record_id = ?", (new_id,))

    check("registro de prueba eliminado", repo.get(new_id) is None)
    return context


def verify_ui(context):
    print("\n=== Arranque de la interfaz (offscreen) ===")
    from PySide6.QtWidgets import QApplication

    from app.ui import theme
    from app.ui.dialogs.fatigue_dialog import FatigueDialog
    from app.ui.dialogs.generic_dialog import GenericDialog
    from app.ui.dialogs.rotary_dialog import RotaryDialog
    from app.ui.main_window import MainWindow
    from app.models import TORSION

    app = QApplication(sys.argv)
    theme.apply(app)
    check("QApplication + tema", True)

    window = MainWindow(context)
    check("MainWindow construida", window is not None)

    for key in ("fatigue", "torsion", "rotary", "quasi", "dashboard",
                "settings"):
        try:
            window.show_page(key)
            check(f"pagina '{key}' carga datos", True)
        except Exception as exc:
            check(f"pagina '{key}' carga datos", False,
                  f"{type(exc).__name__}: {exc}")

    # La tabla de fatiga debe traer exactamente las pruebas en curso, sean
    # las que sean hoy.
    tab = window.pages["fatigue"].ongoing
    en_curso = len(context.fatigue.list(ONGOING))
    check("tabla de fatiga poblada", tab.table.row_count() == en_curso,
          f"{tab.table.row_count()} filas de {en_curso} en curso")

    # --- dialogos --------------------------------------------------------
    record = context.fatigue.list(ONGOING)[0]
    try:
        dialog = FatigueDialog(context.fatigue, context.catalogs,
                               context.audit, test=record)
        collected = dialog._collect()
        check("dialogo de fatiga: carga y recoleccion coherentes",
              collected.test_batch == record.test_batch
              and collected.total_cycles == record.total_cycles,
              f"{collected.test_batch}")
    except Exception as exc:
        check("dialogo de fatiga", False, f"{type(exc).__name__}: {exc}")

    try:
        rotary_record = context.rotary.list()[0]
        RotaryDialog(context.rotary, context.catalogs, context.audit,
                     test=rotary_record)
        check("dialogo de rotary", True)
    except Exception as exc:
        check("dialogo de rotary", False, f"{type(exc).__name__}: {exc}")

    try:
        torsion_record = context.torsion.list()[0]
        GenericDialog(context.torsion, context.catalogs, context.audit,
                      TORSION, test=torsion_record)
        check("dialogo de torsion", True)
    except Exception as exc:
        check("dialogo de torsion", False, f"{type(exc).__name__}: {exc}")

    app.quit()


def main():
    context = verify_writes()
    verify_ui(context)

    print("\n" + "=" * 62)
    if failures:
        print(f"FALLARON {len(failures)}:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("TODAS LAS COMPROBACIONES PASARON")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
