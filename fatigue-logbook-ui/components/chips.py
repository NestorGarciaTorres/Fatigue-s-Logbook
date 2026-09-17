"""Chips de muestras: dieciocho columnas condensadas en una.

Fatiga y Rotary tienen nueve muestras, y cada una ocupaba dos columnas
(rig/ciclos o revs/estatus). Ver la pieza 7 obligaba a desplazarse pasando
veinte columnas. Aqui esas dieciocho se dibujan como una tira de recuadros en
una sola celda, y es donde el color por banco rinde de verdad: repartido en
nueve columnas separadas no se veia nunca junto.

**El color lo lleva el banco; la forma, el estado.** Esa division es lo que
permite que un daltonico siga leyendo la tabla, y que un chip signifique lo
mismo en los dos temas aunque su hexadecimal cambie:

- cuadrado relleno    corre en ese banco ahora mismo
- pastilla sin relleno  solo se anoto como acabo, sin constancia del banco
- contorno punteado   suspendida: corrio y hoy no esta en ningun banco
- trama diagonal      detenida: su banco esta en mantenimiento
- contorno gris       declarada por completo, ya no ocupa banco

Todo lo que se pinta pide el color a la paleta **dentro** de ``paint``. En el
proyecto anterior este modulo copiaba dos colores a constantes propias al
importar (``SUSPENDED_COLOR``, ``MAINTENANCE_COLOR``) y por eso su tema no se
podia cambiar en caliente.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QStyledItemDelegate

from theme.color import ink_for
from theme.manager import theme

# Rol por el que el modelo entrega la lista de chips de una fila.
CHIPS_ROLE = Qt.ItemDataRole.UserRole + 2

SAMPLE_SLOTS = 9

CHIP_HEIGHT = 22
CHIP_MIN_WIDTH = 40
CHIP_GAP = 4
CHIP_RADIUS = 5
CHIP_PADDING = 7
MARGIN = 6

# Todos los chips miden lo mismo, calculado sobre la etiqueta mas larga que
# puede producir compact_number(). Asi la pieza 3 cae en la misma posicion en
# todas las filas y se pueden comparar de un vistazo entre pruebas.
REFERENCE_LABEL = "999K"

RIG = "rig"
STATUS = "status"
DONE = "done"
SUSPENDED = "suspended"
MAINTENANCE = "maintenance"
UNKNOWN = "unknown"

# Banco cuadrado y relleno; resultado en pastilla sin relleno. La forma no
# depende de la vista de quien mira.
RADIUS = {RIG: 4, STATUS: CHIP_HEIGHT // 2, DONE: 4, SUSPENDED: 4,
          MAINTENANCE: 4, UNKNOWN: 4}

SUSPENDED_INSET = 1.5

# La trama no va a plena tinta: dibujada opaca, las diagonales cruzan los
# digitos y '1.5K' se lee peor que en cualquier otro chip -- se comprobo
# ampliando el pixel real. Asi la trama sigue siendo inconfundible y el numero
# manda, que es a lo que se viene.
MAINTENANCE_HATCH_ALPHA = 90


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
    una columna. El valor exacto esta en el tooltip, en la columna de totales y
    en la vista de columnas completas.
    """
    if value is None:
        return "--"
    if value < 1_000:
        return str(value)
    for divisor, sufijo in ((1_000, "K"), (1_000_000, "M"),
                            (1_000_000_000, "B")):
        escalado = value / divisor
        if escalado < 10:
            return f"{escalado:.1f}{sufijo}".replace(".0", "")
        # round() y no '< 1000' a secas: 999,999 escala a 999.999, que
        # formateado sin decimales daria "1000K" -- cinco caracteres.
        if round(escalado) < 1_000:
            return f"{escalado:.0f}{sufijo}"
    return f"{value / 1_000_000_000_000:.0f}T"


def chip_font(base: QFont) -> QFont:
    """Fuente de los chips: menor que la de la tabla.

    Con los 12 pt de la tabla cada chip medía 76 px y las nueve muestras no
    cabian en la columna. Es informacion secundaria --el valor exacto esta en
    el tooltip-- asi que se dibuja mas pequenia.
    """
    fuente = QFont(base)
    tamano = base.pointSizeF()
    if tamano > 0:
        fuente.setPointSizeF(max(8.0, tamano - 3.0))
    return fuente


