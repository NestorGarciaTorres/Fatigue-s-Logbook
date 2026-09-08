"""El semaforo de la columna Dias, dibujado como punto y no como color de texto.

Antes el nivel se indicaba tinendo el numero de verde, ambar o rojo. Sobre la
fila normal se leia bien, pero el color del texto es lo primero que se pierde
cuando la fila cambia de fondo: con la seleccion clara de antes, el rojo caia a
1.05:1 -- el semaforo desaparecia justo al seleccionar la fila para mirarla.

Un punto de color no depende del color del texto: es una forma solida, y el
numero puede ir en el color de siempre, el que el estilo elija para la fila
este seleccionada o no. El punto se pinta justo a la izquierda de la cifra,
en el hueco que deja el numero al ir alineado a la derecha.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyledItemDelegate

DOT = 9          # diametro del punto
GAP = 6          # separacion entre el punto y el numero
PADDING = 5      # el que la hoja de estilos da a QTableView::item
RESERVED = DOT + GAP


class DaysBadgeDelegate(QStyledItemDelegate):
    """Antepone un punto del color del nivel al numero de dias."""

    def __init__(self, level_role, colors: dict, parent=None):
        super().__init__(parent)
        self.level_role = level_role
        self.colors = colors

    def paint(self, painter: QPainter, option, index) -> None:
        # El fondo, la seleccion, el foco y el texto los dibuja el estilo, con
        # los colores que correspondan a la fila. Aqui solo se anade el punto.
        super().paint(painter, option, index)

        level = index.data(self.level_role)
        color = self.colors.get(level) if level else None
        if color is None:
            # Una prueba cerrada no tiene semaforo: no se le pinta un punto
            # que sugiera un nivel que no significa nada.
            return

        # Justo a la izquierda del numero, no en el borde de la celda: la
        # columna es ancha y un punto pegado al margen queda tan lejos de la
        # cifra que deja de leerse como suya.
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        width = QFontMetrics(option.font).horizontalAdvance(text)
        left = option.rect.right() - PADDING - width - GAP - DOT

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(
            max(left, option.rect.left() + 2),
            option.rect.center().y() - DOT / 2 + 1,
            DOT, DOT,
        ))
        painter.restore()

    def sizeHint(self, option, index):
        """Deja sitio al punto, para que no se encime con el numero."""
        size = super().sizeHint(option, index)
        size.setWidth(size.width() + RESERVED)
        return size
