"""El unico punto de contacto con el proyecto original.

La interfaz nueva vive en su propia carpeta y no edita ni un archivo de
``fatigue-logbook``. Lo que si hace es **reutilizar su logica**: los
repositorios, los servicios y los modelos son los mismos, asi que las dos apps
leen y escriben exactamente igual y no pueden divergir.

Tres cosas pasan aqui, y el orden importa:

1. La raiz del proyecto original entra en ``sys.path``, para poder importar
   ``app.*``.
2. ``app.config.SETTINGS_FILE`` se redirige a un archivo propio **antes** de
   que nadie llame a ``AppConfig.load()``. Sin esto, cambiar la base desde
   Ajustes en la app nueva reescribiria el ``settings.json`` del proyecto que
   debe quedar intacto. Es la misma redireccion que el proyecto original ya
   documenta como obligatoria para sus pruebas.
3. Se arma el contexto con la misma secuencia de arranque que ``main.py`` del
   original: respaldo previo si hay migraciones pendientes, migrar, respaldo
   diario.

Las rutas relativas se siguen resolviendo contra la raiz del **original**
(``AppConfig._resolve`` usa su propio ``PROJECT_ROOT``), asi que
``"db/test_records.db"`` apunta a la misma base de siempre. Es deliberado: las
dos apps trabajan sobre los mismos datos, y por eso la nueva respalda antes de
migrar igual que la vieja.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

UI_ROOT = Path(__file__).resolve().parent
ORIGINAL_ROOT = UI_ROOT.parent / "fatigue-logbook"

# Ajustes de la app nueva, con la forma que espera AppConfig. Vive aqui y no en
# el proyecto original a proposito: asi un cambio de base o de respaldos desde
# esta interfaz no toca la configuracion de la app que el laboratorio usa a
# diario.
SETTINGS_FILE = UI_ROOT / "ui_settings.json"

log = logging.getLogger(__name__)


class OriginalProjectMissing(RuntimeError):
    """No se encontro fatigue-logbook al lado de esta carpeta."""


def _ensure_path() -> None:
    if not (ORIGINAL_ROOT / "app" / "__init__.py").is_file():
        raise OriginalProjectMissing(
            f"No se encontro el proyecto original en:\n{ORIGINAL_ROOT}\n\n"
            f"Esta interfaz reutiliza su logica, asi que las dos carpetas "
            f"tienen que estar juntas:\n"
            f"    AI Projects/fatigue-logbook/\n"
            f"    AI Projects/fatigue-logbook-ui/"
        )
    ruta = str(ORIGINAL_ROOT)
    if ruta not in sys.path:
        sys.path.insert(0, ruta)


def _seed_settings() -> None:
    """Crea el archivo propio la primera vez, copiando el del original.

    Se copia en lugar de partir de los valores por omision para que la app
    nueva abra apuntando a la misma base que la vieja, sin que nadie tenga que
    configurarla. A partir de ahi los dos archivos viven su vida.
    """
    if SETTINGS_FILE.exists():
        return

    original = ORIGINAL_ROOT / "settings.json"
    datos: dict = {}
    if original.is_file():
        try:
            datos = json.loads(original.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            # Un settings.json ilegible del original no debe impedir arrancar:
            # AppConfig pondra sus valores por omision.
            log.warning("No se pudo leer %s: %s", original, error)

    SETTINGS_FILE.write_text(
        json.dumps(datos, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def install() -> None:
    """Deja el proyecto original importable y la configuracion redirigida.

    Es idempotente: llamarlo dos veces no cambia nada la segunda.
    """
    _ensure_path()
    _seed_settings()

    from app import config

    config.SETTINGS_FILE = SETTINGS_FILE


def load_config():
    """``AppConfig`` leido del archivo de esta app."""
    install()
    from app.config import AppConfig

    return AppConfig.load()


def build_context(config=None):
    """El contexto listo para usar, con la misma secuencia que el original.

    Devuelve ``(context, applied)``: el contexto y la lista de migraciones que
    se aplicaron, que quien llama puede registrar.

    El respaldo va **antes** de migrar y no despues. En el original eso se
    corrigio tras descubrir que la copia de un dia con migracion guardaba la
    base ya migrada: si algo salia mal no habia a donde volver.
    """
    install()

    from app.config import AppConfig
    from app.context import AppContext
    from app.db import migrations
    from app.services import backup

    context = AppContext(config or AppConfig.load())

    if not context.database.exists():
        raise FileNotFoundError(context.config.database)

    if context.config.auto_backup and migrations.pending(context.database):
        try:
            backup.pre_migration_backup(
                context.config.database, context.config.backups
            )
        except Exception as error:  # el respaldo no debe impedir trabajar
            log.warning("No se pudo respaldar antes de migrar: %s", error)

    applied = context.prepare()

    if context.config.auto_backup:
        try:
            backup.daily_backup(
                context.config.database,
                context.config.backups,
                context.config.backup_keep,
            )
        except Exception as error:  # el respaldo no debe impedir trabajar
            log.warning("No se pudo crear el respaldo diario: %s", error)

    return context, applied
