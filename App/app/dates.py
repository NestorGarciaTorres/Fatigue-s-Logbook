"""Conversion de fechas entre la app y la base de datos.

En la base las fechas estan guardadas como texto ``dd/MM/yyyy``. Se conserva
ese formato para no romper los registros existentes, pero dentro de la app
siempre se trabaja con ``datetime.date``.
"""

from __future__ import annotations

from datetime import date, datetime

DB_FORMAT = "%d/%m/%Y"


def to_db(value: date | None) -> str | None:
    """``date`` -> texto ``dd/MM/yyyy``."""
    return value.strftime(DB_FORMAT) if value else None


def from_db(value: str | None) -> date | None:
    """Texto ``dd/MM/yyyy`` -> ``date``. Devuelve None si no es parseable."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), DB_FORMAT).date()
    except ValueError:
        return None


def display(value: date | None) -> str:
    """Texto listo para mostrar en tabla o reporte."""
    return value.strftime(DB_FORMAT) if value else ""
