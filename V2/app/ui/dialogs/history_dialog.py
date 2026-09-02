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
    "updated": "Edicion",
    "closed": "Cierre",
    "reopened": "Reapertura",
    "deleted": "Baja",
}

HEADERS = ["Fecha", "Usuario", "Equipo", "Accion", "Campo", "Antes", "Despues"]


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
        self.resize(920, 520)

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
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
                entry.machine or "",
                ACTION_LABELS.get(entry.action, entry.action),
                entry.field or "",
                entry.old_value or "",
                entry.new_value or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
