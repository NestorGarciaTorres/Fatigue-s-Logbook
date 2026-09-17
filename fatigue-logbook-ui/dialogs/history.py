"""Las dos ventanas de consulta: historial de cambios e historial de paros.

Son cosas distintas y conviene no confundirlas:

- :class:`HistoryDialog` lee el ``audit_log``: cuenta **campo a campo** quien
  cambio que y cuando. Es lo primero que hay que mirar antes de culpar al
  codigo -- dos veces un cambio inesperado en los datos resulto ser una
  edicion del propio usuario con la app abierta.
- :class:`MaintenanceHistoryDialog` lee los **periodos** en que un banco estuvo
  parado: cuando empezo, cuanto duro, por que y a que piezas dejo detenidas.

Las traducciones de columna y de valor se importan del proyecto original: son
tablas de dominio --que significa ``wo_status = 1``-- y ``form_guard`` las usa
tambien para explicar un conflicto. Copiarlas dejaria dos versiones de lo mismo
envejeciendo por separado.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app import dates
from app.models import TEST_TYPES, AuditEntry, RigMaintenance
from app.services.excel_export import export_maintenance, suggested_filename
from app.ui.dialogs.history_dialog import (
    ACTION_LABELS,
    field_label,
    value_label,
)
from app.ui.report_export import save_report
from components import buttons, labels

# El equipo no es una columna: quien consulta el historial quiere saber que
# cambio y quien lo cambio. El nombre de la maquina va en el tooltip del
# usuario, que es donde se busca cuando de verdad hace falta.
CHANGE_HEADERS = ["Fecha", "Usuario", "Acción", "Campo", "Antes", "Después"]

MAINTENANCE_HEADERS = ["Banco", "Bitácora", "Inicio", "Fin", "Días", "Motivo",
                       "Piezas detenidas", "Registró"]
ABIERTO = "en curso"


def _table(headers: list[str]) -> QTableWidget:
    tabla = QTableWidget(0, len(headers))
    tabla.setHorizontalHeaderLabels(headers)
    tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tabla.setAlternatingRowColors(True)
    tabla.setShowGrid(False)
    tabla.verticalHeader().setVisible(False)
    tabla.horizontalHeader().setHighlightSections(False)
    return tabla


def _item(texto: str) -> QTableWidgetItem:
    item = QTableWidgetItem(texto)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return item


class HistoryDialog(QDialog):
    """Quien cambio que y cuando, campo a campo."""

    def __init__(self, audit, table: str | None = None,
                 record_id: int | None = None,
                 title: str = "Historial de cambios", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(920, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(labels.heading(title))
        self.summary = labels.secondary("", wrap=True)
        layout.addWidget(self.summary)

        self.table = _table(CHANGE_HEADERS)
        cabecera = self.table.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Las columnas de la izquierda tienen ancho conocido y corto; repartir
        # el espacio a partes iguales dejaba 'Pieza 1 · Modo de falla' cortado
        # mientras sobraba sitio en 'Usuario'.
        for columna in range(len(CHANGE_HEADERS) - 2):
            cabecera.setSectionResizeMode(
                columna, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        layout.addLayout(buttons.button_row(
            None,
            buttons.button("Cerrar", buttons.PRIMARY, on_click=self.reject),
            stretch_at_end=False))

        if table and record_id is not None:
            entradas = audit.for_record(table, record_id)
        else:
            entradas = audit.search()
        self.populate(entradas)

    def populate(self, entries: list[AuditEntry]) -> None:
        equipos = sorted({e.machine for e in entries if e.machine})
        self.summary.setText(
            f"{len(entries)} cambios registrados"
            + (f"  ·  desde {len(equipos)} equipos" if len(equipos) > 1 else "")
            if entries else "Este registro no tiene cambios anotados todavía.")

        self.table.setRowCount(len(entries))
        for fila, entrada in enumerate(entries):
            valores = [
                entrada.changed_at.strftime("%d/%m/%Y %H:%M"),
                entrada.changed_by,
                ACTION_LABELS.get(entrada.action, entrada.action),
                field_label(entrada.field),
                value_label(entrada.field, entrada.old_value),
                value_label(entrada.field, entrada.new_value),
            ]
            for columna, valor in enumerate(valores):
                item = _item(valor)
                if columna == 1 and entrada.machine:
                    item.setToolTip(f"Equipo: {entrada.machine}")
                self.table.setItem(fila, columna, item)


def _estado_pieza(record: RigMaintenance, sample) -> str:
    """Como acabo cada pieza respecto a este mantenimiento, para el tooltip.

    Son **cuatro** casos y no dos: volvio a su banco, sigue esperando, la
    llevaron a otro banco para seguir probandola, o el mantenimiento cerro sin
    devolverla.
    """
    if sample.restored:
        return "  (volvió a su banco)"
    if sample.released_date:
        return (f"  (siguió en otro banco el "
                f"{dates.display(sample.released_date)})")
    if record.is_open:
        return "  (sigue detenida)"
    return "  (no se repuso al cerrar)"


class MaintenanceHistoryDialog(QDialog):
    """Los periodos de mantenimiento, del mas reciente al mas antiguo.

    No es el historial de cambios: aqui cada renglon es un **periodo**. Hasta
    que existio esta ventana, solo se veia el mantenimiento abierto en la
    tarjeta de su banco -- los cerrados no aparecian en ninguna pantalla,
    aunque su tiempo se estuviera descontando de los dias de cada prueba.
    """

    def __init__(self, records: list[RigMaintenance],
                 title: str | None = None, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.records = records
        self.setWindowTitle(title or "Historial de mantenimiento")
        self.resize(980, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(labels.heading(title or "Historial de mantenimiento"))
        layout.addWidget(labels.secondary(
            subtitle or self._describe(records), wrap=True))

        self.table = _table(MAINTENANCE_HEADERS)
        cabecera = self.table.horizontalHeader()
        # El motivo es lo unico de largo variable: se lleva el ancho que sobre
        # y las demas se ajustan a su contenido, que es corto y conocido.
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cabecera.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.export_button = buttons.button(
            "Exportar a Excel", buttons.SUCCESS, on_click=self.export)
        layout.addLayout(buttons.button_row(
            self.export_button, None,
            buttons.button("Cerrar", buttons.PRIMARY, on_click=self.reject),
            stretch_at_end=False))

        self.populate(records)

    @staticmethod
    def _describe(records: list[RigMaintenance]) -> str:
        if not records:
            return "Ningún banco estuvo fuera de servicio en este periodo."
        abiertos = sum(1 for r in records if r.is_open)
        total = sum(r.days() or 0 for r in records)
        texto = f"{len(records)} periodos  ·  {total} días fuera de servicio"
        if abiertos:
            texto += (f"  ·  {abiertos} sigue abierto" if abiertos == 1
                      else f"  ·  {abiertos} siguen abiertos")
        return texto

    def populate(self, records: list[RigMaintenance]) -> None:
        self.table.setRowCount(len(records))
        for fila, record in enumerate(records):
            detenidas = [s for s in record.samples if s.is_held]
            dias = record.days()

            valores = [
                record.rig_name,
                TEST_TYPES[record.test_type].label
                if record.test_type in TEST_TYPES else record.test_type,
                dates.display(record.start_date),
                dates.display(record.end_date) if record.end_date else ABIERTO,
                "" if dias is None else str(dias),
                record.reason or "",
                str(len(detenidas)) if record.samples else "0",
                record.created_by or "",
            ]
            for columna, valor in enumerate(valores):
                item = _item(valor)
                if columna == 6 and record.samples:
                    # El detalle de cada pieza en el tooltip: son cuatro
                    # estados distintos y en la celda solo cabe el numero.
                    item.setToolTip("\n".join(
                        f"{s.test_batch or f'registro #{s.record_id}'}  ·  "
                        f"pieza {s.slot}{_estado_pieza(record, s)}"
                        for s in record.samples))
                self.table.setItem(fila, columna, item)

            # Un periodo abierto se marca con una pastilla, no tiniendo el
            # texto: el color de texto se pierde al seleccionar la fila.
            if record.is_open:
                self.table.setCellWidget(fila, 3,
                                         labels.pill(ABIERTO, "maintenance"))

    def export(self) -> None:
        save_report(
            self, len(self.records), suggested_filename("Mantenimiento"),
            lambda ruta: export_maintenance(self.records, ruta),
            empty_message="No hay periodos de mantenimiento que exportar.")
