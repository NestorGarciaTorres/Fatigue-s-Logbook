"""Bitacora de Fatiga: pruebas en curso y finalizadas.

Unifica ``logbooks/fatigue_curr_logbook.py`` y
``logbooks/fatigue_cmplt_logbook.py``, que eran dos ventanas separadas con la
misma consulta y la misma tabla, distintas solo en una columna y un WHERE.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.context import AppContext
from app.models import FINISHED, ONGOING, FatigueTest
from app.services import duration, filtering
from app.services.excel_export import export_fatigue_ongoing, suggested_filename
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.models.table_models import FatigueTableModel
from app.ui.widgets.common import StatCard, heading
from app.ui.widgets.filter_bar import FilterBar
from app.ui.widgets.legend import ActiveFilters, Legend
from app.ui.widgets.record_table import RecordTable


class FatigueTab(QWidget):
    """Una de las dos pestanas. La logica es identica; cambia el estatus."""

    def __init__(self, context: AppContext, status: str, parent=None):
        super().__init__(parent)
        self.context = context
        self.status = status
        self.is_finished = status == FINISHED
        self._records: list[FatigueTest] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- acciones ----------------------------------------------------
        actions = QHBoxLayout()

        # Ya no hay alta directa: una prueba de fatiga nace de una Work Order.
        # El formulario es el mismo, pero se abre desde esa pantalla.
        self.export_button = QPushButton("Exportar a Excel")
        self.export_button.setProperty("accent", "success")
        self.export_button.clicked.connect(self.export)
        actions.addWidget(self.export_button)
        # El reporte pedido es de pruebas en curso.
        self.export_button.setVisible(not self.is_finished)

        # Vista compacta (chips) frente a las 28 columnas de antes.
        self.view_toggle = QPushButton("Ver columnas completas")
        self.view_toggle.setProperty("accent", "secondary")
        self.view_toggle.setCheckable(True)
        self.view_toggle.setToolTip(
            "Alterna entre los chips de muestras y una columna por rig y por "
            "ciclos"
        )
        self.view_toggle.toggled.connect(self._toggle_view)
        actions.addWidget(self.view_toggle)

        actions.addStretch(1)

        self.card_tests = StatCard("Pruebas", "0")
        self.card_samples = StatCard("Piezas probadas", "0")
        self.card_cycles = StatCard("Ciclos acumulados", "0")
        for card in (self.card_tests, self.card_samples, self.card_cycles):
            actions.addWidget(card)

        layout.addLayout(actions)

        # --- filtros -----------------------------------------------------
        self.filters = FilterBar(show_status=False, show_wo=True)
        self.filters.changed.connect(self.apply_filters)
        layout.addWidget(self.filters)

        self.active_filters = ActiveFilters()
        self.active_filters.removed.connect(self.filters.clear_field)
        self.active_filters.setVisible(False)
        layout.addWidget(self.active_filters)

        # --- tabla -------------------------------------------------------
        self.model = FatigueTableModel(
            context.catalogs, show_end_date=self.is_finished
        )
        self.table = RecordTable(self.model)
        self.table.recordActivated.connect(self.open_record)
        self.table.clearFiltersRequested.connect(self.filters.clear)
        layout.addWidget(self.table, 1)

        # La antiguedad solo se marca en la pestana de pruebas abiertas.
        self.legend = Legend(show_days=True, show_wo=not self.is_finished)
        layout.addWidget(self.legend)

    # --- datos -----------------------------------------------------------
    def refresh(self) -> None:
        self._records = self.context.fatigue.list(self.status)

        # Umbrales del semaforo, calculados del historial de esta bitacora.
        thresholds = duration.DurationThresholds.from_history(
            duration.history_durations(self.context.fatigue.list())
        )
        self.model.set_thresholds(thresholds)
        self.legend.set_thresholds(thresholds)

        self.filters.set_customers(self.context.catalogs.customer_names())
        self.filters.set_rigs(self.context.catalogs.rig_names("fatigue"))
        self.apply_filters()

    def apply_filters(self) -> None:
        active = self.filters.filters()
        visible = filtering.apply(self._records, active)
        self.table.set_records(visible, filtered=not active.is_empty())
        self.filters.set_result_count(len(visible), len(self._records))
        self.active_filters.update_from(active)

        self.card_tests.set_value(len(visible))
        self.card_samples.set_value(sum(t.qty_samples for t in visible))
        self.card_cycles.set_value(sum(t.total_cycles for t in visible))

    def _toggle_view(self, full_columns: bool) -> None:
        self.table.set_compact(not full_columns)
        self.view_toggle.setText(
            "Ver vista compacta" if full_columns else "Ver columnas completas"
        )

    # --- acciones --------------------------------------------------------
    def open_record(self, record: FatigueTest) -> None:
        dialog = FatigueDialog(
            self.context.fatigue, self.context.catalogs, self.context.audit,
            test=record, read_only=self.is_finished, parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def export(self) -> None:
        records = self.table.visible_records()
        if not records:
            QMessageBox.information(
                self, "Sin datos", "No hay registros que exportar con estos filtros."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte", suggested_filename(), "Excel (*.xlsx)"
        )
        if not path:
            return

        try:
            saved = export_fatigue_ongoing(
                records, self.context.catalogs.colors(), path
            )
        except Exception as error:  # pragma: no cover
            QMessageBox.critical(self, "Error al exportar", str(error))
            return

        QMessageBox.information(
            self, "Reporte generado",
            f"Se exportaron {len(records)} registro(s) a:\n{saved}",
        )


class FatiguePage(QWidget):
    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)
        layout.addWidget(heading("Bitacora de Fatiga"))

        self.tabs = QTabWidget()
        self.ongoing = FatigueTab(context, ONGOING)
        self.finished = FatigueTab(context, FINISHED)
        self.tabs.addTab(self.ongoing, "En curso")
        self.tabs.addTab(self.finished, "Finalizadas")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 1)

        back = QPushButton("Regresar al menu")
        back.setProperty("accent", "secondary")
        back.clicked.connect(self._go_back)
        row = QHBoxLayout()
        row.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        row.addStretch(1)
        layout.addLayout(row)

        self._back_callback = None

    def set_back_callback(self, callback) -> None:
        self._back_callback = callback

    def _go_back(self) -> None:
        if self._back_callback:
            self._back_callback()

    def _on_tab_changed(self, index: int) -> None:
        self.tabs.widget(index).refresh()

    def refresh(self) -> None:
        self.tabs.currentWidget().refresh()
