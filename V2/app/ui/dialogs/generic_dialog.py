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
    closed_combo,
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
        parent=None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.catalogs = catalogs
        self.audit_repository = audit_repository
        self.config = config
        self.test = test
        self.editing = test is not None

        action = "Editar" if self.editing else "Nueva prueba de"
        self.setWindowTitle(f"{action} {config.label}")
        self.setMinimumWidth(460)

        self._build()
        if self.test:
            self._load(self.test)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        action = "Editar prueba de" if self.editing else "Nueva prueba de"
        layout.addWidget(subheading(f"{action} {self.config.label}"))

        group = QGroupBox("Datos de la prueba")
        form = QFormLayout(group)
        form.setHorizontalSpacing(18)

        self.batch = batch_edit()
        self.customer = closed_combo(self.catalogs.customer_names())
        self.test_date = make_date_edit()
        self.qty = quantity_combo()
        self.rig = closed_combo(self.catalogs.rig_names(self.config.key))
        self.comments = centered_line_edit("Sin comentarios")

        form.addRow("* Test Batch", self.batch)
        form.addRow("* Cliente", self.customer)
        form.addRow("* Fecha de prueba", self.test_date)
        form.addRow("* No. de piezas", self.qty)
        form.addRow("* Test Rig", self.rig)
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

    def _load(self, test: GenericTest) -> None:
        self.batch.setText(test.test_batch)
        set_combo_value(self.customer, test.customer)
        if test.test_date:
            self.test_date.setDate(QDate(test.test_date))
        set_combo_value(self.qty, str(test.qty_samples))
        set_combo_value(self.rig, test.test_rig)
        self.comments.setText("" if test.comments == "--" else test.comments)

    def _collect(self) -> GenericTest:
        return GenericTest(
            id=self.test.id if self.test else None,
            test_batch=validation.normalize_batch(self.batch.text()),
            customer=self.customer.currentText().strip(),
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
                self.repository.create(test, author)
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
