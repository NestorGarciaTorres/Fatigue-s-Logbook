"""Barra de filtros y busqueda.

La version anterior solo tenia dos combos, mes y anio, y filtraba en SQL con
``substr(end_date, 4, 2)``. Aqui se suman cliente, rig, estatus, Work Order,
rango de fechas y busqueda libre.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.filtering import ANY, TestFilters

DATE_FORMAT = "dd/MM/yyyy"


def make_date_edit(initial: date | None = None) -> QDateEdit:
    """QDateEdit con el formato que usa toda la app."""
    widget = QDateEdit()
    widget.setCalendarPopup(True)
    widget.setDisplayFormat(DATE_FORMAT)
    widget.setDate(QDate(initial) if initial else QDate.currentDate())
    # El QDateEdit escribe sobre un QLineEdit propio: la alineacion va ahi.
    if widget.lineEdit() is not None:
        widget.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget


def to_date(widget: QDateEdit) -> date:
    return widget.date().toPython()


class FilterBar(QWidget):
    """Emite ``changed`` cada vez que el usuario ajusta un criterio."""

    changed = Signal()

    def __init__(
        self,
        show_status: bool = True,
        show_wo: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.show_status = show_status
        self.show_wo = show_wo

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar test batch, cliente, rig...")
        self.search.setClearButtonEnabled(True)
        # 160 y no 260: el buscador crece con la ventana --lleva el peso 2 de
        # la fila-- pero su minimo es lo que le pone suelo a la pantalla
        # entera, y una bitacora no puede exigir mas ancho del que tiene el
        # escritorio de un portatil.
        self.search.setMinimumWidth(160)
        row.addWidget(self.search, 2)

        self.customer = self._combo("Cliente", row)
        self.rig = self._combo("Rig", row)

        self.status = None
        if show_status:
            self.status = self._combo("Estatus", row)
            self.status.addItems(["En curso", "Finalizadas"])

        self.wo = None
        if show_wo:
            self.wo = self._combo("WO", row)
            self.wo.addItems(["Si", "No"])

        row.addStretch(1)
        # El conteo se pone al final de la primera fila y no de la segunda: la
        # de fechas es la que iba justa de ancho.
        self.results = QLabel("")
        self.results.setProperty("muted", "true")
        row.addWidget(self.results, 0, Qt.AlignmentFlag.AlignRight)

        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(8)

        # Rotulos cortos en esta fila: escritos enteros ("Rango de fechas",
        # "Limpiar filtros") pedian 265 y 280 px, y la fila entera le ponia a
        # la bitacora un minimo de 1,326 px de ancho. Lo que significan va en
        # el tooltip, que no cuesta ancho.
        self.use_dates = QCheckBox("Fechas")
        self.use_dates.setToolTip("Filtrar por un rango de fechas")
        row2.addWidget(self.use_dates)

        self.date_from = make_date_edit(date(date.today().year, 1, 1))
        self.date_to = make_date_edit()
        for widget in (self.date_from, self.date_to):
            widget.setEnabled(False)

        row2.addWidget(QLabel("De:"))
        row2.addWidget(self.date_from)
        row2.addWidget(QLabel("A:"))
        row2.addWidget(self.date_to)

        self.clear_button = QPushButton("Limpiar")
        self.clear_button.setProperty("accent", "secondary")
        self.clear_button.setToolTip("Quita todos los filtros")
        row2.addWidget(self.clear_button)

        row2.addStretch(1)
        layout.addLayout(row2)

        # --- conexiones --------------------------------------------------
        self.search.textChanged.connect(self.changed)
        self.customer.currentTextChanged.connect(self.changed)
        self.rig.currentTextChanged.connect(self.changed)
        if self.status:
            self.status.currentTextChanged.connect(self.changed)
        if self.wo:
            self.wo.currentTextChanged.connect(self.changed)

        self.use_dates.toggled.connect(self._on_dates_toggled)
        self.date_from.dateChanged.connect(self._on_date_changed)
        self.date_to.dateChanged.connect(self._on_date_changed)
        self.clear_button.clicked.connect(self.clear)

    # --- construccion ----------------------------------------------------
    @staticmethod
    def _combo(label: str, row: QHBoxLayout) -> QComboBox:
        row.addWidget(QLabel(f"{label}:"))
        combo = QComboBox()
        # Un QComboBox mide por su elemento mas largo, asi que el de clientes
        # pedia 292 px por 'MERCEDES-BENZ' y los cuatro juntos le ponian a la
        # bitacora un minimo de 1,326 px. Con esto mide por un numero de
        # caracteres y crece si hay sitio; el nombre completo sigue entero al
        # desplegar la lista.
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(10)
        combo.addItem(ANY)
        combo.setMinimumWidth(110)
        # Peso 1: los combos se reparten el ancho que sobre en vez de
        # quedarse en su minimo mientras el buscador se lo lleva todo.
        row.addWidget(combo, 1)
        return combo

    # --- poblado ---------------------------------------------------------
    def set_customers(self, names: list[str]) -> None:
        self._refill(self.customer, names)

    def set_rigs(self, names: list[str]) -> None:
        self._refill(self.rig, names)

    @staticmethod
    def _refill(combo: QComboBox, values: list[str]) -> None:
        """Repuebla conservando la seleccion si sigue existiendo."""
        previous = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(ANY)
        combo.addItems(values)
        index = combo.findText(previous)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    # --- estado ----------------------------------------------------------
    def filters(self) -> TestFilters:
        status = ANY
        if self.status and self.status.currentText() != ANY:
            status = (
                "Ongoing"
                if self.status.currentText() == "En curso"
                else "Finished"
            )

        return TestFilters(
            search=self.search.text(),
            customer=self.customer.currentText(),
            rig=self.rig.currentText(),
            test_status=status,
            wo_status=self.wo.currentText() if self.wo else ANY,
            date_from=to_date(self.date_from) if self.use_dates.isChecked() else None,
            date_to=to_date(self.date_to) if self.use_dates.isChecked() else None,
        )

    def set_result_count(self, visible: int, total: int) -> None:
        if visible == total:
            self.results.setText(f"{total} registro(s)")
        else:
            self.results.setText(f"{visible} de {total} registro(s)")

    def focus_search(self) -> None:
        """Pone el cursor en el buscador. Es lo que hace Ctrl+F."""
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    def clear_field(self, field: str) -> None:
        """Quita un solo filtro, desde su chip en la franja de activos."""
        combos = {
            "customer": self.customer,
            "rig": self.rig,
            "test_status": self.status,
            "wo_status": self.wo,
        }

        if field == "search":
            self.search.clear()          # ya emite changed
            return

        if field == "dates":
            self.use_dates.setChecked(False)
            return

        combo = combos.get(field)
        if combo is not None:
            combo.setCurrentIndex(0)     # ya emite changed

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

    # --- internos --------------------------------------------------------
    def _on_dates_toggled(self, enabled: bool) -> None:
        self._set_dates_enabled(enabled)
        self.changed.emit()

    def _set_dates_enabled(self, enabled: bool) -> None:
        self.date_from.setEnabled(enabled)
        self.date_to.setEnabled(enabled)

    def _on_date_changed(self) -> None:
        if self.use_dates.isChecked():
            self.changed.emit()
