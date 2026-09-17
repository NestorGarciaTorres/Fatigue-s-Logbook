"""La tabla de registros y sus delegados.

Tres cosas que se pintan a mano, y las tres por el mismo motivo: **el color del
texto es lo primero que se pierde cuando la fila cambia de fondo**.

- El semaforo de la columna Dias es un **punto**, no un numero teniido. Con la
  seleccion clara del tema anterior, el rojo caia a 1.05:1 y el semaforo
  desaparecia justo al seleccionar la fila para mirarla.
- El banco de una columna suelta va en un **chip** que ocupa lo que mide su
  nombre. Pintando la celda entera, 400 filas del mismo T-7243 daban un bloque
  de color de arriba abajo que no distinguia nada.
- La fila seleccionada se marca con una **barra de acento** de 3 px a la
  izquierda, no con el relleno.

Y una trampa de Qt que cuesta descubrir: ``QTableView.drawRow`` **no se
despacha a Python** en PySide6. Se puede definir y Qt no la llama nunca. Lo que
se pinta por fila va en ``paintEvent``.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from components import buttons, labels
from components.chips import (
    RIG,
    SampleChipsDelegate,
    paint_chip_shape,
    strip_width,
)
from components.models import (
    DAYS_LEVEL_ROLE,
    RIG_COLOR_ROLE,
    RIG_KIND_ROLE,
    SORT_ROLE,
    BaseTestTableModel,
)
from theme.color import ink_for
from theme.manager import theme

MAX_COLUMN_WIDTH = 240
SELECTION_BAR = 3
ROW_HEIGHT = 34


def days_color(level: str | None) -> str | None:
    """El color del semaforo, pedido a la paleta en el momento de pintar."""
    if not level:
        return None
    paleta = theme().palette
    return {"ok": paleta.success,
            "warning": paleta.warning,
            "critical": paleta.danger}.get(level)


class DaysBadgeDelegate(QStyledItemDelegate):
    """Un punto de color a la izquierda del numero de dias."""

    DOT = 7
    GAP = 6

    def paint(self, painter: QPainter, option, index) -> None:
        super().paint(painter, option, index)
        color = days_color(index.data(DAYS_LEVEL_ROLE))
        if not color:
            return

        texto = index.data(Qt.ItemDataRole.DisplayRole) or ""
        ancho_texto = QFontMetrics(option.font).horizontalAdvance(str(texto))
        # El punto cae en el hueco que deja el numero al ir alineado a la
        # derecha, asi que no le quita sitio a nada.
        x = option.rect.right() - 6 - ancho_texto - self.GAP - self.DOT
        y = option.rect.center().y() - self.DOT / 2

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(x, y, self.DOT, self.DOT))
        painter.restore()


class RigChipDelegate(QStyledItemDelegate):
    """El banco de una columna suelta, dibujado como chip.

    **La forma la dibuja la misma funcion que la vista compacta y la leyenda**
    (``chips.paint_chip_shape``). No es por reusar: si esta columna pintara su
    propia version, una pieza detenida por mantenimiento saldria con trama en
    la vista de chips y sin ella en la de columnas completas, y la leyenda
    estaria explicando una marca que solo existe en una de las dos.

    Se dibuja tambien con la celda **vacia**, que es el caso que importa: al
    entrar su banco en mantenimiento la pieza se queda sin Test Rig, y sin chip
    la celda no diria nada de por que esta vacia.
    """

    PADDING = 7
    MIN_WIDTH = 30

    def initStyleOption(self, option, index) -> None:
        """El estilo pinta el fondo y la seleccion, pero **no** el texto.

        Aqui y no en ``paint``: ``QStyledItemDelegate.paint`` vuelve a llamar a
        ``initStyleOption`` sobre su propia copia, asi que una opcion en blanco
        que se le pase se descarta. El sintoma era doble: el ``--`` de una
        ranura vacia reaparecia, y el nombre de un banco salia dibujado dos
        veces --una por el estilo, alineada a la izquierda, y otra por el chip,
        centrada-- lo que se veia como un texto emborronado.
        """
        super().initStyleOption(option, index)
        option.text = ""

    def paint(self, painter: QPainter, option, index) -> None:
        crudo = str(index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        # Una ranura vacia se guardo como "--" en las columnas viejas, que no
        # admitian nulos. Ensenarlo tal cual haria pensar que el banco de esa
        # pieza son literalmente dos guiones.
        texto = "" if crudo == "--" else crudo
        color = index.data(RIG_COLOR_ROLE)
        kind = index.data(RIG_KIND_ROLE)

        if not texto and not color and not kind:
            super().paint(painter, option, index)
            return

        # Fondo y seleccion los pinta el estilo; el texto va dentro del chip.
        painter.save()
        super().paint(painter, option, index)

        metricas = QFontMetrics(option.font)
        ancho = max(self.MIN_WIDTH,
                    metricas.horizontalAdvance(texto) + self.PADDING * 2)
        alto = min(option.rect.height() - 8, 22)
        rect = QRectF(option.rect.x() + 6,
                      option.rect.center().y() - alto / 2,
                      min(ancho, option.rect.width() - 12), alto)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tinta = paint_chip_shape(painter, rect, kind or RIG, color)

        if texto:
            painter.setPen(QPen(tinta))
            painter.drawText(
                rect, Qt.AlignmentFlag.AlignCenter,
                metricas.elidedText(texto, Qt.TextElideMode.ElideRight,
                                    int(rect.width()) - 4))
        painter.restore()


class EmptyState(QWidget):
    """Mensaje sobre la tabla cuando no hay nada que ensenar.

    Sin esto queda una rejilla en blanco sin explicacion, que se confunde con
    'no hay datos' o con que la app fallo.
    """

    cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        self.message = labels.subheading("Ningún registro coincide con los filtros")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.message)

        self.button = buttons.button("Limpiar filtros", buttons.GHOST)
        self.button.clicked.connect(self.cleared)
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignCenter)

    def configure(self, filtered: bool) -> None:
        """Distingue 'no hay nada registrado' de 'los filtros no dejan nada'."""
        if filtered:
            self.message.setText("Ningún registro coincide con los filtros")
            self.button.setVisible(True)
        else:
            self.message.setText("Aún no hay registros en esta bitácora")
            self.button.setVisible(False)


class RecordTable(QTableView):
    """Tabla de una bitacora: ordenacion, chips, semaforo y menu."""

    recordActivated = Signal(object)
    clearFiltersRequested = Signal()

    def __init__(self, model: BaseTestTableModel, parent=None):
        super().__init__(parent)
        self._model = model
        self._menu_actions: list[tuple] = []

        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(model)
        # Se ordena por el valor real y no por su texto: si no, '1,000' va
        # antes que '9' y una fecha se ordena por el dia.
        self.proxy.setSortRole(SORT_ROLE)
        self.setModel(self.proxy)

        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setWordWrap(False)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.horizontalHeader().setHighlightSections(False)
        self.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        self.doubleClicked.connect(self._on_double_click)

        self.empty = EmptyState(self.viewport())
        self.empty.cleared.connect(self.clearFiltersRequested)
        self.empty.hide()

        self._apply_delegates()
        # Los delegados piden el color a la paleta al pintar, asi que basta con
        # repintar el viewport cuando cambie el tema.
        theme().themeChanged.connect(self.viewport().update)

    # --- datos ------------------------------------------------------------
    def set_records(self, records: list, filtered: bool = False) -> None:
        self._model.set_records(records)
        self._update_empty_state(filtered)
        self._resize_columns()

    def set_compact(self, compact: bool) -> None:
        if not hasattr(self._model, "set_compact"):
            return
        self._model.set_compact(compact)
        self._apply_delegates()
        self._resize_columns()

    def source_model(self) -> BaseTestTableModel:
        return self._model

    def selected_record(self):
        indices = self.selectionModel().selectedRows()
        if not indices:
            return None
        return self._record_from_index(indices[0])

    def visible_records(self) -> list:
        """Lo que el usuario ve, **en el orden en que lo ve**.

        Es lo que se exporta: un reporte que saliera en otro orden que la
        pantalla obliga a comprobar fila por fila que es lo mismo.
        """
        return [
            self._model.record_at(self.proxy.mapToSource(
                self.proxy.index(fila, 0)).row())
            for fila in range(self.proxy.rowCount())
        ]

    def row_count(self) -> int:
        return self.proxy.rowCount()

    # --- pintado ----------------------------------------------------------
    def _apply_delegates(self) -> None:
        self.setItemDelegate(QStyledItemDelegate(self))
        if self._model.chips_column is not None:
            self.setItemDelegateForColumn(self._model.chips_column,
                                          SampleChipsDelegate(self))
        if self._model.days_column is not None:
            self.setItemDelegateForColumn(self._model.days_column,
                                          DaysBadgeDelegate(self))
        for columna in self._model.rig_columns:
            self.setItemDelegateForColumn(columna, RigChipDelegate(self))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        # drawRow() no se despacha a Python en PySide6: la barra de seleccion
        # se pinta aqui o no se pinta.
        indices = self.selectionModel().selectedRows() if self.selectionModel() else []
        if not indices:
            return
        fila = indices[0].row()
        rect = self.visualRect(self.proxy.index(fila, 0))
        if not rect.isValid():
            return
        painter = QPainter(self.viewport())
        painter.fillRect(
            QRect(0, rect.y(), SELECTION_BAR, rect.height()),
            QColor(theme().palette.accent),
        )
        painter.end()

    def _update_empty_state(self, filtered: bool) -> None:
        vacio = self.proxy.rowCount() == 0
        self.empty.configure(filtered)
        self.empty.setVisible(vacio)
        if vacio:
            self.empty.resize(self.viewport().size())
            self.empty.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.empty.isVisible():
            self.empty.resize(self.viewport().size())
        self._stretch()

    def _resize_columns(self) -> None:
        cabecera = self.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.resizeColumnsToContents()

        for columna in range(self._model.columnCount()):
            if columna == self._model.chips_column:
                # La columna de muestras no se mide por contenido: se le
                # reserva el ancho de las nueve siempre. Midiendola por
                # contenido queda del tamano de la fila mas ancha del momento,
                # y una prueba de nueve piezas capturada despues sale cortada.
                self.setColumnWidth(
                    columna, strip_width(QFontMetrics(self.font())) + 12)
            elif self.columnWidth(columna) > MAX_COLUMN_WIDTH:
                self.setColumnWidth(columna, MAX_COLUMN_WIDTH)
        self._stretch()

    def _stretch(self) -> None:
        """Reparte el ancho sobrante en la columna que mas lo aprovecha."""
        columna = self._model.stretch_column
        if columna is None or self._model.columnCount() == 0:
            return
        usado = sum(self.columnWidth(c)
                    for c in range(self._model.columnCount()) if c != columna)
        sobra = self.viewport().width() - usado
        if sobra > 120:
            self.setColumnWidth(columna, sobra)

    # --- interaccion ------------------------------------------------------
    def _record_from_index(self, index):
        return self._model.record_at(self.proxy.mapToSource(index).row())

    def _on_double_click(self, index) -> None:
        registro = self._record_from_index(index)
        if registro is not None:
            self.recordActivated.emit(registro)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.open_selected():
                return
        super().keyPressEvent(event)

    def open_selected(self) -> bool:
        registro = self.selected_record()
        if registro is None:
            return False
        self.recordActivated.emit(registro)
        return True

    def add_menu_action(self, text: str, callback, shortcut: str = "") -> None:
        """Otra accion en el menu del boton derecho, tras 'Abrir registro'."""
        self._menu_actions.append((text, shortcut, callback))

    def menu_action_texts(self) -> list[str]:
        return ["Abrir registro"] + [t for t, _, _ in self._menu_actions]

    def _show_menu(self, point) -> None:
        registro = self.selected_record()
        index = self.indexAt(point)
        if registro is None and index.isValid():
            self.selectRow(index.row())
            registro = self.selected_record()
        if registro is None:
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
            self.recordActivated.emit(registro)
        elif elegida in otras:
            otras[elegida](registro)
