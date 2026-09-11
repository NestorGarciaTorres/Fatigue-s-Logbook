"""Leyenda de la tabla y resumen de filtros activos.

El triangulo de advertencia del Test Batch significaba "sin Work Order", pero
eso no estaba escrito en ninguna parte: habia que saberlo de memoria.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QStyle,
    QWidget,
)

from app.services import duration
from app.services.catalogs import DEFAULT_PALETTE
from app.services.filtering import ANY, TestFilters
from app.ui import theme
from app.ui.widgets.sample_chips import (
    DONE,
    MAINTENANCE,
    MAINTENANCE_COLOR,
    SUSPENDED_COLOR,
    paint_chip_shape,
)

SWATCH = 11

# Color con el que la leyenda ejemplifica "banco". Ver el comentario en Legend.
RIG_SAMPLE = DEFAULT_PALETTE[11]


def _swatch(color: str, round_: bool = False) -> QLabel:
    """Muestra de color. Redonda para el semaforo, para que la leyenda tenga
    la misma forma que el punto que se dibuja en la columna Dias."""
    label = QLabel()
    label.setFixedSize(SWATCH, SWATCH)
    radius = SWATCH // 2 if round_ else 3
    label.setStyleSheet(
        f"background-color: {color}; border-radius: {radius}px; border: none;"
    )
    return label


def _shape(color: str | None, pill: bool, dashed: bool = False) -> QLabel:
    """Muestra de la forma de un chip.

    Cuadrado y relleno para un banco; pastilla con solo contorno para un
    resultado de pieza, que ya no lleva color. Sin ``color`` hay que dibujar el
    borde: un fondo vacio no se veria. ``dashed`` reproduce el contorno
    punteado del chip de una pieza suspendida.
    """
    label = QLabel()
    label.setFixedSize(22, 12)
    radius = 6 if pill else 2
    if color:
        borde = (f"border: 1px dashed {theme.BACKGROUND};" if dashed
                 else "border: none;")
        fill = f"background-color: {color}; {borde}"
    else:
        fill = f"background-color: transparent; border: 1px solid {theme.BORDER};"
    label.setStyleSheet(f"{fill} border-radius: {radius}px;")
    return label


def _chip_sample(kind: str, color: str | None,
                 width: int = 22, height: int = 12) -> QLabel:
    """Muestra dibujada con el mismo codigo que pinta los chips de la tabla.

    Las formas de arriba se resuelven con hoja de estilos, que basta para un
    cuadrado o una pastilla. La trama diagonal del mantenimiento no se puede
    escribir en QSS, y dibujarla aparte seria tener dos versiones de la misma
    forma: se llama a la de verdad.
    """
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint_chip_shape(painter, QRectF(0.5, 0.5, width - 1, height - 1),
                     kind, color)
    painter.end()

    label = QLabel()
    label.setFixedSize(width, height)
    label.setPixmap(pixmap)
    label.setStyleSheet("background: transparent; border: none;")
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
        show_maintenance: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.show_days = show_days

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 0, 2, 0)
        self._layout.setSpacing(8)
        # La leyenda no manda sobre el ancho de la ventana. Con el minimo que
        # calcula el layout --la suma de todas las muestras y sus rotulos, que
        # ya iba por 1,561 px y con el mantenimiento pasa de 1,900-- la pagina
        # entera no podia encogerse por debajo de eso: en una pantalla de
        # portatil la bitacora nacia mas ancha que el escritorio por culpa de
        # una franja explicativa. Se deja que se recorte antes que estirar la
        # ventana; lo que explica esta ademas en los tooltips de la tabla.
        self._layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

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
            self._layout.addWidget(_caption("Días:"))
            for level in (duration.OK, duration.WARNING, duration.CRITICAL):
                color = {
                    duration.OK: theme.SUCCESS,
                    duration.WARNING: theme.WARNING,
                    duration.CRITICAL: theme.DANGER,
                }[level]
                self._layout.addWidget(_swatch(color, round_=True))
                caption = _caption("")
                self.days_labels.append(caption)
                self._layout.addWidget(caption)
            self._layout.addSpacing(10)

        if show_rigs:
            # Rigs y resultados comparten el mismo campo. Lo que los separa es
            # la forma y el relleno: el color es solo de los bancos.
            # La muestra sale de la paleta de rigs, no de PRIMARY: PRIMARY es
            # el azul de la interfaz y ya no lo lleva ningun banco, asi que
            # usarlo aqui enseniaba un color que no existe en la tabla.
            # Y no es el primero de la paleta: ese es el salmon, el unico tono
            # que se parece al naranja de 'suspendida', y ponerlos uno junto a
            # otro en la leyenda era ensenar justo la confusion que hay que
            # evitar. Este es el mas lejano de los dos (dE 86 contra 26).
            self._layout.addWidget(_shape(RIG_SAMPLE, pill=False))
            self._layout.addWidget(_caption("banco (cuadrado, con color)"))
            self._layout.addSpacing(6)
            self._layout.addWidget(_shape(None, pill=True))
            self._layout.addWidget(_caption("resultado de pieza (pastilla)"))
            self._layout.addSpacing(6)
            # Cuadrado sin relleno: se sabe donde corrio --por eso cuadrado--
            # y ya no esta ahi --por eso sin color--.
            terminada = _chip_sample(DONE, None)
            terminada.setToolTip(
                "Declarada por completo: banco, ciclos, resultado y modo de "
                "falla. Pierde el color porque ya no ocupa el banco."
            )
            self._layout.addWidget(terminada)
            self._layout.addWidget(_caption("terminada (sin color)"))
            self._layout.addSpacing(6)
            # El naranja no es un banco mas: dice que la pieza corrio y hoy
            # no esta en ninguno. Sin esta linea habria que deducirlo.
            self._layout.addWidget(_shape(SUSPENDED_COLOR, pill=False,
                                          dashed=True))
            self._layout.addWidget(_caption("suspendida (sin banco)"))

            if show_maintenance:
                # Mismo naranja: la pieza tambien esta fuera de banco. La trama
                # dice que quien la saco fue el mantenimiento del banco, no la
                # prueba. Los dias de la fila ya vienen sin ese tiempo.
                self._layout.addSpacing(6)
                muestra = _chip_sample(MAINTENANCE, MAINTENANCE_COLOR)
                muestra.setToolTip(
                    "El banco está en mantenimiento. Esos días no cuentan en "
                    "la columna Días."
                )
                self._layout.addWidget(muestra)
                self._layout.addWidget(_caption("detenida por mantenimiento"))

        self._layout.addStretch(1)

    def minimumSizeHint(self):
        """Alto el que haga falta, ancho el que haya.

        Va con ``SetNoConstraint`` de arriba: sin las dos cosas, el layout
        vuelve a ponerle a la franja el ancho de todo su contenido.
        """
        hint = super().minimumSizeHint()
        hint.setWidth(0)
        return hint

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
