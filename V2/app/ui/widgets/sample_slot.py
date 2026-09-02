"""Recuadro de una pieza dentro del formulario.

Antes las nueve piezas eran filas sueltas en una rejilla: `Pieza 4`, `Ciclos` y
`Modo de falla` quedaban separadas por el mismo espacio que separaba una pieza
de la siguiente, y nada indicaba donde terminaba una y empezaba otra.

Ademas, las ranuras por encima del numero de piezas declarado se "atenuaban"
poniendo ``color:`` sobre los campos. Un campo vacio no tiene texto que
colorear, asi que lo unico que cambiaba de color era el rotulo `Pieza N`: con
una pieza declarada se seguian viendo veintisiete campos identicos. Aqui las
piezas sobrantes se ocultan.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QWidget

from app.ui import theme

# Una pieza capturada fuera del numero declarado no se oculta: se muestra con
# este aviso, porque perderla de vista seria peor que la incoherencia.
EXTRA_HINT = (
    "Esta pieza esta capturada por encima del numero declarado.\n"
    "Sube 'No. de piezas' o borra sus datos."
)


class SampleBox(QGroupBox):
    """Las tres capturas de una pieza, agrupadas y rotuladas con su numero."""

    def __init__(self, number: int, rows: list[tuple[str, QWidget]], parent=None):
        super().__init__(f"Pieza {number}", parent)
        self.number = number
        self._fields = [widget for _, widget in rows]

        form = QFormLayout(self)
        form.setContentsMargins(12, 6, 12, 10)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter)

        for caption, widget in rows:
            label = QLabel(caption)
            label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-weight: normal;")
            form.addRow(label, widget)

        self._normal_style = ""
        self._extra_style = (
            f"QGroupBox {{ border: 1px solid {theme.WARNING}; }}"
            f"QGroupBox::title {{ color: {theme.WARNING}; }}"
        )

    # --- estado ----------------------------------------------------------
    def has_data(self) -> bool:
        """Si el usuario capturo algo en esta pieza."""
        for field in self._fields:
            if hasattr(field, "currentText"):
                if field.currentText().strip():
                    return True
            elif hasattr(field, "text"):
                if field.text().strip():
                    return True
        return False

    def mark_extra(self, extra: bool) -> None:
        """Resalta la pieza cuando queda fuera del numero declarado."""
        self.setStyleSheet(self._extra_style if extra else self._normal_style)
        self.setToolTip(EXTRA_HINT if extra else "")
        self.setTitle(f"Pieza {self.number}" + ("  (de mas)" if extra else ""))
