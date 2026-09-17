"""Sombras: la elevacion que QSS no sabe dibujar.

Qt **no soporta ``box-shadow``** en su hoja de estilos. Una tarjeta que quiera
levantarse del fondo tiene dos opciones: un borde duro --que es lo que hacia el
tema anterior, y por eso todo se veia como una rejilla de recuadros-- o un
``QGraphicsDropShadowEffect``, que es lo que se usa aqui.

Una advertencia que cuesta descubrir: un widget solo admite **un**
``QGraphicsEffect``. Ponerle una sombra a algo que ya tenia otro efecto quita el
anterior sin avisar. Por eso se aplica siempre al contenedor y nunca a sus
hijos.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

from theme.manager import theme

# Tres alturas y no mas. Con una escala continua cada pantalla acaba
# inventandose la suya y nada parece del mismo sistema.
LEVELS = {
    "flat": (0, 0, 0),          # (radio, desplazamiento, opacidad extra)
    "raised": (18, 2, 0),
    "floating": (34, 6, 20),
}


def apply_shadow(widget, level: str = "raised") -> QGraphicsDropShadowEffect | None:
    """Pone la sombra del nivel pedido y la devuelve, por si hay que refrescarla.

    En tema oscuro la sombra apenas se ve --negro sobre casi negro-- asi que
    ahi se sube la opacidad: lo que separa una superficie del fondo en oscuro
    es sobre todo su propio color, y la sombra solo la acompana.
    """
    radio, desplazamiento, extra = LEVELS.get(level, LEVELS["raised"])
    if radio == 0:
        widget.setGraphicsEffect(None)
        return None

    paleta = theme().palette
    color = QColor(paleta.shadow)
    if paleta.is_dark:
        color.setAlpha(min(255, color.alpha() + 40 + extra))
    else:
        color.setAlpha(min(255, color.alpha() + extra))

    efecto = QGraphicsDropShadowEffect(widget)
    efecto.setBlurRadius(radio)
    efecto.setXOffset(0)
    efecto.setYOffset(desplazamiento)
    efecto.setColor(color)
    widget.setGraphicsEffect(efecto)
    return efecto


class Elevated:
    """Mezcla para un widget que quiere sombra y que la sombra siga al tema.

    Quien la use tiene que llamar a :meth:`init_elevation` despues del
    constructor de Qt. Se reconecta a ``themeChanged`` porque el color de la
    sombra cambia con el tema, y una sombra que no se actualiza deja un halo
    negro sobre un fondo claro.
    """

    def init_elevation(self, level: str = "raised") -> None:
        self._elevation_level = level
        apply_shadow(self, level)
        theme().themeChanged.connect(self._refresh_elevation)

    def _refresh_elevation(self) -> None:
        apply_shadow(self, getattr(self, "_elevation_level", "raised"))
