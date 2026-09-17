"""Alta, edicion y consulta de una prueba de fatiga.

Es el formulario mas grande de la app: nueve piezas de cuatro campos cada una,
mas los datos generales. De ahi salen casi todas las reglas de forma que usa el
resto:

- **Se abre por filas, no entero.** Las nueve piezas estan siempre ahi, pero la
  ventana nace ensenando dos filas; con las nueve pedia 967 px de alto y en un
  portatil el boton de guardar quedaba fuera de la pantalla.
- **Las piezas que sobran del numero declarado se apagan, no se ocultan.** Con
  una excepcion: si ya traen datos se quedan encendidas y en ambar. Hay
  registros antiguos asi, y apagarlas dejaria el dato a la vista sin manera de
  corregirlo.
- **Los bancos en mantenimiento no se ofrecen.** Poner una pieza en un banco
  parado es capturar algo que no puede estar pasando. La opcion se oculta pero
  el dato no se borra: una pieza que ya tenia ese banco lo conserva.
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

from app import dates
from app.models import (
    EMPTY_RIG,
    FINISHED,
    ONGOING,
    SAMPLE_SLOTS,
    SUSPENDED_RESULT,
    FatigueSample,
    FatigueTest,
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


class FatigueDialog(FormDialog):
    def __init__(self, repository, catalogs, audit_repository,
                 test: FatigueTest | None = None, read_only: bool = False,
                 work_order=None, paused: dict | None = None,
                 unavailable_rigs: set | None = None, parent=None):
        self.repository = repository
        self.catalogs = catalogs
        self.audit_repository = audit_repository
        self.test = test
        # Piezas detenidas porque su banco esta en mantenimiento, por numero.
        # Sin esto el formulario ensenia el Test Rig vacio y nada que lo
        # explique, que es justo lo que se pretende evitar.
        self.paused = dict(paused or {})
        self.unavailable_rigs = set(unavailable_rigs or ())
        self.editing = test is not None
        self.read_only = read_only
        self.work_order = work_order
        # Lo consulta quien abrio el formulario desde una Work Order, para
        # enlazarla con el registro recien creado.
        self.created_id: int | None = None

        super().__init__(self._title(), self._subtitle(), parent)
        self.setMinimumWidth(1000)
        self._build()

        if self.test:
            self._load(self.test)
            # Otra vez despues de cargar: _load asigna las piezas por encima
            # del numero declarado, y la primera pasada aun no las veia.
            self._update_sample_slots()
        elif self.work_order is not None:
            self._prefill_from_work_order(self.work_order)
        if self.read_only:
            self._apply_read_only()
        self._update_moved_rows()

        self.finish_setup(preferred_body=visible_rows_height(
            self.body, self.sample_boxes, self.samples_grid,
            VISIBLE_SAMPLE_ROWS))

    # --- rotulos ------------------------------------------------------------
    def _title(self) -> str:
        if self.read_only:
            return "Consultar prueba de fatiga"
        if self.editing:
            return "Editar prueba de fatiga"
        if self.work_order is not None:
            return "Comenzar prueba de fatiga"
        return "Nueva prueba de fatiga"

    def _subtitle(self) -> str:
        if self.work_order is not None and not self.editing:
            return (f"Desde la Work Order {self.work_order.test_batch}. "
                    f"Los datos se pueden corregir antes de guardar.")
        if self.test is not None:
            return f"{self.test.test_batch}  ·  {self.test.customer}"
        return ""

    # --- construccion -------------------------------------------------------
    def _build(self) -> None:
        general = self._general_block()
        samples = self._samples_block()
        self.set_body(general, samples)

        self.finish_button = buttons.button(
            "Finalizar prueba", buttons.WARNING,
            tooltip="Cierra la prueba. Se exige el registro completo.",
            on_click=self._finish)
        self.reopen_button = buttons.button(
            "Quitar de finalizados", on_click=self._reopen)
        self.history_button = buttons.button(
            "Ver historial", buttons.GHOST, on_click=self._show_history)

        # Solo tienen sentido sobre un registro que ya existe.
        self.finish_button.setVisible(self.editing and not self.read_only)
        self.reopen_button.setVisible(
            self.editing and self.test.test_status == FINISHED)
        self.history_button.setVisible(self.editing)

        self.set_footer(self.finish_button, self.reopen_button,
                        self.history_button)

    def _general_block(self) -> QGroupBox:
        """Los datos de la prueba, en tres columnas.

        Alineadas con la rejilla 3x3 de las muestras. En una sola lista
        vertical, el campo de 'No. de piezas' medía lo mismo que el de
        comentarios.
        """
        general = QGroupBox("Datos generales")
        form = QGridLayout(general)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        self.batch = fields.batch_edit()
        self.customer = fields.closed_combo(self.catalogs.customer_names())
        self.start_date = fields.date_edit()
        self.qty = quantity_combo()

        self.wo = fields.closed_combo(["Si", "No"])
        self.wo.setCurrentIndex(0)

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
        add_field(form, 1, 1, "Tiene Work Order", self.wo)
        # La fecha de fin va al final de la fila: cuando no aplica, el hueco
        # queda en el borde y no parte la rejilla por la mitad.
        self.end_date_label = add_field(form, 1, 2, "Fin de prueba",
                                        self.end_date)

        # El solicitante llega de la Work Order y se queda en el registro. No
        # es obligatorio: los cientos de pruebas anteriores a las Work Orders
        # no tienen ninguno, y exigirlo impediria cerrarlas.
        add_field(form, 2, 0, "Solicitante", self.requester)

        form.addWidget(labels.muted("Comentarios"), 3, 0,
                       alignment=Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter)
        form.addWidget(self.comments, 3, 1, 1, 5)
        balance_field_columns(form, 3)

        # La fecha de fin solo tiene sentido en una prueba ya cerrada. Se
        # guarda como bandera y no se consulta con isVisible(): antes de
        # mostrar el dialogo, isVisible() es False aunque setVisible(True) ya
        # se haya llamado.
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

        self.rigs: list[QComboBox] = []
        self.results: list[QComboBox] = []
        self.cycles: list[QLineEdit] = []
        self.failure_modes: list[QComboBox] = []
        self.sample_boxes: list[SampleBox] = []

        # Sin los bancos en mantenimiento. Una pieza que ya estaba en uno
        # conserva su valor: set_combo_value lo agrega a la lista al cargar.
        nombres = [n for n in self.catalogs.rig_names("fatigue")
                   if n not in self.unavailable_rigs]
        estados = self.catalogs.sample_statuses()
        modos = self.catalogs.failure_modes()

        for slot in range(SAMPLE_SLOTS):
            # Los tres combos se pueden volver a dejar en blanco. En el del
            # banco no es un detalle: una pieza que se suspende sale del rig y
            # vuelve despues, y quien captura tiene que poder borrarlo.
            rig = fields.clearable_combo(nombres, "(sin banco)")
            rig.setMinimumWidth(150)
            rig.setToolTip("Banco en el que corre la pieza.\n"
                           "Déjalo en '(sin banco)' mientras esté suspendida.")
            self.rigs.append(rig)

            resultado = fields.clearable_combo(estados, "(sin resultado)")
            resultado.setMinimumWidth(150)
            resultado.setToolTip(
                "Cómo acabó la pieza: falló, no falló o se suspendió.")
            resultado.currentIndexChanged.connect(
                lambda _=0, s=slot: self._clear_rig_if_suspended(s))
            self.results.append(resultado)

            ciclos = fields.number_edit()
            self.cycles.append(ciclos)

            # Se deja en blanco cuando la pieza no fallo: el catalogo describe
            # como fallo, no si fallo -- eso ya lo dice el campo de arriba.
            modo = fields.clearable_combo(modos, "(sin modo)")
            modo.setMinimumWidth(150)
            modo.setToolTip("Se edita en Ajustes → Modos de falla. "
                            "Déjalo vacío si la pieza no falló.")
            self.failure_modes.append(modo)

            caja = SampleBox(slot + 1, [("Test Rig", rig),
                                        ("Resultado", resultado),
                                        ("Ciclos", ciclos),
                                        ("Modo de falla", modo)])
            self.sample_boxes.append(caja)
            rejilla.addWidget(caja, slot // 3, slot % 3)

        self._build_moved_rows()
        columna.addLayout(rejilla)
        self._update_sample_slots()
        return self.samples_group

    def _build_moved_rows(self) -> None:
        """La fecha en que una pieza detenida paso a otro banco.

        La pieza detenida **no se bloquea**: puede que se decida moverla en vez
        de esperar. Se avisa y quien captura elige; si la deja vacia, vuelve
        sola cuando el mantenimiento cierre.

        Si se mueve, se pregunta que dia: la captura suele ir por detras del
        cambio, y tomar el dia de guardar seguia contando como detenida la
        pieza que ya llevaba dias corriendo en el otro banco.
        """
        self.moved_dates: dict[int, object] = {}
        for numero, registro in self.paused.items():
            if not 1 <= numero <= SAMPLE_SLOTS:
                continue
            inicio = getattr(registro, "start_date", None)
            desde = f" desde el {dates.display(inicio)}" if inicio else ""
            self.rigs[numero - 1].setToolTip(
                f"El banco {registro.rig_name} está en mantenimiento{desde}.\n"
                f"La pieza salió de ahí y vuelve sola al terminar; si se mueve "
                f"a otro banco, ese dato manda.")

            fecha = fields.date_edit()
            fecha.setMaximumDate(QDate.currentDate())
            if inicio:
                fecha.setMinimumDate(QDate(inicio))
            fecha.setToolTip(
                "El día en que la pieza pasó al otro banco. Desde ese día deja "
                "de contar como detenida por el mantenimiento.")
            self.sample_boxes[numero - 1].add_row("Movida el", fecha)
            self.moved_dates[numero] = fecha
            self.rigs[numero - 1].currentIndexChanged.connect(
                self._update_moved_rows)

    # --- estado de las piezas -----------------------------------------------
    def declared_samples(self) -> int:
        try:
            return int(self.qty.currentText())
        except (TypeError, ValueError):
            return SAMPLE_SLOTS

    def _update_sample_slots(self) -> None:
        declaradas = self.declared_samples()

        extras = 0
        for slot, caja in enumerate(self.sample_boxes):
            sobra = slot >= declaradas
            con_datos = caja.has_data()
            extras += int(sobra and con_datos)
            # En consulta no se habilita nada: cargar el registro dispara las
            # senales de los campos, y sin esto una prueba finalizada acabaria
            # abriendose editable.
            caja.set_active(not self.read_only and (not sobra or con_datos))
            caja.mark_extra(sobra and con_datos)

        titulo = "Datos de las muestras"
        if extras:
            titulo += f"  ·  {extras} pieza(s) por encima de las declaradas"
        if self.paused:
            numeros = ", ".join(str(n) for n in sorted(self.paused))
            titulo += (f"  ·  pieza(s) {numeros} detenidas por mantenimiento "
                       f"del banco")
        self.samples_group.setTitle(titulo)

    def _clear_rig_if_suspended(self, slot: int) -> None:
        """Vacia el Test Rig de la pieza que se acaba de marcar 'Susp'.

        Solo hacia ese lado: elegir un banco no borra el resultado. Una pieza
        que vuelve al banco tras una suspension se captura poniendo el banco, y
        ahi el 'Susp' anterior lo quita quien captura.
        """
        if (fields.combo_value(self.results[slot]).casefold()
                != SUSPENDED_RESULT.casefold()):
            return
        rig = self.rigs[slot]
        if fields.combo_value(rig):
            fields.set_combo_value(rig, None)

    def _update_moved_rows(self, *_args) -> None:
        """'Movida el' solo se ve en la pieza detenida a la que se le puso banco."""
        for numero, fecha in self.moved_dates.items():
            self.sample_boxes[numero - 1].set_row_visible(
                fecha, bool(fields.combo_value(self.rigs[numero - 1])))

    def moved_on(self) -> dict:
        """El dia en que cada pieza detenida paso a otro banco, si se movio."""
        return {numero: fields.to_date(fecha)
                for numero, fecha in self.moved_dates.items()
                if fields.combo_value(self.rigs[numero - 1])}

    def _field_for(self, number, caption):
        """El campo donde se captura cada dato que pide 'Finalizar'.

        Si se agrega un campo a ``_completeness_fields``, hay que agregarlo
        tambien aqui. Si falta, el aviso lo dice como 'También falta: …' pero
        sin marcar su campo.
        """
        if number is None:
            return {"Test Batch": self.batch,
                    "Cliente": self.customer,
                    "Inicio de prueba": self.start_date,
                    "No. de piezas": self.qty,
                    "Tiene Work Order": self.wo}.get(caption)
        slot = number - 1
        return {"Test Rig": self.rigs[slot],
                "Resultado": self.results[slot],
                "Ciclos": self.cycles[slot],
                "Modo de falla": self.failure_modes[slot]}.get(caption)

    # --- carga --------------------------------------------------------------
    def _prefill_from_work_order(self, order) -> None:
        """Trae del documento lo que ya viene decidido.

        Se deja editable: si el Test Batch de la orden trae una errata, quien
        corre la prueba tiene que poder corregirla sin volver a Work Orders.
        """
        self.batch.setText(order.test_batch)
        fields.set_combo_value(self.customer, order.customer)
        fields.set_combo_value(self.qty, str(order.qty_samples))
        fields.set_combo_value(self.requester, order.requester)
        if order.comments:
            self.comments.setText(order.comments)
        self._update_sample_slots()

    def _load(self, test: FatigueTest) -> None:
        self.batch.setText(test.test_batch)
        fields.set_combo_value(self.customer, test.customer)
        fields.set_combo_value(self.requester, test.requester)
        if test.start_date:
            self.start_date.setDate(QDate(test.start_date))
        if test.end_date:
            self.end_date.setDate(QDate(test.end_date))
        fields.set_combo_value(self.qty, str(test.qty_samples))
        self.wo.setCurrentText("Si" if test.wo_status else "No")
        self.comments.setText("" if test.comments == "--" else test.comments)

        for indice, sample in enumerate(test.samples):
            # Las ranuras sin usar se guardaron como "--" y 0, no como nulos.
            # Mostrarlas vacias evita que el formulario abra con nueve ceros.
            vacia = (sample.rig in (None, "", EMPTY_RIG)
                     and not sample.result and not sample.cycles
                     and not sample.failure_mode)
            if vacia:
                fields.set_combo_value(self.rigs[indice], None)
                fields.set_combo_value(self.results[indice], None)
                self.cycles[indice].clear()
                fields.set_combo_value(self.failure_modes[indice], None)
                continue

            # El rig puede venir como "--" en una ranura que si se uso: basta
            # con que tenga resultado. Se ensenia vacio, o el combo acabaria
            # ofreciendo "--" como si fuera un banco mas.
            fields.set_combo_value(
                self.rigs[indice],
                None if sample.rig == EMPTY_RIG else sample.rig)
            fields.set_combo_value(self.results[indice], sample.result)
            self.cycles[indice].setText(
                "" if sample.cycles is None else str(sample.cycles))
            fields.set_combo_value(self.failure_modes[indice],
                                   sample.failure_mode)

    def _apply_read_only(self) -> None:
        self.batch.setReadOnly(True)
        self.comments.setReadOnly(True)
        for widget in (self.customer, self.qty, self.wo, self.requester,
                       *self.rigs, *self.results, *self.failure_modes):
            widget.setEnabled(False)
        for widget in (self.start_date, self.end_date):
            widget.setReadOnly(True)
        for widget in self.cycles:
            widget.setReadOnly(True)
        self.save_button.setVisible(False)
        self.finish_button.setVisible(False)
        self.cancel_button.setText("Cerrar")

    # --- guardado -----------------------------------------------------------
    def _collect(self) -> FatigueTest:
        muestras = []
        for rig, resultado, ciclos, modo in zip(
                self.rigs, self.results, self.cycles, self.failure_modes):
            texto = ciclos.text().strip()
            muestras.append(FatigueSample(
                rig=fields.combo_value(rig) or EMPTY_RIG,
                result=fields.combo_value(resultado),
                cycles=int(texto) if texto.isdigit() else None,
                failure_mode=fields.combo_value(modo)))

        test = FatigueTest(
            id=self.test.id if self.test else None,
            test_batch=validation.normalize_batch(self.batch.text()),
            customer=self.customer.currentText().strip(),
            requester=fields.combo_value(self.requester),
            start_date=fields.to_date(self.start_date),
            end_date=self.test.end_date if self.test else None,
            qty_samples=int(self.qty.currentText()),
            comments=self.comments.text().strip() or "--",
            wo_status=self.wo.currentText() == "Si",
            test_status=self.test.test_status if self.test else ONGOING,
            samples=muestras)
        if self.show_end:
            test.end_date = fields.to_date(self.end_date)
        return test

    def _batch_checks(self, test, editing: bool):
        return (self.batch, lambda: (
            validation.validate_test_batch(test.test_batch,
                                           self.catalogs.codes("fatigue")),
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
                # Contra la prueba tal como se abrio: lo que otro equipo
                # guardo mientras tanto se combina en vez de pisarse.
                if not update_merging(self, self.repository, test, autor,
                                      base=self.test,
                                      moved_on=self.moved_on()):
                    return
            else:
                self.created_id = self.repository.create(test, autor)
        except Exception as error:             # pragma: no cover - depende de red
            QMessageBox.critical(self, "Error al guardar", str(error))
            return
        self.accept()

    # --- cerrar y reabrir ---------------------------------------------------
    def _completeness_fields(self, test: FatigueTest):
        """Que se exige para cerrar: los generales y las piezas declaradas.

        Solo hasta la cantidad declarada. Si se probaron 6 piezas, de la 7 a la
        9 se cierran vacias.
        """
        general = {"Test Batch": test.test_batch,
                   "Cliente": test.customer,
                   "Inicio de prueba": test.start_date,
                   "No. de piezas": test.qty_samples,
                   "Tiene Work Order": self.wo.currentText()}

        muestras = []
        for numero in range(1, min(test.qty_samples, SAMPLE_SLOTS) + 1):
            sample = test.samples[numero - 1]
            campos = {"Test Rig": "" if sample.rig == EMPTY_RIG else sample.rig,
                      "Resultado": sample.result,
                      "Ciclos": sample.cycles}
            # El modo de falla solo se le pide a la pieza que fallo: en una
            # 'S/Falla' no hay nada que describir. El criterio sale de
            # validation y no se reescribe.
            if validation.requires_failure_mode(sample.result):
                campos["Modo de falla"] = sample.failure_mode
            muestras.append((numero, campos))
        return general, muestras

    def _finish(self) -> None:
        if not self.test or self.test.id is None:
            return

        test = self._collect()
        # Se valida contra lo que hay en pantalla, no contra lo guardado: el
        # usuario suele llenar los ultimos campos y pulsar 'Finalizar' sin
        # guardar antes.
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
            # Primero se guarda lo capturado y luego se cierra. Antes 'close'
            # solo tocaba el estatus y la fecha, asi que lo que el usuario
            # acababa de escribir se perdia al finalizar.
            if not update_merging(self, self.repository, test, autor,
                                  base=self.test, moved_on=self.moved_on()):
                return
            self.repository.close(self.test.id, fin, autor)
        except Exception as error:             # pragma: no cover
            QMessageBox.critical(self, "Error", str(error))
            return

        # Sin aviso de 'listo': el dialogo se cierra y el registro cambia de
        # pestania a la vista. Un cuadro modal justo antes de accept() solo
        # anadia un clic para enterarse de lo que ya se ve.
        self.accept()

    def _reopen(self) -> None:
        if not self.test or self.test.id is None:
            return
        confirmar = QMessageBox.question(
            self, "Confirmación",
            f"¿Deseas quitar el Test Batch {self.test.test_batch} de la "
            f"sección de pruebas finalizadas?")
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
