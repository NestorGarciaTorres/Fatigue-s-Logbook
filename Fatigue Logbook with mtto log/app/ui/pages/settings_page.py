"""Ajustes: catalogos, colores de rig, base de datos y respaldos.

Es la pantalla que sustituye a ``excel_files/Auxiliar.xlsx``: lo que antes se
editaba abriendo el Excel ahora se edita aqui.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.context import AppContext
from app.models import TEST_TYPES, Customer, FailureMode, Requester, Rig
from app.services import backup
from app.services.catalogs import contrasting_text_color
from app.services.identity import author_label
from app.ui.dialogs.history_dialog import HistoryDialog
from app.ui.pages.base_page import BasePage

# Cuantos caracteres de la ruta se ensenian antes de acortarla por el centro.
PATH_CHARS = 58

TYPE_LABELS = {key: config.label for key, config in TEST_TYPES.items()}


class RigsTab(QWidget):
    """Catalogo de rigs con su color. El color es lo que pinta las tablas."""

    HEADERS = ["Nombre", "Tipo", "Color", "Activo"]

    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)

        info = QLabel(
            "Doble clic en la columna Color para cambiarlo. El color se aplica "
            "en las bitácoras, el dashboard y el reporte de Excel. Solo los "
            "bancos llevan color: los resultados de pieza (Falla, S/Falla, "
            "Susp) se distinguen por la forma del chip."
        )
        info.setProperty("muted", "true")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        add = QPushButton("Agregar rig")
        add.clicked.connect(self.add_rig)
        buttons.addWidget(add)

        toggle = QPushButton("Activar / desactivar")
        toggle.setProperty("accent", "warning")
        toggle.clicked.connect(self.toggle_active)
        buttons.addWidget(toggle)

        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._rigs: list[Rig] = []

    def refresh(self) -> None:
        self._rigs = self.context.catalog_repository.rigs(active_only=False)
        self.table.setRowCount(len(self._rigs))

        for row, rig in enumerate(self._rigs):
            self.table.setItem(row, 0, self._item(rig.name))
            self.table.setItem(row, 1, self._item(TYPE_LABELS.get(rig.test_type, rig.test_type)))

            color_item = self._item(rig.color)
            color_item.setBackground(QColor(rig.color))
            color_item.setForeground(QColor(contrasting_text_color(rig.color)))
            self.table.setItem(row, 2, color_item)

            self.table.setItem(row, 3, self._item("Si" if rig.active else "No"))

    @staticmethod
    def _item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def _on_double_click(self, row: int, column: int) -> None:
        if column != 2:
            return
        self.pick_color(row)

    def pick_color(self, row: int) -> None:
        rig = self._rigs[row]
        chosen = QColorDialog.getColor(
            QColor(rig.color), self, f"Color para {rig.name}"
        )
        if not chosen.isValid():
            return

        color = chosen.name().upper()

        # Ya no hay tonos reservados que evitar: los resultados de pieza no
        # llevan color, asi que cualquier tono es valido para un banco.
        self.context.catalogs.set_color(rig, color)
        self.refresh()

    def add_rig(self) -> None:
        name, ok = QInputDialog.getText(self, "Nuevo rig", "Nombre del rig:")
        if not ok or not name.strip():
            return

        labels = list(TYPE_LABELS.values())
        label, ok = QInputDialog.getItem(
            self, "Nuevo rig", "Tipo de prueba:", labels, 0, False
        )
        if not ok:
            return

        key = next(k for k, v in TYPE_LABELS.items() if v == label)
        index = len(self.context.catalog_repository.rigs(active_only=False))

        from app.services.catalogs import color_for_index

        try:
            self.context.catalogs.save_rig(
                Rig(name=name.strip(), test_type=key, color=color_for_index(index))
            )
        except Exception as error:
            QMessageBox.warning(self, "No se pudo agregar", str(error))
            return

        self.refresh()

    def toggle_active(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return

        rig = self._rigs[row]
        rig.active = not rig.active
        self.context.catalogs.save_rig(rig)
        self.refresh()


class CustomersTab(QWidget):
    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Cliente", "Activo"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        add = QPushButton("Agregar cliente")
        add.clicked.connect(self.add_customer)
        buttons.addWidget(add)

        toggle = QPushButton("Activar / desactivar")
        toggle.setProperty("accent", "warning")
        toggle.clicked.connect(self.toggle_active)
        buttons.addWidget(toggle)

        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._customers: list[Customer] = []

    def refresh(self) -> None:
        self._customers = self.context.catalog_repository.customers(
            active_only=False
        )
        self.table.setRowCount(len(self._customers))
        for row, customer in enumerate(self._customers):
            name = QTableWidgetItem(customer.name)
            name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, name)

            active = QTableWidgetItem("Si" if customer.active else "No")
            active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, active)

    def add_customer(self) -> None:
        name, ok = QInputDialog.getText(self, "Nuevo cliente", "Nombre:")
        if not ok or not name.strip():
            return
        try:
            self.context.catalogs.save_customer(Customer(name=name.strip().upper()))
        except Exception as error:
            QMessageBox.warning(self, "No se pudo agregar", str(error))
            return
        self.refresh()

    def toggle_active(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        customer = self._customers[row]
        customer.active = not customer.active
        self.context.catalogs.save_customer(customer)
        self.refresh()


class CodesTab(QWidget):
    """Claves de tres letras que validan el Test Batch."""

    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)

        info = QLabel(
            "El Test Batch debe seguir el formato 6 dígitos + clave + 2 dígitos "
            "(ejemplo: 242314STF09). Solo se aceptan las claves de esta lista."
        )
        info.setProperty("muted", "true")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Clave", "Tipo de prueba"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.code_input = QLineEdit()
        self.code_input.setMaxLength(3)
        self.code_input.setPlaceholderText("STF")

        self.type_combo = QComboBox()
        for key, label in TYPE_LABELS.items():
            self.type_combo.addItem(label, key)

        add = QPushButton("Agregar clave")
        add.clicked.connect(self.add_code)

        remove = QPushButton("Eliminar seleccionada")
        remove.setProperty("accent", "danger")
        remove.clicked.connect(self.remove_code)

        row.addWidget(self.code_input)
        row.addWidget(self.type_combo)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)

        self._codes = []

    def refresh(self) -> None:
        self._codes = self.context.catalog_repository.all_codes()
        self.table.setRowCount(len(self._codes))
        for row, code in enumerate(self._codes):
            code_item = QTableWidgetItem(code.code)
            code_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, code_item)

            type_item = QTableWidgetItem(
                TYPE_LABELS.get(code.test_type, code.test_type)
            )
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, type_item)

    def add_code(self) -> None:
        code = self.code_input.text().strip().upper()
        if len(code) != 3 or not code.isalpha():
            QMessageBox.warning(
                self, "Clave inválida", "La clave debe ser de tres letras."
            )
            return

        self.context.catalogs.add_code(code, self.type_combo.currentData())
        self.code_input.clear()
        self.refresh()

    def remove_code(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return

        code = self._codes[row]
        confirm = QMessageBox.question(
            self, "Confirmación", f"¿Eliminar la clave {code.code}?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.context.catalogs.remove_code(code.id)
        self.refresh()


class FailureModesTab(QWidget):
    """Diccionario de modos de falla que alimenta el desplegable de cada pieza."""

    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)

        info = QLabel(
            "Cada pieza de Fatiga y Rotary se captura con su modo de falla, "
            "elegido de esta lista. Describe COMO fallo la pieza; para decir "
            "SI fallo estan los estatus Falla / S-Falla / Susp. Si la pieza no "
            "fallo, el campo se deja vacío.\n"
            "Los modos que trae la app al instalarse son genericos: "
            "reemplazalos por la nomenclatura del laboratorio."
        )
        info.setProperty("muted", "true")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Modo de falla", "Activo", "En uso"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.cellDoubleClicked.connect(lambda row, _: self.rename(row))
        layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Fractura por fatiga")
        self.input.returnPressed.connect(self.add_mode)

        add = QPushButton("Agregar modo")
        add.clicked.connect(self.add_mode)

        rename = QPushButton("Renombrar")
        rename.clicked.connect(lambda: self.rename(self.table.currentRow()))

        toggle = QPushButton("Activar / desactivar")
        toggle.setProperty("accent", "warning")
        toggle.clicked.connect(self.toggle_active)

        remove = QPushButton("Eliminar")
        remove.setProperty("accent", "danger")
        remove.clicked.connect(self.remove_mode)

        row.addWidget(self.input)
        for button in (add, rename, toggle, remove):
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

        self._modes: list[FailureMode] = []

    def refresh(self) -> None:
        self._modes = self.context.catalog_repository.failure_modes(
            active_only=False
        )
        self.table.setRowCount(len(self._modes))
        for row, mode in enumerate(self._modes):
            usage = self.context.catalog_repository.failure_mode_usage(mode.label)
            self.table.setItem(row, 0, self._item(mode.label))
            self.table.setItem(row, 1, self._item("Si" if mode.active else "No"))
            self.table.setItem(row, 2, self._item(f"{usage:,}"))

    @staticmethod
    def _item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def _selected(self, row: int) -> FailureMode | None:
        if 0 <= row < len(self._modes):
            return self._modes[row]
        return None

    def add_mode(self) -> None:
        label = self.input.text().strip()
        if not label:
            return
        try:
            self.context.catalogs.save_failure_mode(FailureMode(label=label))
        except Exception as error:
            QMessageBox.warning(self, "No se pudo agregar", str(error))
            return
        self.input.clear()
        self.refresh()

    def rename(self, row: int) -> None:
        """Renombra el modo sin tocar los registros que ya lo usan.

        Se avisa cuando hay muestras capturadas con el nombre viejo: esas
        conservan el texto anterior, porque el modo se guarda como texto en la
        muestra y no como una referencia al catalogo.
        """
        mode = self._selected(row)
        if mode is None:
            return

        label, ok = QInputDialog.getText(
            self, "Renombrar modo", "Nuevo nombre:", text=mode.label
        )
        label = label.strip()
        if not ok or not label or label == mode.label:
            return

        usage = self.context.catalog_repository.failure_mode_usage(mode.label)
        if usage:
            answer = QMessageBox.question(
                self,
                "El modo está en uso",
                f"{usage:,} muestras quedaron capturadas como '{mode.label}'.\n"
                f"Renombrarlo aquí cambia solo la lista: esas muestras seguirán "
                f"mostrando el nombre anterior.\n\n¿Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        mode.label = label
        try:
            self.context.catalogs.save_failure_mode(mode)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo renombrar", str(error))
            return
        self.refresh()

    def toggle_active(self) -> None:
        mode = self._selected(self.table.currentRow())
        if mode is None:
            return
        mode.active = not mode.active
        self.context.catalogs.save_failure_mode(mode)
        self.refresh()

    def remove_mode(self) -> None:
        """Eliminar solo cuando nadie lo usa; si esta en uso, se desactiva."""
        mode = self._selected(self.table.currentRow())
        if mode is None:
            return

        usage = self.context.catalog_repository.failure_mode_usage(mode.label)
        if usage:
            QMessageBox.information(
                self,
                "El modo está en uso",
                f"'{mode.label}' está capturado en {usage:,} muestras, así que "
                f"no se elimina: dejaría esos registros con un valor sin "
                f"explicacion en la lista.\n\nUsa 'Activar / desactivar' para "
                f"retirarlo del desplegable sin perder lo ya capturado.",
            )
            return

        confirm = QMessageBox.question(
            self, "Confirmación", f"¿Eliminar el modo '{mode.label}'?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.context.catalogs.remove_failure_mode(mode.id)
        self.refresh()


class RequestersTab(QWidget):
    """Personas que pueden solicitar una prueba en una Work Order."""

    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)

        info = QLabel(
            "Quien solicita una prueba se elige de esta lista al capturar una "
            "Work Order. La app no trae ninguno de fabrica: son personas del "
            "laboratorio y hay que darlas de alta aquí."
        )
        info.setProperty("muted", "true")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            ["Solicitante", "Activo", "Work Orders"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.cellDoubleClicked.connect(lambda row, _: self.rename(row))
        layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Nombre y apellido")
        self.input.returnPressed.connect(self.add_requester)

        add = QPushButton("Agregar solicitante")
        add.clicked.connect(self.add_requester)

        rename = QPushButton("Renombrar")
        rename.clicked.connect(lambda: self.rename(self.table.currentRow()))

        toggle = QPushButton("Activar / desactivar")
        toggle.setProperty("accent", "warning")
        toggle.clicked.connect(self.toggle_active)

        remove = QPushButton("Eliminar")
        remove.setProperty("accent", "danger")
        remove.clicked.connect(self.remove_requester)

        row.addWidget(self.input)
        for button in (add, rename, toggle, remove):
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

        self._requesters = []

    def refresh(self) -> None:
        self._requesters = self.context.catalog_repository.requesters(
            active_only=False
        )
        self.table.setRowCount(len(self._requesters))
        for row, person in enumerate(self._requesters):
            usage = self.context.work_orders.requester_usage(person.name)
            self.table.setItem(row, 0, self._item(person.name))
            self.table.setItem(row, 1, self._item("Si" if person.active else "No"))
            self.table.setItem(row, 2, self._item(f"{usage:,}"))

    @staticmethod
    def _item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def _selected(self, row: int):
        if 0 <= row < len(self._requesters):
            return self._requesters[row]
        return None

    def add_requester(self) -> None:
        name = self.input.text().strip()
        if not name:
            return
        try:
            self.context.catalogs.save_requester(Requester(name=name))
        except Exception as error:
            QMessageBox.warning(self, "No se pudo agregar", str(error))
            return
        self.input.clear()
        self.refresh()

    def rename(self, row: int) -> None:
        """Renombra sin tocar las Work Orders ya capturadas.

        El solicitante se guarda como texto en cada orden, igual que el modo de
        falla: las ordenes existentes conservan el nombre anterior.
        """
        person = self._selected(row)
        if person is None:
            return

        name, ok = QInputDialog.getText(
            self, "Renombrar solicitante", "Nuevo nombre:", text=person.name
        )
        name = name.strip()
        if not ok or not name or name == person.name:
            return

        usage = self.context.work_orders.requester_usage(person.name)
        if usage:
            answer = QMessageBox.question(
                self,
                "El solicitante tiene órdenes",
                f"{usage:,} Work Orders quedaron capturadas a nombre de "
                f"'{person.name}'.\nRenombrarlo aquí cambia solo la lista: "
                f"esas órdenes seguirán mostrando el nombre anterior."
                f"\n\n¿Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        person.name = name
        try:
            self.context.catalogs.save_requester(person)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo renombrar", str(error))
            return
        self.refresh()

    def toggle_active(self) -> None:
        person = self._selected(self.table.currentRow())
        if person is None:
            return
        person.active = not person.active
        self.context.catalogs.save_requester(person)
        self.refresh()

    def remove_requester(self) -> None:
        """Solo se elimina a quien no tiene ninguna orden; si no, se desactiva."""
        person = self._selected(self.table.currentRow())
        if person is None:
            return

        usage = self.context.work_orders.requester_usage(person.name)
        if usage:
            QMessageBox.information(
                self,
                "El solicitante tiene órdenes",
                f"'{person.name}' aparece en {usage:,} Work Orders, así que no "
                f"se elimina.\n\nUsa 'Activar / desactivar' para retirarlo de "
                f"la lista sin perder ese rastro.",
            )
            return

        confirm = QMessageBox.question(
            self, "Confirmación", f"¿Eliminar a '{person.name}'?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.context.catalogs.remove_requester(person.id)
        self.refresh()


class DatabaseTab(QWidget):
    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)

        group = QGroupBox("Base de datos")
        form = QFormLayout(group)

        # La ruta se acorta por el centro y va entera en el tooltip. Con
        # wordWrap y una ruta larga --que no tiene espacios por donde partir--
        # la etiqueta pedia 1,136 px y era ella sola quien decidia el ancho
        # minimo de la pantalla de Ajustes.
        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        form.addRow("Ruta actual", self.path_label)
        self._show_path(context.config.database)

        self.status_label = QLabel("")
        form.addRow("Estado", self.status_label)

        # Lo que uno viene a comprobar a esta pantalla: si la base es la
        # que cree y si el respaldo esta al dia.
        self.size_label = QLabel("")
        form.addRow("Tamaño", self.size_label)

        self.backup_label = QLabel("")
        form.addRow("Último respaldo", self.backup_label)

        form.addRow("Usuario", QLabel(author_label()))
        layout.addWidget(group)

        buttons = QHBoxLayout()

        # Rotulos cortos y el detalle en el tooltip: los cuatro escritos
        # enteros dejaban esta pantalla a 4 px del ancho de un portatil.
        change = QPushButton("Cambiar base")
        change.setToolTip("Apuntar la app a otro archivo de base de datos")
        change.clicked.connect(self.change_database)
        buttons.addWidget(change)

        test = QPushButton("Probar conexión")
        # El lambda evita que el 'checked' de clicked() llegue como 'quiet'.
        test.clicked.connect(lambda: self.test_connection(quiet=False))
        buttons.addWidget(test)

        backup_button = QPushButton("Respaldar ahora")
        backup_button.setProperty("accent", "success")
        backup_button.clicked.connect(self.make_backup)
        buttons.addWidget(backup_button)

        history = QPushButton("Historial")
        history.setToolTip("Historial de cambios de toda la base")
        history.setProperty("accent", "secondary")
        history.clicked.connect(self.show_history)
        buttons.addWidget(history)

        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def _show_path(self, ruta) -> None:
        """La ruta acortada por el centro; entera en el tooltip.

        Se corta por el centro y no por el final porque lo que identifica una
        base es el principio (el servidor o la unidad) y el final (el archivo);
        lo de en medio es lo prescindible.
        """
        texto = str(ruta)
        if len(texto) > PATH_CHARS:
            mitad = (PATH_CHARS - 3) // 2
            texto = f"{texto[:mitad]}...{texto[-mitad:]}"
        self.path_label.setText(texto)
        self.path_label.setToolTip(str(ruta))

    def refresh(self) -> None:
        self._show_path(self.context.config.database)
        self.test_connection(quiet=True)
        self._describe_file()
        self._describe_backup()

    def _describe_file(self) -> None:
        base = Path(self.context.config.database)
        if not base.is_file():
            self.size_label.setText("El archivo no existe todavía")
            return
        megas = base.stat().st_size / (1024 * 1024)
        self.size_label.setText(f"{megas:,.1f} MB")

    def _describe_backup(self) -> None:
        """Cuando se respaldo por ultima vez, y hace cuanto de eso."""
        ultimo = backup.latest_backup(Path(self.context.config.backups))
        if ultimo is None:
            self.backup_label.setText("Todavía no hay respaldos")
            return
        cuando = datetime.fromtimestamp(ultimo.stat().st_mtime)
        dias = (datetime.now() - cuando).days
        antiguedad = ("hoy" if dias == 0 else
                      "ayer" if dias == 1 else f"hace {dias} días")
        self.backup_label.setText(
            f"{cuando:%d/%m/%Y %H:%M}  ({antiguedad})  ·  {ultimo.name}"
        )

    def change_database(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecciona la base de datos",
            str(self.context.config.database.parent),
            "SQLite (*.db)",
        )
        if not path:
            return

        try:
            self.context.reload_database(path)
        except Exception as error:
            QMessageBox.critical(self, "Error", str(error))
            return

        QMessageBox.information(
            self, "Listo",
            "La app quedó apuntando a la nueva base. "
            "Regresa al menú para recargar las bitácoras.",
        )
        self.refresh()

    def test_connection(self, quiet: bool = False) -> None:
        try:
            tables = self.context.database.table_names()
        except Exception as error:
            self.status_label.setText(f"Error: {error}")
            if not quiet:
                QMessageBox.critical(self, "Sin conexión", str(error))
            return

        self.status_label.setText(f"Conectada. {len(tables)} tablas.")
        if not quiet:
            QMessageBox.information(
                self, "Conexión correcta",
                f"La base responde y tiene {len(tables)} tablas.",
            )

    def make_backup(self) -> None:
        try:
            target = backup.manual_backup(
                Path(self.context.config.database),
                Path(self.context.config.backups),
            )
        except Exception as error:
            QMessageBox.critical(self, "Error", str(error))
            return

        QMessageBox.information(self, "Respaldo creado", str(target))

    def show_history(self) -> None:
        HistoryDialog(self.context.audit, parent=self).exec()


class SettingsPage(BasePage):
    def __init__(self, context: AppContext, parent=None):
        super().__init__("Ajustes", parent)
        self.context = context

        self.tabs = QTabWidget()
        self.rigs_tab = RigsTab(context)
        self.customers_tab = CustomersTab(context)
        self.codes_tab = CodesTab(context)
        self.failure_modes_tab = FailureModesTab(context)
        self.requesters_tab = RequestersTab(context)
        self.database_tab = DatabaseTab(context)

        self.tabs.addTab(self.rigs_tab, "Rigs y colores")
        self.tabs.addTab(self.customers_tab, "Clientes")
        self.tabs.addTab(self.codes_tab, "Claves")
        self.tabs.addTab(self.failure_modes_tab, "Modos de falla")
        self.tabs.addTab(self.requesters_tab, "Solicitantes")
        self.tabs.addTab(self.database_tab, "Base de datos")
        self.content.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        for index in range(self.tabs.count()):
            self.tabs.widget(index).refresh()
