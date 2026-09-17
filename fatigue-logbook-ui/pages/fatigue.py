"""Bitacora de Fatiga: pruebas en curso y finalizadas.

Dos pestanias sobre el mismo componente: la logica es identica y solo cambia el
estatus que se pide al repositorio y si se ensenia la fecha de fin.

Todo lo que aqui se calcula se le pide a los servicios del proyecto original
--``duration`` para el semaforo, ``maintenance`` para los dias detenidos,
``filtering`` para los filtros, ``rig_usage`` donde hace falta-- y **nada** se
recalcula por aqui. Esta pantalla dibuja; los numeros los da quien los sabe.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from app.models import FINISHED, ONGOING, FatigueTest
from app.services import duration, filtering, maintenance
from app.services.excel_export import export_fatigue, suggested_filename
from app.ui.report_export import filter_period, save_report
from excel_compact import export_fatigue_ongoing_compact
from components import buttons, cards
from components.filter_bar import ActiveFilters, FilterBar
from components.legend import Legend
from components.models import FatigueTableModel
from components.table import RecordTable
from pages.base import Page


class FatigueTab(QWidget):
    """Una de las dos pestanias."""

    def __init__(self, context, rig_palette, status: str, parent=None):
        super().__init__(parent)
        self.context = context
        self.rig_palette = rig_palette
        self.status = status
        self.is_finished = status == FINISHED
        self._records: list[FatigueTest] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        # --- acciones ----------------------------------------------------
        # No hay alta directa: una prueba de fatiga nace de una Work Order.
        self.open_button = buttons.button(
            "Abrir registro", buttons.PRIMARY,
            tooltip="Doble clic sobre la fila, o Enter",
            on_click=lambda: self.table.open_selected(), enabled=False)

        self.cycles_button = buttons.button(
            "Capturar ciclos", shortcut="F2",
            tooltip="Solo los ciclos de las piezas que están corriendo",
            on_click=self.capture_cycles, enabled=False)
        self.cycles_button.setVisible(not self.is_finished)

        self.export_button = buttons.button(
            "Exportar a Excel", buttons.SUCCESS, shortcut="Ctrl+E",
            on_click=self.export)

        self.view_toggle = buttons.button(
            "Ver columnas completas", buttons.GHOST,
            tooltip="Alterna entre los chips de muestras y una columna por "
                    "rig y por ciclos",
            checkable=True)
        self.view_toggle.toggled.connect(self._toggle_view)

        layout.addLayout(buttons.button_row(
            self.open_button, self.cycles_button, self.export_button,
            self.view_toggle))

        # --- metricas ----------------------------------------------------
        # En su propia fila, nunca junto a los botones: las dos cosas juntas
        # pedian 1,650 px de minimo y la pantalla nacia mas ancha que el
        # escritorio de un portatil.
        self.card_tests = cards.StatCard("Pruebas", "0")
        self.card_samples = cards.StatCard("Piezas probadas", "0", "accent")
        self.card_cycles = cards.StatCard("Ciclos acumulados", "0", "accent")
        layout.addLayout(cards.stat_row(
            self.card_tests, self.card_samples, self.card_cycles,
            align_right=True))

        # --- filtros -----------------------------------------------------
        self.filters = FilterBar(show_status=False, show_wo=True)
        self.filters.changed.connect(self.apply_filters)
        layout.addWidget(self.filters)

        self.active_filters = ActiveFilters()
        self.active_filters.removed.connect(self.filters.clear_field)
        self.active_filters.setVisible(False)
        layout.addWidget(self.active_filters)

        # --- tabla -------------------------------------------------------
        self.model = FatigueTableModel(rig_palette,
                                       show_end_date=self.is_finished)
        self.table = RecordTable(self.model)
        self.table.recordActivated.connect(self.open_record)
        self.table.clearFiltersRequested.connect(self.filters.clear)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self._update_actions())
        if not self.is_finished:
            self.table.add_menu_action("Capturar ciclos",
                                       self.capture_cycles, "F2")
        layout.addWidget(self.table, 1)

        # El semaforo solo se marca en la pestania de pruebas abiertas.
        self.legend = Legend(show_days=not self.is_finished,
                             show_maintenance=True)
        layout.addWidget(self.legend)

    # --- datos ------------------------------------------------------------
    def refresh(self) -> None:
        self._records = self.context.fatigue.list(self.status)
        historial = self.context.fatigue.list()

        # El mantenimiento va antes que los umbrales: los dias en curso se
        # miden descontando lo que la prueba estuvo parada, y el historial con
        # el que se calibra el semaforo tiene que medirse igual. Calibrar con
        # calendario y medir en dias efectivos daria un semaforo optimista
        # siempre.
        mantenimientos = self.context.maintenance.list()
        detenidas = maintenance.stopped_by_test(historial, mantenimientos)
        self.model.set_maintenance(
            detenidas, maintenance.paused_slots(mantenimientos))

        umbrales = duration.DurationThresholds.from_history(
            duration.history_durations(historial, detenidas))
        self.model.set_thresholds(umbrales)
        if not self.is_finished:
            self.legend.set_thresholds(umbrales)

        bancos = self.context.catalogs.rig_names("fatigue")
        self.filters.set_customers(self.context.catalogs.customer_names())
        self.filters.set_rigs(bancos)

        # La muestra de 'en banco' de la leyenda lleva el color de un banco de
        # verdad, no un color de la interfaz. Ensenar ahi un color que ningun
        # rig tiene es ensenar una marca que no existe en la tabla.
        if bancos:
            self.legend.set_sample_rig(self.rig_palette, bancos[0], "fatigue")

        self.apply_filters()

    def apply_filters(self) -> None:
        activos = self.filters.filters()
        visibles = filtering.apply(self._records, activos)
        self.table.set_records(visibles, filtered=not activos.is_empty())
        self.filters.set_result_count(len(visibles), len(self._records))
        self.active_filters.update_from(activos)

        self.card_tests.set_value(len(visibles))
        self.card_samples.set_value(sum(t.qty_samples for t in visibles))
        self.card_cycles.set_value(sum(t.total_cycles for t in visibles))

    def _toggle_view(self, full_columns: bool) -> None:
        self.table.set_compact(not full_columns)
        self.view_toggle.setText(
            "Ver vista compacta" if full_columns else "Ver columnas completas")

    def _update_actions(self) -> None:
        seleccionado = self.table.selected_record() is not None
        self.open_button.setEnabled(seleccionado)
        self.cycles_button.setEnabled(seleccionado and not self.is_finished)

    def _paused_for(self, record: FatigueTest) -> dict:
        """Las piezas de esta prueba detenidas por mantenimiento, por numero."""
        return {
            slot: registro
            for (test_id, slot), registro in self.model.paused_slots.items()
            if test_id == record.id
        }

    # --- acciones ---------------------------------------------------------
    def capture_cycles(self, record: FatigueTest | None = None) -> None:
        from PySide6.QtWidgets import QDialog

        from dialogs.cycles import CyclesDialog

        record = record if record is not None else self.table.selected_record()
        if record is None or self.is_finished:
            return
        dialogo = CyclesDialog(self.context.fatigue, record,
                               paused=self._paused_for(record), parent=self)
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def open_record(self, record: FatigueTest) -> None:
        from PySide6.QtWidgets import QDialog

        from dialogs.fatigue import FatigueDialog

        abiertos = self.context.maintenance.open_records()
        dialogo = FatigueDialog(
            self.context.fatigue, self.context.catalogs, self.context.audit,
            test=record, read_only=self.is_finished,
            paused=self._paused_for(record),
            # Los bancos en mantenimiento no se ofrecen para poner una pieza:
            # capturar eso seria anotar algo que no puede estar pasando.
            unavailable_rigs=maintenance.rigs_in_maintenance(abiertos),
            parent=self,
        )
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def export(self) -> None:
        """Lo que se ve, en el orden en que se ve: los filtros deciden."""
        registros = self.table.visible_records()
        colores = self.rig_palette.colors()

        if self.is_finished:
            periodo = filter_period(self.filters)
            save_report(
                self, len(registros),
                suggested_filename("Fatigas_Finalizadas"),
                lambda ruta: export_fatigue(registros, colores, ruta,
                                            finished=True, period=periodo),
            )
            return

        # Una fila por pieza: catorce columnas en vez de cuarenta y cinco, sin
        # perder nada. El reporte de finalizadas sigue con el de siempre.
        save_report(
            self, len(registros), suggested_filename(),
            lambda ruta: export_fatigue_ongoing_compact(
                registros, colores, ruta,
                paused=self.model.paused_slots),
        )


class FatiguePage(Page):
    refreshed = Signal()

    def __init__(self, context, rig_palette, parent=None):
        super().__init__("Bitácora de Fatiga",
                         "Ensayos de fatiga en curso y finalizados", parent)
        self.context = context

        self.tabs = QTabWidget()
        self.ongoing = FatigueTab(context, rig_palette, ONGOING)
        self.finished = FatigueTab(context, rig_palette, FINISHED)
        self.tabs.addTab(self.ongoing, "En curso")
        self.tabs.addTab(self.finished, "Finalizadas")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.content.addWidget(self.tabs, 1)

        self.shortcut(QKeySequence.StandardKey.Find, self._focus_search)

    def _focus_search(self) -> None:
        self.tabs.currentWidget().filters.focus_search()

    def _on_tab_changed(self, index: int) -> None:
        self.tabs.widget(index).refresh()

    def refresh(self) -> None:
        self.tabs.currentWidget().refresh()
