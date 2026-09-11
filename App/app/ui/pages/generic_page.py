"""Bitacora de Torsion y de Quasi.

Una sola clase parametrizada por ``TestTypeConfig``. Sustituye a
``logbooks/logbook_torsion.py`` y ``logbooks/logbook_quasi.py``, que eran el
mismo archivo copiado: 234 y 233 lineas identicas salvo seis cadenas.
"""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton

from app.context import AppContext
from app.models import DIRECT_ENTRY_TEST_TYPES, GenericTest, TestTypeConfig
from app.services import filtering
from app.services.excel_export import export_generic, suggested_filename
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.models.table_models import GenericTableModel
from app.ui.pages.base_page import BasePage
from app.ui.report_export import filter_period, save_report
from app.ui.widgets.common import StatCard
from app.ui.widgets.filter_bar import FilterBar
from app.ui.widgets.legend import ActiveFilters, Legend
from app.ui.widgets.record_table import RecordTable


class GenericPage(BasePage):
    def __init__(self, context: AppContext, config: TestTypeConfig, parent=None):
        super().__init__(f"Bitácora de {config.label}", parent)
        self.context = context
        self.config = config
        self._records: list[GenericTest] = []

        actions = QHBoxLayout()

        # El alta directa solo la conserva Torsion: ahi llega la pieza y se
        # corre sin orden previa, asi que sin este boton no habria manera de
        # registrarla. Quasi, como Fatiga y Rotary, nace de una Work Order --
        # y el boton no se pone apagado: un control que hay que explicar
        # estorba mas que su ausencia.
        self.new_button: QPushButton | None = None
        if config.key in DIRECT_ENTRY_TEST_TYPES:
            self.new_button = QPushButton("Nuevo registro")
            self.new_button.setShortcut(QKeySequence.StandardKey.New)
            self.new_button.setToolTip("Ctrl+N")
            self.new_button.clicked.connect(self.open_new)
            actions.addWidget(self.new_button)

        # Abrir un registro solo se podia con doble clic, sin nada que lo
        # dijera. El boton lo pone a la vista y de paso da el atajo.
        self.open_button = QPushButton("Abrir registro")
        self.open_button.setProperty("accent", "secondary")
        self.open_button.setToolTip("Doble clic sobre la fila, o Enter")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(lambda: self.table.open_selected())
        actions.addWidget(self.open_button)

        # Lo que dejen los filtros, igual que en Fatiga y Rotary.
        self.export_button = QPushButton("Exportar a Excel")
        self.export_button.setProperty("accent", "success")
        self.export_button.setShortcut("Ctrl+E")
        self.export_button.setToolTip("Las pruebas que se ven, con sus filtros (Ctrl+E)")
        self.export_button.clicked.connect(self.export)
        actions.addWidget(self.export_button)
        actions.addStretch(1)
        self.content.addLayout(actions)

        cards = QHBoxLayout()
        cards.addStretch(1)
        self.card_tests = StatCard("Pruebas", "0", accent=config.accent)
        self.card_samples = StatCard("Piezas probadas", "0", accent=config.accent)
        cards.addWidget(self.card_tests)
        cards.addWidget(self.card_samples)
        self.content.addLayout(cards)

        # Torsion y Quasi no manejan estatus ni Work Order.
        self.filters = FilterBar(show_status=False, show_wo=False)
        self.filters.changed.connect(self.apply_filters)
        self.content.addWidget(self.filters)

        self.active_filters = ActiveFilters()
        self.active_filters.removed.connect(self.filters.clear_field)
        self.active_filters.setVisible(False)
        self.content.addWidget(self.active_filters)

        self.model = GenericTableModel(context.catalogs)
        self.table = RecordTable(self.model)
        self.table.recordActivated.connect(self.open_record)
        self.table.clearFiltersRequested.connect(self.filters.clear)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.open_button.setEnabled(
                self.table.selected_record() is not None
            )
        )
        self.content.addWidget(self.table, 1)

        self.shortcut(QKeySequence.StandardKey.Find, self.filters.focus_search)

    @property
    def repository(self):
        """El repositorio de esta bitacora, pedido al contexto cada vez.

        Se guardaba al crear la pantalla. Al cambiar de base desde Ajustes el
        contexto arma repositorios nuevos, y Torsion y Quasi seguian leyendo y
        guardando en la base anterior hasta reiniciar la app -- sin nada que
        lo delatara, porque las demas bitacoras si cambiaban.
        """
        return self.context.generic_repository(self.config.key)

    def refresh(self) -> None:
        self._records = self.repository.list()
        self.filters.set_customers(self.context.catalogs.customer_names())
        self.filters.set_rigs(self.context.catalogs.rig_names(self.config.key))
        self.apply_filters()

    def apply_filters(self) -> None:
        active = self.filters.filters()
        visible = filtering.apply(self._records, active)
        self.table.set_records(visible, filtered=not active.is_empty())
        self.filters.set_result_count(len(visible), len(self._records))
        self.active_filters.update_from(active)
        self.card_tests.set_value(len(visible))
        self.card_samples.set_value(sum(t.qty_samples for t in visible))

    def open_new(self) -> None:
        dialog = GenericDialog(
            self.repository, self.context.catalogs, self.context.audit,
            self.config, parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def open_record(self, record: GenericTest) -> None:
        dialog = GenericDialog(
            self.repository, self.context.catalogs, self.context.audit,
            self.config, test=record, parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def export(self) -> None:
        records = self.table.visible_records()
        colores = self.context.catalogs.colors()
        periodo = filter_period(self.filters)
        # El nombre del archivo sin tilde: viaja por correo y por carpetas de
        # red, donde una tilde en el nombre a veces llega rota.
        save_report(
            self, len(records), suggested_filename(self.config.key.capitalize()),
            lambda path: export_generic(records, self.config.label, colores,
                                        path, period=periodo),
        )
