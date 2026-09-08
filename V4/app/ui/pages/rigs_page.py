"""Ocupacion de rigs: que banco esta libre y que corre en cada uno.

Responder "que rig esta libre" exigia leer nueve columnas de rig en todas las
filas de la bitacora. Aqui cada banco del catalogo es una tarjeta con su color,
lo que corre en el y desde cuando.
"""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.context import AppContext
from app.models import EMPTY_RIG, ONGOING, TEST_TYPES
from app.services import duration, rig_usage
from app.services.catalogs import contrasting_text_color
from app.ui import theme
from app.ui.pages.base_page import BasePage
from app.ui.widgets.common import StatCard

CARD_WIDTH = 240
COLUMNS = 4


class RigCard(QFrame):
    """Un banco de pruebas. Emite el test batch al pulsarlo."""

    opened = Signal(object)

    def __init__(self, rig, occupants: list, finished: int = 0, parent=None):
        super().__init__(parent)
        self.rig = rig
        self.occupants = occupants
        self.finished = finished
        busy = bool(occupants)

        self.setFixedWidth(CARD_WIDTH)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        border = rig.color if busy else theme.BORDER
        self.setStyleSheet(
            f"QFrame {{ background-color: {theme.SURFACE};"
            f" border: 2px solid {border}; border-radius: 8px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # --- encabezado con el color del rig ------------------------------
        header = QLabel(rig.name)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(
            f"background-color: {rig.color};"
            f" color: {contrasting_text_color(rig.color)};"
            f" border: none; border-radius: 4px;"
            f" font-weight: bold; font-size: 12pt; padding: 4px;"
        )
        layout.addWidget(header)

        kind = TEST_TYPES[rig.test_type].label
        # Cuantas piezas ha terminado el banco va junto al tipo: es el
        # mismo dato que el panel del dashboard, y aqui responde "este
        # banco esta libre, y ha sacado esto".
        if finished:
            kind = f"{kind}  ·  {finished:,} piezas"
        subtitle = QLabel(kind)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 9pt; border: none;"
        )
        subtitle.setToolTip(
            f"{finished:,} piezas terminadas en este banco, de pruebas ya "
            f"cerradas" if finished else "Sin piezas terminadas anotadas"
        )
        layout.addWidget(subtitle)

        if not busy:
            free = QLabel("Libre")
            free.setAlignment(Qt.AlignmentFlag.AlignCenter)
            free.setStyleSheet(
                f"color: {theme.SUCCESS}; font-size: 11pt;"
                f" font-weight: bold; border: none; padding: 8px;"
            )
            layout.addWidget(free)
            layout.addStretch(1)
            return

        for record, days, level in occupants:
            layout.addWidget(self._occupant(record, days, level))

        layout.addStretch(1)

    def _occupant(self, record, days: int | None, level: str) -> QWidget:
        colors = {
            duration.OK: theme.TEXT,
            duration.WARNING: theme.WARNING,
            duration.CRITICAL: theme.DANGER,
        }

        row = QWidget()
        row.setStyleSheet("border: none;")
        box = QVBoxLayout(row)
        box.setContentsMargins(0, 2, 0, 2)
        box.setSpacing(1)

        batch = QLabel(record.test_batch)
        batch.setStyleSheet(
            f"color: {theme.TEXT}; font-size: 11pt; border: none;"
        )
        box.addWidget(batch)

        detail = QLabel(
            f"{record.customer}  ·  {days} días" if days is not None
            else record.customer
        )
        detail.setStyleSheet(
            f"color: {colors[level]}; font-size: 9pt; border: none;"
        )
        box.addWidget(detail)
        return row


class RigsPage(BasePage):
    def __init__(self, context: AppContext, parent=None):
        super().__init__("Ocupación de rigs", parent)
        self.context = context

        header = QHBoxLayout()
        self.card_busy = StatCard("Rigs ocupados", "0", theme.WARNING)
        self.card_free = StatCard("Rigs libres", "0", theme.SUCCESS)
        self.card_tests = StatCard("Pruebas en curso", "0", theme.INFO)
        for card in (self.card_busy, self.card_free, self.card_tests):
            header.addWidget(card)
        header.addStretch(1)

        refresh = QPushButton("Actualizar")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        self.content.addLayout(header)

        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet(
            f"color: {theme.WARNING}; font-size: 10pt;"
        )
        self.notice.setVisible(False)
        self.content.addWidget(self.notice)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(10)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        area.setWidget(self.container)
        self.content.addWidget(area, 1)

    def refresh(self) -> None:
        occupancy, unknown, ongoing_count = self._collect()

        # Historico completo, sin rango de fechas: aqui la pregunta es
        # cuanto ha sacado el banco, no cuanto sacó en un periodo.
        piezas = rig_usage.finished_pieces(
            self.context.fatigue.list(),
            self.context.rotary.list(),
            {"torsion": self.context.torsion.list(),
             "quasi": self.context.quasi.list()},
        )

        self._clear_grid()
        rigs = self.context.catalogs.rigs()
        busy = 0

        for index, rig in enumerate(rigs):
            occupants = occupancy.get((rig.name, rig.test_type), [])
            if occupants:
                busy += 1
            card = RigCard(rig, occupants,
                           piezas.by_rig.get((rig.name, rig.test_type), 0))
            self.grid.addWidget(card, index // COLUMNS, index % COLUMNS)

        self.card_busy.set_value(busy)
        self.card_free.set_value(len(rigs) - busy)
        self.card_tests.set_value(ongoing_count)

        if unknown:
            listed = ", ".join(
                f"{name} ({count})" for name, count in sorted(unknown.items())
            )
            # Hasta la migracion 008 esto se llenaba de 'Falla' y 'S/Falla':
            # eran resultados capturados en el campo de banco. Ya no. Lo que
            # aparezca aqui ahora es un banco de verdad que falta del catalogo.
            self.notice.setText(
                f"Valores en columnas de rig que no están en el catálogo: "
                f"{listed}. Agrégalos en Ajustes -> Rigs y colores, o "
                f"corrígelos en el registro: esas piezas no aparecen "
                f"asignadas a ningún banco."
            )
            self.notice.setVisible(True)
        else:
            self.notice.setVisible(False)

    def _collect(self):
        """Que corre en cada rig, segun las pruebas en curso.

        El cruce lo hace ``app.services.rig_usage``, que es el mismo que usa la
        tarjeta del dashboard: cuando cada pantalla lo calculaba por su cuenta,
        una decia 11 bancos ocupados y la otra 10.
        """
        fatigue = self.context.fatigue.list(ONGOING)
        rotary = self.context.rotary.list(ONGOING)
        ocupados, fuera = rig_usage.occupancy(
            fatigue, rotary,
            rig_usage.catalog_keys(self.context.catalogs.rigs()),
        )

        # La antiguedad se calcula aparte porque cada bitacora tiene sus
        # propios umbrales: los de Fatiga salen del historial de Fatiga.
        umbrales = {
            "fatigue": duration.DurationThresholds.from_history(
                duration.history_durations(self.context.fatigue.list())
            ),
            "rotary": duration.DurationThresholds.from_history(
                duration.history_durations(self.context.rotary.list())
            ),
        }

        occupancy: dict[tuple[str, str], list] = defaultdict(list)
        for (nombre, tipo), pruebas in ocupados.items():
            for test in pruebas:
                days = duration.days_running(test.start_date)
                level = umbrales[tipo].level(days)
                occupancy[(nombre, tipo)].append((test, days, level))

        return occupancy, fuera, len(fatigue) + len(rotary)
    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
