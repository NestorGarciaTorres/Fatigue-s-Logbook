"""Aviso de que otro equipo guardo algo en lo que se esta viendo.

Varias computadoras usan la misma base, y una pantalla abierta no se entera de
nada hasta que se navega o se pulsa F5: se podia elegir un banco que otro
equipo acababa de ocupar, o dar por pendiente una orden ya comenzada.

**No se recarga sola**, y es deliberado: recargar a mitad de captura pierde la
fila seleccionada y lo desplazado. El aviso dice que hay algo nuevo y quien
quiere lo trae.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout

from components import buttons, labels


class ChangesBanner(QFrame):
    """Franja discreta con lo que cambio y un boton para traerlo."""

    refreshRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("banner", "info")
        self.setFrameShape(QFrame.Shape.NoFrame)

        fila = QHBoxLayout(self)
        fila.setContentsMargins(14, 8, 10, 8)
        fila.setSpacing(12)

        self.message = labels.label("")
        fila.addWidget(self.message, 1)

        self.refresh_button = buttons.button(
            "Actualizar", buttons.PRIMARY,
            tooltip="Traer lo que guardaron otros equipos",
            on_click=self.refreshRequested.emit)
        fila.addWidget(self.refresh_button)

        self.hide()

    def show_changes(self, entries: list) -> None:
        """Ensenia el aviso, o lo esconde si no hay nada nuevo."""
        if not entries:
            self.hide()
            return

        equipos = sorted({e.machine for e in entries if e.machine})
        ultimo = max((e.changed_at for e in entries), default=None)

        cuantos = len(entries)
        texto = (f"{cuantos} cambio nuevo" if cuantos == 1
                 else f"{cuantos} cambios nuevos")
        if equipos:
            texto += f" desde {', '.join(equipos[:3])}"
            if len(equipos) > 3:
                texto += f" y {len(equipos) - 3} más"
        if isinstance(ultimo, datetime):
            texto += f"  ·  el último a las {ultimo:%H:%M}"

        self.message.setText(texto)
        self.show()
