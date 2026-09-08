"""Historial de cambios de un registro o de toda la base."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.db.repositories import AuditRepository
from app.models import AuditEntry

ACTION_LABELS = {
    "created": "Alta",
    "updated": "Edición",
    "closed": "Cierre",
    "reopened": "Reapertura",
    "started": "Comenzada",
    "deleted": "Baja",
}

# El historial guarda el nombre de la columna, que es lo correcto para la base
# pero ilegible en pantalla: 'test_rig3' no le dice nada a quien consulta por
# que una pieza se quedo sin banco.
FIELD_LABELS = {
    "test_batch": "Test Batch",
    "customer": "Cliente",
    "start_date": "Inicio de prueba",
    "end_date": "Fin de prueba",
    "test_date": "Fecha de prueba",
    "qty_samples": "No. de piezas",
    "comments": "Comentarios",
    "wo_status": "Tiene Work Order",
    "test_status": "Estatus",
    "test_rig": "Test Rig",
    "test_type": "Tipo de prueba",
    "requester": "Requester",
    "status": "Estado",
    "priority": "Prioridad",
    "started_test_id": "Registro creado",
    "registro": "Registro",
    "work order": "Work Order",
    "prioridad": "Prioridad",
}

# Columnas por muestra: 'cycles4' se lee como 'Pieza 4 - Ciclos'.
SAMPLE_FIELDS = {
    "test_rig": "Test Rig",
    "result": "Resultado",
    "cycles": "Ciclos",
    "failure_mode": "Modo de falla",
    "revs": "Revoluciones",
    "status": "Estatus",
}

# Valores que en la base son codigos y en pantalla no significan nada.
VALUE_LABELS = {
    "test_status": {"Ongoing": "En curso", "Finished": "Finalizada"},
    "wo_status": {"1": "Si", "0": "No"},
}

# Un banco borrado se guarda como "--". Mostrarlo tal cual haria pensar que el
# valor nuevo es literalmente esos dos guiones.
EMPTY_DISPLAY = "(vacío)"
EMPTY_VALUES = {None, "", "--"}

# El equipo no es una columna: quien consulta el historial quiere saber
# que cambio y quien lo cambio. El nombre de la maquina va en el tooltip
# del usuario, que es donde se busca cuando de verdad hace falta.
HEADERS = ["Fecha", "Usuario", "Acción", "Campo", "Antes", "Después"]


def field_label(field: str | None) -> str:
    """Nombre legible de la columna que cambio."""
    if not field:
        return ""
    if field in FIELD_LABELS:
        return FIELD_LABELS[field]

    # Las columnas por muestra acaban en el numero de pieza.
    stem = field.rstrip("0123456789")
    number = field[len(stem):]
    if number and stem in SAMPLE_FIELDS:
        return f"Pieza {number}  -  {SAMPLE_FIELDS[stem]}"
    return field


def value_label(field: str | None, value) -> str:
    """Valor legible, distinguiendo 'se borro' de 'no cambio'."""
    if value in EMPTY_VALUES:
        return EMPTY_DISPLAY
    text = str(value)
    return VALUE_LABELS.get(field or "", {}).get(text, text)


class HistoryDialog(QDialog):
    def __init__(
        self,
        audit: AuditRepository,
        table: str | None = None,
        record_id: int | None = None,
        title: str = "Historial de cambios",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(860, 520)

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Las columnas de la izquierda tienen ancho conocido y corto; repartir
        # el espacio a partes iguales dejaba 'Pieza 1 - Modo de falla' cortado
        # en 'Pieza 1 - Mod...' mientras sobraba sitio en 'Usuario'.
        for column in range(len(HEADERS) - 2):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        layout.addWidget(self.table)

        buttons = QDialogButtonBox()
        # No se usa StandardButton.Close: Qt lo rotula segun el idioma del
        # sistema y salia 'Close' en medio de una ventana en espanol.
        buttons.addButton("Cerrar", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        if table and record_id is not None:
            entries = audit.for_record(table, record_id)
        else:
            entries = audit.search()

        self.populate(entries)

    def populate(self, entries: list[AuditEntry]) -> None:
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = [
                entry.changed_at.strftime("%d/%m/%Y %H:%M"),
                entry.changed_by,
                ACTION_LABELS.get(entry.action, entry.action),
                field_label(entry.field),
                value_label(entry.field, entry.old_value),
                value_label(entry.field, entry.new_value),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 1 and entry.machine:
                    item.setToolTip(f"Equipo: {entry.machine}")
                self.table.setItem(row, column, item)
