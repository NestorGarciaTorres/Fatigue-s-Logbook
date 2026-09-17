"""Punto de entrada de la interfaz redisenada.

    python main.py

Reutiliza entera la logica del proyecto ``fatigue-logbook`` que vive al lado:
repositorios, servicios y modelos son los suyos y no se tocan. Lo que hay aqui
es la capa de presentacion.

Se usa la extension .py para que la consola ensenie los errores de arranque;
para lanzarlo sin consola basta con ``pythonw main.py``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bridge  # noqa: E402

log = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    configure_logging()

    try:
        bridge.install()
    except bridge.OriginalProjectMissing as error:
        print(error, file=sys.stderr)
        return 1

    from PySide6.QtWidgets import QApplication, QMessageBox

    from theme.manager import theme
    from window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Bitácora de Pruebas")

    # El tema va antes que nada de la ventana: aplicarlo despues repinta toda
    # la app sin motivo y se ve el parpadeo.
    theme().attach(app)

    try:
        context, applied = bridge.build_context()
    except FileNotFoundError as ruta:
        QMessageBox.critical(
            None,
            "Base de datos no encontrada",
            f"No se encontró la base de datos en:\n{ruta}\n\n"
            f"Revisa {bridge.SETTINGS_FILE.name} en la carpeta de esta app.",
        )
        return 1
    except Exception as error:
        QMessageBox.critical(
            None,
            "Error al preparar la base de datos",
            f"No se pudo abrir o migrar la base:\n\n{error}",
        )
        return 1

    if applied:
        log.info("Migraciones aplicadas: %s", ", ".join(applied))

    window = MainWindow(context)
    window.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
