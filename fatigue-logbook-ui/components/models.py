"""Modelos de tabla de las bitacoras.

Lo que se dibuja sale de aqui; lo que **significa** sale de los servicios del
proyecto original, que no se tocan:

- "ya termino esta pieza"  -> ``FatigueSample.is_closed``
- "esta suspendida"        -> ``FatigueSample.is_suspended``
- "hace falta modo de falla" -> ``validation.requires_failure_mode``
- "cuantos dias lleva"     -> ``duration.days_running`` / ``elapsed``
- "esta detenida"          -> ``maintenance.paused_slots``

Ninguno de esos criterios se reescribe aqui. Duplicar uno es como el proyecto
anterior acabo con una pantalla diciendo que un banco estaba ocupado y otra que
no.

**La alineacion es de la columna, no de la celda** (:func:`column_alignment`):
numeros a la derecha, todo lo demas a la izquierda, y el encabezado como su
columna. Decidirla mirando el valor de cada celda --que es lo que habia antes--
hacia que una celda vacia se alineara distinto que sus vecinas, porque ``None``
no es ni fecha ni numero.

Y los colores se piden a la paleta **en el momento de pintar**, nunca se copian
a una constante de modulo.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle

from app import dates
from app.models import EMPTY_RIG, FINISHED, ONGOING, SAMPLE_SLOTS, is_blank
from app.services import duration, validation
from components.chips import (
    CHIPS_ROLE,
    DONE,
    MAINTENANCE,
    RIG,
    STATUS,
    SUSPENDED,
    UNKNOWN,
    Chip,
    chips_tooltip,
    compact_number,
)
from theme.manager import theme

# Roles propios. El delegado lee estos en vez de un color de texto: el color de
# texto es lo primero que se pierde cuando la fila cambia de fondo al
# seleccionarla.
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
DAYS_LEVEL_ROLE = Qt.ItemDataRole.UserRole + 3
RIG_COLOR_ROLE = Qt.ItemDataRole.UserRole + 4
# Que **forma** lleva el chip de esa celda: banco, suspendida, detenida por
# mantenimiento... El color no basta para decirlo -- un daltonico lee la
# forma-- y ademas una pieza detenida tiene la celda vacia, asi que sin este
# rol no habria nada que dibujar.
RIG_KIND_ROLE = Qt.ItemDataRole.UserRole + 5

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
CENTER = Qt.AlignmentFlag.AlignCenter

DAYS_HEADER = "Días"

# El estatus se guarda en ingles porque asi nacio la base; lo que se muestra no
# tiene por que serlo.
STATUS_LABELS = {ONGOING: "En curso", FINISHED: "Finalizada"}

NUMERIC_HEADERS = frozenset({
    "ID", "Piezas", "Total ciclos", "Total revs", DAYS_HEADER,
})
NUMERIC_PREFIXES = ("Ciclos ", "Revs ")


def column_alignment(header: str):
    """La alineacion de una columna, decidida por su encabezado."""
    if header in NUMERIC_HEADERS or header.startswith(NUMERIC_PREFIXES):
        return RIGHT
    return LEFT


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


def has_content(label: str | None, number: int | None,
                extra: str | None = None) -> bool:
    """Si una ranura de muestra se uso.

    El formulario anterior guardaba ``"--"`` y ``0`` en las ranuras vacias en
    lugar de dejarlas nulas, asi que no basta con comprobar None: sin esto las
    nueve ranuras se dibujarian siempre, llenas de ceros.

    Es publica porque tambien la pregunta el reporte compacto de Excel
    (``excel_compact.used_slots``): las piezas de la hoja tienen que ser
    exactamente las que la tabla dibuja, y con dos copias del criterio dejan
    de serlo en cuanto alguien retoca una.
    """
    return (label not in (None, "", EMPTY_RIG)) or bool(number) or bool(extra)


def _is_complete(sample) -> bool:
    """Si la pieza esta declarada por completo y ya no ocupa su banco.

    El criterio del modo de falla **no se reescribe**: sale de
    ``validation.requires_failure_mode``, que es el mismo que exige el cierre
    de una prueba. Duplicarlo dejaria a las 'S/Falla' eternamente incompletas
    en una pantalla y completas en otra.
    """
    if is_blank(sample.rig) or not sample.cycles or not sample.result:
        return False
    if validation.requires_failure_mode(sample.result):
        return bool(sample.failure_mode)
    return True


def _mode_suffix(failure_mode: str) -> str:
    return f"  ·  {failure_mode}" if failure_mode else ""


class BaseTestTableModel(QAbstractTableModel):
    """Lo comun a las cuatro bitacoras."""

    headers: list[str] = []
    days_column: int | None = None
    chips_column: int | None = None
    rig_columns: set[int] = set()
    stretch_column: int | None = None
    frozen_columns: int = 0

    def __init__(self, rig_palette, parent=None):
        super().__init__(parent)
        self.rig_palette = rig_palette
        self._records: list = []
        self.thresholds = duration.DurationThresholds()
        self.stopped: dict[int, int] = {}
        self.paused_slots: dict[tuple[int, int], object] = {}
        self._warning_icon: QIcon | None = None

    # --- datos que vienen de los servicios -------------------------------
    def set_maintenance(self, stopped: dict, paused: dict) -> None:
        self.stopped = stopped or {}
        self.paused_slots = paused or {}
        self._refresh()

    def stopped_for(self, record) -> int:
        return self.stopped.get(record.id, 0)

    def paused_at(self, record, slot: int):
        return self.paused_slots.get((record.id, slot))

    def set_thresholds(self, thresholds) -> None:
        self.thresholds = thresholds
        self._refresh()

    def _refresh(self) -> None:
        if self._records:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._records) - 1, len(self.headers) - 1),
            )

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

    # --- Qt ---------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def alignment(self, column: int):
        if column == self.chips_column:
            return LEFT
        if 0 <= column < len(self.headers):
            return column_alignment(self.headers[column])
        return LEFT

    def headerData(self, section, orientation,
                   role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            # El encabezado se alinea como su columna. Si no, un numero a la
            # derecha cuelga de un titulo a la izquierda y la tabla se lee mal.
            return self.alignment(section)
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        record = self._records[index.row()]
        column = index.column()

        if role == CHIPS_ROLE and column == self.chips_column:
            return self.chips(record)

        if role == Qt.ItemDataRole.DisplayRole:
            if column == self.chips_column:
                return ""
            return _text(self.value(record, column))

        if role == SORT_ROLE:
            if column == self.chips_column:
                return self.chips_sort_key(record)
            valor = self.value(record, column)
            if isinstance(valor, date):
                return valor.toordinal()
            if isinstance(valor, (int, float)):
                return valor
            return _text(valor).lower()

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return self.alignment(column)

        if role == DAYS_LEVEL_ROLE and column == self.days_column:
            return self.days_info(record)[1]

        if role == RIG_COLOR_ROLE and column in self.rig_columns:
            return self.rig_cell_color(record, column,
                                       self.value(record, column))

        if role == RIG_KIND_ROLE and column in self.rig_columns:
            return self.rig_cell_kind(record, column,
                                      self.value(record, column))

        if role == Qt.ItemDataRole.ToolTipRole:
            if column == self.chips_column:
                return chips_tooltip(self.chips(record))
            if column == self.days_column:
                return self.days_info(record)[2]
            return self.tooltip(record, column)

        if role == Qt.ItemDataRole.DecorationRole and column == 1:
            if self.needs_warning(record):
                return self._warning()

        return None

    # --- para redefinir ---------------------------------------------------
    def value(self, record, column: int):
        raise NotImplementedError

    def chips(self, record) -> list[Chip]:
        return []

    def chips_sort_key(self, record):
        return 0

    def rig_cell_color(self, record, column: int, value) -> str | None:
        return None if is_blank(value) else self.rig_palette.color(value)

    def rig_cell_kind(self, record, column: int, value) -> str | None:
        """La forma del chip de esa celda. None si no hay que dibujar nada.

        Se pregunta con ``is_blank`` y no por la verdad de Python: una ranura
        vacia puede ser ``None``, ``""`` o ``"--"`` --las columnas viejas no
        guardaban nulos-- y ``"--"`` es una cadena cierta, asi que un banco
        vacio acababa dibujando un recuadro vacio que no dice nada.
        """
        return None if is_blank(value) else RIG

    def days_info(self, record) -> tuple[int | None, str | None, str | None]:
        return None, None, None

    def needs_warning(self, record) -> bool:
        return False

    def tooltip(self, record, column: int) -> str | None:
        if column in self.rig_columns:
            rig = self.value(record, column)
            if rig and rig != EMPTY_RIG and not self.rig_palette.known(rig):
                return f"'{rig}' no está en el catálogo de rigs"
        return None

    # --- dias -------------------------------------------------------------
    def _running_days(self, record):
        """Prueba abierta: dias corriendo, con semaforo.

        Lo que se muestra es **tiempo de ensayo**: si el banco estuvo en
        mantenimiento, esos dias no cuentan. Sin descontarlos, una prueba
        parada tres semanas por un cambio de mordazas se pondria en rojo por
        algo que no depende de ella.
        """
        detenida = self.stopped_for(record)
        dias = duration.days_running(record.start_date, stopped=detenida)
        if dias is None:
            return None, None, "Sin fecha de inicio"

        nivel = self.thresholds.level(dias)
        aviso = f"Lleva {dias} días en curso.\n{self.thresholds.describe()}"
        if detenida:
            aviso = (
                f"{dias} días de ensayo: {dias + detenida} de calendario menos "
                f"{detenida} detenida por mantenimiento del banco.\n"
                f"{self.thresholds.describe()}"
            )
        if nivel == duration.CRITICAL:
            aviso = "Revisar: " + aviso
        return dias, nivel, aviso

    def _closed_days(self, record):
        """Prueba cerrada: cuanto duro. **Sin semaforo**, ya es historia.

        El nivel va en None y no en 'ok': antes la columna de finalizadas se
        pintaba entera de verde, que es lo mismo que decir 'todas bien' cuando
        en realidad no se esta midiendo nada.
        """
        detenida = self.stopped_for(record)
        dias = duration.elapsed(record.start_date, record.end_date,
                                stopped=detenida)
        if dias is None:
            return None, None, "Sin fecha de inicio o de fin"
        if detenida:
            return dias, None, (
                f"La prueba duró {dias} días de ensayo: {dias + detenida} de "
                f"calendario menos {detenida} de mantenimiento del banco"
            )
        return dias, None, f"La prueba duró {dias} días"

    def _warning(self) -> QIcon:
        if self._warning_icon is None:
            self._warning_icon = QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_MessageBoxWarning
            )
        return self._warning_icon


class FatigueTableModel(BaseTestTableModel):
    """Fatiga: nueve piezas, cada una con banco, resultado, ciclos y modo."""

    def __init__(self, rig_palette, show_end_date: bool,
                 compact: bool = True, parent=None):
        # super() va primero: PySide6 no admite asignar atributos sobre un
        # QObject cuyo constructor base aun no corrio.
        super().__init__(rig_palette, parent)
        self.show_end_date = show_end_date
        self.compact = compact
        self._build_headers()

    def _build_headers(self) -> None:
        headers = ["ID", "Test Batch", "Cliente", "Requester", "Inicio"]
        if self.show_end_date:
            headers.append("Fin")

        self.days_column = len(headers)
        headers.append(DAYS_HEADER)
        headers += ["Piezas", "Comentarios"]
        self.stretch_column = headers.index("Comentarios")
        self._first_sample = len(headers)

        rig_columns: set[int] = set()
        if self.compact:
            self.chips_column = len(headers)
            headers.append("Muestras")
        else:
            self.chips_column = None
            for slot in range(1, SAMPLE_SLOTS + 1):
                rig_columns.add(len(headers))
                headers += [f"Test Rig {slot}", f"Resultado {slot}",
                            f"Ciclos {slot}", f"Modo falla {slot}"]

        # Ni 'WO' ni 'Estatus': el estatus es constante por construccion --la
        # pestania ya lo dice-- y 'WO' decia lo mismo que el triangulo que ya
        # lleva el Test Batch.
        headers.append("Total ciclos")
        self.headers = headers
        self.rig_columns = rig_columns
        # En la vista completa se congelan ID, Test Batch y Cliente: son 44
        # columnas y al desplazarse se perdia de que fila se estaba leyendo.
        self.frozen_columns = 0 if self.compact else 3

    def set_compact(self, compact: bool) -> None:
        if compact == self.compact:
            return
        self.beginResetModel()
        self.compact = compact
        self._build_headers()
        self.endResetModel()

    def value(self, record, column: int):
        base = [record.id, record.test_batch, record.customer,
                record.requester, record.start_date]
        if self.show_end_date:
            base.append(record.end_date)
        base.append(self.days_info(record)[0])
        base += [record.qty_samples, record.comments]

        if column < len(base):
            return base[column]

        offset = column - self._first_sample
        if self.compact:
            cola = offset - 1
        else:
            if offset < SAMPLE_SLOTS * 4:
                sample = record.samples[offset // 4]
                return (sample.rig, sample.result, sample.cycles,
                        sample.failure_mode)[offset % 4]
            cola = offset - SAMPLE_SLOTS * 4
        return [record.total_cycles][cola]

    def chips(self, record) -> list[Chip]:
        chips: list[Chip] = []
        for indice, sample in enumerate(record.samples, start=1):
            if not has_content(sample.rig, sample.cycles,
                               sample.result or sample.failure_mode):
                continue

            ciclos = f"{sample.cycles:,}" if sample.cycles else "sin ciclos"
            paleta = theme().palette

            # El orden de las preguntas importa y no es arbitrario. Una pieza
            # parada por mantenimiento esta fuera de banco, asi que se pregunta
            # antes que por el color del rig: el suyo esta vacio justo por eso.
            parada = self.paused_at(record, indice)
            suspendida = not record.is_finished and sample.is_suspended
            color_rig = self.rig_palette.color(sample.rig)

            if parada:
                color, kind = paleta.maintenance, MAINTENANCE
            elif _is_complete(sample):
                # Declarada por completo: ya no corre en ningun banco, asi que
                # pierde el color. El color del banco significa "esta aqui
                # ahora"; en una pieza terminada solo diria donde estuvo, y eso
                # ya lo dice el tooltip.
                color, kind = None, DONE
            elif color_rig:
                color, kind = color_rig, RIG
            elif suspendida:
                color, kind = paleta.warning, SUSPENDED
            elif sample.result:
                color, kind = None, STATUS
            else:
                color, kind = None, UNKNOWN

            detalle = []
            if sample.rig and sample.rig != EMPTY_RIG:
                detalle.append(f"banco {sample.rig}")
            if parada:
                desde = (f" desde el {dates.display(parada.start_date)}"
                         if parada.start_date else "")
                detalle.append(
                    f"detenida por mantenimiento de {parada.rig_name}{desde}")
            elif kind == DONE:
                detalle.append(f"terminada  ·  {sample.result}")
            elif suspendida:
                detalle.append("suspendida, fuera de banco")
            elif sample.result:
                detalle.append(sample.result)
            if not detalle:
                detalle.append("sin banco ni resultado")

            chips.append(Chip(
                label=compact_number(sample.cycles),
                color=color,
                kind=kind,
                tooltip=(f"Pieza {indice}:  {'  ·  '.join(detalle)}"
                         f"  ·  {ciclos} ciclos"
                         + _mode_suffix(sample.failure_mode)),
            ))
        return chips

    def rig_cell_color(self, record, column: int, value) -> str | None:
        # Las dos vistas ensenian lo mismo, asi que la regla es la misma que la
        # de los chips: se decide con _sample_kind y de ahi sale el color.
        kind = self.rig_cell_kind(record, column, value)
        paleta = theme().palette
        if kind == MAINTENANCE:
            return paleta.maintenance
        if kind == SUSPENDED:
            return paleta.warning
        if kind == RIG:
            return None if is_blank(value) else self.rig_palette.color(value)
        return None

    def rig_cell_kind(self, record, column: int, value) -> str | None:
        """La forma del chip, con la misma regla que la vista compacta.

        El orden de las preguntas importa y es el mismo que en ``chips()``: una
        pieza detenida tiene la celda vacia **justo porque** su banco entro en
        mantenimiento, asi que eso se pregunta antes que por el banco.
        """
        slot = (column - self._first_sample) // 4
        sample = record.samples[slot]

        if self.paused_at(record, slot + 1):
            return MAINTENANCE
        if _is_complete(sample):
            # Declarada por completo: pierde el color, igual que su chip. El
            # nombre del banco se sigue leyendo en la celda, que es donde vive
            # el dato.
            return DONE
        if not record.is_finished and sample.is_suspended:
            return SUSPENDED
        return None if is_blank(value) else RIG

    def chips_sort_key(self, record):
        return record.total_cycles

    def days_info(self, record):
        if record.is_finished:
            return self._closed_days(record)
        return self._running_days(record)

    def needs_warning(self, record) -> bool:
        # El triangulo dice "sin Work Order". Solo en las abiertas: en una
        # prueba cerrada hace anios ya no hay nada que hacer al respecto.
        return not record.wo_status and not record.is_finished

    def tooltip(self, record, column: int) -> str | None:
        if column == 1 and self.needs_warning(record):
            return "Esta prueba no tiene Work Order"

        if column in self.rig_columns:
            # Una celda de banco vacia no explica nada por si sola, y es
            # justo el caso que mas hay que explicar.
            slot = (column - self._first_sample) // 4
            parada = self.paused_at(record, slot + 1)
            if parada:
                desde = (f" desde el {dates.display(parada.start_date)}"
                         if parada.start_date else "")
                return (f"Pieza {slot + 1}: detenida porque el banco "
                        f"{parada.rig_name} está en mantenimiento{desde}.\n"
                        f"Vuelve sola al cerrarse; si se mueve a otro banco, "
                        f"ese dato manda.")
            if (not record.is_finished
                    and record.samples[slot].is_suspended):
                return (f"Pieza {slot + 1}: suspendida. Corrió y ahora no "
                        f"está en ningún banco.")
        return super().tooltip(record, column)


class RotaryTableModel(BaseTestTableModel):
    """Rotary: un rig por prueba y nueve pares revoluciones/estatus.

    La diferencia de fondo con Fatiga: **el banco es de la prueba entera**, no
    de cada pieza. Al vaciarlo se suspenden de golpe todas las que seguian
    corriendo, y por eso la suspension se decide a nivel de prueba
    (``RotaryTest.is_suspended``) y no pieza a pieza.
    """

    def __init__(self, rig_palette, compact: bool = True, parent=None):
        super().__init__(rig_palette, parent)
        self.compact = compact
        self._build_headers()

    def _build_headers(self) -> None:
        headers = ["ID", "Test Batch", "Cliente", "Requester", "Inicio", "Fin"]
        self.days_column = len(headers)
        headers += [DAYS_HEADER, "Piezas", "Comentarios", "Rotary Rig"]

        self.rig_columns = {headers.index("Rotary Rig")}
        self.stretch_column = headers.index("Comentarios")
        self._first_sample = len(headers)

        if self.compact:
            self.chips_column = len(headers)
            headers.append("Muestras")
        else:
            self.chips_column = None
            for slot in range(1, SAMPLE_SLOTS + 1):
                headers += [f"Revs {slot}", f"Estatus {slot}",
                            f"Modo falla {slot}"]

        # Rotary si conserva 'Estatus': es la unica bitacora que mezcla
        # pruebas abiertas y cerradas en la misma tabla, asi que ahi la
        # columna distingue algo. En espaniol, no el valor crudo de la base.
        headers += ["Total revs", "Estatus"]
        self.headers = headers
        self.frozen_columns = 0 if self.compact else 3

    def set_compact(self, compact: bool) -> None:
        if compact == self.compact:
            return
        self.beginResetModel()
        self.compact = compact
        self._build_headers()
        self.endResetModel()

    def value(self, record, column: int):
        base = [record.id, record.test_batch, record.customer,
                record.requester, record.start_date, record.end_date,
                self.days_info(record)[0], record.qty_samples,
                record.comments, record.test_rig]
        if column < len(base):
            return base[column]

        offset = column - self._first_sample
        if self.compact:
            cola = offset - 1
        else:
            if offset < SAMPLE_SLOTS * 3:
                sample = record.samples[offset // 3]
                return (sample.revs, sample.status,
                        sample.failure_mode)[offset % 3]
            cola = offset - SAMPLE_SLOTS * 3
        return [record.total_revs,
                STATUS_LABELS.get(record.test_status,
                                  record.test_status)][cola]

    def chips(self, record) -> list[Chip]:
        chips: list[Chip] = []
        fuera_de_banco = record.is_suspended
        for indice, sample in enumerate(record.samples, start=1):
            if not has_content(sample.status, sample.revs,
                               sample.failure_mode):
                continue

            suspendida = fuera_de_banco and sample.is_running
            estado = (sample.status if sample.status != EMPTY_RIG
                      else "sin estatus")
            if suspendida:
                estado = "suspendida, fuera de banco"
            revs = f"{sample.revs:,}" if sample.revs else "sin revs"

            if suspendida:
                color, kind = theme().palette.warning, SUSPENDED
            elif sample.status and sample.status != EMPTY_RIG:
                color, kind = None, STATUS
            else:
                color, kind = None, UNKNOWN

            chips.append(Chip(
                label=compact_number(sample.revs),
                color=color,
                kind=kind,
                tooltip=(f"Pieza {indice}:  {estado}  ·  {revs} revs"
                         + _mode_suffix(sample.failure_mode)),
            ))
        return chips

    def rig_cell_color(self, record, column: int, value) -> str | None:
        # Una sola columna, la de la prueba: o esta en un banco, o esta
        # suspendida entera.
        color = (None if is_blank(value)
                 else self.rig_palette.color(value, "rotary"))
        if color:
            return color
        return theme().palette.warning if record.is_suspended else None

    def rig_cell_kind(self, record, column: int, value) -> str | None:
        if not is_blank(value) and self.rig_palette.color(value, "rotary"):
            return RIG
        if record.is_suspended:
            return SUSPENDED
        return None if is_blank(value) else RIG

    def chips_sort_key(self, record):
        return record.total_revs

    def days_info(self, record):
        # Rotary mezcla abiertas y cerradas en una sola tabla, asi que se
        # decide fila por fila y no por pestania.
        if record.test_status == FINISHED:
            return self._closed_days(record)
        return self._running_days(record)


class GenericTableModel(BaseTestTableModel):
    """Torsion y Quasi. Una sola clase para las dos bitacoras.

    No llevan estatus ni dias: lo que esta registrado esta hecho, y la prueba
    es de un rato. Su Test Rig es un dato del registro, no un banco que se
    queda ocupado.
    """

    headers = ["ID", "Test Batch", "Cliente", "Requester", "Fecha", "Piezas",
               "Comentarios", "Test Rig"]
    rig_columns = {7}
    stretch_column = 6

    def __init__(self, rig_palette, test_type: str, parent=None):
        super().__init__(rig_palette, parent)
        self.test_type = test_type

    def value(self, record, column: int):
        return [record.id, record.test_batch, record.customer,
                record.requester, record.test_date, record.qty_samples,
                record.comments, record.test_rig][column]

    def rig_cell_color(self, record, column: int, value) -> str | None:
        return (None if is_blank(value)
                else self.rig_palette.color(value, self.test_type))

    def rig_cell_kind(self, record, column: int, value) -> str | None:
        return None if is_blank(value) else RIG
