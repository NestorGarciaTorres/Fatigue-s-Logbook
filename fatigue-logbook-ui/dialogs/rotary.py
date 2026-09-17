"""Alta, edicion y consulta de una prueba de Rotary.

Misma forma que Fatiga, con una diferencia de fondo: **el banco es de la prueba
entera**, no de cada pieza. Por eso el Rotary Rig esta en los datos generales y
no en cada recuadro, y vaciarlo suspende de golpe todas las piezas que
seguian corriendo.

Cada pieza lleva tres campos --revoluciones, estatus y modo de falla-- en vez
de los cuatro de Fatiga.
"""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from app.models import (
    EMPTY_RIG,
    FINISHED,
    ONGOING,
    SAMPLE_SLOTS,
    RotarySample,
    RotaryTest,
)
from app.services import validation
from app.services.identity import current_author
from components import buttons, fields, labels
from components.forms import (
    VISIBLE_SAMPLE_ROWS,
    SampleBox,
    add_field,
    balance_field_columns,
    quantity_combo,
    visible_rows_height,
)
from dialogs.base import FormDialog, gather_issues, missing_issues, update_merging


class RotaryDialog(FormDialog):
    def __init__(self, repository, catalogs, audit_repository,
                 test: RotaryTest | None = None, read_only: bool = False,
                 work_order=None, parent=None):
        self.repository = repository
        self.catalogs = catalogs
        self.audit_repository = audit_repository
        self.test = test
        self.editing = test is not None
        self.read_only = read_only
        self.work_order = work_order
        self.created_id: int | None = None

        super().__init__(self._title(), self._subtitle(), parent)
        self.setMinimumWidth(940)
        self._build()

        if self.test:
            self._load(self.test)
            self._update_sample_slots()
        elif self.work_order is not None:
            self._prefill_from_work_order(self.work_order)
        if self.read_only:
            self._apply_read_only()

        self.finish_setup(preferred_body=visible_rows_height(
            self.body, self.sample_boxes, self.samples_grid,
            VISIBLE_SAMPLE_ROWS))

    def _title(self) -> str:
        if self.read_only:
            return "Consultar prueba de Rotary"
        if self.editing:
            return "Editar prueba de Rotary"
        if self.work_order is not None:
            return "Comenzar prueba de Rotary"
        return "Nueva prueba de Rotary"

    def _subtitle(self) -> str:
        if self.work_order is not None and not self.editing:
            return (f"Desde la Work Order {self.work_order.test_batch}. "
                    f"Los datos se pueden corregir antes de guardar.")
        if self.test is not None:
            return f"{self.test.test_batch}  ·  {self.test.customer}"
        return ""

    # --- construccion -------------------------------------------------------
    def _build(self) -> None:
        self.set_body(self._general_block(), self._samples_block())

        self.finish_button = buttons.button(
            "Finalizar prueba", buttons.WARNING, on_click=self._finish)
        self.reopen_button = buttons.button("Quitar de finalizados",
                                            on_click=self._reopen)
        self.history_button = buttons.button("Ver historial", buttons.GHOST,
                                             on_click=self._show_history)

        self.finish_button.setVisible(self.editing and not self.read_only)
        self.reopen_button.setVisible(
            self.editing and self.test.test_status == FINISHED)
        self.history_button.setVisible(self.editing)

        self.set_footer(self.finish_button, self.reopen_button,
                        self.history_button)

    def _general_block(self) -> QGroupBox:
        general = QGroupBox("Datos generales")
        form = QGridLayout(general)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        self.batch = fields.batch_edit()
        self.customer = fields.closed_combo(self.catalogs.customer_names())
        self.start_date = fields.date_edit()
        self.qty = quantity_combo()
        self.rig = fields.clearable_combo(self.catalogs.rig_names("rotary"),
                                          "(sin banco)")
        self.rig.setToolTip(
            "En Rotary el banco es de la prueba entera.\n"
            "Déjalo vacío para suspender las piezas que estén corriendo.")
        self.requester = fields.clearable_combo(self.catalogs.requesters(),
                                                "(sin solicitante)")
        self.requester.setToolTip(
            "Quién pidió la prueba. Se edita en Ajustes → Solicitantes.")
        self.end_date = fields.date_edit()
        self.comments = fields.line_edit("Sin comentarios")

        add_field(form, 0, 0, "* Test Batch", self.batch)
        add_field(form, 0, 1, "* Cliente", self.customer)
        add_field(form, 0, 2, "* Inicio de prueba", self.start_date)

        add_field(form, 1, 0, "* No. de piezas", self.qty)
        add_field(form, 1, 1, "* Rotary Rig", self.rig)
        self.end_date_label = add_field(form, 1, 2, "Fin de prueba",
                                        self.end_date)

        # Llega de la Work Order y se queda en el registro. Opcional: las
        # pruebas anteriores a las Work Orders no tienen solicitante.
        add_field(form, 2, 0, "Solicitante", self.requester)

        form.addWidget(labels.muted("Comentarios"), 3, 0,
                       alignment=Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter)
        form.addWidget(self.comments, 3, 1, 1, 5)
        balance_field_columns(form, 3)

        # Bandera en lugar de isVisible(): antes de mostrar el dialogo,
        # isVisible() responde False aunque ya se haya llamado setVisible.
        self.show_end = self.read_only or (
            self.test is not None and self.test.test_status == FINISHED)
        self.end_date.setVisible(self.show_end)
        self.end_date_label.setVisible(self.show_end)

        self.qty.currentIndexChanged.connect(self._update_sample_slots)
        return general

    def _samples_block(self) -> QGroupBox:
        self.samples_group = QGroupBox("Datos de las muestras")
        columna = QVBoxLayout(self.samples_group)

        rejilla = QGridLayout()
        rejilla.setHorizontalSpacing(12)
        rejilla.setVerticalSpacing(10)
        self.samples_grid = rejilla

        self.revs: list[QLineEdit] = []
        self.statuses: list[QComboBox] = []
        self.failure_modes: list[QComboBox] = []
        self.sample_boxes: list[SampleBox] = []

        estados = self.catalogs.sample_statuses()
        modos = self.catalogs.failure_modes()

        for slot in range(SAMPLE_SLOTS):
            revoluciones = fields.number_edit()
            self.revs.append(revoluciones)

            estado = fields.clearable_combo(estados, "(sin estatus)")
            estado.setMinimumWidth(150)
            estado.setToolTip(
                "Cómo acabó la pieza: falló, no falló o se suspendió.")
            self.statuses.append(estado)

            modo = fields.clearable_combo(modos, "(sin modo)")
            modo.setMinimumWidth(150)
            modo.setToolTip("Se edita en Ajustes → Modos de falla. "
                            "Déjalo vacío si la pieza no falló.")
            self.failure_modes.append(modo)

            caja = SampleBox(slot + 1, [("Revoluciones", revoluciones),
                                        ("Estatus", estado),
                                        ("Modo de falla", modo)])
            self.sample_boxes.append(caja)
            rejilla.addWidget(caja, slot // 3, slot % 3)

        columna.addLayout(rejilla)
        self._update_sample_slots()
        return self.samples_group

    # --- estado de las piezas -----------------------------------------------
    def declared_samples(self) -> int:
        try:
            return int(self.qty.currentText())
        except (TypeError, ValueError):
            return SAMPLE_SLOTS

    def _update_sample_slots(self) -> None:
        """Igual que en Fatiga: las nueve se ensenian siempre, solo se captura
        en las declaradas, y una que sobre pero traiga datos se queda encendida
        y en ambar para poder corregirla."""
        declaradas = self.declared_samples()

        extras = 0
        for slot, caja in enumerate(self.sample_boxes):
            sobra = slot >= declaradas
            con_datos = caja.has_data()
            extras += int(sobra and con_datos)
            caja.set_active(not self.read_only and (not sobra or con_datos))
            caja.mark_extra(sobra and con_datos)

        titulo = "Datos de las muestras"
        if extras:
            titulo += f"  ·  {extras} pieza(s) por encima de las declaradas"
        self.samples_group.setTitle(titulo)

    def _field_for(self, number, caption):
        if number is None:
            return {"Test Batch": self.batch,
                    "Cliente": self.customer,
                    "Inicio de prueba": self.start_date,
                    "No. de piezas": self.qty,
                    "Rotary Rig": self.rig}.get(caption)
        slot = number - 1
        return {"Revoluciones": self.revs[slot],
                "Estatus": self.statuses[slot],
                "Modo de falla": self.failure_modes[slot]}.get(caption)

    # --- carga --------------------------------------------------------------
    def _prefill_from_work_order(self, order) -> None:
        self.batch.setText(order.test_batch)
        fields.set_combo_value(self.customer, order.customer)
        fields.set_combo_value(self.requester, order.requester)
        fields.set_combo_value(self.qty, str(order.qty_samples))
        if order.comments:
            self.comments.setText(order.comments)
        self._update_sample_slots()

    def _load(self, test: RotaryTest) -> None:
        self.batch.setText(test.test_batch)
        fields.set_combo_value(self.customer, test.customer)
        fields.set_combo_value(self.requester, test.requester)
        if test.start_date:
            self.start_date.setDate(QDate(test.start_date))
        if test.end_date:
            self.end_date.setDate(QDate(test.end_date))
        fields.set_combo_value(self.qty, str(test.qty_samples))
        fields.set_combo_value(
            self.rig, None if test.test_rig == EMPTY_RIG else test.test_rig)
        self.comments.setText("" if test.comments == "--" else test.comments)

        for indice, sample in enumerate(test.samples):
            vacia = (not sample.revs
                     and sample.status in (None, "", EMPTY_RIG)
                     and not sample.failure_mode)
            if vacia:
                self.revs[indice].clear()
                fields.set_combo_value(self.statuses[indice], None)
                fields.set_combo_value(self.failure_modes[indice], None)
                continue
            self.revs[indice].setText(
                "" if sample.revs is None else str(sample.revs))
            fields.set_combo_value(
                self.statuses[indice],
                None if sample.status == EMPTY_RIG else sample.status)
            fields.set_combo_value(self.failure_modes[indice],
                                   sample.failure_mode)

    def _apply_read_only(self) -> None:
        self.batch.setReadOnly(True)
        self.comments.setReadOnly(True)
        for widget in (self.customer, self.qty, self.rig, self.requester,
                       *self.statuses, *self.failure_modes):
            widget.setEnabled(False)
        for widget in (self.start_date, self.end_date):
            widget.setReadOnly(True)
        for widget in self.revs:
            widget.setReadOnly(True)
        self.save_button.setVisible(False)
        self.finish_button.setVisible(False)
        self.cancel_button.setText("Cerrar")

    # --- guardado -----------------------------------------------------------
    def _collect(self) -> RotaryTest:
        muestras = []
        for revoluciones, estado, modo in zip(self.revs, self.statuses,
                                              self.failure_modes):
            texto = revoluciones.text().strip()
            muestras.append(RotarySample(
                revs=int(texto) if texto.isdigit() else None,
                status=fields.combo_value(estado) or EMPTY_RIG,
                failure_mode=fields.combo_value(modo)))

        test = RotaryTest(
            id=self.test.id if self.test else None,
            test_batch=validation.normalize_batch(self.batch.text()),
            customer=self.customer.currentText().strip(),
            requester=fields.combo_value(self.requester),
            start_date=fields.to_date(self.start_date),
            end_date=self.test.end_date if self.test else None,
            qty_samples=int(self.qty.currentText()),
            comments=self.comments.text().strip() or "--",
            test_rig=fields.combo_value(self.rig) or EMPTY_RIG,
            test_status=self.test.test_status if self.test else ONGOING,
            samples=muestras)
        if self.show_end:
            test.end_date = fields.to_date(self.end_date)
        return test

    def _batch_checks(self, test, editing: bool):
        return (self.batch, lambda: (
            validation.validate_test_batch(test.test_batch,
                                           self.catalogs.codes("rotary")),
            validation.validate_unique_batch(
                test.test_batch,
                self.repository.batch_exists(test.test_batch,
                                             exclude_id=test.id),
                editing=editing)))

    def _save(self) -> None:
        test = self._collect()
        problemas = gather_issues([
            (self.customer, lambda: validation.validate_required(
                test.customer, test.qty_samples)),
            self._batch_checks(test, self.editing),
            (self.end_date if self.show_end else self.start_date,
             lambda: validation.validate_dates(test.start_date,
                                               test.end_date)),
        ])
        if problemas:
            self.show_issues("No se puede guardar", problemas)
            return
        self.clear_issues()

        autor = current_author()
        try:
            if self.editing:
                if not update_merging(self, self.repository, test, autor,
                                      base=self.test):
                    return
            else:
                self.created_id = self.repository.create(test, autor)
        except Exception as error:             # pragma: no cover - depende de red
            QMessageBox.critical(self, "Error al guardar", str(error))
            return
        self.accept()

    # --- cerrar y reabrir ---------------------------------------------------
    def _completeness_fields(self, test: RotaryTest):
        general = {"Test Batch": test.test_batch,
                   "Cliente": test.customer,
                   "Inicio de prueba": test.start_date,
                   "No. de piezas": test.qty_samples,
                   "Rotary Rig": ("" if test.test_rig == EMPTY_RIG
                                  else test.test_rig)}

        muestras = []
        for numero in range(1, min(test.qty_samples, SAMPLE_SLOTS) + 1):
            sample = test.samples[numero - 1]
            campos = {"Revoluciones": sample.revs,
                      "Estatus": ("" if sample.status == EMPTY_RIG
                                  else sample.status)}
            if validation.requires_failure_mode(sample.status):
                campos["Modo de falla"] = sample.failure_mode
            muestras.append((numero, campos))
        return general, muestras

    def _finish(self) -> None:
        if not self.test or self.test.id is None:
            return

        test = self._collect()
        general, muestras = self._completeness_fields(test)
        problemas = gather_issues([self._batch_checks(test, True)]) \
            + missing_issues(general, muestras, self._field_for)
        if problemas:
            self.show_issues("No se puede finalizar la prueba", problemas)
            return
        self.clear_issues()

        from dialogs.close_test import CloseTestDialog

        dialogo = CloseTestDialog(self.test.test_batch, parent=self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        fin = dialogo.end_date()
        try:
            validation.validate_dates(test.start_date, fin)
        except validation.ValidationError as error:
            QMessageBox.warning(self, "Fecha inválida", str(error))
            return

        autor = current_author()
        try:
            if not update_merging(self, self.repository, test, autor,
                                  base=self.test):
                return
            self.repository.close(self.test.id, fin, autor)
        except Exception as error:             # pragma: no cover
            QMessageBox.critical(self, "Error", str(error))
            return
        self.accept()

    def _reopen(self) -> None:
        if not self.test or self.test.id is None:
            return
        confirmar = QMessageBox.question(
            self, "Confirmación",
            f"¿Deseas quitar el Test Batch {self.test.test_batch} de las "
            f"pruebas finalizadas?")
        if confirmar != QMessageBox.StandardButton.Yes:
            return
        try:
            self.repository.reopen(self.test.id, current_author())
        except Exception as error:             # pragma: no cover
            QMessageBox.critical(self, "Error", str(error))
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
