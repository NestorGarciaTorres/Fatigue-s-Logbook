"""Tabla de registros reutilizable.

Sustituye al ``Tableview`` de ttkbootstrap. El ordenamiento por columna, las
filas alternadas y el ajuste de anchos vienen de fabrica en Qt; antes habia que
reconstruir la tabla completa en cada refresco.
"""

from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.models.table_models import SORT_ROLE, BaseTestTableModel
from app.ui.widgets import sample_chips
from app.ui.widgets.sample_chips import SampleChipsDelegate

MAX_COLUMN_WIDTH = 240

# La columna de muestras no se mide por su contenido: se le reserva el ancho de
# las nueve muestras siempre. Medirla por contenido la dejaba del tamano de la
# fila mas ancha del momento, y una prueba de nueve piezas capturada despues
# quedaba cortada.


class EmptyState(QWidget):
    """Mensaje sobre la tabla cuando el filtro no deja nada.

    Antes quedaba una rejilla en blanco sin explicacion, que se confunde con
    'no hay datos' o con que la app fallo.
    """

    cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        self.message = QLabel("Ningun registro coincide con los filtros")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 14pt; background: transparent;"
        )
        layout.addWidget(self.message)

        self.button = QPushButton("Limpiar filtros")
        self.button.setProperty("accent", "secondary")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.clicked.connect(self.cleared)
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignCenter)

    def configure(self, filtered: bool) -> None:
        """Distingue 'no hay nada registrado' de 'los filtros no dejan nada'."""
        if filtered:
            self.message.setText("Ningun registro coincide con los filtros")
            self.button.setVisible(True)
        else:
            self.message.setText("Aun no hay registros en esta bitacora")
            self.button.setVisible(False)


class RecordTable(QTableView):
    """Vista de una bitacora. Emite el registro al hacer doble clic."""

    recordActivated = Signal(object)
    clearFiltersRequested = Signal()

    def __init__(self, model: BaseTestTableModel, parent=None):
        super().__init__(parent)
        self._source = model
        self._sized_for: tuple | None = None

        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(model)
        self._proxy.setSortRole(SORT_ROLE)
        self.setModel(self._proxy)

        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        self.setWordWrap(False)
        self.setShowGrid(True)

        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(34)

        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setHighlightSections(False)

        self._chips_delegate = SampleChipsDelegate(self)
        self._apply_delegate()

        self._empty = EmptyState(self.viewport())
        self._empty.cleared.connect(self.clearFiltersRequested)
        self._empty.hide()

        self.doubleClicked.connect(self._on_double_click)
        model.modelReset.connect(self._apply_delegate)

    # --- datos -----------------------------------------------------------
    def set_records(self, records: list, filtered: bool = False) -> None:
        self._source.set_records(records)
        self._resize_if_needed()
        self._update_empty_state(filtered)

    def set_compact(self, compact: bool) -> None:
        """Alterna entre la vista de chips y la de columnas completas."""
        if not hasattr(self._source, "set_compact"):
            return
        self._source.set_compact(compact)
        self._apply_delegate()
        # Cambio el juego de columnas: hay que volver a medir.
        self._sized_for = None
        self._resize_if_needed()

    def source_model(self) -> BaseTestTableModel:
        return self._source

    def selected_record(self):
        indexes = self.selectionModel().selectedRows()
        if not indexes:
            return None
        return self._record_from_index(indexes[0])

    def row_count(self) -> int:
        return self._proxy.rowCount()

    def visible_records(self) -> list:
        """Registros en el orden en que se ven, para exportarlos igual."""
        records = []
        for row in range(self._proxy.rowCount()):
            index = self._proxy.index(row, 0)
            record = self._record_from_index(index)
            if record is not None:
                records.append(record)
        return records

    # --- presentacion ----------------------------------------------------
    def _apply_delegate(self) -> None:
        chips_column = getattr(self._source, "chips_column", None)
        for column in range(self._source.columnCount()):
            if self.itemDelegateForColumn(column) is self._chips_delegate:
                self.setItemDelegateForColumn(column, None)
        if chips_column is not None:
            self.setItemDelegateForColumn(chips_column, self._chips_delegate)

    def _resize_if_needed(self) -> None:
        """Mide los anchos una sola vez por juego de columnas.

        Antes se llamaba a resizeColumnsToContents() en cada set_records(), es
        decir en cada tecla del buscador: las columnas saltaban de ancho
        mientras el usuario escribia.
        """
        signature = (tuple(self._source.headers), self._proxy.rowCount() > 0)
        if signature == self._sized_for:
            return

        self.resizeColumnsToContents()
        chips_column = getattr(self._source, "chips_column", None)

        for column in range(self._proxy.columnCount()):
            if column == chips_column:
                continue
            if self.columnWidth(column) > MAX_COLUMN_WIDTH:
                self.setColumnWidth(column, MAX_COLUMN_WIDTH)

        if chips_column is not None:
            self.setColumnWidth(
                chips_column,
                sample_chips.strip_width(QFontMetrics(
                    sample_chips.chip_font(self.font())
                )),
            )

        self._sized_for = signature

    def _update_empty_state(self, filtered: bool) -> None:
        if self._proxy.rowCount():
            self._empty.hide()
            return
        self._empty.configure(filtered)
        self._empty.resize(self.viewport().size())
        self._empty.show()
        self._empty.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._empty.isVisible():
            self._empty.resize(self.viewport().size())

    # --- internos --------------------------------------------------------
    def _record_from_index(self, index):
        source_index = self._proxy.mapToSource(index)
        return self._source.record_at(source_index.row())

    def _on_double_click(self, index) -> None:
        record = self._record_from_index(index)
        if record is not None:
            self.recordActivated.emit(record)

    def keyPressEvent(self, event) -> None:
        # Enter abre el registro seleccionado, igual que el doble clic.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            record = self.selected_record()
            if record is not None:
                self.recordActivated.emit(record)
                return
        super().keyPressEvent(event)
