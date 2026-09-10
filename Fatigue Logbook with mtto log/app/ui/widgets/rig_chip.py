"""Chip para las columnas que llevan un solo banco por fila.

Torsion, Quasi y Rotary tienen un rig por prueba, no nueve. Esa celda se
pintaba entera del color del banco, y con 400 filas del mismo T-7243 el
resultado era un bloque de color de arriba abajo que no distinguia nada y se
comia la pantalla. El color sigue estando; ocupa lo que mide el nombre.

Es el mismo lenguaje que la tira de muestras de Fatiga: cuadrado con color
para un banco, y el naranja punteado para una prueba suspendida.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate

from app.services.catalogs import contrasting_text_color
from app.ui import theme
from app.ui.widgets.sample_chips import SUSPENDED_COLOR, SUSPENDED_INSET

PADDING_X = 8
PADDING_Y = 4
RADIUS = 3
MARGIN = 5


class RigChipDelegate(QStyledItemDelegate):
    """Dibuja el nombre del banco dentro de un recuadro de su color."""

    def __init__(self, color_role, parent=None):
        super().__init__(parent)
        self.color_role = color_role

    def initStyleOption(self, option, index) -> None:
        super().initStyleOption(option, index)
        # El texto lo dibuja el chip; si lo deja el estilo salen los dos.
        option.text = ""

    def paint(self, painter: QPainter, option, index) -> None:
        super().paint(painter, option, index)

        texto = index.data(Qt.ItemDataRole.DisplayRole) or ""
        color = index.data(self.color_role)
        if not texto.strip() and not color:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(option.rect)

        metrics = option.fontMetrics
        ancho = min(
            metrics.horizontalAdvance(texto) + PADDING_X * 2,
            option.rect.width() - MARGIN * 2,
        )
        alto = metrics.height() + PADDING_Y * 2
        rect = QRectF(
            option.rect.x() + MARGIN,
            option.rect.y() + (option.rect.height() - alto) / 2,
            max(ancho, 0),
            alto,
        )

        if color:
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, RADIUS, RADIUS)
            tinta = QColor(contrasting_text_color(color))
            if color.upper() == SUSPENDED_COLOR.upper():
                # Suspendida: mismo contorno punteado que en los chips de pieza.
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(tinta, 1, Qt.PenStyle.DotLine))
                painter.drawRoundedRect(
                    rect.adjusted(SUSPENDED_INSET, SUSPENDED_INSET,
                                  -SUSPENDED_INSET, -SUSPENDED_INSET),
                    RADIUS, RADIUS,
                )
            painter.setPen(QPen(tinta))
        else:
            # Un banco que no esta en el catalogo: se ve, pero sin color.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(theme.BORDER)))
            painter.drawRoundedRect(rect, RADIUS, RADIUS)
            painter.setPen(QPen(QColor(theme.TEXT_MUTED)))

        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, texto)
        painter.restore()
