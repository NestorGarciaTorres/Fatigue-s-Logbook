"""Poner un banco en mantenimiento y sacarlo de mantenimiento.

Los dos dialogos ensenian lo mismo antes de aceptar: **que piezas se mueven**.
Un mantenimiento no toca solo al banco --vacia el Test Rig de las piezas que
estaban corriendo en el, y al cerrarlo se las devuelve-- y eso hay que verlo
antes de pulsar, no descubrirlo despues en la bitacora.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QVBoxLayout,
)

from app import dates
from app.models import MaintenanceSample, RigMaintenance
from components import buttons, fields, labels

# Cuantas piezas se enumeran antes de resumir. Con mas, la lista es mas larga
# que el dialogo y deja de leerse.
LISTED = 8


def _piece_lines(samples: list[MaintenanceSample]) -> list[str]:
    lineas = [f"{s.test_batch or f'registro #{s.record_id}'}  ·  pieza {s.slot}"
              for s in samples[:LISTED]]
    if len(samples) > LISTED:
        lineas.append(f"… y {len(samples) - LISTED} más")
    return lineas


def _piece_box(title: str, samples: list[MaintenanceSample],
               empty: str) -> QGroupBox:
    caja = QGroupBox(title)
    columna = QVBoxLayout(caja)
    columna.setSpacing(3)

    if not samples:
        columna.addWidget(labels.muted(empty, wrap=True))
        return caja

    for linea in _piece_lines(samples):
        columna.addWidget(labels.secondary(linea))
    return caja


class StartMaintenanceDialog(QDialog):
    """Abre el periodo y avisa de las piezas que van a salir del banco."""

    def __init__(self, rig, affected: list[MaintenanceSample], parent=None):
        super().__init__(parent)
        self.rig = rig
        self.affected = affected

        self.setWindowTitle(f"Mantenimiento de {rig.name}")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(labels.subheading(
            f"Poner {rig.name} en mantenimiento"))

        form = QFormLayout()
        self.start_edit = fields.date_edit()
        # Un mantenimiento que empieza maniana no puede sacar piezas hoy. Se
        # permite fecharlo hacia atras: casi siempre se captura al dia
        # siguiente, cuando el banco ya lleva parado desde ayer.
        self.start_edit.setMaximumDate(QDate.currentDate())
        form.addRow("Inicio", self.start_edit)

        self.reason_edit = fields.line_edit(
            "Cambio de mordazas, calibración, falla eléctrica…",
            centered=False)
        form.addRow("Motivo", self.reason_edit)
        layout.addLayout(form)

        layout.addWidget(_piece_box(
            f"Piezas que salen del banco ({len(affected)})", affected,
            "Ninguna prueba está corriendo en este banco: solo se registra el "
            "periodo fuera de servicio."))

        layout.addWidget(labels.muted(
            "Las piezas quedan sin banco y marcadas como detenidas. Los días "
            "de mantenimiento no cuentan en la columna Días de la bitácora.",
            wrap=True))

        self.save_button = buttons.button(
            "Poner en mantenimiento", buttons.MAINTENANCE,
            on_click=self.accept)
        layout.addLayout(buttons.button_row(
            None,
            buttons.button("Cancelar", buttons.GHOST, on_click=self.reject),
            self.save_button, stretch_at_end=False))

    def start_date(self) -> date:
        return fields.to_date(self.start_edit)

    def reason(self) -> str:
        return self.reason_edit.text().strip()

    def maintenance(self, created_by: str = "") -> RigMaintenance:
        """El periodo tal como hay que guardarlo."""
        return RigMaintenance(rig_name=self.rig.name,
                              test_type=self.rig.test_type,
                              rig_id=self.rig.id,
                              start_date=self.start_date(),
                              reason=self.reason(),
                              created_by=created_by)


class FinishMaintenanceDialog(QDialog):
    """Cierra el periodo y ofrece devolver las piezas a su banco."""

    def __init__(self, record: RigMaintenance, parent=None):
        super().__init__(parent)
        self.record = record

        self.setWindowTitle(f"Mantenimiento de {record.rig_name}")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(labels.subheading(
            f"Terminar el mantenimiento de {record.rig_name}"))

        detalle = [f"Desde el {dates.display(record.start_date)}"]
        dias = record.days()
        if dias is not None:
            detalle.append(f"{dias} días fuera de servicio")
        if record.reason:
            detalle.append(record.reason)
        layout.addWidget(labels.secondary("  ·  ".join(detalle), wrap=True))

        form = QFormLayout()
        self.end_edit = fields.date_edit()
        # No puede terminar antes de empezar; la validacion se pone en el
        # propio control para no tener que rechazar el dialogo despues.
        if record.start_date:
            self.end_edit.setMinimumDate(QDate(record.start_date))
        form.addRow("Fin", self.end_edit)
        layout.addLayout(form)

        # Las que el mantenimiento aun retiene. La que se llevaron a otro banco
        # no vuelve: su banco ahora es el otro.
        pendientes = [s for s in record.samples if s.is_held]
        layout.addWidget(_piece_box(
            f"Piezas que vuelven al banco ({len(pendientes)})", pendientes,
            "No hay piezas pendientes de devolver."))

        self.restore_check = QCheckBox("Devolver las piezas a este banco")
        self.restore_check.setChecked(True)
        self.restore_check.setEnabled(bool(pendientes))
        self.restore_check.setToolTip(
            "Solo se repone la pieza cuyo Test Rig siga vacío: si mientras el "
            "banco estuvo parado se movió a otro, ese dato manda.")
        layout.addWidget(self.restore_check)

        self.save_button = buttons.button(
            "Terminar mantenimiento", buttons.SUCCESS, on_click=self.accept)
        layout.addLayout(buttons.button_row(
            None,
            buttons.button("Cancelar", buttons.GHOST, on_click=self.reject),
            self.save_button, stretch_at_end=False))

    def end_date(self) -> date:
        return fields.to_date(self.end_edit)

    def restore(self) -> bool:
        return self.restore_check.isChecked()
