"""Cierre de una prueba: pide la fecha de fin.

Reemplaza a ``tools/close_fatigue_record.py``, que ademas de la ventana hacia
su propio UPDATE interpolando el nombre de la tabla en el SQL y decidia esa
tabla mirando si el test batch contenia 'SRF'. Ahora el dialogo solo devuelve
la fecha; quien sabe a que tabla escribir es el repositorio que lo abrio.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from app.ui.widgets.filter_bar import make_date_edit


class CloseTestDialog(QDialog):
    def __init__(self, test_batch: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Finalizar prueba")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        label = QLabel(f"Test Batch: <b>{test_batch}</b>")
        layout.addWidget(label)

        form = QFormLayout()
        self.date_edit = make_date_edit()
        form.addRow("Fecha de fin de prueba", self.date_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        accept = buttons.addButton(
            "Guardar", QDialogButtonBox.ButtonRole.AcceptRole
        )
        accept.setProperty("accent", "success")
        buttons.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def end_date(self) -> date:
        return self.date_edit.date().toPython()
