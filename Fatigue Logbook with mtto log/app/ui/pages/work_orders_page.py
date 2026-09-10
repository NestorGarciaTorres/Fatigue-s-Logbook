"""Work Orders: las ordenes de trabajo preparadas, antes de que haya prueba.

Una sola pantalla para las cuatro bitacoras, porque quien prepara las ordenes
las captura todas juntas sin importar el tipo de ensayo. De aqui sale el
formulario de la bitacora: 'Comenzar prueba' lo abre con los datos del
documento ya puestos.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from app import dates
from app.context import AppContext
from app.models import (
    STARTABLE_TEST_TYPES,
    TEST_TYPES,
    WO_PENDING,
    WO_STARTED,
    WorkOrder,
)
from app.services.identity import current_author
from app.ui import theme
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.dialogs.rotary_dialog import RotaryDialog
from app.ui.dialogs.work_order_dialog import WorkOrderDialog
from app.ui.pages.base_page import BasePage

TYPE_LABELS = {key: config.label for key, config in TEST_TYPES.items()}

# Alto de fila y ancho de la columna de accion: el boton pide 180x37.
ROW_HEIGHT = 46
ACTION_WIDTH = 200

ALL = "Todas"
FILTERS = (WO_PENDING + "s", WO_STARTED + "s", ALL)


class WorkOrdersPage(BasePage):
    HEADERS = [
        "#", "Tipo", "Test Batch", "Cliente", "Piezas", "Requester", "Creada",
        "Estado", "",
    ]
    PRIORITY_COLUMN = 0
    ACTION_COLUMN = 8
    # La columna de prioridad lleva un numero de una o dos cifras: estirarla
    # como las demas solo le quita sitio al Test Batch.
    PRIORITY_WIDTH = 52

    def __init__(self, context: AppContext, parent=None):
        super().__init__("Work Orders", parent)
        self.context = context
        self._orders: list[WorkOrder] = []

        actions = QHBoxLayout()

        self.new_button = QPushButton("Nueva Work Order")
        self.new_button.setProperty("accent", "success")
        self.new_button.setShortcut(QKeySequence.StandardKey.New)
        self.new_button.setToolTip("Ctrl+N")
        self.new_button.clicked.connect(self.create_order)
        actions.addWidget(self.new_button)

        self.edit_button = QPushButton("Editar")
        self.edit_button.clicked.connect(self.edit_order)
        actions.addWidget(self.edit_button)

        self.delete_button = QPushButton("Eliminar")
        self.delete_button.setProperty("accent", "danger")
        self.delete_button.clicked.connect(self.delete_order)
        actions.addWidget(self.delete_button)

        # --- orden de prioridad ------------------------------------------
        # El orden de la lista es el orden en que hay que correr las pruebas.
        # Se acomoda desde aqui, sobre la seleccion.
        actions.addSpacing(16)
        self.first_button = QPushButton("Primero")
        self.first_button.setToolTip(
            "Pone la orden seleccionada a la cabeza de la fila."
        )
        self.first_button.clicked.connect(self.move_to_top)
        actions.addWidget(self.first_button)

        self.up_button = QPushButton("Subir")
        self.up_button.setShortcut("Alt+Up")
        self.up_button.setToolTip("Sube un lugar la orden seleccionada (Alt+↑)")
        self.up_button.clicked.connect(lambda: self.move_order(-1))
        actions.addWidget(self.up_button)

        self.down_button = QPushButton("Bajar")
        self.down_button.setShortcut("Alt+Down")
        self.down_button.setToolTip("Baja un lugar la orden seleccionada (Alt+↓)")
        self.down_button.clicked.connect(lambda: self.move_order(1))
        actions.addWidget(self.down_button)

        actions.addStretch(1)
        self.content.addLayout(actions)

        # El filtro y el resumen van en su propia fila. Con todo en una sola,
        # los seis botones mas el combo y el resumen pedian 1,862 px de minimo
        # y la pantalla nacia mas ancha que el escritorio de un portatil.
        controles = QHBoxLayout()
        controles.addWidget(QLabel("Mostrar"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(FILTERS)
        self.status_filter.currentTextChanged.connect(self.refresh)
        controles.addWidget(self.status_filter)

        controles.addStretch(1)
        self.summary = QLabel()
        self.summary.setProperty("muted", "true")
        controles.addWidget(self.summary)
        self.content.addLayout(controles)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        # La fila por omision mide 30 px y aplastaba el boton a 21: pide 37 de
        # alto y se dibujaba recortado. Se le da sitio.
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # ResizeToContents mide el item de la celda, no el widget que se le
        # pone encima, asi que la columna de la accion se fija a mano.
        header.setSectionResizeMode(
            self.ACTION_COLUMN, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(self.ACTION_COLUMN, ACTION_WIDTH)
        header.setSectionResizeMode(
            self.PRIORITY_COLUMN, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(self.PRIORITY_COLUMN, self.PRIORITY_WIDTH)
        self.table.doubleClicked.connect(self.edit_order)
        self.table.itemSelectionChanged.connect(self._update_move_buttons)
        self.content.addWidget(self.table, 1)

        hint = QLabel(
            "Las cuatro bitácoras comienzan su prueba desde aquí. Torsión "
            "conserva además su botón de alta directa, para la pieza que llega "
            "y se corre sin orden previa."
        )
        hint.setProperty("muted", "true")
        hint.setWordWrap(True)
        self.content.addWidget(hint)

    # --- datos -----------------------------------------------------------
    def refresh(self) -> None:
        choice = self.status_filter.currentText()
        status = None
        if choice.startswith(WO_PENDING):
            status = WO_PENDING
        elif choice.startswith(WO_STARTED):
            status = WO_STARTED

        self._orders = self.context.work_orders.list(status=status)
        # A cero primero: setRowCount() a la baja deja vivos los widgets de
        # celda de las filas que sobran, y reaparecian encima de las nuevas.
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._orders))

        # El numero que se ve es la posicion en la fila de pendientes, no el
        # valor guardado: al comenzar o borrar ordenes ese valor deja huecos.
        rank = 0
        for row, order in enumerate(self._orders):
            if not order.is_started:
                rank += 1
            self._fill_row(row, order, rank if not order.is_started else None)

        pendientes = self.context.work_orders.pending_count()
        self.summary.setText(
            f"{len(self._orders)} en la lista  ·  {pendientes} pendientes"
        )
        self._update_move_buttons()

    def _fill_row(self, row: int, order: WorkOrder, rank: int | None) -> None:
        posicion = self._item(str(rank) if rank else "—")
        if rank == 1:
            # La primera de la fila es la que toca correr: se marca para que
            # se vea de un vistazo cual es sin leer la columna entera.
            posicion.setForeground(QColor(theme.INFO))
            posicion.setToolTip("La siguiente prueba a comenzar")
        elif rank is None:
            posicion.setForeground(QColor(theme.TEXT_MUTED))
            posicion.setToolTip("Ya comenzada: no ocupa lugar en la fila")
        self.table.setItem(row, self.PRIORITY_COLUMN, posicion)

        tipo = self._item(TYPE_LABELS.get(order.test_type, order.test_type))
        self.table.setItem(row, 1, tipo)
        self.table.setItem(row, 2, self._item(order.test_batch))
        self.table.setItem(row, 3, self._item(order.customer))
        self.table.setItem(row, 4, self._item(str(order.qty_samples)))
        self.table.setItem(row, 5, self._item(order.requester))

        self.table.setItem(
            row, 6, self._item(dates.display(order.created_at) if order.created_at
                               else "")
        )

        estado = self._item(order.status)
        if order.is_started:
            estado.setForeground(QColor(theme.SUCCESS))
            if order.started_test_id:
                estado.setToolTip(
                    f"Registro #{order.started_test_id} en la bitácora de "
                    f"{TYPE_LABELS.get(order.test_type, order.test_type)}"
                )
        self.table.setItem(row, 7, estado)

        self.table.setCellWidget(row, self.ACTION_COLUMN, self._action(order))

    def _update_move_buttons(self) -> None:
        """Los botones de orden solo aplican a una pendiente, y no en el borde."""
        order = self._selected()
        pendientes = [o for o in self._orders if not o.is_started]
        movible = order is not None and not order.is_started

        posicion = pendientes.index(order) if movible else -1
        self.up_button.setEnabled(movible and posicion > 0)
        self.first_button.setEnabled(movible and posicion > 0)
        self.down_button.setEnabled(
            movible and 0 <= posicion < len(pendientes) - 1
        )

    def _action(self, order: WorkOrder):
        """Lo que se puede hacer con esta orden, o por que no se puede.

        Donde no hay accion no se pone un boton apagado: un control que hay que
        explicar estorba mas que la ausencia del control.
        """
        if order.is_started:
            return self._note(
                f"  → #{order.started_test_id}  " if order.started_test_id
                else "  comenzada  "
            )

        if order.test_type not in STARTABLE_TEST_TYPES:
            # Las cuatro bitacoras estan enlazadas; esto solo salta ante un
            # tipo de ensayo que no exista en el catalogo, que seria un dato
            # corrupto y no un caso normal.
            label = TYPE_LABELS.get(order.test_type, order.test_type)
            return self._note(
                "  tipo desconocido  ",
                f"'{label}' no es ninguna de las cuatro bitácoras: revisa el "
                f"tipo de ensayo de esta orden.",
            )

        button = QPushButton("Comenzar prueba")
        button.setProperty("accent", "success")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(34)
        button.clicked.connect(lambda _=False, o=order: self.start_test(o))
        return button

    @staticmethod
    def _note(text: str, tooltip: str = "") -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if tooltip:
            label.setToolTip(tooltip)
        return label

    @staticmethod
    def _item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def _selected(self) -> WorkOrder | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._orders):
            return self._orders[row]
        return None

    # --- acciones --------------------------------------------------------
    def create_order(self) -> None:
        dialog = WorkOrderDialog(
            self.context.work_orders, self.context.catalogs, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def edit_order(self) -> None:
        order = self._selected()
        if order is None:
            return
        if order.is_started:
            QMessageBox.information(
                self, "Work Order ya comenzada",
                "Esta orden ya dio lugar a una prueba. Corrige los datos en el "
                "registro de la bitácora, no aquí: cambiarlos ahora dejaría la "
                "orden y la prueba diciendo cosas distintas.",
            )
            return

        dialog = WorkOrderDialog(
            self.context.work_orders, self.context.catalogs, order=order,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def move_order(self, delta: int) -> None:
        self._reorder(lambda wo_id, author:
                      self.context.work_orders.move(wo_id, delta, author))

    def move_to_top(self) -> None:
        self._reorder(self.context.work_orders.move_to_top)

    def _reorder(self, operation) -> None:
        """Aplica un cambio de orden y deja seleccionada la misma orden.

        Sin volver a seleccionarla, pulsar 'Subir' dos veces movia dos ordenes
        distintas: la seleccion se queda en la fila, y la fila ya es otra.
        """
        order = self._selected()
        if order is None or order.is_started:
            return

        try:
            if not operation(order.id, current_author()):
                return
        except Exception as error:             # pragma: no cover - depende de red
            QMessageBox.critical(
                self, "No se pudo cambiar el orden", str(error)
            )
            return

        self.refresh()
        self.select_order(order.id)

    def select_order(self, work_order_id: int) -> None:
        for row, listed in enumerate(self._orders):
            if listed.id == work_order_id:
                self.table.selectRow(row)
                return

    def delete_order(self) -> None:
        order = self._selected()
        if order is None:
            return
        if order.is_started:
            QMessageBox.information(
                self, "Work Order ya comenzada",
                "No se elimina una orden que ya tiene prueba: es el rastro de "
                "quien la solicito y cuando se preparo.",
            )
            return

        confirm = QMessageBox.question(
            self, "Confirmación",
            f"Eliminar la Work Order {order.test_batch}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.context.work_orders.delete(order.id, current_author())
        self.refresh()

    def start_test(self, order: WorkOrder) -> None:
        """Abre el formulario de la bitacora con los datos de la orden."""
        if order.test_type == "fatigue":
            dialog = FatigueDialog(
                self.context.fatigue, self.context.catalogs, self.context.audit,
                work_order=order, parent=self,
            )
        elif order.test_type == "rotary":
            dialog = RotaryDialog(
                self.context.rotary, self.context.catalogs, self.context.audit,
                work_order=order, parent=self,
            )
        elif order.test_type in TEST_TYPES:
            # Torsion y Quasi comparten formulario, parametrizado por su
            # TestTypeConfig. Antes esta rama devolvia sin hacer nada porque el
            # boton no llegaba a existir para ellas.
            dialog = GenericDialog(
                self.context.generic_repository(order.test_type),
                self.context.catalogs, self.context.audit,
                TEST_TYPES[order.test_type], work_order=order, parent=self,
            )
        else:                                  # pragma: no cover - tipo ajeno
            return

        # La orden se marca despues de guardar, no antes: si el usuario cancela
        # el formulario tiene que seguir pendiente.
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.refresh()
            return

        if dialog.created_id is None:
            # El formulario se acepto sin crear registro (por ejemplo al
            # cerrarse desde otra accion). No se marca nada.
            self.refresh()
            return

        try:
            self.context.work_orders.mark_started(
                order.id, dialog.created_id, current_author()
            )
        except Exception as error:             # pragma: no cover - depende de red
            QMessageBox.critical(
                self, "La prueba se guardo, la orden no",
                f"El registro #{dialog.created_id} quedo creado, pero la Work "
                f"Order no pudo marcarse como comenzada:\n{error}",
            )

        self.refresh()
        QMessageBox.information(
            self, "Prueba comenzada",
            f"Se creó el registro #{dialog.created_id} en la bitácora de "
            f"{TYPE_LABELS.get(order.test_type, order.test_type)}, en "
            f"'En curso'.",
        )
