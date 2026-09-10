"""Historial de mantenimientos: los periodos en que un banco estuvo parado.

No es el historial de cambios de ``audit_log``, que cuenta campo a campo lo que
se edito. Aqui cada renglon es un **periodo**: cuando empezo, cuando termino,
cuanto duro, por que y a que piezas dejo detenidas.

Hasta ahora solo se veia el mantenimiento **abierto**, en la tarjeta de su
banco. Los cerrados no aparecian en ninguna pantalla: el tiempo se medía --se
descontaba de los dias de la prueba-- pero no se podia consultar de donde
salia.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app import dates
from app.models import TEST_TYPES, RigMaintenance
from app.ui import theme

HEADERS = ["Banco", "Bitácora", "Inicio", "Fin", "Días", "Motivo",
           "Piezas detenidas", "Registró"]

# Columna del 'Fin', que es la unica que cambia de color: un periodo sin fecha
# de fin sigue abierto, y eso es lo primero que se busca al abrir la ventana.
END_COLUMN = 3
ABIERTO = "en curso"


class MaintenanceHistoryDialog(QDialog):
    """Los periodos de mantenimiento, de lo mas reciente a lo mas antiguo."""

    def __init__(self, records: list[RigMaintenance], title: str | None = None,
                 subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title or "Historial de mantenimiento")
        self.resize(940, 520)

        layout = QVBoxLayout(self)

        encabezado = QLabel(title or "Historial de mantenimiento")
        encabezado.setProperty("subheading", "true")
        layout.addWidget(encabezado)

        self.summary = QLabel(subtitle or self._describe(records))
        self.summary.setProperty("muted", "true")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        # El motivo es lo unico de largo variable: se lleva el ancho que sobre
        # y las demas se ajustan a su contenido, que es corto y conocido.
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(
            HEADERS.index("Motivo"), QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

        buttons = QDialogButtonBox()
        # No se usa StandardButton.Close: Qt lo rotula segun el idioma del
        # sistema y salia 'Close' en medio de una ventana en espanol.
        buttons.addButton("Cerrar", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.populate(records)

    @staticmethod
    def _describe(records: list[RigMaintenance]) -> str:
        if not records:
            return "No hay mantenimientos registrados todavía."
        abiertos = sum(1 for r in records if r.is_open)
        dias = sum(r.days() or 0 for r in records)
        partes = [
            f"{len(records)} periodo" + ("s" if len(records) != 1 else ""),
            f"{dias} día" + ("s" if dias != 1 else "") + " fuera de servicio",
        ]
        if abiertos:
            partes.append(f"{abiertos} sin cerrar")
        return "  ·  ".join(partes)

    def populate(self, records: list[RigMaintenance]) -> None:
        self.table.setRowCount(len(records))

        for row, record in enumerate(records):
            paradas = [s for s in record.samples if not s.restored]
            dias = record.days()

            valores = [
                record.rig_name,
                TEST_TYPES[record.test_type].label
                if record.test_type in TEST_TYPES else record.test_type,
                dates.display(record.start_date) if record.start_date else "",
                dates.display(record.end_date) if record.end_date else ABIERTO,
                "" if dias is None else str(dias),
                record.reason or "",
                str(len(record.samples)) if record.samples else "—",
                record.created_by or "",
            ]

            for column, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)

            # El motivo es lo unico de largo libre y Qt lo corta con puntos
            # suspensivos cuando no cabe: entero, en el tooltip.
            if record.reason:
                self.table.item(row, HEADERS.index("Motivo")).setToolTip(
                    record.reason
                )

            if record.is_open:
                # El unico color de la tabla: lo que sigue parado hoy.
                self.table.item(row, END_COLUMN).setForeground(
                    QColor(theme.MAINTENANCE)
                )

            if record.samples:
                detalle = "\n".join(
                    f"{s.test_batch or f'#{s.record_id}'}  ·  pieza {s.slot}"
                    + ("" if s.restored else "  (sin reponer)")
                    for s in record.samples
                )
                self.table.item(row, HEADERS.index("Piezas detenidas")) \
                    .setToolTip(detalle)
            if paradas:
                self.table.item(row, HEADERS.index("Piezas detenidas")).setText(
                    f"{len(record.samples)}  ({len(paradas)} sin reponer)"
                )
