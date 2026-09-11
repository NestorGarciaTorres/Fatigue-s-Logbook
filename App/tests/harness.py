"""Piezas comunes de las pruebas.

Dos reglas que salieron a base de tropezar con ellas:

1. **Nunca contra la base real.** ``AppContext.prepare()`` aplica migraciones.
   Una prueba que abriera ``db/test_records.db`` dejaba migrada la base de
   produccion antes de que nadie hubiera sacado un respaldo. Aqui siempre se
   trabaja sobre una copia temporal.

2. **Nada de contar filas fijas.** La app esta en uso y la base crece. Una
   prueba que espere "10 registros en curso" fallara la semana que viene sin
   que nada este mal. Se comprueba contra lo que diga la base, no contra un
   numero escrito a mano.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

REAL_DATABASE = PROJECT / "db" / "test_records.db"


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
            self.failures.append(label)
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
    target = Path(tempfile.mkdtemp(prefix="bitacora_test_")) / name
    if REAL_DATABASE.exists():
        shutil.copy(REAL_DATABASE, target)
    return target


def empty_database(name: str = "nueva.db") -> Path:
    """Ruta a una base que aun no existe, para probar el arranque desde cero."""
    return Path(tempfile.mkdtemp(prefix="bitacora_nueva_")) / name


def make_context(path: Path | None = None):
    """AppContext ya migrado sobre una copia."""
    from app.config import AppConfig
    from app.context import AppContext

    context = AppContext(
        AppConfig(database_path=str(path or database_copy()), auto_backup=False)
    )
    context.prepare()
    return context


def offscreen() -> None:
    """Qt sin ventanas. Solo para las pruebas que no miden pixeles.

    Con la plataforma 'offscreen' las fuentes no resuelven y el texto sale como
    cajas vacias, asi que lo que compruebe un render tiene que correr con la
    plataforma nativa.
    """
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


def qt_app():
    """QApplication con el tema aplicado, reutilizando la que ya exista."""
    from PySide6.QtWidgets import QApplication

    from app.ui import theme

    app = QApplication.instance() or QApplication(sys.argv)
    theme.apply(app)
    return app


def settle(app, rounds: int = 10) -> None:
    """Deja que Qt procese lo pendiente antes de medir."""
    for _ in range(rounds):
        app.processEvents()
