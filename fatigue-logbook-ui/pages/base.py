"""Estructura comun de una pantalla: cabecera, cuerpo y atajos."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from components import labels


class Page(QWidget):
    """Una pantalla con titulo, subtitulo y sitio para su contenido.

    La navegacion ya no se hace con un boton 'Regresar al menu' por pantalla:
    la barra lateral esta siempre visible. Lo que se conserva son los atajos,
    porque el laboratorio ya los tiene en los dedos.
    """

    # Se emite cuando el usuario recarga a mano (F5). La ventana oculta
    # entonces el aviso de datos nuevos: ya estan en pantalla.
    refreshed = Signal()

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(24, 20, 24, 20)
        self.root.setSpacing(14)

        cabecera = QVBoxLayout()
        cabecera.setSpacing(2)
        self.title_label = labels.heading(title)
        cabecera.addWidget(self.title_label)
        if subtitle:
            self.subtitle_label = labels.secondary(subtitle)
            cabecera.addWidget(self.subtitle_label)
        else:
            self.subtitle_label = None

        fila = QHBoxLayout()
        fila.addLayout(cabecera)
        fila.addStretch(1)
        self.header_extra = QHBoxLayout()
        self.header_extra.setSpacing(8)
        fila.addLayout(self.header_extra)
        self.root.addLayout(fila)

        self.content = QVBoxLayout()
        self.content.setSpacing(12)
        self.root.addLayout(self.content, 1)

        self.shortcut(QKeySequence.StandardKey.Refresh, self.reload)

    def shortcut(self, sequence, slot) -> QShortcut:
        """Atajo que vive con la pagina y solo dispara si esta a la vista."""
        atajo = QShortcut(sequence, self)
        atajo.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        atajo.activated.connect(slot)
        return atajo

    def refresh(self) -> None:
        """Cada pantalla recarga sus datos al mostrarse."""

    def reload(self) -> None:
        """Recarga a peticion del usuario, y lo anuncia."""
        self.refresh()
        self.refreshed.emit()
