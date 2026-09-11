"""Tabla de registros reutilizable.

Sustituye al ``Tableview`` de ttkbootstrap. El ordenamiento por columna, las
filas alternadas y el ajuste de anchos vienen de fabrica en Qt; antes habia que
reconstruir la tabla completa en cada refresco.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.models.table_models import (
    DAYS_COLORS,
    DAYS_LEVEL_ROLE,
    RIG_COLOR_ROLE,
    SORT_ROLE,
    BaseTestTableModel,
)
from app.ui.widgets import sample_chips
from app.ui.widgets.days_badge import DaysBadgeDelegate
from app.ui.widgets.rig_chip import RigChipDelegate
from app.ui.widgets.sample_chips import SampleChipsDelegate

MAX_COLUMN_WIDTH = 240

# Ancho de la barra que marca la fila seleccionada. La seleccion es oscura a
# proposito --es lo unico que deja legibles los chips y el semaforo que van
# encima-- asi que lo que la hace inconfundible no es el relleno sino esta
# barra, en el borde izquierdo de la fila.
SELECTION_BAR = 3

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

        self.message = QLabel("Ningún registro coincide con los filtros")
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
            self.message.setText("Ningún registro coincide con los filtros")
            self.button.setVisible(True)
        else:
            self.message.setText("Aun no hay registros en esta bitacora")
            self.button.setVisible(False)


def paint_selection_bar(view: QTableView) -> None:
    """Barra de acento a la izquierda de la fila seleccionada.

    Va en ``paintEvent`` por dos motivos. Una regla ``QTableView::item:selected``
    de la hoja de estilos se aplica celda a celda: saldria una barra por columna
    en vez de una por fila. Y ``drawRow``, que seria el sitio natural, no se
    despacha a Python en PySide6 -- se puede definir, pero Qt nunca la llama,
    asi que la barra no se dibujaba.
    """
    modelo = view.selectionModel()
    filas = modelo.selectedRows() if modelo else []
    if not filas:
        return

    painter = QPainter(view.viewport())
    color = QColor(theme.PRIMARY)
    for index in filas:
        rect = view.visualRect(index)
        if rect.isValid() and rect.height():
            painter.fillRect(
                QRect(0, rect.top(), SELECTION_BAR, rect.height()), color
            )
    painter.end()


class FrozenColumns(QTableView):
    """Las primeras columnas, fijas encima de la tabla.

    En la vista de 46 columnas el desplazamiento horizontal se llevaba el ID,
    el Test Batch y el Cliente: al llegar a 'Test Rig 7' ya no se sabia de que
    prueba se estaba leyendo. Es la misma idea que el ``freeze_panes`` que la
    app ya aplica al Excel que exporta.

    Es una segunda vista sobre el mismo modelo y la misma seleccion, asi que no
    hay estado que sincronizar: solo geometria y desplazamiento vertical.
    """

    def __init__(self, view: QTableView):
        super().__init__(view)
        self._view = view
        self.setModel(view.model())
        self.setSelectionModel(view.selectionModel())

        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(True)
        self.setWordWrap(False)
        self.setSortingEnabled(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QTableView.Shape.NoFrame)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(
            view.verticalHeader().defaultSectionSize()
        )
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setStretchLastSection(False)
        # El borde derecho es lo que dice que ahi termina lo que no se mueve.
        self.setStyleSheet(f"border-right: 2px solid {theme.PRIMARY};")
        self.hide()

        view.verticalScrollBar().valueChanged.connect(
            self.verticalScrollBar().setValue
        )
        view.horizontalHeader().sectionResized.connect(
            lambda *_: self.sync()
        )
        self.doubleClicked.connect(view._on_double_click)

    def sync(self) -> None:
        """Ajusta que columnas se ven y donde queda la tabla fija."""
        cuantas = getattr(self._view.source_model(), "frozen_columns", 0)
        columnas = self._view.model().columnCount()
        if not cuantas or cuantas >= columnas:
            self.hide()
            return

        ancho = 0
        for column in range(columnas):
            if column < cuantas:
                self.setColumnHidden(column, False)
                self.setColumnWidth(column, self._view.columnWidth(column))
                ancho += self._view.columnWidth(column)
            else:
                self.setColumnHidden(column, True)

        marco = self._view.frameWidth()
        self.setGeometry(
            marco, marco, ancho,
            self._view.viewport().height() + self._view.horizontalHeader().height(),
        )
        self.verticalScrollBar().setValue(self._view.verticalScrollBar().value())
        self.show()
        self.raise_()

    def wheelEvent(self, event) -> None:
        # La rueda sobre las columnas fijas mueve la tabla, no la copia.
        self._view.wheelEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        paint_selection_bar(self)


class RecordTable(QTableView):
    """Vista de una bitacora. Emite el registro al hacer doble clic."""

    recordActivated = Signal(object)
    clearFiltersRequested = Signal()

    def __init__(self, model: BaseTestTableModel, parent=None):
        super().__init__(parent)
        self._source = model
        self._sized_for: tuple | None = None
        self._natural_widths: dict[int, int] = {}

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
        self._days_delegate = DaysBadgeDelegate(DAYS_LEVEL_ROLE, DAYS_COLORS, self)
        self._rig_delegate = RigChipDelegate(RIG_COLOR_ROLE, self)
        self._apply_delegate()

        self._empty = EmptyState(self.viewport())
        self._empty.cleared.connect(self.clearFiltersRequested)
        self._empty.hide()

        self._frozen = FrozenColumns(self)

        # Abrir un registro se hacia solo con doble clic, y eso no lo dice
        # nadie: sin boton, sin menu y sin barra de estado no hay forma de
        # descubrirlo. El menu del boton derecho lo pone a la vista.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        # Acciones de la bitacora que van al mismo menu (add_menu_action).
        self._menu_actions: list[tuple[str, str, object]] = []

        self.doubleClicked.connect(self._on_double_click)
        model.modelReset.connect(self._apply_delegate)

    # --- datos -----------------------------------------------------------
    def set_records(self, records: list, filtered: bool = False) -> None:
        self._source.set_records(records)
        self._resize_if_needed()
        self._update_empty_state(filtered)
        self._frozen.sync()

    def set_compact(self, compact: bool) -> None:
        """Alterna entre la vista de chips y la de columnas completas."""
        if not hasattr(self._source, "set_compact"):
            return
        self._source.set_compact(compact)
        self._apply_delegate()
        # Cambio el juego de columnas: hay que volver a medir.
        self._sized_for = None
        self._resize_if_needed()
        self._frozen.sync()

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
        days_column = getattr(self._source, "days_column", None)
        chip_rigs = getattr(self._source, "chip_rig_columns", set())
        mios = (self._chips_delegate, self._days_delegate, self._rig_delegate)
        for column in range(self._source.columnCount()):
            if self.itemDelegateForColumn(column) in mios:
                self.setItemDelegateForColumn(column, None)
        if chips_column is not None:
            self.setItemDelegateForColumn(chips_column, self._chips_delegate)
        if days_column is not None:
            self.setItemDelegateForColumn(days_column, self._days_delegate)
        for column in chip_rigs:
            self.setItemDelegateForColumn(column, self._rig_delegate)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        paint_selection_bar(self)

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

        # El ancho medido por contenido de cada columna repartible. Se guarda
        # aqui porque el reparto se recalcula en cada cambio de tamano de la
        # ventana y hay que partir siempre de la misma medida, no de la del
        # reparto anterior.
        self._natural_widths = {
            columna: self.columnWidth(columna)
            for columna in range(self._proxy.columnCount())
            if columna != chips_column
        }
        self._sized_for = signature
        self._apply_stretch()

    def _apply_stretch(self) -> None:
        """Reparte el ancho que sobra en la ventana.

        Medida por contenido, la tabla dejaba entre un tercio y dos tercios de
        la pantalla en blanco --Torsion usaba 870 px de 2528-- mientras los
        comentarios quedaban cortados a 240.

        El sobrante se reparte en proporcion a lo que mide cada columna, con
        dos limites: ninguna crece a mas del doble --una columna de tres
        digitos a 90 px es tan absurda como el hueco que se quiere quitar-- y
        la de muestras no se toca, que su ancho es el de nueve chips. Lo que
        quede despues de eso se lo lleva la columna de comentarios, que es la
        que de verdad cambia de fila a fila.
        """
        if not self._natural_widths:
            return

        stretch = getattr(self._source, "stretch_column", None)
        naturales = {
            columna: ancho
            for columna, ancho in self._natural_widths.items()
            if columna < self._proxy.columnCount()
        }
        if not naturales:
            return

        fijas = sum(
            self.columnWidth(c)
            for c in range(self._proxy.columnCount())
            if c not in naturales
        )
        sobrante = self.viewport().width() - fijas - sum(naturales.values())
        if sobrante <= 0:
            for columna, ancho in naturales.items():
                if self.columnWidth(columna) != ancho:
                    self.setColumnWidth(columna, ancho)
            return

        total = sum(naturales.values())
        anchos = {}
        for columna, ancho in naturales.items():
            crecido = ancho + int(sobrante * ancho / total)
            anchos[columna] = min(crecido, ancho * 2)

        if stretch in anchos:
            anchos[stretch] += (
                self.viewport().width() - fijas - sum(anchos.values())
            )

        for columna, ancho in anchos.items():
            if self.columnWidth(columna) != ancho:
                self.setColumnWidth(columna, ancho)

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
        self._apply_stretch()
        self._frozen.sync()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_stretch()
        self._frozen.sync()

    def _show_menu(self, point) -> None:
        record = self.selected_record()
        index = self.indexAt(point)
        if record is None and index.isValid():
            self.selectRow(index.row())
            record = self.selected_record()
        if record is None:
            return
        menu = QMenu(self)
        abrir = menu.addAction("Abrir registro")
        abrir.setShortcut("Enter")
        otras = {}
        for texto, atajo, callback in self._menu_actions:
            accion = menu.addAction(texto)
            if atajo:
                accion.setShortcut(atajo)
            otras[accion] = callback

        elegida = menu.exec(self.viewport().mapToGlobal(point))
        if elegida is abrir:
            self.recordActivated.emit(record)
        elif elegida in otras:
            otras[elegida](record)

    def add_menu_action(self, text: str, callback, shortcut: str = "") -> None:
        """Otra accion en el menu del boton derecho, despues de 'Abrir registro'.

        ``callback`` recibe el registro de la fila. El atajo solo se rotula:
        quien lo define de verdad es el boton de la pantalla.
        """
        self._menu_actions.append((text, shortcut, callback))

    def menu_action_texts(self) -> list[str]:
        return ["Abrir registro"] + [texto for texto, _, _ in self._menu_actions]

    def open_selected(self) -> bool:
        """Abre lo seleccionado. Devuelve si habia algo que abrir."""
        record = self.selected_record()
        if record is None:
            return False
        self.recordActivated.emit(record)
        return True

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
