"""Chips de muestras: 18 columnas condensadas en una.

Las bitacoras de Fatiga y Rotary tenian 28 columnas porque cada una de las 9
muestras ocupaba dos (rig/ciclos o revs/estatus). Ver la pieza 7 obligaba a
desplazarse horizontalmente pasando veinte columnas.

Aqui esas 18 columnas se dibujan como una tira de recuadros de color en una
sola celda. Es tambien donde el color por rig rinde de verdad: antes quedaba
repartido en nueve columnas separadas que nunca se veian juntas.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate

from app.models import SAMPLE_SLOTS
from app.services.catalogs import contrasting_text_color
from app.ui import theme

# Rol por el que el modelo entrega la lista de chips de una fila.
CHIPS_ROLE = Qt.ItemDataRole.UserRole + 2

CHIP_HEIGHT = 20
CHIP_MIN_WIDTH = 38
CHIP_GAP = 4
CHIP_RADIUS = 4
CHIP_PADDING = 6
MARGIN = 6

# Todos los chips miden lo mismo, calculado sobre la etiqueta mas larga que
# puede producir compact_number(). Asi la pieza 3 queda en la misma posicion
# en todas las filas y se pueden comparar de un vistazo entre pruebas.
REFERENCE_LABEL = "999K"

RIG = "rig"
STATUS = "status"
UNKNOWN = "unknown"

# Los resultados de pieza ya no llevan color: el color queda reservado para
# los bancos, que es donde distingue algo. Lo que separa un banco de un
# resultado es la forma -- banco cuadrado y relleno, resultado en pastilla sin
# relleno -- y eso no depende de la vista de quien lo mira.
RADIUS = {RIG: 3, STATUS: CHIP_HEIGHT // 2, UNKNOWN: 3}


@dataclass(frozen=True)
class Chip:
    """Un recuadro: texto corto, color de fondo y detalle en el tooltip."""

    label: str
    color: str | None
    tooltip: str
    kind: str = RIG


def compact_number(value: int | None) -> str:
    """Numero de 4 caracteres como maximo: 845 / 8.1K / 450K / 8.1M.

    Se sacrifica precision a proposito para que las nueve muestras quepan en
    una columna. El valor exacto esta en el tooltip, en la columna de totales
    y en la vista de columnas completas.
    """
    if value is None:
        return "--"
    if value < 1_000:
        return str(value)
    for divisor, suffix in ((1_000, "K"), (1_000_000, "M"), (1_000_000_000, "B")):
        scaled = value / divisor
        if scaled < 10:
            return f"{scaled:.1f}{suffix}".replace(".0", "")
        # round() y no <1000 a secas: 999,999 escala a 999.999, que formateado
        # sin decimales daria "1000K" -- cinco caracteres. Sube de unidad.
        if round(scaled) < 1_000:
            return f"{scaled:.0f}{suffix}"
    return f"{value / 1_000_000_000_000:.0f}T"


def chip_font(base: QFont) -> QFont:
    """Fuente de los chips: menor que la de la tabla.

    Con los 12 pt de la tabla cada chip medía 76 px y las nueve muestras no
    cabían en la columna. Es informacion secundaria -- el valor exacto esta en
    el tooltip -- asi que se dibuja mas pequena.
    """
    font = QFont(base)
    size = base.pointSizeF()
    if size > 0:
        font.setPointSizeF(max(8.0, size - 3.0))
    return font


def chip_width(metrics) -> int:
    """Ancho uniforme de un chip para las metricas dadas."""
    return max(
        CHIP_MIN_WIDTH,
        metrics.horizontalAdvance(REFERENCE_LABEL) + CHIP_PADDING * 2,
    )


def strip_width(metrics, count: int = SAMPLE_SLOTS) -> int:
    """Ancho de una tira de ``count`` chips, margenes y separaciones incluidos."""
    if count <= 0:
        return MARGIN * 2
    return MARGIN * 2 + count * chip_width(metrics) + (count - 1) * CHIP_GAP


class SampleChipsDelegate(QStyledItemDelegate):
    """Dibuja la tira de chips de la columna 'Muestras'."""

    def paint(self, painter: QPainter, option, index) -> None:
        # El texto de la celda va vacio, asi que esto pinta solo el fondo y la
        # seleccion; los chips se dibujan encima.
        super().paint(painter, option, index)

        chips = index.data(CHIPS_ROLE)
        if not chips:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(option.rect)

        # Las mismas metricas que usa sizeHint(), para que el ancho reservado y
        # el dibujado coincidan exactamente.
        font = chip_font(option.font)
        painter.setFont(font)
        width = chip_width(QFontMetrics(font))
        x = option.rect.x() + MARGIN
        y = option.rect.y() + (option.rect.height() - CHIP_HEIGHT) / 2

        for position, chip in enumerate(chips):
            if x + width > option.rect.right() - MARGIN:
                # Solo pasa si el usuario angosta la columna a mano.
                painter.setPen(QPen(QColor(theme.TEXT_MUTED)))
                painter.drawText(
                    QRectF(x, y, option.rect.right() - x, CHIP_HEIGHT),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    f"+{len(chips) - position}",
                )
                break

            rect = QRectF(x, y, width, CHIP_HEIGHT)
            radius = RADIUS.get(chip.kind, CHIP_RADIUS)

            if chip.color:
                painter.setBrush(QColor(chip.color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect, radius, radius)
                painter.setPen(QPen(QColor(contrasting_text_color(chip.color))))
            else:
                # Muestra sin rig asignado: solo contorno.
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(theme.BORDER)))
                painter.drawRoundedRect(rect, radius, radius)
                painter.setPen(QPen(QColor(theme.TEXT_MUTED)))

            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, chip.label)
            x += width + CHIP_GAP

        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        """Siempre reserva sitio para las nueve muestras.

        Antes devolvia el ancho de los chips de *esa* fila, asi que la columna
        acababa midiendo lo que necesitara la fila mas ancha del momento. Al
        capturar despues una prueba de nueve piezas la columna ya no crecia
        --se mide una sola vez por juego de columnas-- y las ultimas quedaban
        cortadas. Con un ancho fijo, ademas, la pieza 7 cae en la misma
        posicion en todas las filas.
        """
        return QSize(
            strip_width(QFontMetrics(chip_font(option.font))),
            CHIP_HEIGHT + MARGIN * 2,
        )


def chips_tooltip(chips: list[Chip]) -> str:
    """Tooltip con el detalle completo de las muestras."""
    if not chips:
        return "Sin muestras registradas"
    return "\n".join(chip.tooltip for chip in chips)
