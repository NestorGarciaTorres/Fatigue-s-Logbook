"""Botones.

Una sola fabrica con variantes declaradas por propiedad. La variante
``primary`` va **rellena** y el resto no: en el tema anterior los botones eran
todos contorneados y del mismo grosor, asi que la accion principal de una
pantalla no se distinguia de las otras cinco.

Dos cosas aprendidas que se respetan aqui:

- **Un ``QPushButton`` no acorta su texto.** Si no cabe, Qt lo recorta por los
  dos lados ("'oner en mantenimient") sin avisar. Por eso :func:`button` acepta
  un ``tooltip`` y la recomendacion es rotulo corto y detalle en el tooltip, en
  vez de rotulos largos que luego hay que adivinar.
- **Una fila horizontal no encoge.** Botones y tarjetas de metrica en la misma
  fila sumaban 1,650 px de minimo en Fatiga. La solucion es partir la fila, no
  acortar los rotulos a la fuerza; :func:`button_row` deja eso explicito.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy

PRIMARY = "primary"
SECONDARY = "secondary"      # el aspecto por omision: relleno de superficie
GHOST = "ghost"
SUCCESS = "success"
DANGER = "danger"
WARNING = "warning"
MAINTENANCE = "maintenance"


def button(text: str, variant: str = SECONDARY, *, tooltip: str = "",
           shortcut: str = "", on_click=None, enabled: bool = True,
           checkable: bool = False) -> QPushButton:
    """Un boton con su variante puesta como propiedad, no como estilo."""
    widget = QPushButton(text)
    if variant and variant != SECONDARY:
        widget.setProperty("variant", variant)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setEnabled(enabled)

    if checkable:
        widget.setCheckable(True)
    if shortcut:
        widget.setShortcut(shortcut)
        # El atajo se anuncia siempre: un atajo que no esta escrito en ningun
        # sitio es un atajo que solo usa quien lo programo.
        tooltip = f"{tooltip}  ({shortcut})" if tooltip else shortcut
    if tooltip:
        widget.setToolTip(tooltip)
    if on_click is not None:
        widget.clicked.connect(lambda _checked=False: on_click())
    return widget


def nav_button(text: str, on_click=None) -> QPushButton:
    """Elemento de la navegacion lateral. Se marca activo con ``set_active``."""
    widget = QPushButton(text)
    widget.setProperty("nav", "item")
    widget.setProperty("active", "false")
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                         QSizePolicy.Policy.Fixed)
    if on_click is not None:
        widget.clicked.connect(lambda _checked=False: on_click())
    return widget


def set_active(widget: QPushButton, active: bool) -> None:
    """Marca o desmarca un elemento de navegacion.

    Con repolish, porque Qt no reaplica la hoja al cambiar una propiedad: sin
    esto el elemento activo no se distingue de los demas.
    """
    valor = "true" if active else "false"
    if widget.property("active") == valor:
        return
    widget.setProperty("active", valor)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def button_row(*widgets, stretch_at_end: bool = True) -> QHBoxLayout:
    """Una fila de botones.

    Se deja el espacio sobrante al final y no entre los botones: agrupados a la
    izquierda se leen como un grupo de acciones, repartidos parecen cinco cosas
    sin relacion.
    """
    fila = QHBoxLayout()
    fila.setSpacing(8)
    for widget in widgets:
        if widget is None:
            fila.addStretch(1)
        else:
            fila.addWidget(widget)
    if stretch_at_end:
        fila.addStretch(1)
    return fila
