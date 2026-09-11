"""Menu principal.

Los botones van en dos grupos: los que abren una bitacora para capturar
pruebas, y los de gestion y consulta. Antes era una rejilla unica de siete
botones identicos donde 'Ajustes' pesaba visualmente lo mismo que 'Fatiga'.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.services.identity import author_label
from app.ui import theme
from app.ui.widgets.common import heading

# (identificador de pagina, texto, acento)
LOGBOOKS = [
    ("fatigue", "Fatiga", None),
    ("torsion", "Torsión", "warning"),
    ("rotary", "Rotary", "danger"),
    ("quasi", "Quasi", None),
]

MANAGEMENT = [
    ("work_orders", "Work Orders", "success"),
    ("rigs", "Ocupación de rigs", "secondary"),
    ("dashboard", "Dashboard", "secondary"),
    ("settings", "Ajustes", "secondary"),
]

LOGBOOK_SIZE = (240, 78)
MANAGEMENT_SIZE = (240, 52)


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setStyleSheet(
        f"color: {theme.TEXT_MUTED}; font-size: 9pt; font-weight: bold;"
        f" letter-spacing: 1px;"
    )
    return label


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"color: {theme.BORDER}; background-color: {theme.BORDER};")
    line.setFixedHeight(1)
    return line


class MenuPage(QWidget):
    navigate = Signal(str)

    def __init__(self, database_name: str, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        layout.addWidget(heading("Bitácora de Pruebas"))

        container = QWidget()
        container.setMaximumWidth(540)
        inner = QVBoxLayout(container)
        inner.setSpacing(10)
        inner.setContentsMargins(0, 0, 0, 0)

        inner.addWidget(_section("Captura de pruebas"))
        inner.addLayout(self._grid(LOGBOOKS, LOGBOOK_SIZE, bold=True))

        inner.addSpacing(8)
        inner.addWidget(_separator())
        inner.addWidget(_section("Gestión y consulta"))
        inner.addLayout(self._grid(MANAGEMENT, MANAGEMENT_SIZE, bold=False))

        layout.addWidget(container, 0, Qt.AlignmentFlag.AlignCenter)

        footer = QLabel(f"{author_label()}  ·  {database_name}")
        footer.setProperty("muted", "true")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)

    def _grid(self, entries, size, bold: bool) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(10)
        for index, (key, label, accent) in enumerate(entries):
            button = QPushButton(label)
            button.setMinimumSize(*size)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if accent:
                button.setProperty("accent", accent)
            if bold:
                # Las bitacoras son a lo que se entra a diario: pesan mas.
                button.setStyleSheet("font-size: 13pt;")
            button.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
            grid.addWidget(button, index // 2, index % 2)
        return grid
