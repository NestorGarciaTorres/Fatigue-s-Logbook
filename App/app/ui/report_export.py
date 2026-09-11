"""Guardar un reporte a Excel desde cualquier pantalla.

El mismo recorrido en las seis que exportan: nada que exportar se dice sin
abrir el dialogo de archivo, un error se ensenia en lugar de perderse, y al
terminar se dice cuantos registros quedaron y donde.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

EMPTY_MESSAGE = "No hay registros que exportar con estos filtros."


def filter_period(filter_bar) -> tuple:
    """El rango de fechas de la barra de filtros, para el titulo del reporte."""
    activos = filter_bar.filters()
    return activos.date_from, activos.date_to


def save_report(parent, count: int, suggested: str, write,
                empty_message: str = EMPTY_MESSAGE) -> Path | None:
    """Pregunta donde guardar y llama a ``write(ruta)``.

    Devuelve la ruta escrita, o None si no se escribio nada.
    """
    if not count:
        QMessageBox.information(parent, "Sin datos", empty_message)
        return None

    path, _ = QFileDialog.getSaveFileName(
        parent, "Guardar reporte", suggested, "Excel (*.xlsx)"
    )
    if not path:
        return None

    try:
        saved = write(path)
    except Exception as error:  # pragma: no cover - disco lleno, archivo abierto
        QMessageBox.critical(parent, "Error al exportar", str(error))
        return None

    QMessageBox.information(
        parent, "Reporte generado",
        f"Se exportaron {count} registro(s) a:\n{saved}",
    )
    return Path(saved)