def chip_width(metrics) -> int:
    return max(CHIP_MIN_WIDTH,
               metrics.horizontalAdvance(REFERENCE_LABEL) + CHIP_PADDING * 2)


def strip_width(metrics, count: int = SAMPLE_SLOTS) -> int:
    """Ancho de una tira de ``count`` chips, margenes y separaciones incluidos."""
    if count <= 0:
        return MARGIN * 2
    return MARGIN * 2 + count * chip_width(metrics) + (count - 1) * CHIP_GAP


def paint_chip_shape(painter: QPainter, rect: QRectF, kind: str,
                     color: str | None) -> QColor:
    """Dibuja el cuerpo de un chip y devuelve con que color va su texto.

    Lo llaman el delegado de la tabla y la leyenda. Si la leyenda dibujara su
    propia version, ensenaria una forma que la tabla ya no usa en cuanto una de
    las dos cambiara -- y la leyenda existe justo para que no haya que saberse
    las formas de memoria.
    """
    paleta = theme().palette
    radio = RADIUS.get(kind, CHIP_RADIUS)

    if not color:
        # Sin relleno. El contorno separa dos cosas que si son distintas: una
        # pieza terminada --que ya no ocupa banco, y por eso pierde el color--
        # va con el gris del texto, y una ranura capturada a medias con el gris
        # apagado del borde.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        borde = paleta.text_muted if kind == DONE else paleta.border
        painter.setPen(QPen(QColor(borde)))
        painter.drawRoundedRect(rect, radio, radio)
        return QColor(paleta.text_muted)

    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(rect, radio, radio)
    tinta = QColor(ink_for(color))

    if kind == SUSPENDED:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(tinta, 1, Qt.PenStyle.DotLine))
        painter.drawRoundedRect(
            rect.adjusted(SUSPENDED_INSET, SUSPENDED_INSET,
                          -SUSPENDED_INSET, -SUSPENDED_INSET),
            radio, radio,
        )
    elif kind == MAINTENANCE:
        # La trama va encima del relleno, no en lugar de el: el color tiene que
        # seguir leyendose y la diagonal solo agrega el motivo.
        painter.setPen(Qt.PenStyle.NoPen)
        trama = QColor(tinta)
        trama.setAlpha(MAINTENANCE_HATCH_ALPHA)
        painter.setBrush(QBrush(trama, Qt.BrushStyle.BDiagPattern))
        painter.drawRoundedRect(rect, radio, radio)

    return tinta


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
        fuente = chip_font(option.font)
        painter.setFont(fuente)
        ancho = chip_width(QFontMetrics(fuente))
        x = option.rect.x() + MARGIN
        y = option.rect.y() + (option.rect.height() - CHIP_HEIGHT) / 2

        for posicion, chip in enumerate(chips):
            if x + ancho > option.rect.right() - MARGIN:
                # Solo pasa si el usuario angosta la columna a mano.
                painter.setPen(QPen(QColor(theme().palette.text_muted)))
                painter.drawText(
                    QRectF(x, y, option.rect.right() - x, CHIP_HEIGHT),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    f"+{len(chips) - posicion}",
                )
                break

            rect = QRectF(x, y, ancho, CHIP_HEIGHT)
            tinta = paint_chip_shape(painter, rect, chip.kind, chip.color)
            painter.setPen(QPen(tinta))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, chip.label)
            x += ancho + CHIP_GAP

        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        """Siempre reserva sitio para las nueve muestras.

        Devolviendo el ancho de los chips de *esa* fila, la columna acababa
        midiendo lo que necesitara la fila mas ancha del momento; al capturar
        despues una prueba de nueve piezas la columna ya no crecia --se mide
        una sola vez por juego de columnas-- y las ultimas quedaban cortadas.
        """
        return QSize(strip_width(QFontMetrics(chip_font(option.font))),
                     CHIP_HEIGHT + MARGIN * 2)


def chips_tooltip(chips: list[Chip]) -> str:
    if not chips:
        return "Sin muestras registradas"
    return "\n".join(chip.tooltip for chip in chips)
