"""Leyenda de la tabla.

Existe porque el significado de una marca no puede vivir solo en la memoria de
quien lleva anios usando la app: en el proyecto anterior, el triangulo del Test
Batch queria decir "sin Work Order" y eso no estaba escrito en ninguna parte.

Las muestras de forma las dibuja :func:`chips.paint_chip_shape`, la **misma**
funcion que usa la tabla. Si la leyenda dibujara su propia version, ensenaria
una forma que la tabla ya no usa en cuanto una de las dos cambiara -- y la
leyenda existe justo para lo contrario.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from components import labels
from components.chips import (
    DONE,
    MAINTENANCE,
    RIG,
    STATUS,
    SUSPENDED,
    paint_chip_shape,
)
from theme.manager import theme

SWATCH_W = 26
SWATCH_H = 15
DOT = 11


def _chip_sample(kind: str, color: str | None) -> QLabel:
    """Una muestra de chip dibujada con la misma funcion que la tabla."""
    pixmap = QPixmap(SWATCH_W, SWATCH_H)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint_chip_shape(painter, QRectF(0.5, 0.5, SWATCH_W - 1, SWATCH_H - 1),
                     kind, color)
    painter.end()

    etiqueta = QLabel()
    etiqueta.setPixmap(pixmap)
    etiqueta.setFixedSize(SWATCH_W, SWATCH_H)
    return etiqueta


def _dot(color: str) -> QLabel:
    """Punto del semaforo. Redondo, para que no se confunda con un chip."""
    pixmap = QPixmap(DOT, DOT)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(Qt.GlobalColor.transparent)
    from PySide6.QtGui import QColor
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(0, 0, DOT, DOT))
    painter.end()

    etiqueta = QLabel()
    etiqueta.setPixmap(pixmap)
    etiqueta.setFixedSize(DOT, DOT)
    return etiqueta


class Legend(QWidget):
    """Que significa cada forma y cada color de la tabla."""

    def __init__(self, show_days: bool = True, show_maintenance: bool = True,
                 parent=None):
        super().__init__(parent)
        self.show_days = show_days
        self.show_maintenance = show_maintenance
        # El banco de ejemplo se guarda por **nombre**, no por color: el color
        # se pide al cambiar de tema, como todo lo demas. Guardando el
        # hexadecimal, la muestra se quedaba con el del tema en que se cargo la
        # pantalla -- el mismo fallo que este sistema existe para evitar.
        self._sample_rig: tuple[object, str, str] | None = None
        self._thresholds = None

        # Un hijo de ancho fijo le pone suelo a la ventana entera: la franja de
        # la leyenda del proyecto anterior llegaba a pedir 1,900 px y por si
        # sola impedia que la pantalla cupiera en un portatil. Con esto la
        # leyenda encoge y, si no cabe, se recorta en vez de empujar.
        self.setSizePolicy(QSizePolicy.Policy.Ignored,
                           QSizePolicy.Policy.Fixed)

        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(14)
        self._build()
        theme().themeChanged.connect(self._rebuild)

    def minimumSizeHint(self):
        """Ancho minimo cero, a proposito.

        Con ``SetNoConstraint`` sola no basta: hacen falta las dos cosas o el
        minimo del hijo sigue mandando sobre el de la ventana.
        """
        base = super().minimumSizeHint()
        base.setWidth(0)
        return base

    # --- construccion -----------------------------------------------------
    def _clear(self) -> None:
        while self.row.count():
            item = self.row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _rebuild(self) -> None:
        self._clear()
        self._build()

    def _entry(self, muestra: QWidget, texto: str, detalle: str) -> None:
        """Una entrada de leyenda: rotulo corto, explicacion en el tooltip.

        Los rotulos van cortos a proposito. Escritos enteros, la franja pedia
        tanto ancho que se recortaba a media palabra ("suspendida, f"), que se
        lee peor que una palabra sola. Lo que significa cada marca no se pierde:
        esta en el tooltip, que no cuesta ancho.
        """
        etiqueta = labels.muted(texto)
        etiqueta.setToolTip(detalle)
        muestra.setToolTip(detalle)
        self.row.addWidget(muestra)
        self.row.addWidget(etiqueta)
        self.row.addSpacing(4)

    def _sample_color(self) -> str:
        """El color del banco de ejemplo, resuelto en el tema de ahora."""
        if self._sample_rig is not None:
            palette, nombre, tipo = self._sample_rig
            color = palette.color(nombre, tipo)
            if color:
                return color
        return theme().palette.info

    def _build(self) -> None:
        paleta = theme().palette
        ejemplo = self._sample_color()

        self._entry(_chip_sample(RIG, ejemplo), "en banco",
                    "La pieza corre en ese banco ahora mismo. El color "
                    "identifica al banco.")
        self._entry(_chip_sample(DONE, None), "declarada",
                    "Pieza declarada por completo: ya no ocupa banco, por eso "
                    "pierde el color. Dónde corrió está en el tooltip de la "
                    "fila y en la vista de columnas completas.")
        self._entry(_chip_sample(STATUS, None), "solo resultado",
                    "Solo se anotó cómo acabó, sin constancia de en qué banco "
                    "corrió. Es el caso de casi todo lo anterior a 2026.")
        self._entry(_chip_sample(SUSPENDED, paleta.warning), "suspendida",
                    "La pieza corrió y hoy no está en ningún banco: tiene "
                    "ciclos acumulados y el Test Rig vacío.")
        if self.show_maintenance:
            self._entry(_chip_sample(MAINTENANCE, paleta.maintenance),
                        "mantenimiento",
                        "El banco de esa pieza está fuera de servicio. La "
                        "prueba no avanza, y esos días no cuentan como días "
                        "de ensayo.")

        if self.show_days:
            self.row.addSpacing(10)
            self._entry(_dot(paleta.success), "al día",
                        "La prueba lleva menos tiempo del habitual.")
            self._entry(_dot(paleta.warning), "atención",
                        "Lleva más de lo habitual en este laboratorio.")
            self._entry(_dot(paleta.danger), "revisar",
                        "Lleva mucho más de lo habitual: conviene mirarla.")

        self.row.addStretch(1)
        if self._thresholds is not None:
            resumen = labels.muted(self._thresholds.describe())
            resumen.setToolTip(
                "Los umbrales salen del historial de pruebas ya cerradas de "
                "esta bitácora, así que se ajustan solos si cambia el ritmo "
                "del laboratorio.")
            self.row.addWidget(resumen)

    def set_thresholds(self, thresholds) -> None:
        """Los umbrales del semaforo, que salen del historial y cambian solos."""
        self._thresholds = thresholds
        self._rebuild()

    def set_sample_rig(self, rig_palette, name: str, test_type: str) -> None:
        """Que banco se usa de ejemplo en la muestra de 'en banco'.

        Se guarda el banco, no su color: la muestra tiene que ensenar el color
        que ese banco tiene **en el tema activo**, y eso cambia al conmutar.
        """
        self._sample_rig = (rig_palette, name, test_type)
        self._rebuild()
