"""Estructura comun de las paginas de bitacora."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from app.ui.widgets.common import heading


class BasePage(QWidget):
    """Titulo, contenido y boton de regreso.

    En la version anterior el regreso implicaba ``destroy()`` de un Toplevel,
    ``deiconify()`` del padre y reposicionar la ventana en el monitor correcto
    a mano. Con un QStackedWidget basta con cambiar de pagina.
    """

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._back_callback = None

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(10)
        self._layout.addWidget(heading(title))

        self.content = QVBoxLayout()
        self.content.setSpacing(10)
        self._layout.addLayout(self.content, 1)

        footer = QHBoxLayout()
        self.back_button = QPushButton("Regresar al menu")
        self.back_button.setProperty("accent", "secondary")
        self.back_button.clicked.connect(self._go_back)
        footer.addWidget(self.back_button, 0, Qt.AlignmentFlag.AlignLeft)
        footer.addStretch(1)
        self._layout.addLayout(footer)

    def set_back_callback(self, callback) -> None:
        self._back_callback = callback

    def _go_back(self) -> None:
        if self._back_callback:
            self._back_callback()

    def refresh(self) -> None:
        """Cada pagina recarga sus datos al mostrarse."""
