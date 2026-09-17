"""Tipografia y etiquetas de estado.

Ninguna de estas funciones pone un color ni un tamano: **ponen una propiedad**
y el color y el tamano salen de la hoja de estilos. Es toda la diferencia entre
un tema conmutable y uno que no lo es -- en el proyecto anterior estas mismas
etiquetas se creaban con ``setStyleSheet(f"color: {theme.TEXT_MUTED}; ...")`` y
ese color quedaba congelado en el widget para siempre.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel

# Los roles que entiende la hoja de estilos (QLabel[role="..."]).
DISPLAY = "display"
HEADING = "heading"
SUBHEADING = "subheading"
SECONDARY = "secondary"
MUTED = "muted"
EYEBROW = "eyebrow"
METRIC = "metric"


def label(text: str = "", role: str | None = None,
          wrap: bool = False, align=None) -> QLabel:
    """Una etiqueta con su papel tipografico declarado."""
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    if wrap:
        widget.setWordWrap(True)
    if align is not None:
        widget.setAlignment(align)
    return widget


def display(text: str) -> QLabel:
    return label(text, DISPLAY)


def heading(text: str) -> QLabel:
    return label(text, HEADING)


def subheading(text: str) -> QLabel:
    return label(text, SUBHEADING)


def secondary(text: str, wrap: bool = False) -> QLabel:
    return label(text, SECONDARY, wrap=wrap)


def muted(text: str, wrap: bool = False) -> QLabel:
    return label(text, MUTED, wrap=wrap)


def eyebrow(text: str) -> QLabel:
    """Rotulo de seccion, en mayusculas y pequenio."""
    return label(text.upper(), EYEBROW)


def metric(text: str = "0") -> QLabel:
    return label(text, METRIC)


def pill(text: str, kind: str = "neutral") -> QLabel:
    """Etiqueta de estado. ``kind``: neutral, success, warning, danger,
    info o maintenance."""
    widget = QLabel(text)
    widget.setProperty("pill", kind)
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget


def set_pill(widget: QLabel, text: str, kind: str) -> None:
    """Cambia una etiqueta de estado ya creada.

    Se repolisa a mano porque Qt no vuelve a aplicar la hoja al cambiar una
    propiedad: sin esto, la pastilla cambia de texto pero no de color.
    """
    widget.setText(text)
    if widget.property("pill") != kind:
        widget.setProperty("pill", kind)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


def divider() -> QFrame:
    """Linea de separacion de 1 px, del color del tema."""
    linea = QFrame()
    linea.setProperty("role", "divider")
    linea.setFrameShape(QFrame.Shape.NoFrame)
    linea.setFixedHeight(1)
    return linea


def elide(text: str, limit: int) -> str:
    """Acorta por el centro y conserva las dos puntas.

    Para rutas y nombres largos: lo que identifica una ruta es el principio
    (el servidor o la unidad) y el final (el archivo); lo de en medio es lo
    prescindible. Un ``QLabel`` con ``wordWrap`` no sirve aqui -- un texto sin
    espacios no se puede partir, y su ancho minimo acaba siendo el texto
    entero.
    """
    if len(text) <= limit:
        return text
    mitad = (limit - 3) // 2
    return f"{text[:mitad]}...{text[-mitad:]}"
