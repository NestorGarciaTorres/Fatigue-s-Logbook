"""Alta y edicion de una Work Order.

La WO es el documento fisico que autoriza una prueba: define que ensayo se
hara, sobre cuantas piezas, para que cliente, con que Test Batch y quien lo
solicita. Se captura antes de que la prueba exista, y de ella sale el
formulario de la bitacora cuando alguien pulsa 'Comenzar prueba'.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from app.db.repositories import WorkOrderRepository
from app.models import TEST_TYPES, WO_PENDING, WorkOrder
from app.services import validation
from app.services.catalogs import CatalogService
from app.services.identity import author_label, current_author
from app.ui.dialogs.form_guard import (
    GuardedDialog,
    gather_issues,
    update_merging,
)
from app.ui.widgets.common import (
    CenteredComboBox,
    add_field,
    balance_field_columns,
    batch_edit,
    centered_line_edit,
    closed_combo,
    fit_dialog_to_screen,
    quantity_combo,
    scroll_body,
    set_combo_value,
    subheading,
)

TYPE_LABELS = {key: config.label for key, config in TEST_TYPES.items()}


class WorkOrderDialog(GuardedDialog):
    def __init__(
        self,
        repository: WorkOrderRepository,
        catalogs: CatalogService,
        order: WorkOrder | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.catalogs = catalogs
        self.order = order
        self.editing = order is not None

        self.setWindowTitle(self._title())
        self.setMinimumWidth(760)
        self._build()

        if self.order:
            self._load(self.order)
        # Igual que en Fatiga y Rotary, con los datos ya cargados.
        fit_dialog_to_screen(self, self.scroll, self.body)
        # Punto de partida de 'cambios sin guardar', igual que en Fatiga.
        self.mark_clean()

    def _title(self) -> str:
        return "Editar Work Order" if self.editing else "Nueva Work Order"

    # --- construccion ----------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(subheading(self._title()))
        # Lo que impide guardar, a la vista y sin cuadro modal.
        layout.addWidget(self.issue_banner())

        group = QGroupBox("Datos de la orden")
        form = QGridLayout(group)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        self.test_type = CenteredComboBox()
        for key, label in TYPE_LABELS.items():
            self.test_type.addItem(label, key)

        self.batch = batch_edit()
        self.customer = closed_combo(self.catalogs.customer_names())
        self.qty = quantity_combo()
        self.requester = closed_combo(self.catalogs.requesters())
        self.requester.setToolTip(
            "Se edita en Ajustes -> Solicitantes."
        )
        self.comments = centered_line_edit("Sin comentarios")

        add_field(form, 0, 0, "* Tipo de prueba", self.test_type)
        add_field(form, 0, 1, "* Test Batch", self.batch)
        add_field(form, 0, 2, "* Cliente", self.customer)

        add_field(form, 1, 0, "* No. de piezas", self.qty)
        add_field(form, 1, 1, "* Requester", self.requester)

        comments_label = QLabel("Comentarios")
        form.addWidget(comments_label, 2, 0,
                       alignment=Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter)
        form.addWidget(self.comments, 2, 1, 1, 5)

        balance_field_columns(form, 3)

        # El Test Batch se valida contra las claves del tipo elegido, asi que
        # cambiar el tipo cambia lo que se acepta.
        self.hint = QLabel()
        self.hint.setProperty("muted", "true")
        self.hint.setWordWrap(True)

        # La misma estructura que los formularios de las bitacoras: los datos
        # se desplazan y los botones quedan fijos. La orden es corta y cabe en
        # un portatil, pero con la escala de Windows alta o una pantalla baja
        # el boton de crearla tambien quedaria fuera.
        self.scroll, self.body = scroll_body(group, self.hint)
        layout.addWidget(self.scroll, 1)
        self.test_type.currentIndexChanged.connect(self._update_hint)
        self._update_hint()

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.button_box = QDialogButtonBox()
        self.save_button = self.button_box.addButton(
            "Guardar cambios" if self.editing else "Crear Work Order",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.save_button.setProperty("accent", "success")
        self.button_box.addButton(
            "Cancelar", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.button_box.accepted.connect(self._save)
        self.button_box.rejected.connect(self.reject)
        buttons.addWidget(self.button_box)
        layout.addLayout(buttons)

    def _update_hint(self) -> None:
        key = self.test_type.currentData()
        codes = self.catalogs.codes(key) if key else []
        self.hint.setText(
            "Test Batch: 6 dígitos + clave + 2 dígitos. "
            f"Claves de {TYPE_LABELS.get(key, key)}: "
            + (", ".join(codes) if codes else "sin claves en el catálogo")
        )

    # --- carga y guardado ------------------------------------------------
    def _load(self, order: WorkOrder) -> None:
        index = self.test_type.findData(order.test_type)
        if index >= 0:
            self.test_type.setCurrentIndex(index)
        self.batch.setText(order.test_batch)
        set_combo_value(self.customer, order.customer)
        set_combo_value(self.qty, str(order.qty_samples))
        set_combo_value(self.requester, order.requester)
        self.comments.setText(order.comments)

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
            created_by=(self.order.created_by if self.order else author_label()),
        )

    def _save(self) -> None:
        order = self._collect()

        def solicitante() -> None:
            if not order.requester:
                raise validation.ValidationError(
                    "Elige quién solicita la prueba. Si la lista está vacía, "
                    "agrega personas en Ajustes -> Solicitantes."
                )

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
                    editing=self.editing,
                ),
            )),
            (self.requester, solicitante),
        ])
        if problemas:
            self.show_issues("No se puede guardar", problemas)
            return
        self.clear_issues()

        author = current_author()
        try:
            if self.editing:
                # Contra la orden tal como se abrio: si otro equipo la comenzo
                # o la movio de prioridad mientras tanto, eso no se deshace.
                if not update_merging(self, self.repository, order, author,
                                      base=self.order):
                    return
            else:
                self.repository.create(order, author)
        except Exception as error:  # pragma: no cover - depende de la red
            QMessageBox.critical(self, "Error al guardar", str(error))
            return

        self.accept()
