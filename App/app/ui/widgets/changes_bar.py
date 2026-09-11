"""Aviso de que otro equipo guardo cambios en lo que se esta viendo.

Varias computadoras usan la misma base, y una pantalla abierta no se enteraba
de nada hasta que se navegaba o se pulsaba F5: se podia elegir un banco que
otro equipo acababa de ocupar, o dar por pendiente una orden ya comenzada.

No se recarga sola. Recargar a mitad de trabajo pierde la fila seleccionada y
lo desplazado; el aviso dice que hay algo nuevo y quien quiere lo trae.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from app.models import AuditEntry
from app.ui.dialogs.history_dialog import field_label

# Nombres que se escriben antes de resumir en 'y N mas'.
NAMES_LISTED = 3
# Renglones del detalle que sale al pasar el cursor.
DETAIL_LINES = 10


def ago(moment: datetime, now: datetime) -> str:
    """'hace 3 min'. El reloj de otro equipo puede ir adelantado: nunca negativo."""
    segundos = (now - moment).total_seconds()
    if segundos < 60:
        return "hace un momento"
    minutos = int(segundos // 60)
    if minutos < 60:
        return f"hace {minutos} min"
    horas = minutos // 60
    return "hace 1 hora" if horas == 1 else f"hace {horas} horas"


def _record_label(entry: AuditEntry) -> str:
    return entry.test_batch or f"el registro #{entry.record_id}"


def _names(people: list[str]) -> str:
    if len(people) == 1:
        return people[0]
    if len(people) > NAMES_LISTED:
        return (", ".join(people[:NAMES_LISTED])
                + f" y {len(people) - NAMES_LISTED} más")
    return ", ".join(people[:-1]) + " y " + people[-1]


def describe_changes(entries: list[AuditEntry],
                     now: datetime | None = None) -> str:
    """Una frase: quien guardo, en que y cuando fue lo ultimo."""
    if not entries:
        return ""
    now = now or datetime.now()
    personas = list(dict.fromkeys(e.changed_by or "otro equipo" for e in entries))
    registros = list(dict.fromkeys((e.table_name, e.record_id) for e in entries))
    ultimo = max(entries, key=lambda e: e.changed_at)

    verbo = "guardó" if len(personas) == 1 else "guardaron"
    if len(registros) == 1:
        que = f"cambios en {_record_label(ultimo)}"
    else:
        que = f"cambios en {len(registros)} registros"
    return f"{_names(personas)} {verbo} {que} {ago(ultimo.changed_at, now)}."


def describe_detail(entries: list[AuditEntry]) -> str:
    """Un renglon por apunte, para el tooltip: cuando, quien, que y donde."""
    lineas = []
    for entry in entries[:DETAIL_LINES]:
        linea = (f"{entry.changed_at:%d/%m %H:%M}  {entry.changed_by}"
                 + (f" ({entry.machine})" if entry.machine else "")
                 + f"  ·  {_record_label(entry)}")
        if entry.field:
            linea += f"  ·  {field_label(entry.field)}"
        lineas.append(linea)
    if len(entries) > DETAIL_LINES:
        lineas.append(f"…  y {len(entries) - DETAIL_LINES} cambios más")
    return "\n".join(lineas)


class ChangesBar(QWidget):
    """La franja del aviso, sobre la pantalla visible. Oculta mientras no hay nada."""

    refreshRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QHBoxLayout(self)
        # El margen va en este contenedor y no en la ventana: oculto, no deja
        # una franja vacia encima de cada pantalla.
        outer.setContentsMargins(11, 8, 11, 0)

        self.frame = QFrame()
        self.frame.setProperty("changes", "true")
        outer.addWidget(self.frame)

        layout = QHBoxLayout(self.frame)
        layout.setContentsMargins(12, 6, 8, 6)
        layout.setSpacing(10)

        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message, 1)

        self.refresh_button = QPushButton("Actualizar")
        self.refresh_button.setToolTip("Vuelve a cargar esta pantalla (F5)")
        self.refresh_button.clicked.connect(self.refreshRequested)
        layout.addWidget(self.refresh_button)

        self.hide()

    def show_changes(self, entries: list[AuditEntry],
                     now: datetime | None = None) -> None:
        if not entries:
            self.hide()
            return
        self.message.setText("Hay datos nuevos: " + describe_changes(entries, now))
        self.setToolTip(describe_detail(entries))
        self.show()
