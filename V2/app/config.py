"""Configuracion de la aplicacion.

La ruta de la base de datos vive en ``settings.json``, fuera del codigo, para
que se pueda apuntar al recurso de red sin volver a empaquetar nada.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = PROJECT_ROOT / "settings.json"

DEFAULT_DATABASE = PROJECT_ROOT / "db" / "test_records.db"
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "db backups"


@dataclass
class AppConfig:
    """Ajustes persistentes. Se serializa tal cual a ``settings.json``."""

    database_path: str = str(DEFAULT_DATABASE)
    backup_dir: str = str(DEFAULT_BACKUP_DIR)
    backup_keep: int = 30
    auto_backup: bool = True

    # --- rutas resueltas -------------------------------------------------
    @property
    def database(self) -> Path:
        return self._resolve(self.database_path)

    @property
    def backups(self) -> Path:
        return self._resolve(self.backup_dir)

    @staticmethod
    def _resolve(value: str) -> Path:
        """Las rutas relativas se interpretan desde la raiz del proyecto.

        Asi la app funciona sin importar desde donde se lance, a diferencia de
        la version anterior que dependia del directorio de trabajo.
        """
        path = Path(value)
        return path if path.is_absolute() else (PROJECT_ROOT / path)

    # --- persistencia ----------------------------------------------------
    @classmethod
    def load(cls) -> "AppConfig":
        if not SETTINGS_FILE.exists():
            config = cls()
            config.save()
            return config

        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Un settings.json corrupto no debe impedir abrir la app.
            return cls()

        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        SETTINGS_FILE.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
