"""Modelos de tabla para las bitacoras.

Reemplazan al ``Tableview`` de ttkbootstrap, que obligaba a reconstruir la
tabla entera con ``build_table_data()`` en cada refresco y guardaba los datos
como cadenas: por eso la marca de advertencia se concatenaba al test batch y
habia que quitarla con ``.replace()`` antes de editar.

Fatiga y Rotary tienen dos vistas:

- **compacta** (por omision): las 9 muestras se dibujan como chips de color en
  una sola columna, y la fila cabe en pantalla.
- **completa**: una columna por rig y por ciclos, como estaba antes, para
  cuando se necesita leer o copiar un valor exacto.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import QApplication, QStyle

from app import dates
from app.models import EMPTY_RIG, FINISHED, SAMPLE_SLOTS
from app.services import duration
from app.services.catalogs import CatalogService, contrasting_text_color
from app.ui import theme
from app.ui.widgets.sample_chips import (
    CHIPS_ROLE,
    RIG,
    STATUS,
    UNKNOWN,
    Chip,
    chips_tooltip,
    compact_number,
)

# Rol propio para ordenar por el valor real (fecha, entero) y no por su texto.
SORT_ROLE = Qt.ItemDataRole.UserRole + 1

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
CENTER = Qt.AlignmentFlag.AlignCenter

DAYS_HEADER = "Dias"

# Semaforo de antiguedad. Se pinta el texto y no el fondo: el fondo ya lo usan
# los colores de rig, y dos fondos de color en la misma fila compiten.
DAYS_COLORS = {
    duration.OK: theme.SUCCESS,
    duration.WARNING: theme.WARNING,
    duration.CRITICAL: theme.DANGER,
}


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return dates.display(value)
    if isinstance(value, bool):
        return "Si" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _has_content(
    label: str | None, number: int | None, extra: str | None = None
) -> bool:
    """Si una ranura de muestra se uso.

    El formulario anterior guardaba ``"--"`` y ``0`` en las ranuras vacias en
    lugar de dejarlas nulas, asi que no basta con comprobar None: sin esto las
    nueve ranuras se dibujarian siempre, llenas de ceros.

    ``extra`` cubre el modo de falla: una pieza puede tener modo anotado y nada
    mas, y aun asi debe dibujarse.
    """
    used_label = label not in (None, "", EMPTY_RIG)
    used_number = bool(number)
    return used_label or used_number or bool(extra)


def _mode_suffix(failure_mode: str) -> str:
    """Cola del tooltip con el modo de falla, si se capturo."""
    return f"  ·  {failure_mode}" if failure_mode else ""


def _alignment(value):
    """Alineacion segun el tipo de dato.

    Antes todo iba centrado, incluidos los ciclos: comparar 8,084 contra
    80,840 centrados obliga a leer digito por digito. Los numeros van a la
    derecha, donde las unidades quedan alineadas entre filas.
    """
    if isinstance(value, bool):
        return CENTER
    if isinstance(value, (int, float)):
        return RIGHT
    if isinstance(value, date):
        return CENTER
    return LEFT


class BaseTestTableModel(QAbstractTableModel):
    """Comportamiento comun: colores de rig, orden y acceso al registro."""

    headers: list[str] = []
    rig_columns: set[int] = set()
    batch_column: int = 1
    chips_column: int | None = None
    days_column: int | None = None

    def __init__(self, catalogs: CatalogService, parent=None):
        super().__init__(parent)
        self.catalogs = catalogs
        self._records: list = []
        self._warning_icon: QIcon | None = None
        self.thresholds = duration.DurationThresholds()

    def set_thresholds(self, thresholds: duration.DurationThresholds) -> None:
        self.thresholds = thresholds
        if self._records and self.days_column is not None:
            top = self.index(0, self.days_column)
            bottom = self.index(len(self._records) - 1, self.days_column)
            self.dataChanged.emit(bottom, top)

    # --- datos -----------------------------------------------------------
    def set_records(self, records: list) -> None:
        self.beginResetModel()
        self._records = list(records)
        self.endResetModel()

    def record_at(self, row: int):
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def records(self) -> list:
        return list(self._records)

    # --- QAbstractTableModel --------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return section + 1

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        record = self._records[index.row()]
        column = index.column()

        # --- columna de chips --------------------------------------------
        if self.chips_column is not None and column == self.chips_column:
            chips = self.chips(record)
            if role == CHIPS_ROLE:
                return chips
            if role == Qt.ItemDataRole.DisplayRole:
                return ""            # lo pinta el delegado
            if role == SORT_ROLE:
                return self.chips_sort_key(record)
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(LEFT)
            if role == Qt.ItemDataRole.ToolTipRole:
                return chips_tooltip(chips)
            return None

        value = self.value(record, column)

        if role == Qt.ItemDataRole.DisplayRole:
            return _text(value)

        if role == SORT_ROLE:
            # Las fechas y los numeros se ordenan por su valor real.
            if value is None:
                return ""
            if isinstance(value, date):
                return value.toordinal()
            return value

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(_alignment(value))

        if role == Qt.ItemDataRole.BackgroundRole and column in self.rig_columns:
            color = self.cell_color(value)
            if color:
                return QColor(color)

        if role == Qt.ItemDataRole.ForegroundRole and column in self.rig_columns:
            color = self.cell_color(value)
            if color:
                return QColor(contrasting_text_color(color))

        if column == self.days_column:
            days, level, hint = self.days_info(record)
            if role == Qt.ItemDataRole.ForegroundRole:
                return QColor(DAYS_COLORS[level])
            if role == Qt.ItemDataRole.FontRole and level == duration.CRITICAL:
                font = QFont()
                font.setBold(True)
                return font
            if role == Qt.ItemDataRole.ToolTipRole:
                return hint

        if role == Qt.ItemDataRole.DecorationRole and column == self.batch_column:
            if self.needs_warning(record):
                return self._warning()

        if role == Qt.ItemDataRole.ToolTipRole:
            return self.tooltip(record, column)

        return None

    # --- puntos de extension ---------------------------------------------
    def value(self, record, column: int):
        raise NotImplementedError

    def chips(self, record) -> list[Chip]:
        return []

    def chips_sort_key(self, record):
        return 0

    def cell_color(self, value) -> str | None:
        """Color de una celda de rig. Solo los bancos llevan color."""
        return self.catalogs.color(value)

    def is_status(self, value) -> bool:
        """Si el valor es uno de los resultados de pieza del catalogo."""
        if not value:
            return False
        text = str(value).strip().upper()
        return any(text == s.upper() for s in self.catalogs.sample_statuses())

    def days_info(self, record) -> tuple[int | None, str, str | None]:
        """(dias, nivel del semaforo, tooltip) de la columna de antiguedad."""
        return None, duration.OK, None

    def _running_days(self, record) -> tuple[int | None, str, str | None]:
        """Prueba abierta: dias corriendo, con semaforo."""
        days = duration.days_running(record.start_date)
        if days is None:
            return None, duration.OK, "Sin fecha de inicio"

        level = self.thresholds.level(days)
        hint = f"Lleva {days} dias en curso.\n{self.thresholds.describe()}"
        if level == duration.CRITICAL:
            hint = "Revisar: " + hint
        return days, level, hint

    @staticmethod
    def _closed_days(record) -> tuple[int | None, str, str | None]:
        """Prueba cerrada: cuanto duro. Sin semaforo, ya es historia."""
        days = duration.elapsed(record.start_date, record.end_date)
        if days is None:
            return None, duration.OK, "Sin fecha de inicio o de fin"
        return days, duration.OK, f"La prueba duro {days} dias"

    def needs_warning(self, record) -> bool:
        return False

    def tooltip(self, record, column: int) -> str | None:
        if column in self.rig_columns:
            rig = self.value(record, column)
            if rig and rig != EMPTY_RIG and not self.cell_color(rig):
                return f"'{rig}' no esta en el catalogo de rigs"
        return None

    def _warning(self) -> QIcon:
        if self._warning_icon is None:
            style = QApplication.style()
            self._warning_icon = style.standardIcon(
                QStyle.StandardPixmap.SP_MessageBoxWarning
            )
        return self._warning_icon


class FatigueTableModel(BaseTestTableModel):
    """Fatiga: 9 pares rig/ciclos."""

    def __init__(
        self,
        catalogs: CatalogService,
        show_end_date: bool,
        compact: bool = True,
        parent=None,
    ):
        # super() va primero: PySide6 no admite asignar atributos sobre un
        # QObject cuyo constructor de la clase base aun no corrio.
        super().__init__(catalogs, parent)
        self.show_end_date = show_end_date
        self.compact = compact
        self._build_headers()

    def _build_headers(self) -> None:
        headers = ["ID", "Test Batch", "Cliente", "Inicio"]
        if self.show_end_date:
            headers.append("Fin")

        self.days_column = len(headers)
        headers.append(DAYS_HEADER)

        headers += ["Piezas", "Comentarios"]

        # Indice donde empiezan las columnas de muestra.
        self._first_sample = len(headers)

        rig_columns: set[int] = set()
        if self.compact:
            self.chips_column = len(headers)
            headers.append("Muestras")
        else:
            self.chips_column = None
            for slot in range(1, SAMPLE_SLOTS + 1):
                rig_columns.add(len(headers))
                headers += [
                    f"Test Rig {slot}", f"Resultado {slot}", f"Ciclos {slot}",
                    f"Modo falla {slot}",
                ]

        headers += ["Total ciclos", "WO", "Estatus"]
        self.headers = headers
        self.rig_columns = rig_columns

    def set_compact(self, compact: bool) -> None:
        if compact == self.compact:
            return
        self.beginResetModel()
        self.compact = compact
        self._build_headers()
        self.endResetModel()

    def value(self, record, column: int):
        base = [
            record.id,
            record.test_batch,
            record.customer,
            record.start_date,
        ]
        if self.show_end_date:
            base.append(record.end_date)
        base.append(self.days_info(record)[0])
        base += [record.qty_samples, record.comments]

        if column < len(base):
            return base[column]

        offset = column - self._first_sample

        if self.compact:
            tail = offset - 1        # la columna de chips ocupa una sola
        else:
            # Cuatro columnas por muestra: rig, resultado, ciclos y modo.
            if offset < SAMPLE_SLOTS * 4:
                sample = record.samples[offset // 4]
                return (sample.rig, sample.result, sample.cycles,
                        sample.failure_mode)[offset % 4]
            tail = offset - SAMPLE_SLOTS * 4

        return [record.total_cycles, record.wo_status, record.test_status][tail]

    def chips(self, record) -> list[Chip]:
        chips = []
        for index, sample in enumerate(record.samples, start=1):
            if not _has_content(
                sample.rig, sample.cycles,
                sample.result or sample.failure_mode,
            ):
                continue

            cycles = f"{sample.cycles:,}" if sample.cycles else "sin ciclos"

            # El color es del banco. La forma dice de que se tiene constancia:
            # cuadrado si se sabe donde corrio, pastilla si solo se anoto como
            # acabo -- que es el caso de casi todo lo anterior a 2026.
            rig_color = self.catalogs.color(sample.rig)
            if rig_color:
                color, kind = rig_color, RIG
            elif sample.result:
                color, kind = None, STATUS
            else:
                color, kind = None, UNKNOWN

            detalle = []
            if sample.rig and sample.rig != EMPTY_RIG:
                detalle.append(f"banco {sample.rig}")
            if sample.result:
                detalle.append(sample.result)
            if not detalle:
                detalle.append("sin banco ni resultado")

            chips.append(
                Chip(
                    label=compact_number(sample.cycles),
                    color=color,
                    kind=kind,
                    tooltip=(
                        f"Pieza {index}:  {'  ·  '.join(detalle)}"
                        f"  ·  {cycles} ciclos"
                        + _mode_suffix(sample.failure_mode)
                    ),
                )
            )
        return chips

    def chips_sort_key(self, record):
        return record.total_cycles

    def days_info(self, record):
        # La pestana de finalizadas muestra cuanto duro; la de en curso,
        # cuanto lleva abierta.
        if self.show_end_date:
            return self._closed_days(record)
        return self._running_days(record)

    def needs_warning(self, record) -> bool:
        """Pruebas sin Work Order. Antes se marcaban pegando un emoji al texto."""
        return not record.wo_status

    def tooltip(self, record, column: int) -> str | None:
        if column == self.batch_column and not record.wo_status:
            return "Esta prueba no tiene Work Order"
        return super().tooltip(record, column)


class RotaryTableModel(BaseTestTableModel):
    """Rotary: un rig por prueba y 9 pares revoluciones/estatus."""

    def __init__(
        self, catalogs: CatalogService, compact: bool = True, parent=None
    ):
        super().__init__(catalogs, parent)
        self.compact = compact
        self._build_headers()

    def _build_headers(self) -> None:
        headers = ["ID", "Test Batch", "Cliente", "Inicio", "Fin"]
        self.days_column = len(headers)
        headers += [DAYS_HEADER, "Piezas", "Comentarios", "Rotary Rig"]

        self.rig_columns = {headers.index("Rotary Rig")}
        self._first_sample = len(headers)

        if self.compact:
            self.chips_column = len(headers)
            headers.append("Muestras")
        else:
            self.chips_column = None
            for slot in range(1, SAMPLE_SLOTS + 1):
                headers += [
                    f"Revs {slot}", f"Estatus {slot}", f"Modo falla {slot}"
                ]

        headers += ["Total revs", "Estatus"]
        self.headers = headers

    def set_compact(self, compact: bool) -> None:
        if compact == self.compact:
            return
        self.beginResetModel()
        self.compact = compact
        self._build_headers()
        self.endResetModel()

    def value(self, record, column: int):
        base = [
            record.id, record.test_batch, record.customer, record.start_date,
            record.end_date, self.days_info(record)[0], record.qty_samples,
            record.comments, record.test_rig,
        ]
        if column < len(base):
            return base[column]

        offset = column - self._first_sample

        if self.compact:
            tail = offset - 1
        else:
            if offset < SAMPLE_SLOTS * 3:
                sample = record.samples[offset // 3]
                return (sample.revs, sample.status,
                        sample.failure_mode)[offset % 3]
            tail = offset - SAMPLE_SLOTS * 3

        return [record.total_revs, record.test_status][tail]

    def chips(self, record) -> list[Chip]:
        chips = []
        for index, sample in enumerate(record.samples, start=1):
            if not _has_content(sample.status, sample.revs,
                                sample.failure_mode):
                continue
            status = sample.status if sample.status != EMPTY_RIG else "sin estatus"
            revs = f"{sample.revs:,}" if sample.revs else "sin revs"
            chips.append(
                Chip(
                    label=compact_number(sample.revs),
                    color=None,
                    kind=STATUS if self.is_status(sample.status) else UNKNOWN,
                    tooltip=(
                        f"Pieza {index}:  {status}  ·  {revs} revs"
                        + _mode_suffix(sample.failure_mode)
                    ),
                )
            )
        return chips

    def chips_sort_key(self, record):
        return record.total_revs

    def days_info(self, record):
        # Rotary mezcla abiertas y cerradas en una sola tabla, asi que se
        # decide fila por fila.
        if record.test_status == FINISHED:
            return self._closed_days(record)
        return self._running_days(record)


class GenericTableModel(BaseTestTableModel):
    """Torsion y Quasi. Una sola clase para las dos bitacoras."""

    headers = [
        "ID", "Test Batch", "Cliente", "Fecha", "Piezas", "Comentarios",
        "Test Rig",
    ]
    rig_columns = {6}

    def value(self, record, column: int):
        return [
            record.id, record.test_batch, record.customer, record.test_date,
            record.qty_samples, record.comments, record.test_rig,
        ][column]
