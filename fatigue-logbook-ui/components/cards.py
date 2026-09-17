"""Tarjetas: superficies que se levantan del fondo.

Sustituyen a la ``StatCard`` del proyecto anterior, que se pintaba con tres
``setStyleSheet`` inline --marco, titulo y valor-- con los colores congelados
al construirla. Aqui el color sale de la hoja y el relieve de una sombra, asi
que la misma tarjeta vale en los dos temas.

El color de acento de una metrica se resuelve **al pintar**, no al crear: una
tarjeta creada en tema claro y vista en oscuro tiene que ensenar el acento del
tema en que se esta mirando.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from components import labels
from components.elevation import Elevated
from theme.manager import theme


class Card(QFrame, Elevated):
    """Superficie elevada con un layout vertical dentro."""

    def __init__(self, level: str = "raised", surface: str = "card",
                 parent=None):
        super().__init__(parent)
        self.setProperty("surface", surface)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 14)
        self.body.setSpacing(8)

        self.init_elevation(level)

    def add(self, widget: QWidget, stretch: int = 0):
        self.body.addWidget(widget, stretch)
        return widget


# Los acentos que puede llevar una metrica. Se guarda el **nombre** del token y
# no su valor: el valor se pide a la paleta en cada repintado, que es lo que
# permite cambiar de tema sin reconstruir la tarjeta.
ACCENTS = ("text", "accent", "success", "warning", "danger", "info",
           "maintenance")


class StatCard(Card):
    """Un numero grande con su rotulo. La cabecera de cada bitacora lleva tres.

    ``accent`` es el nombre de un token, no un color: 'success', 'maintenance',
    'text'. Pasar un hexadecimal aqui seria volver a congelar el color.
    """

    def __init__(self, title: str, value: str = "0", accent: str = "text",
                 hint: str = "", parent=None):
        super().__init__(parent=parent)
        self.body.setSpacing(2)
        self._accent = accent if accent in ACCENTS else "text"

        self.title_label = labels.muted(title)
        self.value_label = labels.metric(str(value))
        self.body.addWidget(self.title_label)
        self.body.addWidget(self.value_label)

        if hint:
            self.setToolTip(hint)

        self._paint_accent()
        theme().themeChanged.connect(self._paint_accent)

    def _paint_accent(self) -> None:
        # El unico color que se escribe a mano en toda la interfaz, y se
        # reescribe en cada cambio de tema por eso mismo. No se puede sacar de
        # la hoja porque el acento es un dato de la tarjeta, no de su tipo.
        color = getattr(theme().palette, self._accent)
        self.value_label.setStyleSheet(f"color: {color};")

    def set_value(self, value) -> None:
        if isinstance(value, int):
            self.value_label.setText(f"{value:,}")
        else:
            self.value_label.setText(str(value))

    def set_accent(self, accent: str) -> None:
        if accent in ACCENTS and accent != self._accent:
            self._accent = accent
            self._paint_accent()


def stat_row(*cards: StatCard, align_right: bool = False) -> QHBoxLayout:
    """Fila de metricas.

    Va en su **propia** fila, nunca junto a los botones de accion: en el
    proyecto anterior las dos cosas juntas pedian 1,650 px de minimo en Fatiga
    y 1,862 en Work Orders, y la pantalla nacia mas ancha que el escritorio de
    un portatil.
    """
    fila = QHBoxLayout()
    fila.setSpacing(10)
    if align_right:
        fila.addStretch(1)
    for card in cards:
        fila.addWidget(card)
    if not align_right:
        fila.addStretch(1)
    return fila


class Section(QWidget):
    """Un bloque con su rotulo encima. Para agrupar sin meter un marco mas."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(labels.eyebrow(title), 0, Qt.AlignmentFlag.AlignLeft)
        self.body = layout

    def add(self, widget: QWidget, stretch: int = 0):
        self.body.addWidget(widget, stretch)
        return widget
