"""Alta y edicion de una Work Order.

La WO es el documento que autoriza una prueba: define que ensayo se hara, sobre
cuantas piezas, para que cliente, con que Test Batch y quien lo solicita. Se
captura **antes** de que la prueba exista, y de ella sale el formulario de la
bitacora cuando alguien pulsa 'Comenzar prueba'.

El Test Batch se valida contra las claves del tipo elegido, asi que cambiar el
tipo cambia lo que se acepta: el formulario lo dice debajo en vez de esperar a
que falle el guardado.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QGroupBox, QMessageBox

from app.models import TEST_TYPES, WO_PENDING, WorkOrder
from app.services import validation
from app.services.identity import author_label, current_author
from components import fields, labels
from components.forms import add_field, balance_field_columns, quantity_combo
from dialogs.base import FormDialog, gather_issues, update_merging

TYPE_LABELS = {clave: config.label for clave, config in TEST_TYPES.items()}


class WorkOrderDialog(FormDialog):
    def __init__(self, repository, catalogs, order: WorkOrder | None = None,
                 parent=None):
        self.repository = repository
        self.catalogs = catalogs
        self.order = order
        self.editing = order is not None

        super().__init__(
            "Editar Work Order" if self.editing else "Nueva Work Order",
            "El documento que autoriza la prueba, antes de que exista.",
            parent)
        self.setMinimumWidth(720)
        self._build()

        if self.order:
            self._load(self.order)
        self.finish_setup()

    # --- construccion -------------------------------------------------------
    def _build(self) -> None:
        grupo = QGroupBox("Datos de la orden")
        form = QGridLayout(grupo)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        self.test_type = fields.SearchableComboBox()
        for clave, etiqueta in TYPE_LABELS.items():
            self.test_type.addItem(etiqueta, clave)

        self.batch = fields.batch_edit()
        self.customer = fields.closed_combo(self.catalogs.customer_names())
        self.qty = quantity_combo()
        self.requester = fields.closed_combo(self.catalogs.requesters())
        self.requester.setToolTip("Se edita en Ajustes → Solicitantes.")
        self.comments = fields.line_edit("Sin comentarios")

        add_field(form, 0, 0, "* Tipo de prueba", self.test_type)
        add_field(form, 0, 1, "* Test Batch", self.batch)
        add_field(form, 0, 2, "* Cliente", self.customer)

        add_field(form, 1, 0, "* No. de piezas", self.qty)
        add_field(form, 1, 1, "* Requester", self.requester)

        form.addWidget(labels.muted("Comentarios"), 2, 0,
                       alignment=Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter)
        form.addWidget(self.comments, 2, 1, 1, 5)
        balance_field_columns(form, 3)

        self.hint = labels.muted("", wrap=True)
        self.set_body(grupo, self.hint)
        self.test_type.currentIndexChanged.connect(self._update_hint)
        self._update_hint()

        self.set_footer(save="Guardar cambios" if self.editing
                        else "Crear Work Order")

    def _update_hint(self) -> None:
        clave = self.test_type.currentData()
        claves = self.catalogs.codes(clave) if clave else []
        self.hint.setText(
            "Test Batch: 6 dígitos + clave + 2 dígitos. "
            f"Claves de {TYPE_LABELS.get(clave, clave)}: "
            + (", ".join(claves) if claves
               else "sin claves en el catálogo"))

    # --- carga --------------------------------------------------------------
    def _load(self, order: WorkOrder) -> None:
        indice = self.test_type.findData(order.test_type)
        if indice >= 0:
            self.test_type.setCurrentIndex(indice)
        self.batch.setText(order.test_batch)
        fields.set_combo_value(self.customer, order.customer)
        fields.set_combo_value(self.qty, str(order.qty_samples))
        fields.set_combo_value(self.requester, order.requester)
        self.comments.setText(order.comments)

    # --- guardado -----------------------------------------------------------
    def _collect(self) -> WorkOrder:
        return WorkOrder(
            id=self.order.id if self.order else None,
            test_type=self.test_type.currentData(),
            test_batch=validation.normalize_batch(self.batch.text()),
            customer=self.customer.currentText().strip(),
            qty_samples=int(self.qty.currentText()),
            requester=self.requester.currentText().strip(),
            comments=self.comments.text().strip(),
            status=self.order.status if self.order else WO_PENDING,
            # Una orden nueva entra al final de la fila; editar una existente
            # no la mueve de sitio.
            priority=(self.order.priority if self.order
                      else self.repository.next_priority()),
            started_test_id=self.order.started_test_id if self.order else None,
            created_at=(self.order.created_at if self.order else None)
            or date.today(),
            created_by=(self.order.created_by if self.order
                        else author_label()))

    def _save(self) -> None:
        order = self._collect()

        def solicitante() -> None:
            if not order.requester:
                raise validation.ValidationError(
                    "Elige quién solicita la prueba. Si la lista está vacía, "
                    "agrega personas en Ajustes → Solicitantes.")

        problemas = gather_issues([
            (self.customer, lambda: validation.validate_required(
                order.customer, order.qty_samples)),
            (self.batch, lambda: (
                validation.validate_test_batch(
                    order.test_batch, self.catalogs.codes(order.test_type)),
                validation.validate_unique_batch(
                    order.test_batch,
                    self.repository.batch_exists(order.test_batch,
                                                 exclude_id=order.id),
                    editing=self.editing))),
            (self.requester, solicitante),
        ])
        if problemas:
            self.show_issues("No se puede guardar", problemas)
            return
        self.clear_issues()

        autor = current_author()
        try:
            if self.editing:
                # Contra la orden tal como se abrio: si otro equipo la comenzo
                # o la movio de prioridad mientras tanto, eso no se deshace.
                if not update_merging(self, self.repository, order, autor,
                                      base=self.order):
                    return
            else:
                self.repository.create(order, autor)
        except Exception as error:             # pragma: no cover - depende de red
            QMessageBox.critical(self, "Error al guardar", str(error))
            return
        self.accept()
