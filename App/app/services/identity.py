"""Quien esta usando la app.

Sin login: se toma la sesion de Windows. Es suficiente para trazabilidad
interna y no agrega mantenimiento de usuarios ni contrasenas.
"""

from __future__ import annotations

import getpass
import platform
from functools import lru_cache


@lru_cache(maxsize=1)
def current_author() -> tuple[str, str]:
    """Devuelve ``(usuario, equipo)``. No cambia durante la sesion."""
    try:
        user = getpass.getuser()
    except Exception:  # pragma: no cover - entornos sin variables de entorno
        user = "desconocido"

    try:
        machine = platform.node() or "desconocido"
    except Exception:  # pragma: no cover
        machine = "desconocido"

    return user, machine


def author_label() -> str:
    user, machine = current_author()
    return f"{user} ({machine})"
