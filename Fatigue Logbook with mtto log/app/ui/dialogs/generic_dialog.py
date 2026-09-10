"""Alta y edicion de pruebas de Torsion y Quasi.

Reemplaza a ``forms/generic_form.py``. Aquel recibia una lista de seis
elementos y los leia por indice (``self.table_to_edit[5]``); aqui recibe un
``TestTypeConfig`` con nombres.
"""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.db.repositories import GenericRepository
from app.models import EMPTY_RIG, GenericTest, TestTypeConfig
from app.services import validation
from app.services.catalogs import CatalogService
from app.services.identity import current_author
from app.ui.dialogs.history_dialog import HistoryDialog
from app.ui.widgets.common import (
    batch_edit,
    centered_line_edit,
    clearable_combo,
    closed_combo,
    combo_value,
    quantity_combo,
    set_combo_value,
    subheading,
)
from app.ui.widgets.filter_bar import make_date_edit


class GenericDialog(QDialog):
    def __init__(
        self,
        repository: GenericRepository,
        catalogs: CatalogService,
        audit_repository,
        config: TestTypeConfig,
        test: GenericTest | None = None,
        work_order=None,
        parent=None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.catalogs = catalogs
        self.audit_repository = audit_repository
        self.config = config
        self.test = test
        self.editing = test is not None
        self.work_order = work_order
        # Lo consulta quien abrio el formulario desde una Work Order, para
        # enlazarla con el registro recien creado. Mismo contrato que en
        # FatigueDialog y RotaryDialog: la pantalla de Work Orders no tiene
        # por que saber que dialogo abrio.
        self.created_id: int | None = None

        self.setWindowTitle(self._title())
        self.setMinimumWidth(460)

        self._build()
        if self.test:
            self._load(self.test)
        elif self.work_order is not None:
            self._prefill_from_work_order(self.work_order)

    def _title(self) -> str:
        if self.editing:
            return f"Editar prueba de {self.config.label}"
        if self.work_order is not None:
            return f"Comenzar prueba  -  WO {self.work_order.test_batch}"
        return f"Nueva prueba de {self.config.label}"

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(subheading(self._title()))

        group = QGroupBox("Datos de la prueba")
        form = QFormLayout(group)
        form.setHorizontalSpacing(18)

        self.batch = batch_edit()
        self.customer = closed_combo(self.catalogs.customer_names())
        self.test_date = make_date_edit()
        self.qty = quantity_combo()
        self.rig = closed_combo(self.catalogs.rig_names(self.config.key))
        # Llega de la Work Order y se queda en el registro. Opcional: los
        # registros anteriores a las Work Orders no tienen solicitante.
        self.requester = clearable_combo(
            self.catalogs.requesters(), "(sin solicitante)"
        )
        self.requester.setToolTip(
            "Quien pidió la prueba. Se edita en Ajustes -> Solicitantes."
        )
        self.comments = centered_line_edit("Sin comentarios")

        form.addRow("* Test Batch", self.batch)
        form.addRow("* Cliente", self.customer)
        form.addRow("* Fecha de prueba", self.test_date)
        form.addRow("* No. de piezas", self.qty)
        form.addRow("* Test Rig", self.rig)
        form.addRow("Solicitante", self.requester)
        form.addRow("Comentarios", self.comments)

        layout.addWidget(group)

        buttons = QHBoxLayout()

        self.history_button = QPushButton("Ver historial")
        self.history_button.setProperty("accent", "secondary")
        self.history_button.clicked.connect(self._show_history)
        self.history_button.setVisible(self.editing)
        buttons.addWidget(self.history_button)

        buttons.addStretch(1)

        self.button_box = QDialogButtonBox()
        save = self.button_box.addButton(
            "Guardar cambios" if self.editing else "Ingresar registro",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        save.setProperty("accent", "success")
        self.button_box.addButton(
            "Cancelar", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.button_box.accepted.connect(self._save)
        self.button_box.rejected.connect(self.reject)
        buttons.addWidget(self.button_box)

        layout.addLayout(buttons)

    def _prefill_from_work_order(self, order) -> None:
        """Trae del documento lo que ya viene decidido.

        Se deja editable, igual que en Fatiga: si el Test Batch de la orden
        trae una errata, quien corre la prueba la corrige sin volver atras.
        """
        self.batch.setText(order.test_batch)
        set_combo_value(self.customer, order.customer)
        set_combo_value(self.qty, str(order.qty_samples))
        set_combo_value(self.requester, order.requester)
        if order.comments:
            self.comments.setText(order.comments)

    def _load(self, test: GenericTest) -> None:
        self.batch.setText(test.test_batch)
        set_combo_value(self.customer, test.customer)
        if test.test_date:
            self.test_date.setDate(QDate(test.test_date))
        set_combo_value(self.qty, str(test.qty_samples))
        set_combo_value(self.rig, test.test_rig)
        set_combo_value(self.requester, test.requester)
        self.comments.setText("" if test.comments == "--" else test.comments)

    def _collect(self) -> GenericTest:
        return GenericTest(
            id=self.test.id if self.test else None,
            test_batch=validation.normalize_batch(self.batch.text()),
            customer=self.customer.currentText().strip(),
            requester=combo_value(self.requester),
            test_date=self.test_date.date().toPython(),
            qty_samples=int(self.qty.currentText()),
            comments=self.comments.text().strip() or "--",
            test_rig=self.rig.currentText().strip() or EMPTY_RIG,
        )

    def _save(self) -> None:
        test = self._collect()

        try:
            validation.validate_required(test.customer, test.qty_samples)
            validation.validate_test_batch(
                test.test_batch, self.catalogs.codes(self.config.key)
            )
            validation.validate_unique_batch(
                test.test_batch,
                self.repository.batch_exists(test.test_batch, exclude_id=test.id),
                editing=self.editing,
            )
        except validation.ValidationError as error:
            QMessageBox.warning(self, "Datos incompletos", str(error))
            return

        author = current_author()
        try:
            if self.editing:
                self.repository.update(test, author)
            else:
                self.created_id = self.repository.create(test, author)
        except Exception as error:  # pragma: no cover
            QMessageBox.critical(self, "Error al guardar", str(error))
            return

        self.accept()

    def _show_history(self) -> None:
        if not self.test or self.test.id is None:
            return
        HistoryDialog(
            self.audit_repository,
            table=self.repository.table,
            record_id=self.test.id,
            title=f"Historial de {self.test.test_batch}",
            parent=self,
        ).exec()
