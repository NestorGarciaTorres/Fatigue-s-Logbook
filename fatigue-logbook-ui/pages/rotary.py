"""Bitacora de Rotary.

Una sola tabla, no dos pestanias como Fatiga: es la unica bitacora que mezcla
pruebas abiertas y cerradas en la misma vista, asi que ahi la columna de
estatus si distingue algo y el filtro de estatus tiene sentido.

Tampoco hay alta directa: una prueba Rotary nace de una Work Order.
"""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog

from app.models import RotaryTest
from app.services import duration, filtering
from app.services.excel_export import export_rotary, suggested_filename
from app.ui.report_export import filter_period, save_report
from components import buttons, cards
from components.filter_bar import ActiveFilters, FilterBar
from components.legend import Legend
from components.models import RotaryTableModel
from components.table import RecordTable
from pages.base import Page


class RotaryPage(Page):
    def __init__(self, context, rig_palette, parent=None):
        super().__init__("Bitácora de Rotary",
                         "Ensayos rotativos, en curso y finalizados", parent)
        self.context = context
        self.rig_palette = rig_palette
        self._records: list[RotaryTest] = []

        self.open_button = buttons.button(
            "Abrir registro", buttons.PRIMARY,
            tooltip="Doble clic sobre la fila, o Enter",
            on_click=lambda: self.table.open_selected(), enabled=False)

        self.export_button = buttons.button(
            "Exportar a Excel", buttons.SUCCESS, shortcut="Ctrl+E",
            tooltip="Las pruebas que se ven, con sus filtros",
            on_click=self.export)

        self.view_toggle = buttons.button(
            "Ver columnas completas", buttons.GHOST,
            tooltip="Alterna entre los chips de muestras y una columna por "
                    "revs y por estatus",
            checkable=True)
        self.view_toggle.toggled.connect(self._toggle_view)

        self.content.addLayout(buttons.button_row(
            self.open_button, self.export_button, self.view_toggle))

        self.card_tests = cards.StatCard("Pruebas", "0")
        self.card_samples = cards.StatCard("Piezas probadas", "0", "accent")
        self.card_revs = cards.StatCard("Revoluciones", "0", "accent")
        self.content.addLayout(cards.stat_row(
            self.card_tests, self.card_samples, self.card_revs,
            align_right=True))

        self.filters = FilterBar(show_status=True, show_wo=False)
        self.filters.changed.connect(self.apply_filters)
        self.content.addWidget(self.filters)

        self.active_filters = ActiveFilters()
        self.active_filters.removed.connect(self.filters.clear_field)
        self.active_filters.setVisible(False)
        self.content.addWidget(self.active_filters)

        self.model = RotaryTableModel(rig_palette)
        self.table = RecordTable(self.model)
        self.table.recordActivated.connect(self.open_record)
        self.table.clearFiltersRequested.connect(self.filters.clear)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.open_button.setEnabled(
                self.table.selected_record() is not None))
        self.content.addWidget(self.table, 1)

        # Sin mantenimiento: de momento solo Fatiga saca piezas del banco. En
        # Rotary el banco es de la prueba entera, asi que un mantenimiento la
        # suspenderia completa y eso es otra conversacion.
        self.legend = Legend(show_days=True, show_maintenance=False)
        self.content.addWidget(self.legend)

        self.shortcut(QKeySequence.StandardKey.Find,
                      self.filters.focus_search)

    # --- datos ------------------------------------------------------------
    def refresh(self) -> None:
        self._records = self.context.rotary.list()

        umbrales = duration.DurationThresholds.from_history(
            duration.history_durations(self._records))
        self.model.set_thresholds(umbrales)
        self.legend.set_thresholds(umbrales)

        bancos = self.context.catalogs.rig_names("rotary")
        self.filters.set_customers(self.context.catalogs.customer_names())
        self.filters.set_rigs(bancos)
        if bancos:
            self.legend.set_sample_rig(self.rig_palette, bancos[0], "rotary")

        self.apply_filters()

    def apply_filters(self) -> None:
        activos = self.filters.filters()
        visibles = filtering.apply(self._records, activos)
        self.table.set_records(visibles, filtered=not activos.is_empty())
        self.filters.set_result_count(len(visibles), len(self._records))
        self.active_filters.update_from(activos)

        self.card_tests.set_value(len(visibles))
        self.card_samples.set_value(sum(t.qty_samples for t in visibles))
        self.card_revs.set_value(sum(t.total_revs for t in visibles))

    def _toggle_view(self, full_columns: bool) -> None:
        self.table.set_compact(not full_columns)
        self.view_toggle.setText(
            "Ver vista compacta" if full_columns else "Ver columnas completas")

    # --- acciones ---------------------------------------------------------
    def open_record(self, record: RotaryTest) -> None:
        from dialogs.rotary import RotaryDialog

        dialogo = RotaryDialog(
            self.context.rotary, self.context.catalogs, self.context.audit,
            test=record, read_only=record.is_finished, parent=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def export(self) -> None:
        registros = self.table.visible_records()
        periodo = filter_period(self.filters)
        save_report(
            self, len(registros), suggested_filename("Rotary"),
            lambda ruta: export_rotary(registros, self.rig_palette.colors(),
                                       ruta, period=periodo),
        )
