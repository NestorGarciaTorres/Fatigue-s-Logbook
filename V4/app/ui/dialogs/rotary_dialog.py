"""Alta, edicion y consulta de una prueba Rotary.

Reemplaza a ``forms/edit_rotary_form.py``. De paso corrige el combo de rig:
alli se construia con ``values="I-25"`` -- una cadena, no una lista -- asi que
Tk la partia y ofrecia 'I', '-', '2' y '5' como cuatro opciones sueltas.
"""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QIntValidator
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
    QPushButton,
    QVBoxLayout,
)

from app.db.repositories import RotaryRepository
from app.models import EMPTY_RIG, FINISHED, SAMPLE_SLOTS, RotarySample, RotaryTest
from app.services import validation
from app.services.catalogs import CatalogService
from app.services.identity import current_author
from app.ui.dialogs.close_test_dialog import CloseTestDialog
from app.ui.dialogs.history_dialog import HistoryDialog
from app.ui.widgets.common import (
    CenteredComboBox,
    add_field,
    balance_field_columns,
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
from app.ui.widgets.sample_slot import SampleBox


class RotaryDialog(QDialog):
    def __init__(
        self,
        repository: RotaryRepository,
        catalogs: CatalogService,
        audit_repository,
        test: RotaryTest | None = None,
        read_only: bool = False,
        work_order=None,
        parent=None,
    ):
        super().__init__(parent)
        self.repository = repository
        self.catalogs = catalogs
        self.audit_repository = audit_repository
        self.test = test
        self.editing = test is not None
        self.read_only = read_only
        self.work_order = work_order
        self.created_id: int | None = None

        self.setWindowTitle(self._title())
        self.setMinimumWidth(900)
        self._build()

        if self.test:
            self._load(self.test)
            self._update_sample_slots()
        elif self.work_order is not None:
            self._prefill_from_work_order(self.work_order)
        if self.read_only:
            self._apply_read_only()

    def _title(self) -> str:
        if self.read_only:
            return "Prueba Rotary finalizada"
        if self.editing:
            return "Editar prueba Rotary"
        if self.work_order is not None:
            return f"Comenzar prueba  -  WO {self.work_order.test_batch}"
        return "Nueva prueba Rotary"

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(subheading(self._title()))

        # Tres columnas, igual que en Fatiga y alineadas con la rejilla 3x3 de
        # las muestras.
        general = QGroupBox("Datos generales")
        form = QGridLayout(general)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        self.batch = batch_edit()
        self.customer = closed_combo(self.catalogs.customer_names())
        self.start_date = make_date_edit()
        self.qty = quantity_combo()
        # Se puede vaciar: si la prueba se suspende, el banco queda libre y
        # el registro tiene que poder decirlo.
        self.rig = clearable_combo(self.catalogs.rig_names("rotary"),
                                   "(sin banco)")
        self.comments = centered_line_edit("Sin comentarios")

        self.end_date = make_date_edit()

        add_field(form, 0, 0, "* Test Batch", self.batch)
        add_field(form, 0, 1, "* Cliente", self.customer)
        add_field(form, 0, 2, "* Inicio de prueba", self.start_date)

        add_field(form, 1, 0, "* No. de piezas", self.qty)
        add_field(form, 1, 1, "* Rotary Rig", self.rig)
        self.end_date_label = add_field(form, 1, 2, "Fin de prueba",
                                        self.end_date)

        comments_label = QLabel("Comentarios")
        form.addWidget(comments_label, 2, 0,
                       alignment=Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter)
        form.addWidget(self.comments, 2, 1, 1, 5)

        balance_field_columns(form, 3)
        layout.addWidget(general)

        # Bandera en lugar de isVisible(): antes de mostrar el dialogo,
        # isVisible() responde False aunque ya se haya llamado setVisible(True).
        self.show_end = self.read_only or (
            self.test is not None and self.test.test_status == FINISHED
        )
        self.end_date.setVisible(self.show_end)
        self.end_date_label.setVisible(self.show_end)

        # --- muestras ----------------------------------------------------
        self.samples_group = QGroupBox("Datos de las muestras")
        samples_layout = QVBoxLayout(self.samples_group)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self.revs: list[QLineEdit] = []
        self.statuses: list[QComboBox] = []
        self.failure_modes: list[QComboBox] = []
        self.sample_boxes: list[SampleBox] = []
        status_labels = self.catalogs.sample_statuses()
        mode_names = self.catalogs.failure_modes()

        for slot in range(SAMPLE_SLOTS):
            revs = QLineEdit()
            revs.setValidator(QIntValidator(0, 2_000_000_000, self))
            revs.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.revs.append(revs)

            status = clearable_combo(status_labels, "(sin estatus)")
            status.setMinimumWidth(140)
            self.statuses.append(status)

            mode = clearable_combo(mode_names, "(sin modo)")
            mode.setMinimumWidth(140)
            mode.setToolTip(
                "Se edita en Ajustes -> Modos de falla. "
                "Déjalo vacío si la pieza no falló."
            )
            self.failure_modes.append(mode)

            box = SampleBox(
                slot + 1,
                [("Revoluciones", revs), ("Estatus", status),
                 ("Modo de falla", mode)],
            )
            self.sample_boxes.append(box)
            grid.addWidget(box, slot // 3, slot % 3)

        samples_layout.addLayout(grid)
        layout.addWidget(self.samples_group)

        # --- botones -----------------------------------------------------
        buttons = QHBoxLayout()

        self.finish_button = QPushButton("Finalizar prueba")
        self.finish_button.setProperty("accent", "warning")
        self.finish_button.clicked.connect(self._finish)
        buttons.addWidget(self.finish_button)

        self.reopen_button = QPushButton("Quitar de finalizados")
        self.reopen_button.clicked.connect(self._reopen)
        buttons.addWidget(self.reopen_button)

        self.history_button = QPushButton("Ver historial")
        self.history_button.setProperty("accent", "secondary")
        self.history_button.clicked.connect(self._show_history)
        buttons.addWidget(self.history_button)

        buttons.addStretch(1)

        self.button_box = QDialogButtonBox()
        self.save_button = self.button_box.addButton(
            "Guardar cambios" if self.editing else "Ingresar registro",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.save_button.setProperty("accent", "success")
        self.button_box.addButton(
            "Cerrar" if self.read_only else "Cancelar",
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        self.button_box.accepted.connect(self._save)
        self.button_box.rejected.connect(self.reject)
        buttons.addWidget(self.button_box)

        layout.addLayout(buttons)

        is_finished = self.test is not None and self.test.test_status == FINISHED
        self.finish_button.setVisible(self.editing and not is_finished)
        self.reopen_button.setVisible(is_finished)
        self.history_button.setVisible(self.editing)

        self.qty.currentTextChanged.connect(self._update_sample_slots)
        # Igual que en Fatiga: capturar en una pieza tambien recalcula, para
        # que la marca de 'de mas' aparezca al escribir y no al cambiar la
        # cantidad.
        for combo in (*self.statuses, *self.failure_modes):
            combo.currentIndexChanged.connect(self._update_sample_slots)
        for field in self.revs:
            field.textChanged.connect(self._update_sample_slots)

        self._update_sample_slots()

    def declared_samples(self) -> int:
        try:
            return int(self.qty.currentText())
        except (TypeError, ValueError):
            return SAMPLE_SLOTS

    def _update_sample_slots(self) -> None:
        """Habilita las piezas declaradas y apaga el resto.

        Igual que en Fatiga: las nueve se muestran siempre, solo se captura en
        las que la prueba declara, y una que sobre pero ya traiga datos se
        queda encendida y en ambar para poder corregirla.
        """
        declared = self.declared_samples()

        extras = 0
        for slot, box in enumerate(self.sample_boxes):
            beyond = slot >= declared
            with_data = box.has_data()
            extras += int(beyond and with_data)
            box.set_active(not self.read_only and (not beyond or with_data))
            box.mark_extra(beyond and with_data)

        title = "Datos de las muestras"
        if extras:
            title += f"  -  {extras} pieza(s) por encima de las declaradas"
        self.samples_group.setTitle(title)


    def _prefill_from_work_order(self, order) -> None:
        """Trae del documento lo que ya viene decidido.

        Se deja editable: si el Test Batch de la orden trae una errata, quien
        corre la prueba tiene que poder corregirla sin volver a Work Orders.
        """
        self.batch.setText(order.test_batch)
        set_combo_value(self.customer, order.customer)
        set_combo_value(self.qty, str(order.qty_samples))
        if order.comments:
            self.comments.setText(order.comments)
        self._update_sample_slots()

    # --- carga y guardado ------------------------------------------------
    def _load(self, test: RotaryTest) -> None:
        self.batch.setText(test.test_batch)
        set_combo_value(self.customer, test.customer)
        if test.start_date:
            self.start_date.setDate(QDate(test.start_date))
        if test.end_date:
            self.end_date.setDate(QDate(test.end_date))
        set_combo_value(self.qty, str(test.qty_samples))
        set_combo_value(self.rig, test.test_rig)
        self.comments.setText("" if test.comments == "--" else test.comments)

        for index, sample in enumerate(test.samples):
            empty = (
                sample.status in (None, "", EMPTY_RIG)
                and not sample.revs
                and not sample.failure_mode
            )
            if empty:
                self.revs[index].clear()
                set_combo_value(self.statuses[index], None)
                set_combo_value(self.failure_modes[index], None)
                continue

            self.revs[index].setText(
                "" if sample.revs is None else str(sample.revs)
            )
            set_combo_value(
                self.statuses[index],
                None if sample.status == EMPTY_RIG else sample.status,
            )
            set_combo_value(self.failure_modes[index], sample.failure_mode)

    def _apply_read_only(self) -> None:
        self.batch.setReadOnly(True)
        self.comments.setReadOnly(True)
        for widget in (self.customer, self.qty, self.rig, *self.statuses,
                       *self.failure_modes):
            widget.setEnabled(False)
        for widget in (self.start_date, self.end_date):
            widget.setReadOnly(True)
        for widget in self.revs:
            widget.setReadOnly(True)
        self.save_button.setVisible(False)
        self.finish_button.setVisible(False)

    def _collect(self) -> RotaryTest:
        samples = []
        for revs, status, mode in zip(self.revs, self.statuses,
                                      self.failure_modes):
            text = revs.text().strip()
            samples.append(
                RotarySample(
                    revs=int(text) if text.isdigit() else None,
                    status=combo_value(status) or EMPTY_RIG,
                    failure_mode=combo_value(mode),
                )
            )

        test = RotaryTest(
            id=self.test.id if self.test else None,
            test_batch=validation.normalize_batch(self.batch.text()),
            customer=self.customer.currentText().strip(),
            start_date=self.start_date.date().toPython(),
            end_date=self.test.end_date if self.test else None,
            qty_samples=int(self.qty.currentText()),
            comments=self.comments.text().strip() or "--",
            test_rig=combo_value(self.rig) or EMPTY_RIG,
            test_status=self.test.test_status if self.test else "Ongoing",
            samples=samples,
        )
        if self.show_end:
            test.end_date = self.end_date.date().toPython()
        return test

    def _save(self) -> None:
        test = self._collect()

        try:
            validation.validate_required(test.customer, test.qty_samples)
            validation.validate_test_batch(
                test.test_batch, self.catalogs.codes("rotary")
            )
            validation.validate_dates(test.start_date, test.end_date)
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

    def _completeness_fields(self, test: RotaryTest):
        """Que se exige para cerrar: generales y las piezas declaradas.

        Solo hasta la cantidad declarada; de ahi en adelante pueden ir vacias.
        """
        general = {
            "Test Batch": test.test_batch,
            "Cliente": test.customer,
            "Inicio de prueba": test.start_date,
            "No. de piezas": test.qty_samples,
            "Rotary Rig": "" if test.test_rig == EMPTY_RIG else test.test_rig,
        }

        samples = []
        for number in range(1, min(test.qty_samples, SAMPLE_SLOTS) + 1):
            sample = test.samples[number - 1]
            fields = {
                "Revoluciones": sample.revs,
                "Estatus": "" if sample.status == EMPTY_RIG else sample.status,
            }
            if validation.requires_failure_mode(sample.status):
                fields["Modo de falla"] = sample.failure_mode
            samples.append((number, fields))

        return general, samples

    def _finish(self) -> None:
        if not self.test or self.test.id is None:
            return

        test = self._collect()

        try:
            validation.validate_test_batch(
                test.test_batch, self.catalogs.codes("rotary")
            )
            validation.validate_unique_batch(
                test.test_batch,
                self.repository.batch_exists(test.test_batch, exclude_id=test.id),
                editing=True,
            )
            general, samples = self._completeness_fields(test)
            validation.validate_complete_for_finish(general, samples)
        except validation.ValidationError as error:
            QMessageBox.warning(self, "Faltan datos para finalizar", str(error))
            return

        dialog = CloseTestDialog(self.test.test_batch, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        end_date = dialog.end_date()
        try:
            validation.validate_dates(test.start_date, end_date)
        except validation.ValidationError as error:
            QMessageBox.warning(self, "Fecha inválida", str(error))
            return

        author = current_author()
        try:
            # Se guarda antes de cerrar: 'close' solo toca estatus y fecha, y
            # sin esto lo que el usuario acaba de capturar se perderia.
            self.repository.update(test, author)
            self.repository.close(self.test.id, end_date, author)
        except Exception as error:  # pragma: no cover
            QMessageBox.critical(self, "Error", str(error))
            return

        # Sin aviso de "listo": el dialogo se cierra y el registro cambia de
        # pestania a la vista. Un cuadro modal justo antes de accept() solo
        # anadia un clic para enterarse de lo que ya se ve.
        self.accept()

    def _reopen(self) -> None:
        if not self.test or self.test.id is None:
            return

        confirm = QMessageBox.question(
            self,
            "Confirmación",
            f"¿Deseas quitar el Test Batch {self.test.test_batch} "
            f"de la sección de pruebas finalizadas?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self.repository.reopen(self.test.id, current_author())
        except Exception as error:  # pragma: no cover
            QMessageBox.critical(self, "Error", str(error))
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
