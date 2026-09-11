"""Mantenimiento de bancos en el dashboard: el historial y lo que costo.

El tiempo de mantenimiento ya se medía --se descuenta de los dias de cada
prueba y sale en la tarjeta del banco parado-- pero no se podia consultar: los
periodos cerrados no aparecian en ninguna pantalla. Aqui va el historial, con
el mismo rango de fechas que el resto del dashboard.

Es una lista y no una grafica por la misma razon que el panel de piezas: los
periodos son pocos y muy desiguales, y lo que se quiere leer de cada uno es
**cuando, cuanto y por que**, que en una barra no cabe.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app import dates
from app.models import TEST_TYPES, RigMaintenance
from app.ui import theme

# Cuantos periodos se enumeran antes de resumir. El dashboard es un vistazo;
# el historial completo esta a un boton.
MAX_ROWS = 6
SWATCH = 10


def _label(text: str, color: str, size: int = 10, bold: bool = False) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {color}; font-size: {size}pt; border: none;"
        + (" font-weight: bold;" if bold else "")
    )
    return label


class MaintenancePanel(QFrame):
    """Un renglon por periodo de mantenimiento, del mas reciente al mas viejo."""

    historyRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"QFrame {{ background-color: {theme.SURFACE};"
            f" border-radius: 6px; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(6)

        titulo = QHBoxLayout()
        titulo.addWidget(_label("Mantenimiento de bancos", theme.TEXT, 11))
        titulo.addStretch(1)
        self.subtitle = _label("", theme.TEXT_MUTED, 9)
        titulo.addWidget(self.subtitle)

        self.history_button = QPushButton("Ver historial completo")
        self.history_button.setProperty("accent", "secondary")
        self.history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_button.setStyleSheet("font-size: 9pt; padding: 4px 10px;")
        self.history_button.clicked.connect(self.historyRequested)
        titulo.addWidget(self.history_button)
        outer.addLayout(titulo)

        self.rows = QGridLayout()
        self.rows.setHorizontalSpacing(10)
        self.rows.setVerticalSpacing(3)
        # El motivo es lo unico de largo variable: se lleva lo que sobre.
        self.rows.setColumnStretch(4, 1)
        outer.addLayout(self.rows)

        self.note = _label("", theme.TEXT_MUTED, 9)
        self.note.setWordWrap(True)
        outer.addWidget(self.note)
        outer.addStretch(1)

    # --- datos -----------------------------------------------------------
    def set_history(self, records: list[RigMaintenance], rigs,
                    downtime: dict) -> None:
        """``records`` ya viene filtrado al rango y ordenado por el servicio."""
        self._clear()

        colores = {(r.name, r.test_type): r.color for r in rigs}
        # Los nombres se repiten entre bitacoras --hay tres I-25-- asi que solo
        # esos llevan de cual son.
        repetidos = {r.name for r in rigs
                     if sum(1 for o in rigs if o.name == r.name) > 1}

        total = sum(downtime.values())
        bancos = len({r.key for r in records})
        if records:
            self.subtitle.setText(
                f"{total} día" + ("s" if total != 1 else "")
                + f" fuera de servicio  ·  {bancos} banco"
                + ("s" if bancos != 1 else "")
            )
        else:
            self.subtitle.setText("")

        self.history_button.setVisible(bool(records))

        if not records:
            self.note.setText(
                "Ningún banco estuvo en mantenimiento en este periodo."
            )
            self.note.setVisible(True)
            return

        for fila, record in enumerate(records[:MAX_ROWS]):
            self.rows.addWidget(
                self._swatch(colores.get(record.key, theme.BORDER)), fila, 0
            )

            nombre = record.rig_name
            if record.rig_name in repetidos:
                etiqueta = TEST_TYPES.get(record.test_type)
                if etiqueta:
                    nombre = f"{nombre}  ·  {etiqueta.label}"
            self.rows.addWidget(_label(nombre, theme.TEXT), fila, 1)

            periodo = dates.display(record.start_date) if record.start_date else ""
            periodo += "  →  "
            periodo += (dates.display(record.end_date) if record.end_date
                        else "en curso")
            color = theme.MAINTENANCE if record.is_open else theme.TEXT_MUTED
            self.rows.addWidget(_label(periodo, color, 9), fila, 2)

            dias = record.days() or 0
            duracion = _label(f"{dias} d", theme.TEXT, 9)
            duracion.setAlignment(Qt.AlignmentFlag.AlignRight
                                  | Qt.AlignmentFlag.AlignVCenter)
            duracion.setFixedWidth(46)
            self.rows.addWidget(duracion, fila, 3)

            motivo = _label(record.reason or "sin motivo anotado",
                            theme.TEXT if record.reason else theme.TEXT_MUTED, 9)
            self.rows.addWidget(motivo, fila, 4)

        sobran = len(records) - MAX_ROWS
        if sobran > 0:
            self.note.setText(
                f"y {sobran} periodo más" if sobran == 1
                else f"y {sobran} periodos más"
            )
            self.note.setVisible(True)
        else:
            self.note.setVisible(False)

    def _swatch(self, color: str) -> QLabel:
        """El color del banco, el mismo que lleva en la tabla y en su tarjeta."""
        punto = QLabel()
        punto.setFixedSize(SWATCH, SWATCH)
        punto.setStyleSheet(
            f"background-color: {color}; border-radius: 2px; border: none;"
        )
        return punto

    def _clear(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
