"""Work Orders: las ordenes preparadas, antes de que exista la prueba.

Una sola pantalla para las cuatro bitacoras, porque quien prepara las ordenes
las captura todas juntas sin importar el tipo de ensayo. De aqui sale el
formulario de la bitacora: 'Comenzar prueba' lo abre con los datos ya puestos.

**El orden de la lista es el orden en que hay que correr las pruebas.** El
numero que se ve es la posicion en la fila de pendientes, no el valor guardado:
al comenzar o borrar ordenes ese valor deja huecos que no significan nada.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from app import dates
from app.models import (
    STARTABLE_TEST_TYPES,
    TEST_TYPES,
    WO_PENDING,
    WO_STARTED,
    WorkOrder,
)
from app.services import maintenance
from app.services.excel_export import export_work_orders, suggested_filename
from app.services.identity import current_author
from app.ui.report_export import save_report
from components import buttons, fields, labels
from pages.base import Page

TYPE_LABELS = {clave: config.label for clave, config in TEST_TYPES.items()}

# Alto de fila: el boton de accion pide 37 px y sus margenes 8, asi que con
# los 30 por omision --y aun con 46-- se dibujaba rozando el borde de la fila.
ROW_HEIGHT = 54
ACTION_WIDTH = 190

ALL = "Todas"
FILTERS = (WO_PENDING + "s", WO_STARTED + "s", ALL)


class WorkOrdersPage(Page):
    HEADERS = ["#", "Tipo", "Test Batch", "Cliente", "Piezas", "Requester",
               "Creada", "Estado", ""]
    PRIORITY_COLUMN = 0
    ACTION_COLUMN = 8
    PRIORITY_WIDTH = 52

    def __init__(self, context, rig_palette, parent=None):
        super().__init__("Work Orders",
                         "Las órdenes de trabajo que autorizan cada prueba",
                         parent)
        self.context = context
        self.rig_palette = rig_palette
        self._orders: list[WorkOrder] = []

        # --- acciones ----------------------------------------------------
        self.new_button = buttons.button(
            "Nueva Work Order", buttons.PRIMARY, shortcut="Ctrl+N",
            on_click=self.create_order)
        self.edit_button = buttons.button("Editar", on_click=self.edit_order)
        self.delete_button = buttons.button(
            "Eliminar", buttons.DANGER, on_click=self.delete_order)

        self.first_button = buttons.button(
            "Primero", buttons.GHOST,
            tooltip="Pone la orden seleccionada a la cabeza de la fila",
            on_click=self.move_to_top)
        self.up_button = buttons.button(
            "Subir", buttons.GHOST, shortcut="Alt+Up",
            tooltip="Sube un lugar la orden seleccionada",
            on_click=lambda: self.move_order(-1))
        self.down_button = buttons.button(
            "Bajar", buttons.GHOST, shortcut="Alt+Down",
            tooltip="Baja un lugar la orden seleccionada",
            on_click=lambda: self.move_order(1))

        fila = QHBoxLayout()
        fila.setSpacing(8)
        for boton in (self.new_button, self.edit_button, self.delete_button):
            fila.addWidget(boton)
        fila.addSpacing(20)
        for boton in (self.first_button, self.up_button, self.down_button):
            fila.addWidget(boton)
        fila.addStretch(1)
        self.content.addLayout(fila)

        # --- filtro y resumen --------------------------------------------
        # En su propia fila: con todo junto, los seis botones mas el combo y el
        # resumen pedian 1,862 px de minimo.
        controles = QHBoxLayout()
        controles.setSpacing(10)
        controles.addWidget(labels.muted("Mostrar"))
        self.status_filter = fields.SearchableComboBox(centered=False)
        self.status_filter.addItems(FILTERS)
        self.status_filter.currentTextChanged.connect(self.refresh)
        controles.addWidget(self.status_filter)

        self.summary = labels.muted("")
        controles.addWidget(self.summary)
        controles.addStretch(1)

        self.export_button = buttons.button(
            "Exportar a Excel", buttons.SUCCESS, shortcut="Ctrl+E",
            tooltip="Las órdenes que se ven, en su orden",
            on_click=self.export)
        controles.addWidget(self.export_button)
        self.content.addLayout(controles)

        # --- tabla -------------------------------------------------------
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)

        cabecera = self.table.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        cabecera.setHighlightSections(False)
        # ResizeToContents mide el item de la celda, no el widget que se le
        # pone encima, asi que la columna de la accion se fija a mano.
        cabecera.setSectionResizeMode(self.ACTION_COLUMN,
                                      QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.ACTION_COLUMN, ACTION_WIDTH)
        cabecera.setSectionResizeMode(self.PRIORITY_COLUMN,
                                      QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.PRIORITY_COLUMN, self.PRIORITY_WIDTH)

        self.table.doubleClicked.connect(self.edit_order)
        self.table.itemSelectionChanged.connect(self._update_move_buttons)
        self.content.addWidget(self.table, 1)

        nota = labels.muted(
            "Las cuatro bitácoras comienzan su prueba desde aquí. Torsión "
            "conserva además su botón de alta directa, para la pieza que "
            "llega y se corre sin orden previa.", wrap=True)
        self.content.addWidget(nota)

    # --- datos ------------------------------------------------------------
    def refresh(self) -> None:
        elegido = self.status_filter.currentText()
        estado = None
        if elegido.startswith(WO_PENDING):
            estado = WO_PENDING
        elif elegido.startswith(WO_STARTED):
            estado = WO_STARTED

        self._orders = self.context.work_orders.list(status=estado)
        # A cero primero: setRowCount() a la baja deja vivos los widgets de
        # celda de las filas que sobran, y reaparecian encima de las nuevas.
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._orders))

        posicion = 0
        for fila, orden in enumerate(self._orders):
            if not orden.is_started:
                posicion += 1
            self._fill_row(fila, orden,
                           posicion if not orden.is_started else None)

        pendientes = self.context.work_orders.pending_count()
        self.summary.setText(
            f"{len(self._orders)} en la lista  ·  {pendientes} pendientes")
        self._update_move_buttons()

    def _fill_row(self, fila: int, orden: WorkOrder,
                  rank: int | None) -> None:
        lugar = self._item(str(rank) if rank else "—")
        if rank == 1:
            # La primera de la fila es la que toca correr. Se marca con una
            # pastilla y no tiniendo el texto: el color de texto es lo primero
            # que se pierde al seleccionar la fila.
            lugar.setToolTip("La siguiente prueba a comenzar")
        elif rank is None:
            lugar.setToolTip("Ya comenzada: no ocupa lugar en la fila")
        self.table.setItem(fila, self.PRIORITY_COLUMN, lugar)

        self.table.setItem(fila, 1, self._item(
            TYPE_LABELS.get(orden.test_type, orden.test_type)))
        self.table.setItem(fila, 2, self._item(orden.test_batch))
        self.table.setItem(fila, 3, self._item(orden.customer))
        self.table.setItem(fila, 4, self._item(str(orden.qty_samples)))
        self.table.setItem(fila, 5, self._item(orden.requester))
        self.table.setItem(fila, 6, self._item(
            dates.display(orden.created_at) if orden.created_at else ""))

        # El estado va como pastilla, que es un widget y toma su color de la
        # hoja de estilos: asi sigue al tema sin que nadie lo repinte.
        self.table.setCellWidget(fila, 7, self._status_cell(orden))
        self.table.setItem(fila, 7, self._item(""))
        self.table.setCellWidget(fila, self.ACTION_COLUMN, self._action(orden))

    @staticmethod
    def _wrap(widget: QWidget) -> QWidget:
        """Centra un widget dentro de su celda."""
        contenedor = QWidget()
        caja = QHBoxLayout(contenedor)
        caja.setContentsMargins(6, 4, 6, 4)
        caja.addStretch(1)
        caja.addWidget(widget)
        caja.addStretch(1)
        return contenedor

    def _status_cell(self, orden: WorkOrder) -> QWidget:
        pastilla = labels.pill(
            orden.status, "success" if orden.is_started else "info")
        if orden.is_started and orden.started_test_id:
            pastilla.setToolTip(
                f"Registro #{orden.started_test_id} en la bitácora de "
                f"{TYPE_LABELS.get(orden.test_type, orden.test_type)}")
        return self._wrap(pastilla)

    def _action(self, orden: WorkOrder) -> QWidget:
        """Lo que se puede hacer con esta orden, o por que no se puede.

        Donde no hay accion no se pone un boton apagado: un control que hay que
        explicar estorba mas que la ausencia del control.
        """
        if orden.is_started:
            texto = (f"→ #{orden.started_test_id}" if orden.started_test_id
                     else "comenzada")
            return self._wrap(labels.muted(texto))

        if orden.test_type not in STARTABLE_TEST_TYPES:
            # Las cuatro bitacoras estan enlazadas; esto solo salta ante un
            # tipo de ensayo que no exista en el catalogo, que seria un dato
            # corrupto y no un caso normal.
            etiqueta = TYPE_LABELS.get(orden.test_type, orden.test_type)
            nota = labels.muted("tipo desconocido")
            nota.setToolTip(
                f"'{etiqueta}' no es ninguna de las cuatro bitácoras: revisa "
                f"el tipo de ensayo de esta orden.")
            return self._wrap(nota)

        boton = buttons.button("Comenzar prueba", buttons.SUCCESS,
                               on_click=lambda o=orden: self.start_test(o))
        return self._wrap(boton)

    @staticmethod
    def _item(texto: str) -> QTableWidgetItem:
        item = QTableWidgetItem(texto)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def _selected(self) -> WorkOrder | None:
        fila = self.table.currentRow()
        if 0 <= fila < len(self._orders):
            return self._orders[fila]
        return None

    def _update_move_buttons(self) -> None:
        """Los botones de orden solo aplican a una pendiente, y no en el borde."""
        orden = self._selected()
        pendientes = [o for o in self._orders if not o.is_started]
        movible = orden is not None and not orden.is_started

        posicion = pendientes.index(orden) if movible else -1
        self.up_button.setEnabled(movible and posicion > 0)
        self.first_button.setEnabled(movible and posicion > 0)
        self.down_button.setEnabled(
            movible and 0 <= posicion < len(pendientes) - 1)
        self.edit_button.setEnabled(movible)
        self.delete_button.setEnabled(movible)

    # --- acciones ---------------------------------------------------------
    def _dialog(self, order=None):
        from dialogs.work_order import WorkOrderDialog

        return WorkOrderDialog(self.context.work_orders,
                               self.context.catalogs, order=order, parent=self)

    def create_order(self) -> None:
        if self._dialog().exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def edit_order(self) -> None:
        orden = self._selected()
        if orden is None:
            return
        if orden.is_started:
            QMessageBox.information(
                self, "Work Order ya comenzada",
                "Esta orden ya dio lugar a una prueba. Corrige los datos en el "
                "registro de la bitácora, no aquí: cambiarlos ahora dejaría la "
                "orden y la prueba diciendo cosas distintas.")
            return
        if self._dialog(orden).exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def move_order(self, delta: int) -> None:
        self._reorder(lambda wo_id, autor:
                      self.context.work_orders.move(wo_id, delta, autor))

    def move_to_top(self) -> None:
        self._reorder(self.context.work_orders.move_to_top)

    def _reorder(self, operacion) -> None:
        """Aplica un cambio de orden y deja seleccionada la misma orden.

        Sin volver a seleccionarla, pulsar 'Subir' dos veces movia dos ordenes
        distintas: la seleccion se queda en la fila, y la fila ya es otra.
        """
        orden = self._selected()
        if orden is None or orden.is_started:
            return
        try:
            if not operacion(orden.id, current_author()):
                return
        except Exception as error:            # pragma: no cover - depende de red
            QMessageBox.critical(self, "No se pudo cambiar el orden",
                                 str(error))
            return

        self.refresh()
        self.select_order(orden.id)

    def select_order(self, work_order_id: int) -> None:
        for fila, listada in enumerate(self._orders):
            if listada.id == work_order_id:
                self.table.selectRow(fila)
                return

    def delete_order(self) -> None:
        orden = self._selected()
        if orden is None:
            return
        if orden.is_started:
            QMessageBox.information(
                self, "Work Order ya comenzada",
                "No se elimina una orden que ya tiene prueba: es el rastro de "
                "quién la solicitó y cuándo se preparó.")
            return

        confirmar = QMessageBox.question(
            self, "Confirmación",
            f"¿Eliminar la Work Order {orden.test_batch}?")
        if confirmar != QMessageBox.StandardButton.Yes:
            return

        self.context.work_orders.delete(orden.id, current_author())
        self.refresh()

    def start_test(self, orden: WorkOrder) -> None:
        """Abre el formulario de la bitacora con los datos de la orden."""
        from dialogs.fatigue import FatigueDialog
        from dialogs.generic import GenericDialog
        from dialogs.rotary import RotaryDialog

        if orden.test_type == "fatigue":
            dialogo = FatigueDialog(
                self.context.fatigue, self.context.catalogs,
                self.context.audit, work_order=orden,
                # Una prueba que nace no puede empezar en un banco parado.
                unavailable_rigs=maintenance.rigs_in_maintenance(
                    self.context.maintenance.open_records()),
                parent=self)
        elif orden.test_type == "rotary":
            dialogo = RotaryDialog(
                self.context.rotary, self.context.catalogs,
                self.context.audit, work_order=orden, parent=self)
        elif orden.test_type in TEST_TYPES:
            dialogo = GenericDialog(
                self.context.generic_repository(orden.test_type),
                self.context.catalogs, self.context.audit,
                TEST_TYPES[orden.test_type], work_order=orden, parent=self)
        else:                                 # pragma: no cover - tipo ajeno
            return

        # La orden se marca despues de guardar, no antes: si el usuario
        # cancela el formulario tiene que seguir pendiente.
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            self.refresh()
            return
        if dialogo.created_id is None:
            self.refresh()
            return

        try:
            self.context.work_orders.mark_started(
                orden.id, dialogo.created_id, current_author())
        except Exception as error:            # pragma: no cover - depende de red
            QMessageBox.critical(
                self, "La prueba se guardó, la orden no",
                f"El registro #{dialogo.created_id} quedó creado, pero la Work "
                f"Order no pudo marcarse como comenzada:\n{error}")

        self.refresh()
        QMessageBox.information(
            self, "Prueba comenzada",
            f"Se creó el registro #{dialogo.created_id} en la bitácora de "
            f"{TYPE_LABELS.get(orden.test_type, orden.test_type)}, en "
            f"'En curso'.")

    def export(self) -> None:
        ordenes = list(self._orders)
        save_report(
            self, len(ordenes), suggested_filename("Work_Orders"),
            lambda ruta: export_work_orders(ordenes, ruta, TYPE_LABELS),
            empty_message="No hay órdenes que exportar con este filtro.")
