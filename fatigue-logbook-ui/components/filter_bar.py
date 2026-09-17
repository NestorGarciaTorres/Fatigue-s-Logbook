"""Barra de filtros y resumen de lo que esta filtrando.

Los criterios son los de ``app.services.filtering.TestFilters``, del proyecto
original: esta barra los recoge, no los define. Asi la bitacora, el dashboard y
el reporte filtran exactamente igual.

El resumen de filtros activos no es adorno. Con la barra plegada o con la
pantalla a medio desplazar, "no aparece el registro que busco" y "hay un filtro
puesto que no recuerdo" se ven igual; cada criterio activo sale como una
pastilla que se puede quitar de una en una.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.filtering import ANY, TestFilters
from components import buttons, fields, labels


class FilterBar(QWidget):
    """Busqueda, cliente, banco, Work Order y rango de fechas."""

    changed = Signal()

    def __init__(self, show_status: bool = False, show_wo: bool = False,
                 parent=None):
        super().__init__(parent)
        self.show_status = show_status
        self.show_wo = show_wo

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(8)

        # Dos filas y no una. Con todo seguido, la barra pedia 1,346 px de
        # minimo ella sola y la ventana entera se iba a 1,608: mas ancha que el
        # escritorio de un portatil de 1366. Es el mismo arreglo que el
        # proyecto anterior ya habia tenido que hacer dos veces -- partir la
        # fila, no acortar los rotulos a la fuerza.
        arriba = QHBoxLayout()
        arriba.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Buscar batch, cliente, solicitante, banco o comentario…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.changed)
        self.search.setMinimumWidth(200)
        arriba.addWidget(self.search, 1)

        self.result_label = labels.muted("")
        arriba.addWidget(self.result_label)

        self.clear_button = buttons.button("Limpiar", buttons.GHOST,
                                           on_click=self.clear)
        arriba.addWidget(self.clear_button)
        raiz.addLayout(arriba)

        abajo = QHBoxLayout()
        abajo.setSpacing(10)

        self.customer = self._combo("Cliente", abajo)
        self.rig = self._combo("Banco", abajo)
        if show_status:
            self.status = self._combo("Estatus", abajo)
            self.status.addItems(["En curso", "Finalizada"])
        else:
            self.status = None
        if show_wo:
            self.wo = self._combo("WO", abajo)
            self.wo.addItems(["Si", "No"])
        else:
            self.wo = None

        self.use_dates = QCheckBox("Fechas")
        self.use_dates.toggled.connect(self._on_dates_toggled)
        abajo.addWidget(self.use_dates)

        self.date_from = fields.date_edit(date(date.today().year, 1, 1))
        self.date_to = fields.date_edit()
        for campo in (self.date_from, self.date_to):
            # Ocultos mientras no se filtre por fechas. Deshabilitados pero
            # visibles seguian costando 248 px de minimo, y ademas dos campos
            # apagados que no se pueden usar son ruido.
            campo.setVisible(False)
            campo.dateChanged.connect(self._on_date_changed)
            abajo.addWidget(campo)

        abajo.addStretch(1)
        raiz.addLayout(abajo)

    # --- construccion -----------------------------------------------------
    def _combo(self, caption: str, row: QHBoxLayout) -> QComboBox:
        row.addWidget(labels.muted(caption))
        combo = fields.SearchableComboBox(centered=False)
        combo.addItem(ANY)
        # Mide por caracteres y no por su elemento mas largo: el de clientes
        # pedia 292 px por 'MERCEDES-BENZ'.
        combo.setMinimumContentsLength(10)
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        # La conexion se hace una sola vez, aqui. Hacerla al rellenar el combo
        # la acumularia en cada refresco, y el filtro se aplicaria tantas veces
        # como veces se hubiera recargado el catalogo.
        combo.currentIndexChanged.connect(self.changed)
        row.addWidget(combo)
        return combo

    # --- catalogos --------------------------------------------------------
    def set_customers(self, names: list[str]) -> None:
        self._refill(self.customer, names)

    def set_rigs(self, names: list[str]) -> None:
        self._refill(self.rig, names)

    @staticmethod
    def _refill(combo: QComboBox, values: list[str]) -> None:
        """Rellena conservando lo elegido: refrescar no debe quitar el filtro."""
        actual = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(ANY)
        combo.addItems(values)
        indice = combo.findText(actual)
        combo.setCurrentIndex(indice if indice >= 0 else 0)
        combo.blockSignals(False)

    # --- lectura ----------------------------------------------------------
    def filters(self) -> TestFilters:
        return TestFilters(
            search=self.search.text(),
            customer=self.customer.currentText(),
            rig=self.rig.currentText(),
            test_status=self.status.currentText() if self.status else ANY,
            wo_status=self.wo.currentText() if self.wo else ANY,
            date_from=(fields.to_date(self.date_from)
                       if self.use_dates.isChecked() else None),
            date_to=(fields.to_date(self.date_to)
                     if self.use_dates.isChecked() else None),
        )

    def set_result_count(self, visible: int, total: int) -> None:
        if visible == total:
            self.result_label.setText(f"{total:,} registros")
        else:
            self.result_label.setText(
                f"{visible:,} de {total:,} registros con los filtros puestos")

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    # --- limpieza ---------------------------------------------------------
    def clear_field(self, field: str) -> None:
        """Quita un criterio suelto, desde su pastilla."""
        objetivos = {
            "search": lambda: self.search.clear(),
            "customer": lambda: self.customer.setCurrentIndex(0),
            "rig": lambda: self.rig.setCurrentIndex(0),
            "test_status": lambda: (self.status
                                    and self.status.setCurrentIndex(0)),
            "wo_status": lambda: self.wo and self.wo.setCurrentIndex(0),
            "dates": lambda: self.use_dates.setChecked(False),
        }
        accion = objetivos.get(field)
        if accion:
            accion()
            self.changed.emit()

    def clear(self) -> None:
        for widget in (self.customer, self.rig, self.status, self.wo):
            if widget is not None:
                widget.blockSignals(True)
                widget.setCurrentIndex(0)
                widget.blockSignals(False)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.use_dates.blockSignals(True)
        self.use_dates.setChecked(False)
        self.use_dates.blockSignals(False)
        self._set_dates_enabled(False)
        self.changed.emit()

    # --- fechas -----------------------------------------------------------
    def _on_dates_toggled(self, enabled: bool) -> None:
        self._set_dates_enabled(enabled)
        self.changed.emit()

    def _set_dates_enabled(self, enabled: bool) -> None:
        # Se muestran y se ocultan, no solo se habilitan: asi no cuestan ancho
        # minimo mientras no se usen.
        self.date_from.setVisible(enabled)
        self.date_to.setVisible(enabled)

    def _on_date_changed(self) -> None:
        if self.use_dates.isChecked():
            self.changed.emit()


class ActiveFilters(QWidget):
    """Los criterios puestos, cada uno con su boton de quitar."""

    removed = Signal(str)

    CAPTIONS = {
        "search": "Búsqueda",
        "customer": "Cliente",
        "rig": "Banco",
        "test_status": "Estatus",
        "wo_status": "Work Order",
        "dates": "Fechas",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(6)
        self.row.addWidget(labels.muted("Filtrando por"))
        self.row.addStretch(1)
        self._chips: list[QWidget] = []

    def update_from(self, criterios: TestFilters) -> None:
        for chip in self._chips:
            chip.setParent(None)
        self._chips = []

        activos: list[tuple[str, str]] = []
        if criterios.search.strip():
            activos.append(("search", criterios.search.strip()))
        if criterios.customer != ANY:
            activos.append(("customer", criterios.customer))
        if criterios.rig != ANY:
            activos.append(("rig", criterios.rig))
        if criterios.test_status != ANY:
            activos.append(("test_status", criterios.test_status))
        if criterios.wo_status != ANY:
            activos.append(("wo_status", criterios.wo_status))
        if criterios.date_from or criterios.date_to:
            desde = criterios.date_from.strftime("%d/%m/%Y") if criterios.date_from else "…"
            hasta = criterios.date_to.strftime("%d/%m/%Y") if criterios.date_to else "…"
            activos.append(("dates", f"{desde} a {hasta}"))

        for campo, valor in activos:
            chip = buttons.button(
                f"{self.CAPTIONS.get(campo, campo)}: {valor}  ✕",
                buttons.GHOST,
                tooltip="Quitar este filtro",
                on_click=lambda c=campo: self.removed.emit(c),
            )
            self.row.insertWidget(self.row.count() - 1, chip)
            self._chips.append(chip)

        self.setVisible(bool(activos))
