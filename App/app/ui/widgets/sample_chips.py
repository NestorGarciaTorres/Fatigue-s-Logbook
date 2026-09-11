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
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
)
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
DONE = "done"
SUSPENDED = "suspended"
MAINTENANCE = "maintenance"
UNKNOWN = "unknown"

# Los resultados de pieza ya no llevan color: el color queda reservado para
# los bancos, que es donde distingue algo. Lo que separa un banco de un
# resultado es la forma -- banco cuadrado y relleno, resultado en pastilla sin
# relleno -- y eso no depende de la vista de quien lo mira.
RADIUS = {RIG: 3, STATUS: CHIP_HEIGHT // 2, DONE: 3, SUSPENDED: 3,
          MAINTENANCE: 3, UNKNOWN: 3}

# El naranja de una pieza suspendida. Es el mismo WARNING de la interfaz, y no
# uno cualquiera: la migracion 010 lo tiene entre los colores reservados, asi
# que ningun banco puede acercarsele (dE >= 24). Sin esa reserva un chip
# naranja se leeria como "corriendo en el banco naranja", que es justo lo
# contrario de lo que significa.
SUSPENDED_COLOR = theme.WARNING

# Ademas del color, la forma: la pieza suspendida lleva un contorno punteado
# por dentro del relleno, igual que las ranuras inactivas del formulario. El
# color solo no basta para quien no distingue un naranja de un salmon.
SUSPENDED_INSET = 1.5

# Rojo para el banco en mantenimiento, ademas de la trama diagonal. Naranja y
# rojo distan dE 47: una pieza suspendida por la prueba y una detenida por el
# banco ya no se parecen, y la trama lo confirma para quien no separe los dos
# tonos.
#
# El rojo no es DANGER, y el porque esta medido. Sobre los tres fondos de fila
# DANGER da 3.58 / 2.49 / 3.99: en la franja alterna el numero del chip cae por
# debajo del minimo de 3:1 -- el mismo fallo que dejo nueve de dieciseis
# colores ilegibles cuando se aclaro esa franja. Se barrieron los rojos que si
# llegan a 3:1 en las tres, y el mejor es este.
#
# Tiene un precio y conviene saberlo: queda a dE 23.5 del salmon del rig
# I-02-1, medio punto por debajo del dE 24 que se exige entre un chip y un
# banco. Se acepta porque aqui esa distancia no trabaja sola -- ningun chip de
# banco lleva trama, asi que la forma separa los dos casos aunque el color se
# acerque -- y porque la alternativa era sacrificar la legibilidad del numero,
# que no tiene nada que la respalde.
MAINTENANCE_COLOR = theme.MAINTENANCE

# La trama no va a plena tinta: dibujada opaca, las diagonales cruzan los
# digitos y '1.5K' se lee peor que en cualquier otro chip -- se comprobo
# ampliando el pixel real. Con esta transparencia la trama sigue siendo
# inconfundible y el numero manda, que es a lo que se viene.
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


def paint_chip_shape(painter: QPainter, rect: QRectF, kind: str,
                     color: str | None) -> QColor:
    """Dibuja el cuerpo de un chip y devuelve con que color va su texto.

    Lo llaman el delegado de la tabla y la leyenda. Si la leyenda dibujara su
    propia version, ensenaria una forma que la tabla ya no usa en cuanto una de
    las dos cambiara -- y la leyenda existe justo para que no haya que saberse
    las formas de memoria.
    """
    radius = RADIUS.get(kind, CHIP_RADIUS)

    if not color:
        # Sin relleno. El contorno separa dos cosas que si son distintas: una
        # pieza terminada --que ya no ocupa banco, y por eso pierde el color--
        # se dibuja con el gris del texto, y una ranura capturada a medias con
        # el gris apagado del borde.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        borde = theme.TEXT_MUTED if kind == DONE else theme.BORDER
        painter.setPen(QPen(QColor(borde)))
        painter.drawRoundedRect(rect, radius, radius)
        return QColor(theme.TEXT_MUTED)

    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(rect, radius, radius)
    ink = QColor(contrasting_text_color(color))

    if kind == SUSPENDED:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(ink, 1, Qt.PenStyle.DotLine))
        painter.drawRoundedRect(
            rect.adjusted(SUSPENDED_INSET, SUSPENDED_INSET,
                          -SUSPENDED_INSET, -SUSPENDED_INSET),
            radius, radius,
        )
    elif kind == MAINTENANCE:
        # La trama va encima del relleno, no en lugar de el: el naranja tiene
        # que seguir leyendose como 'fuera de banco' y la diagonal solo agrega
        # el motivo.
        painter.setPen(Qt.PenStyle.NoPen)
        trama = QColor(ink)
        trama.setAlpha(MAINTENANCE_HATCH_ALPHA)
        painter.setBrush(QBrush(trama, Qt.BrushStyle.BDiagPattern))
        painter.drawRoundedRect(rect, radius, radius)

    return ink


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
            ink = paint_chip_shape(painter, rect, chip.kind, chip.color)

            painter.setPen(QPen(ink))
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
