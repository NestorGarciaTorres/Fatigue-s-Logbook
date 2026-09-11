"""Respaldos de la base de datos.

Sustituye al respaldo manual que produjo las carpetas ``12_11_25`` y
``14_11_25``: se hace uno al abrir la app, como maximo uno por dia.
"""

from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)


def daily_backup(database: Path, backup_root: Path, keep: int = 30) -> Path | None:
    """Copia la base a ``backup_root/AAAA-MM-DD/``. Devuelve la ruta creada.

    Si ya existe el respaldo de hoy no hace nada, para no copiar el archivo en
    cada arranque.
    """
    if not database.is_file() or database.stat().st_size == 0:
        log.warning("No hay base que respaldar en %s", database)
        return None

    target_dir = backup_root / date.today().isoformat()
    target = target_dir / database.name

    if target.exists():
        return target

    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(database, target)
    log.info("Respaldo creado en %s", target)

    prune(backup_root, keep)
    return target


def manual_backup(database: Path, backup_root: Path) -> Path:
    """Respaldo con marca de tiempo, disparado desde Ajustes."""
    return _stamped_backup(database, backup_root / "manual")


def pre_migration_backup(database: Path, backup_root: Path) -> Path | None:
    """Copia la base tal como esta *antes* de migrarla.

    El respaldo diario no basta para esto: si la app ya se abrio hoy, el de hoy
    ya existe y no se vuelve a hacer, asi que una migracion aplicada por la
    tarde no tendria ningun punto de retorno del estado previo. Este se guarda
    aparte, con marca de tiempo, y solo cuando hay algo que migrar.
    """
    if not database.is_file() or database.stat().st_size == 0:
        log.warning("No hay base que respaldar en %s", database)
        return None

    target = _stamped_backup(database, backup_root / "pre-migracion")
    log.info("Respaldo previo a la migracion en %s", target)
    return target


def _stamped_backup(database: Path, target_dir: Path) -> Path:
    from datetime import datetime

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / f"{database.stem}_{stamp}{database.suffix}"
    shutil.copy2(database, target)
    return target


def latest_backup(backup_root: Path) -> Path | None:
    """El respaldo mas reciente, sea diario, manual o previo a una migracion.

    Se busca por fecha del archivo y no por el nombre de la carpeta: los
    respaldos manuales y los previos a una migracion no viven en carpetas con
    nombre de fecha.
    """
    if not backup_root.is_dir():
        return None
    copias = [path for path in backup_root.rglob("*.db") if path.is_file()]
    if not copias:
        return None
    return max(copias, key=lambda path: path.stat().st_mtime)


def prune(backup_root: Path, keep: int) -> None:
    """Conserva solo las ``keep`` carpetas de respaldo diario mas recientes."""
    if keep <= 0 or not backup_root.is_dir():
        return

    # Solo las carpetas con nombre de fecha ISO: las viejas (12_11_25) y la de
    # respaldos manuales se dejan intactas.
    daily = sorted(
        (
            path
            for path in backup_root.iterdir()
            if path.is_dir() and _is_iso_date(path.name)
        ),
        reverse=True,
    )

    for stale in daily[keep:]:
        try:
            shutil.rmtree(stale)
            log.info("Respaldo antiguo eliminado: %s", stale.name)
        except OSError as exc:  # pragma: no cover
            log.warning("No se pudo eliminar %s: %s", stale, exc)


def _is_iso_date(name: str) -> bool:
    try:
        date.fromisoformat(name)
    except ValueError:
        return False
    return True
