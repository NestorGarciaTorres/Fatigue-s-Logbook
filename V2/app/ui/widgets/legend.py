"""Leyenda de la tabla y resumen de filtros activos.

El triangulo de advertencia del Test Batch significaba "sin Work Order", pero
eso no estaba escrito en ninguna parte: habia que saberlo de memoria.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QWidget,
)

from app.services import duration
from app.services.filtering import ANY, TestFilters
from app.ui import theme

SWATCH = 11


def _swatch(color: str) -> QLabel:
    label = QLabel()
    label.setFixedSize(SWATCH, SWATCH)
    label.setStyleSheet(
        f"background-color: {color}; border-radius: 3px; border: none;"
    )
    return label


def _shape(color: str | None, pill: bool) -> QLabel:
    """Muestra de la forma de un chip.

    Cuadrado y relleno para un banco; pastilla con solo contorno para un
    resultado de pieza, que ya no lleva color. Sin ``color`` hay que dibujar el
    borde: un fondo vacio no se veria.
    """
    label = QLabel()
    label.setFixedSize(22, 12)
    radius = 6 if pill else 2
    if color:
        fill = f"background-color: {color}; border: none;"
    else:
        fill = f"background-color: transparent; border: 1px solid {theme.BORDER};"
    label.setStyleSheet(f"{fill} border-radius: {radius}px;")
    return label


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {theme.TEXT_MUTED}; font-size: 10pt; border: none;"
    )
    return label


class Legend(QWidget):
    """Franja con el significado de los colores y los iconos de la tabla."""

    def __init__(
        self,
        show_days: bool = True,
        show_wo: bool = True,
        show_rigs: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.show_days = show_days

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 0, 2, 0)
        self._layout.setSpacing(8)

        if show_wo:
            icon = QLabel()
            icon.setPixmap(
                self.style()
                .standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
                .pixmap(14, 14)
            )
            self._layout.addWidget(icon)
            self._layout.addWidget(_caption("sin Work Order"))
            self._layout.addSpacing(10)

        self.days_labels: list[QLabel] = []
        if show_days:
            self._layout.addWidget(_caption("Dias:"))
            for level in (duration.OK, duration.WARNING, duration.CRITICAL):
                color = {
                    duration.OK: theme.SUCCESS,
                    duration.WARNING: theme.WARNING,
                    duration.CRITICAL: theme.DANGER,
                }[level]
                self._layout.addWidget(_swatch(color))
                caption = _caption("")
                self.days_labels.append(caption)
                self._layout.addWidget(caption)
            self._layout.addSpacing(10)

        if show_rigs:
            # Rigs y resultados comparten el mismo campo. Lo que los separa es
            # la forma y el relleno: el color es solo de los bancos.
            self._layout.addWidget(_shape(theme.PRIMARY, pill=False))
            self._layout.addWidget(_caption("banco (cuadrado, con color)"))
            self._layout.addSpacing(6)
            self._layout.addWidget(_shape(None, pill=True))
            self._layout.addWidget(_caption("resultado de pieza (pastilla)"))

        self._layout.addStretch(1)

    def set_thresholds(self, thresholds: duration.DurationThresholds) -> None:
        if not self.show_days or not self.days_labels:
            return
        captions = [
            f"hasta {thresholds.warning}",
            f"{thresholds.warning + 1} a {thresholds.critical - 1}",
            f"{thresholds.critical} o mas",
        ]
        for label, text in zip(self.days_labels, captions):
            label.setText(text)
            label.setToolTip(thresholds.describe())


class ActiveFilters(QWidget):
    """Chips de los filtros aplicados, con una X para quitarlos uno a uno.

    Sin esto hay que volver a la barra de filtros para recordar que esta
    aplicado, y es facil creer que 'faltan registros' cuando solo hay un
    filtro puesto.
    """

    removed = Signal(str)     # nombre del campo a limpiar

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 0, 2, 0)
        self._layout.setSpacing(6)
        self._layout.addStretch(1)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

    def update_from(self, filters: TestFilters) -> None:
        self._clear()

        chips: list[tuple[str, str]] = []
        if filters.search.strip():
            chips.append(("search", f"Texto: {filters.search.strip()}"))
        if filters.customer != ANY:
            chips.append(("customer", f"Cliente: {filters.customer}"))
        if filters.rig != ANY:
            chips.append(("rig", f"Rig: {filters.rig}"))
        if filters.test_status != ANY:
            label = "En curso" if filters.test_status == "Ongoing" else "Finalizadas"
            chips.append(("test_status", f"Estatus: {label}"))
        if filters.wo_status != ANY:
            chips.append(("wo_status", f"WO: {filters.wo_status}"))
        if filters.date_from or filters.date_to:
            from app import dates
            desde = dates.display(filters.date_from) or "?"
            hasta = dates.display(filters.date_to) or "?"
            chips.append(("dates", f"Fechas: {desde} a {hasta}"))

        self.setVisible(bool(chips))
        for index, (field, text) in enumerate(chips):
            self._layout.insertWidget(index, self._chip(field, text))

    def _chip(self, field: str, text: str) -> QWidget:
        button = QPushButton(f"{text}   x")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip("Quitar este filtro")
        button.setStyleSheet(
            f"QPushButton {{ background-color: {theme.SURFACE_ALT};"
            f" border: 1px solid {theme.BORDER}; border-radius: 10px;"
            f" color: {theme.TEXT}; font-size: 10pt; font-weight: normal;"
            f" padding: 3px 10px; }}"
            f"QPushButton:hover {{ border-color: {theme.DANGER};"
            f" color: {theme.DANGER}; }}"
        )
        button.clicked.connect(lambda _=False, f=field: self.removed.emit(f))
        return button

    def _clear(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
