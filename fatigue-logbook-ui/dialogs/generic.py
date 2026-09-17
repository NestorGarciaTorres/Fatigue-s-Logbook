"""Alta, edicion y consulta de una prueba de Torsion o Quasi.

Las dos comparten forma --una sola fecha, un solo rig, sin estatus ni piezas
individuales-- asi que comparten formulario, parametrizado por su
``TestTypeConfig``.

Cabe de sobra en un portatil, y aun asi usa la misma estructura que los demas:
cuerpo desplazable y botones fijos. Con la escala de Windows alta, un
formulario que hoy cabe deja de caber, y entonces el boton de guardar se va
fuera de la pantalla sin que nadie lo haya tocado.
"""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QFormLayout, QGroupBox, QMessageBox

from app.models import EMPTY_RIG, GenericTest, TestTypeConfig
from app.services import validation
from app.services.identity import current_author
from components import buttons, fields
from components.forms import quantity_combo
from dialogs.base import FormDialog, gather_issues, update_merging


class GenericDialog(FormDialog):
    def __init__(self, repository, catalogs, audit_repository,
                 config: TestTypeConfig, test: GenericTest | None = None,
                 work_order=None, parent=None):
        self.repository = repository
        self.catalogs = catalogs
        self.audit_repository = audit_repository
        self.config = config
        self.test = test
        self.editing = test is not None
        self.work_order = work_order
        self.created_id: int | None = None

        super().__init__(self._title(), self._subtitle(), parent)
        self.setMinimumWidth(560)
        self._build()

        if self.test:
            self._load(self.test)
        elif self.work_order is not None:
            self._prefill_from_work_order(self.work_order)

        self.finish_setup()

    def _title(self) -> str:
        if self.editing:
            return f"Editar prueba de {self.config.label}"
        if self.work_order is not None:
            return f"Comenzar prueba de {self.config.label}"
        return f"Nueva prueba de {self.config.label}"

    def _subtitle(self) -> str:
        if self.work_order is not None and not self.editing:
            return (f"Desde la Work Order {self.work_order.test_batch}. "
                    f"Los datos se pueden corregir antes de guardar.")
        if self.test is not None:
            return f"{self.test.test_batch}  ·  {self.test.customer}"
        return ""

    # --- construccion -------------------------------------------------------
    def _build(self) -> None:
        grupo = QGroupBox("Datos de la prueba")
        form = QFormLayout(grupo)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)

        self.batch = fields.batch_edit()
        self.customer = fields.closed_combo(self.catalogs.customer_names())
        self.test_date = fields.date_edit()
        self.qty = quantity_combo()
        self.rig = fields.closed_combo(
            self.catalogs.rig_names(self.config.key))
        # Llega de la Work Order y se queda en el registro. Opcional: los
        # registros anteriores a las Work Orders no tienen solicitante.
        self.requester = fields.clearable_combo(self.catalogs.requesters(),
                                                "(sin solicitante)")
        self.requester.setToolTip(
            "Quién pidió la prueba. Se edita en Ajustes → Solicitantes.")
        self.comments = fields.line_edit("Sin comentarios")

        form.addRow("* Test Batch", self.batch)
        form.addRow("* Cliente", self.customer)
        form.addRow("* Fecha de prueba", self.test_date)
        form.addRow("* No. de piezas", self.qty)
        form.addRow("* Test Rig", self.rig)
        form.addRow("Solicitante", self.requester)
        form.addRow("Comentarios", self.comments)

        self.set_body(grupo)

        self.history_button = buttons.button("Ver historial", buttons.GHOST,
                                             on_click=self._show_history)
        self.history_button.setVisible(self.editing)
        self.set_footer(
            self.history_button,
            save="Guardar cambios" if self.editing else "Ingresar registro")

    # --- carga --------------------------------------------------------------
    def _prefill_from_work_order(self, order) -> None:
        """Trae del documento lo que ya viene decidido.

        Se deja editable, igual que en Fatiga: si el Test Batch de la orden
        trae una errata, quien corre la prueba tiene que poder corregirla sin
        volver a Work Orders.
        """
        self.batch.setText(order.test_batch)
        fields.set_combo_value(self.customer, order.customer)
        fields.set_combo_value(self.requester, order.requester)
        fields.set_combo_value(self.qty, str(order.qty_samples))
        if order.comments:
            self.comments.setText(order.comments)

    def _load(self, test: GenericTest) -> None:
        self.batch.setText(test.test_batch)
        fields.set_combo_value(self.customer, test.customer)
        fields.set_combo_value(self.requester, test.requester)
        if test.test_date:
            self.test_date.setDate(QDate(test.test_date))
        fields.set_combo_value(self.qty, str(test.qty_samples))
        fields.set_combo_value(
            self.rig, None if test.test_rig == EMPTY_RIG else test.test_rig)
        self.comments.setText("" if test.comments == "--" else test.comments)

    # --- guardado -----------------------------------------------------------
    def _collect(self) -> GenericTest:
        return GenericTest(
            id=self.test.id if self.test else None,
            test_batch=validation.normalize_batch(self.batch.text()),
            customer=self.customer.currentText().strip(),
            requester=fields.combo_value(self.requester),
            test_date=fields.to_date(self.test_date),
            qty_samples=int(self.qty.currentText()),
            comments=self.comments.text().strip() or "--",
            test_rig=self.rig.currentText().strip() or EMPTY_RIG)

    def _save(self) -> None:
        test = self._collect()

        problemas = gather_issues([
            (self.customer, lambda: validation.validate_required(
                test.customer, test.qty_samples)),
            (self.batch, lambda: (
                validation.validate_test_batch(
                    test.test_batch, self.catalogs.codes(self.config.key)),
                validation.validate_unique_batch(
                    test.test_batch,
                    self.repository.batch_exists(test.test_batch,
                                                 exclude_id=test.id),
                    editing=self.editing))),
        ])
        if problemas:
            self.show_issues("No se puede guardar", problemas)
            return
        self.clear_issues()

        autor = current_author()
        try:
            if self.editing:
                # Contra la prueba tal como se abrio, igual que en Fatiga.
                if not update_merging(self, self.repository, test, autor,
                                      base=self.test):
                    return
            else:
                self.created_id = self.repository.create(test, autor)
        except Exception as error:             # pragma: no cover
            QMessageBox.critical(self, "Error al guardar", str(error))
            return
        self.accept()

    def _show_history(self) -> None:
        if not self.test or self.test.id is None:
            return
        from dialogs.history import HistoryDialog

        HistoryDialog(self.audit_repository, table=self.repository.table,
                      record_id=self.test.id,
                      title=f"Historial de {self.test.test_batch}",
                      parent=self).exec()
