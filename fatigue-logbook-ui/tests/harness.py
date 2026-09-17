"""Piezas comunes de las pruebas de la interfaz nueva.

Mismo formato de salida que las del proyecto original --``OK``/``FALLO`` por
comprobacion y codigo 1 si algo falla-- para que se lean igual y se puedan
correr juntas.

Las dos reglas del original se heredan enteras:

1. **Nunca contra la base real.** ``AppContext.prepare()`` aplica migraciones.
   Una prueba que abriera ``db/test_records.db`` dejaria migrada la base de
   produccion antes de que nadie hubiera sacado un respaldo.
2. **Nada de contar filas fijas.** La app esta en uso y la base crece. Se
   compara contra lo que diga la base, no contra un numero escrito a mano.

Y una tercera, propia de aqui: **una comprobacion de color dice la medida**.
``dE 20.7`` o ``3.01 : 1`` en el detalle, para que al fallar se vea cuanto
falta y no solo que fallo.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

UI_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UI_ROOT))

import bridge  # noqa: E402  (tiene que ir despues de tocar sys.path)

bridge.install()

REAL_DATABASE = bridge.ORIGINAL_ROOT / "db" / "test_records.db"


class Report:
    """Lleva la cuenta de lo comprobado y decide el codigo de salida."""

    def __init__(self, title: str):
        self.title = title
        self.failures: list[str] = []
        self.passed = 0

    def section(self, text: str) -> None:
        print(f"\n=== {text} ===")

    def check(self, label: str, condition, detail: str = "") -> bool:
        ok = bool(condition)
        print(("OK    " if ok else "FALLO ") + label
              + (f"   {detail}" if detail else ""))
        if ok:
            self.passed += 1
        else:
            self.failures.append(f"{label}   {detail}".rstrip())
        return ok

    def note(self, text: str) -> None:
        print(f"      {text}")

    def finish(self) -> int:
        print("\n" + "=" * 66)
        if self.failures:
            print(f"{self.title}: FALLARON {len(self.failures)} "
                  f"de {self.passed + len(self.failures)}")
            for failure in self.failures:
                print(f"  - {failure}")
            return 1
        print(f"{self.title}: {self.passed} comprobaciones, todas pasaron")
        return 0


def database_copy(name: str = "test_records.db") -> Path:
    """Copia temporal de la base real, o una vacia si no existe."""
    target = Path(tempfile.mkdtemp(prefix="bitacora_ui_test_")) / name
    if REAL_DATABASE.exists():
        shutil.copy(REAL_DATABASE, target)
    return target


def make_context(path: Path | None = None):
    """``AppContext`` ya migrado sobre una copia, nunca sobre la base real."""
    from app.config import AppConfig
    from app.context import AppContext

    context = AppContext(
        AppConfig(database_path=str(path or database_copy()), auto_backup=False)
    )
    context.prepare()
    return context


def offscreen() -> None:
    """Qt sin ventanas. Solo para lo que no mide pixeles ni texto.

    Con la plataforma 'offscreen' las fuentes no resuelven y el texto sale como
    cajas vacias, asi que lo que compruebe un render tiene que correr con la
    plataforma nativa.
    """
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


def qt_app(theme_name: str | None = None):
    """``QApplication`` con el tema aplicado, reutilizando la que ya exista.

    La preferencia se redirige a un archivo temporal **antes** de tocar nada:
    una prueba que cambia de tema para medirlo no tiene por que dejarle al
    usuario la app abriendo en oscuro la proxima vez. Es el mismo cuidado que
    con ``settings.json``, y se descubrio igual -- abriendo la app y
    encontrandola en un tema que nadie habia elegido.
    """
    from PySide6.QtWidgets import QApplication

    from theme import manager

    manager.SETTINGS_FILE = (
        Path(tempfile.mkdtemp(prefix="bitacora_tema_")) / "ui_theme.json")

    app = QApplication.instance() or QApplication(sys.argv)
    manager.theme().attach(app)
    if theme_name:
        manager.theme().set_theme(theme_name)
    return app


def shutdown(app) -> None:
    """Cierra lo que quede abierto antes de salir.

    Un dialogo vivo cuando el interprete empieza a apagarse deja el proceso
    colgado: las comprobaciones terminan, se imprime el resumen y la suite no
    devuelve nunca -- lo que a su vez cuelga ``run_all.py``, que espera a cada
    proceso. Se descubrio asi, con una suite que pasaba y no terminaba.

    ``mark_clean`` antes de cerrar: un formulario con cambios pregunta si
    descartarlos, y esa pregunta es un cuadro modal que nadie va a contestar.
    """
    for widget in app.topLevelWidgets():
        if hasattr(widget, "mark_clean"):
            widget.mark_clean()
        widget.close()
        widget.deleteLater()
    settle(app, 5)


def settle(app, rounds: int = 10) -> None:
    """Deja que Qt procese lo pendiente antes de medir."""
    for _ in range(rounds):
        app.processEvents()


def ratio(value: float) -> str:
    """Formato de una razon de contraste, para el detalle de una comprobacion."""
    return f"{value:.2f} : 1"
