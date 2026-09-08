"""Alta, edicion y consulta de una prueba de fatiga.

Reemplaza a ``forms/edit_fatigue_form.py``. Aquel formulario recibia una tupla
y tenia que decidir los indices segun si la prueba estaba finalizada
(``self.initial_rig_position = 7`` frente a ``6``), porque la consulta de
finalizadas incluia ``end_date`` a mitad de la lista. Aqui recibe un
``FatigueTest`` y ese problema desaparece.
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

from app.db.repositories import FatigueRepository
from app.models import EMPTY_RIG, FINISHED, SAMPLE_SLOTS, FatigueSample, FatigueTest
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


class FatigueDialog(QDialog):
    def __init__(
        self,
        repository: FatigueRepository,
        catalogs: CatalogService,
        audit_repository,
        test: FatigueTest | None = None,
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
        # Lo consulta quien abrio el formulario desde una Work Order, para
        # enlazarla con el registro recien creado.
        self.created_id: int | None = None

        self.setWindowTitle(self._title())
        self.setMinimumWidth(980)
        self._build()

        if self.test:
            self._load(self.test)
            # Otra vez despues de cargar: _load asigna las piezas despues del
            # numero declarado, y la primera pasada aun no las veia.
            self._update_sample_slots()
        elif self.work_order is not None:
            self._prefill_from_work_order(self.work_order)
        if self.read_only:
            self._apply_read_only()

    def _title(self) -> str:
        if self.read_only:
            return "Prueba de fatiga finalizada"
        if self.editing:
            return "Editar prueba de fatiga"
        if self.work_order is not None:
            return f"Comenzar prueba  -  WO {self.work_order.test_batch}"
        return "Nueva prueba de fatiga"

    # --- construccion ----------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(subheading(self._title()))

        # --- datos generales ---------------------------------------------
        # En tres columnas, alineadas con la rejilla 3x3 de las muestras. Antes
        # era una sola lista vertical y el campo de 'No. de piezas' medía lo
        # mismo que el de comentarios.
        general = QGroupBox("Datos generales")
        form = QGridLayout(general)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        self.batch = batch_edit()
        self.customer = closed_combo(self.catalogs.customer_names())
        self.start_date = make_date_edit()
        self.qty = quantity_combo()

        self.wo = closed_combo(["Si", "No"])
        self.wo.setCurrentIndex(0)

        self.end_date = make_date_edit()

        self.comments = centered_line_edit("Sin comentarios")

        add_field(form, 0, 0, "* Test Batch", self.batch)
        add_field(form, 0, 1, "* Cliente", self.customer)
        add_field(form, 0, 2, "* Inicio de prueba", self.start_date)

        add_field(form, 1, 0, "* No. de piezas", self.qty)
        add_field(form, 1, 1, "Tiene Work Order", self.wo)
        # La fecha de fin va al final de la fila: cuando no aplica, el hueco
        # queda en el borde y no parte la rejilla por la mitad.
        self.end_date_label = add_field(form, 1, 2, "Fin de prueba",
                                        self.end_date)

        comments_label = QLabel("Comentarios")
        form.addWidget(comments_label, 2, 0,
                       alignment=Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter)
        form.addWidget(self.comments, 2, 1, 1, 5)

        balance_field_columns(form, 3)
        layout.addWidget(general)

        # La fecha de fin solo tiene sentido en una prueba ya cerrada.
        # Se guarda como bandera y no se consulta con isVisible(): antes de
        # mostrar el dialogo, isVisible() es False aunque setVisible(True) ya
        # se haya llamado.
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

        self.rigs: list[QComboBox] = []
        self.results: list[QComboBox] = []
        self.cycles: list[QLineEdit] = []
        self.failure_modes: list[QComboBox] = []
        self.sample_boxes: list[SampleBox] = []
        # Banco y resultado son campos distintos desde la migracion 008: antes
        # compartian uno solo y el desplegable ofrecia las dos cosas mezcladas.
        rig_names = self.catalogs.rig_names("fatigue")
        status_names = self.catalogs.sample_statuses()
        mode_names = self.catalogs.failure_modes()

        for slot in range(SAMPLE_SLOTS):
            # Los tres combos se pueden volver a dejar en blanco. En el del
            # banco no es un detalle: una pieza que se suspende sale del rig y
            # vuelve despues, y quien captura tiene que poder borrar el banco
            # que ya habia anotado.
            rig = clearable_combo(rig_names, "(sin banco)")
            rig.setMinimumWidth(150)
            rig.setToolTip(
                "Banco en el que corre la pieza.\n"
                "Déjalo en '(sin banco)' mientras la pieza esté suspendida."
            )
            self.rigs.append(rig)

            result = clearable_combo(status_names, "(sin resultado)")
            result.setMinimumWidth(150)
            result.setToolTip("Cómo acabó la pieza: falló, no falló o se suspendió.")
            self.results.append(result)

            cycles = QLineEdit()
            cycles.setValidator(QIntValidator(0, 2_000_000_000, self))
            cycles.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cycles.append(cycles)

            # Se deja en blanco cuando la pieza no fallo: el catalogo describe
            # como fallo, no si fallo -- eso ya lo dice el campo de arriba.
            mode = clearable_combo(mode_names, "(sin modo)")
            mode.setMinimumWidth(150)
            mode.setToolTip(
                "Se edita en Ajustes -> Modos de falla. "
                "Déjalo vacío si la pieza no falló."
            )
            self.failure_modes.append(mode)

            box = SampleBox(
                slot + 1,
                [("Test Rig", rig), ("Resultado", result), ("Ciclos", cycles),
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

        # Si la prueba es de 2 piezas, los recuadros 3 al 9 se apagan.
        self.qty.currentTextChanged.connect(self._update_sample_slots)
        # Y tambien al capturar: hasta ahora la marca de 'pieza de mas' solo se
        # recalculaba al cambiar la cantidad, asi que escribir en la pieza 7 de
        # una prueba de 6 no marcaba nada hasta tocar el combo.
        for combo in (*self.rigs, *self.results, *self.failure_modes):
            combo.currentIndexChanged.connect(self._update_sample_slots)
        for field in self.cycles:
            field.textChanged.connect(self._update_sample_slots)

        self._update_sample_slots()

    def declared_samples(self) -> int:
        try:
            return int(self.qty.currentText())
        except (TypeError, ValueError):
            return SAMPLE_SLOTS

    def _update_sample_slots(self) -> None:
        """Habilita las piezas que caben en el numero declarado y apaga el resto.

        Las nueve se muestran siempre, pero solo se captura en las que la
        prueba declara: capturar la pieza 8 de una prueba de 6 era la forma de
        equivocarse mas facil que tenia el formulario.

        Con una excepcion: una pieza que sobra **pero ya trae datos** se queda
        encendida y en ambar. Hay registros antiguos asi, y apagarla dejaria el
        dato a la vista sin manera de corregirlo.
        """
        declared = self.declared_samples()

        extras = 0
        for slot, box in enumerate(self.sample_boxes):
            beyond = slot >= declared
            with_data = box.has_data()
            extras += int(beyond and with_data)
            # En consulta no se habilita nada: cargar el registro dispara las
            # senales de los campos, y sin esto una prueba finalizada acabaria
            # abriendose editable.
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
    def _load(self, test: FatigueTest) -> None:
        self.batch.setText(test.test_batch)
        set_combo_value(self.customer, test.customer)
        if test.start_date:
            self.start_date.setDate(QDate(test.start_date))
        if test.end_date:
            self.end_date.setDate(QDate(test.end_date))
        set_combo_value(self.qty, str(test.qty_samples))
        self.wo.setCurrentText("Si" if test.wo_status else "No")
        self.comments.setText("" if test.comments == "--" else test.comments)

        for index, sample in enumerate(test.samples):
            # Las ranuras sin usar se guardaron como "--" y 0, no como nulos.
            # Mostrarlas vacias evita que el formulario abra con nueve ceros.
            empty = (
                sample.rig in (None, "", EMPTY_RIG)
                and not sample.result
                and not sample.cycles
                and not sample.failure_mode
            )
            if empty:
                set_combo_value(self.rigs[index], None)
                set_combo_value(self.results[index], None)
                self.cycles[index].clear()
                set_combo_value(self.failure_modes[index], None)
                continue

            # El rig puede venir como "--" en una ranura que si se uso: basta
            # con que tenga resultado. Se muestra vacio, o el combo acabaria
            # ofreciendo "--" como si fuera un banco mas.
            set_combo_value(
                self.rigs[index],
                None if sample.rig == EMPTY_RIG else sample.rig,
            )
            set_combo_value(self.results[index], sample.result)
            self.cycles[index].setText(
                "" if sample.cycles is None else str(sample.cycles)
            )
            set_combo_value(self.failure_modes[index], sample.failure_mode)

    def _apply_read_only(self) -> None:
        self.batch.setReadOnly(True)
        self.comments.setReadOnly(True)
        for widget in (self.customer, self.qty, self.wo, *self.rigs,
                       *self.results, *self.failure_modes):
            widget.setEnabled(False)
        for widget in (self.start_date, self.end_date):
            widget.setReadOnly(True)
        for widget in self.cycles:
            widget.setReadOnly(True)
        self.save_button.setVisible(False)
        self.finish_button.setVisible(False)

    def _collect(self) -> FatigueTest:
        samples = []
        for rig, result, cycles, mode in zip(
            self.rigs, self.results, self.cycles, self.failure_modes
        ):
            text = cycles.text().strip()
            samples.append(
                FatigueSample(
                    rig=combo_value(rig) or EMPTY_RIG,
                    result=combo_value(result),
                    cycles=int(text) if text.isdigit() else None,
                    failure_mode=combo_value(mode),
                )
            )

        test = FatigueTest(
            id=self.test.id if self.test else None,
            test_batch=validation.normalize_batch(self.batch.text()),
            customer=self.customer.currentText().strip(),
            start_date=self.start_date.date().toPython(),
            end_date=self.test.end_date if self.test else None,
            qty_samples=int(self.qty.currentText()),
            comments=self.comments.text().strip() or "--",
            wo_status=self.wo.currentText() == "Si",
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
                test.test_batch, self.catalogs.codes("fatigue")
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
        except Exception as error:  # pragma: no cover - depende de la red
            QMessageBox.critical(self, "Error al guardar", str(error))
            return

        self.accept()

    # --- acciones --------------------------------------------------------
    def _completeness_fields(self, test: FatigueTest):
        """Que se exige para cerrar: los generales y las piezas declaradas.

        Solo hasta la cantidad declarada. Si se probaron 6 piezas, de la 7 a la
        9 se cierran vacias.
        """
        general = {
            "Test Batch": test.test_batch,
            "Cliente": test.customer,
            "Inicio de prueba": test.start_date,
            "No. de piezas": test.qty_samples,
            "Tiene Work Order": self.wo.currentText(),
        }

        samples = []
        for number in range(1, min(test.qty_samples, SAMPLE_SLOTS) + 1):
            sample = test.samples[number - 1]
            fields = {
                "Test Rig": "" if sample.rig == EMPTY_RIG else sample.rig,
                "Resultado": sample.result,
                "Ciclos": sample.cycles,
            }
            # El modo de falla solo se pide a la pieza que fallo: en una
            # 'S/Falla' no hay nada que describir.
            if validation.requires_failure_mode(sample.result):
                fields["Modo de falla"] = sample.failure_mode
            samples.append((number, fields))

        return general, samples

    def _finish(self) -> None:
        if not self.test or self.test.id is None:
            return

        test = self._collect()

        # Se valida contra lo que hay en pantalla, no contra lo guardado: el
        # usuario suele llenar los ultimos campos y pulsar 'Finalizar' sin
        # guardar antes.
        try:
            validation.validate_test_batch(
                test.test_batch, self.catalogs.codes("fatigue")
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
            # Primero se guarda lo capturado y luego se cierra. Antes 'close'
            # solo tocaba el estatus y la fecha, asi que lo que el usuario
            # acababa de escribir en el formulario se perdia al finalizar.
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
