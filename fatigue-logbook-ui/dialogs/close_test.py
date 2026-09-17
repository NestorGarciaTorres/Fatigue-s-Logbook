"""Cierre de una prueba: pide la fecha de fin.

Es lo unico que hace. Quien sabe a que tabla escribir es el repositorio que lo
abrio; el dialogo solo devuelve la fecha.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import QDialog, QFormLayout, QVBoxLayout

from components import buttons, fields, labels


class CloseTestDialog(QDialog):
    def __init__(self, test_batch: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Finalizar prueba")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(labels.subheading("Finalizar prueba"))
        layout.addWidget(labels.secondary(
            f"Test Batch {test_batch}. A partir de aquí el registro pasa a ser "
            f"histórico y se consulta durante años.", wrap=True))

        form = QFormLayout()
        self.date_edit = fields.date_edit()
        form.addRow("Fecha de fin de prueba", self.date_edit)
        layout.addLayout(form)

        self.save_button = buttons.button("Finalizar", buttons.PRIMARY,
                                          on_click=self.accept)
        layout.addLayout(buttons.button_row(
            None,
            buttons.button("Cancelar", buttons.GHOST, on_click=self.reject),
            self.save_button,
            stretch_at_end=False))

    def end_date(self) -> date:
        return fields.to_date(self.date_edit)
