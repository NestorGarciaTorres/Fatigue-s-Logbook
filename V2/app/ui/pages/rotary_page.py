"""Bitacora de Rotary.

Conserva forma propia porque cada muestra lleva revoluciones y estatus, no rig
y ciclos. Reemplaza a ``logbooks/logbook_rotary.py``, que hacia ``SELECT *`` y
dependia del orden fisico de las columnas.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton

from app.context import AppContext
from app.models import ROTARY, RotaryTest
from app.services import duration, filtering
from app.ui.dialogs.rotary_dialog import RotaryDialog
from app.ui.models.table_models import RotaryTableModel
from app.ui.pages.base_page import BasePage
from app.ui.widgets.common import StatCard
from app.ui.widgets.filter_bar import FilterBar
from app.ui.widgets.legend import ActiveFilters, Legend
from app.ui.widgets.record_table import RecordTable


class RotaryPage(BasePage):
    def __init__(self, context: AppContext, parent=None):
        super().__init__("Bitacora de Rotary", parent)
        self.context = context
        self._records: list[RotaryTest] = []

        actions = QHBoxLayout()
        # Ya no hay alta directa: una prueba Rotary nace de una Work Order.
        # El formulario es el mismo, pero se abre desde esa pantalla.

        self.view_toggle = QPushButton("Ver columnas completas")
        self.view_toggle.setProperty("accent", "secondary")
        self.view_toggle.setCheckable(True)
        self.view_toggle.setToolTip(
            "Alterna entre los chips de muestras y una columna por revs y por "
            "estatus"
        )
        self.view_toggle.toggled.connect(self._toggle_view)
        actions.addWidget(self.view_toggle)

        actions.addStretch(1)

        self.card_tests = StatCard("Pruebas", "0", accent=ROTARY.accent)
        self.card_samples = StatCard("Piezas probadas", "0", accent=ROTARY.accent)
        self.card_revs = StatCard("Revoluciones", "0", accent=ROTARY.accent)
        for card in (self.card_tests, self.card_samples, self.card_revs):
            actions.addWidget(card)
        self.content.addLayout(actions)

        self.filters = FilterBar(show_status=True, show_wo=False)
        self.filters.changed.connect(self.apply_filters)
        self.content.addWidget(self.filters)

        self.active_filters = ActiveFilters()
        self.active_filters.removed.connect(self.filters.clear_field)
        self.active_filters.setVisible(False)
        self.content.addWidget(self.active_filters)

        self.model = RotaryTableModel(context.catalogs)
        self.table = RecordTable(self.model)
        self.table.recordActivated.connect(self.open_record)
        self.table.clearFiltersRequested.connect(self.filters.clear)
        self.content.addWidget(self.table, 1)

        self.legend = Legend(show_days=True, show_wo=False)
        self.content.addWidget(self.legend)

    def refresh(self) -> None:
        self._records = self.context.rotary.list()

        thresholds = duration.DurationThresholds.from_history(
            duration.history_durations(self._records)
        )
        self.model.set_thresholds(thresholds)
        self.legend.set_thresholds(thresholds)

        self.filters.set_customers(self.context.catalogs.customer_names())
        self.filters.set_rigs(self.context.catalogs.rig_names("rotary"))
        self.apply_filters()

    def apply_filters(self) -> None:
        active = self.filters.filters()
        visible = filtering.apply(self._records, active)
        self.table.set_records(visible, filtered=not active.is_empty())
        self.filters.set_result_count(len(visible), len(self._records))
        self.active_filters.update_from(active)
        self.card_tests.set_value(len(visible))
        self.card_samples.set_value(sum(t.qty_samples for t in visible))
        self.card_revs.set_value(sum(t.total_revs for t in visible))

    def _toggle_view(self, full_columns: bool) -> None:
        self.table.set_compact(not full_columns)
        self.view_toggle.setText(
            "Ver vista compacta" if full_columns else "Ver columnas completas"
        )

    def open_record(self, record: RotaryTest) -> None:
        dialog = RotaryDialog(
            self.context.rotary, self.context.catalogs, self.context.audit,
            test=record, read_only=record.is_finished, parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
