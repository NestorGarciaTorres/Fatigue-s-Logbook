"""Punto de entrada de la Bitacora de Pruebas (PySide6).

    python main.py

Sustituye a ``main.pyw``. Se usa la extension .py para que la consola muestre
los errores de arranque; para lanzarlo sin consola basta con ``pythonw main.py``
o un acceso directo.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.context import AppContext  # noqa: E402
from app.services import backup  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

log = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    configure_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("Bitacora de Pruebas")
    theme.apply(app)

    context = AppContext()

    if not context.database.exists():
        QMessageBox.critical(
            None,
            "Base de datos no encontrada",
            f"No se encontro la base de datos en:\n{context.config.database}\n\n"
            "Revisa settings.json o corre primero:\n"
            "    python tools/pick_database.py",
        )
        return 1

    try:
        applied = context.prepare()
    except Exception as error:
        QMessageBox.critical(
            None,
            "Error al preparar la base de datos",
            f"No se pudo abrir o migrar la base:\n\n{error}",
        )
        return 1

    if applied:
        log.info("Migraciones aplicadas: %s", ", ".join(applied))

    if context.config.auto_backup:
        try:
            backup.daily_backup(
                context.config.database,
                context.config.backups,
                context.config.backup_keep,
            )
        except Exception as error:  # el respaldo no debe impedir trabajar
            log.warning("No se pudo crear el respaldo diario: %s", error)

    window = MainWindow(context)
    window.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
