"""Bitacoras de Torsion y Quasi.

Las dos comparten forma --una sola fecha, un solo rig, sin estatus-- asi que
comparten pantalla, parametrizada por su ``TestTypeConfig``.

El alta directa solo la conserva **Torsion**: ahi llega la pieza y se corre sin
orden previa, asi que sin ese boton no habria manera de registrarla. Quasi,
como Fatiga y Rotary, nace de una Work Order -- y el boton no se pone apagado:
un control que hay que explicar estorba mas que su ausencia.
"""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog

from app.models import DIRECT_ENTRY_TEST_TYPES, GenericTest, TestTypeConfig
from app.services import filtering
from app.services.excel_export import export_generic, suggested_filename
from app.ui.report_export import filter_period, save_report
from components import buttons, cards
from components.filter_bar import ActiveFilters, FilterBar
from components.models import GenericTableModel
from components.table import RecordTable
from pages.base import Page

SUBTITLES = {
    "torsion": "Ensayos de torsión",
    "quasi": "Ensayos cuasiestáticos",
}


class GenericPage(Page):
    def __init__(self, context, rig_palette, config: TestTypeConfig,
                 parent=None):
        super().__init__(f"Bitácora de {config.label}",
                         SUBTITLES.get(config.key, ""), parent)
        self.context = context
        self.rig_palette = rig_palette
        self.config = config
        self._records: list[GenericTest] = []

        acciones = []
        self.new_button = None
        if config.key in DIRECT_ENTRY_TEST_TYPES:
            self.new_button = buttons.button(
                "Nuevo registro", buttons.PRIMARY, shortcut="Ctrl+N",
                on_click=self.open_new)
            acciones.append(self.new_button)

        self.open_button = buttons.button(
            "Abrir registro",
            buttons.PRIMARY if self.new_button is None else buttons.SECONDARY,
            tooltip="Doble clic sobre la fila, o Enter",
            on_click=lambda: self.table.open_selected(), enabled=False)
        acciones.append(self.open_button)

        self.export_button = buttons.button(
            "Exportar a Excel", buttons.SUCCESS, shortcut="Ctrl+E",
            tooltip="Las pruebas que se ven, con sus filtros",
            on_click=self.export)
        acciones.append(self.export_button)

        self.content.addLayout(buttons.button_row(*acciones))

        self.card_tests = cards.StatCard("Pruebas", "0")
        self.card_samples = cards.StatCard("Piezas probadas", "0", "accent")
        self.content.addLayout(cards.stat_row(
            self.card_tests, self.card_samples, align_right=True))

        # Torsion y Quasi no manejan estatus ni Work Order.
        self.filters = FilterBar(show_status=False, show_wo=False)
        self.filters.changed.connect(self.apply_filters)
        self.content.addWidget(self.filters)

        self.active_filters = ActiveFilters()
        self.active_filters.removed.connect(self.filters.clear_field)
        self.active_filters.setVisible(False)
        self.content.addWidget(self.active_filters)

        self.model = GenericTableModel(rig_palette, config.key)
        self.table = RecordTable(self.model)
        self.table.recordActivated.connect(self.open_record)
        self.table.clearFiltersRequested.connect(self.filters.clear)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.open_button.setEnabled(
                self.table.selected_record() is not None))
        self.content.addWidget(self.table, 1)

        self.shortcut(QKeySequence.StandardKey.Find,
                      self.filters.focus_search)

    @property
    def repository(self):
        """El repositorio de esta bitacora, pedido al contexto **cada vez**.

        Se guardaba al crear la pantalla, y al cambiar de base desde Ajustes el
        contexto arma repositorios nuevos: Torsion y Quasi seguian leyendo y
        guardando en la base anterior hasta reiniciar la app, sin nada que lo
        delatara porque las demas bitacoras si cambiaban.
        """
        return self.context.generic_repository(self.config.key)

    # --- datos ------------------------------------------------------------
    def refresh(self) -> None:
        self._records = self.repository.list()
        self.filters.set_customers(self.context.catalogs.customer_names())
        self.filters.set_rigs(self.context.catalogs.rig_names(self.config.key))
        self.apply_filters()

    def apply_filters(self) -> None:
        activos = self.filters.filters()
        visibles = filtering.apply(self._records, activos)
        self.table.set_records(visibles, filtered=not activos.is_empty())
        self.filters.set_result_count(len(visibles), len(self._records))
        self.active_filters.update_from(activos)

        self.card_tests.set_value(len(visibles))
        self.card_samples.set_value(sum(t.qty_samples for t in visibles))

    # --- acciones ---------------------------------------------------------
    def _dialog(self, test=None):
        from dialogs.generic import GenericDialog

        return GenericDialog(
            self.repository, self.context.catalogs, self.context.audit,
            self.config, test=test, parent=self)

    def open_new(self) -> None:
        if self._dialog().exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def open_record(self, record: GenericTest) -> None:
        if self._dialog(record).exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def export(self) -> None:
        registros = self.table.visible_records()
        periodo = filter_period(self.filters)
        # El nombre del archivo sin tilde: viaja por correo y por carpetas de
        # red, donde una tilde en el nombre a veces llega rota.
        save_report(
            self, len(registros),
            suggested_filename(self.config.key.capitalize()),
            lambda ruta: export_generic(registros, self.config.label,
                                        self.rig_palette.colors(), ruta,
                                        period=periodo),
        )
