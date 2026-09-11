"""Reportes a Excel de las bitacoras.

Empezo con uno solo, el de fatigas en curso, y ahora son seis: fatiga en curso
y finalizada, Rotary, Torsion y Quasi, las Work Orders y el historial de
mantenimiento. Comparten el aspecto --titulo con su fecha o periodo,
encabezado oscuro, encabezado congelado y autofiltro-- y cada celda de banco
lleva el color configurado para ese rig, de modo que el reporte impreso se lea
igual que la pantalla.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app import dates
from app.models import (
    EMPTY_RIG,
    FINISHED,
    ONGOING,
    SAMPLE_SLOTS,
    TEST_TYPES,
    FatigueTest,
    GenericTest,
    RigMaintenance,
    RotaryTest,
    WorkOrder,
    is_blank,
)
from app.services.catalogs import contrasting_text_color

HEADER_FILL = PatternFill("solid", fgColor="2B3E50")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)

# Las pruebas sin Work Order se resaltan, igual que en la bitacora.
NO_WO_FILL = PatternFill("solid", fgColor="FDECEA")

# Pieza suspendida: corrio, acumulo ciclos y hoy no esta en ningun banco. En
# pantalla es un chip naranja; aqui es la misma idea con el mismo color, para
# que el reporte impreso no pierda la unica marca que distingue una pieza
# retirada de una ranura que nadie uso.
SUSPENDED_FILL = PatternFill("solid", fgColor="F0AD4E")
SUSPENDED_FONT = Font(color="1B2631", bold=True)
SUSPENDED_LABEL = "Suspendida"
SUSPENDED_NOTE = (
    f"{SUSPENDED_LABEL}: la pieza corrio y esta fuera de banco; "
    "sus ciclos son los acumulados hasta que se retiro."
)

# Pieza parada porque su banco esta en mantenimiento. Mismo rojo que el chip
# de la tabla; se repite el hex y no se importa app.ui.theme porque un
# servicio no depende de la interfaz -- es lo mismo que ya se hace arriba con
# el naranja de las suspendidas.
MAINTENANCE_FILL = PatternFill("solid", fgColor="FE9296")
MAINTENANCE_FONT = Font(color="1B2631", bold=True)
MAINTENANCE_LABEL = "Mantenimiento"
MAINTENANCE_NOTE = (
    f"{MAINTENANCE_LABEL}: el banco de esa pieza esta fuera de servicio. "
    "La prueba no avanza mientras dure, y esos dias no cuentan como dias "
    "de ensayo en la bitacora."
)

# Un mantenimiento que sigue abierto: es lo primero que se busca en la hoja.
OPEN_FONT = Font(color="C0392B", bold=True)

TOTAL_FONT = Font(bold=True, size=11)
CENTER = Alignment(horizontal="center", vertical="center")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

# Los estatus se guardan en ingles; en el reporte, como en pantalla. Se repite
# aqui y no se importa de la tabla porque un servicio no depende de la
# interfaz.
STATUS_TEXT = {ONGOING: "En curso", FINISHED: "Finalizada"}

BASE_HEADERS = ["ID", "Test Batch", "Cliente", "Requester", "Inicio",
                "Piezas", "Comentarios"]
TAIL_HEADERS = ["Total ciclos", "WO"]

# Rig, resultado, ciclos y modo de falla por cada una de las 9 muestras.
COLUMNS_PER_SAMPLE = 4

COLUMN_WIDTHS = {
    "ID": 8,
    "Test Batch": 15,
    "Cliente": 20,
    "Requester": 18,
    "Inicio": 12,
    "Fin": 12,
    "Fecha": 12,
    "Piezas": 8,
    "Comentarios": 30,
    "Total ciclos": 14,
    "Total revs": 14,
    "WO": 6,
}

# El modo de falla es texto largo; 13 lo cortaria en casi todos los casos.
MODE_WIDTH = 20


# --- piezas comunes ---------------------------------------------------------
def _hex(color: str) -> str:
    """openpyxl espera el color sin '#'."""
    return color.lstrip("#").upper()


def _date(value) -> str:
    return dates.display(value) if value else ""


def _comments(value) -> str:
    return "" if value in (None, "--") else value


def _rig(value) -> str:
    return "" if is_blank(value) else value


def period_text(period: tuple | None) -> str:
    """El periodo del reporte para el titulo; sin rango, la fecha de hoy."""
    desde, hasta = period or (None, None)
    if desde and hasta:
        return f"del {dates.display(desde)} al {dates.display(hasta)}"
    if desde:
        return f"desde el {dates.display(desde)}"
    if hasta:
        return f"hasta el {dates.display(hasta)}"
    return dates.display(date.today())


def _new_sheet(sheet_title: str, title: str, headers: list[str]):
    """Libro con su titulo en la fila 1 y el encabezado en la 2."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title[:31]          # Excel no admite mas

    sheet.append([title])
    sheet.merge_cells(
        start_row=1, start_column=1, end_row=1, end_column=len(headers)
    )
    title_cell = sheet.cell(row=1, column=1)
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal="left", vertical="center")

    sheet.append(headers)
    for column in range(1, len(headers) + 1):
        cell = sheet.cell(row=2, column=column)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = BORDER
    return workbook, sheet


def _append_row(sheet, values: list, width: int, fill=None) -> int:
    sheet.append(values)
    fila = sheet.max_row
    for column in range(1, width + 1):
        cell = sheet.cell(row=fila, column=column)
        cell.alignment = CENTER
        cell.border = BORDER
        if fill is not None:
            cell.fill = fill
    return fila


def _paint_rig(cell, rig_colors: dict[str, str]) -> None:
    color = rig_colors.get(str(cell.value or ""))
    if color:
        cell.fill = PatternFill("solid", fgColor=_hex(color))
        cell.font = Font(color=_hex(contrasting_text_color(color)))


def _totals(sheet, headers: list[str], values: dict[str, object]) -> int:
    fila = sheet.max_row + 1
    sheet.cell(row=fila, column=1, value="TOTALES").font = TOTAL_FONT
    for header, value in values.items():
        cell = sheet.cell(row=fila, column=headers.index(header) + 1, value=value)
        cell.font = TOTAL_FONT
        cell.alignment = CENTER
    return fila


def _save(workbook, sheet, headers: list[str], destination, widths: dict,
          freeze: str, last_data_row: int) -> Path:
    for index, header in enumerate(headers, start=1):
        default = MODE_WIDTH if header.startswith("Modo falla") else 13
        sheet.column_dimensions[get_column_letter(index)].width = widths.get(
            header, default
        )
    sheet.freeze_panes = freeze
    sheet.auto_filter.ref = (
        f"A2:{get_column_letter(len(headers))}{max(last_data_row, 2)}"
    )
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


# --- fatiga -----------------------------------------------------------------
def _base_headers(finished: bool) -> list[str]:
    headers = list(BASE_HEADERS)
    if finished:
        # La fecha de cierre junto a la de inicio: es lo que se lee de una
        # prueba terminada, y lo que filtra el rango de fechas.
        headers.insert(headers.index("Inicio") + 1, "Fin")
    return headers


def build_headers(finished: bool = False) -> list[str]:
    headers = _base_headers(finished)
    for slot in range(1, SAMPLE_SLOTS + 1):
        headers += [
            f"Test Rig {slot}", f"Resultado {slot}", f"Ciclos {slot}",
            f"Modo falla {slot}",
        ]
    headers += TAIL_HEADERS
    return headers


def export_fatigue(
    tests: list[FatigueTest],
    rig_colors: dict[str, str],
    destination: str | Path,
    paused: dict[tuple[int, int], object] | None = None,
    finished: bool = False,
    period: tuple | None = None,
) -> Path:
    """Genera el archivo y devuelve su ruta.

    ``paused`` son las piezas detenidas por mantenimiento del banco, con la
    misma clave que usa la tabla: ``(id de prueba, numero de pieza)``. Sin
    ellas el reporte impreso ensenia esas piezas como una suspension mas, y
    no es lo mismo: una la retiro la prueba y la otra el banco.

    ``finished`` agrega la fecha de fin y titula con ``period``, el rango de
    fechas que tenian puesto los filtros.
    """
    detenidas = paused or {}
    base = _base_headers(finished)
    headers = build_headers(finished)

    if finished:
        workbook, sheet = _new_sheet(
            "Fatigas finalizadas",
            f"Pruebas de fatiga finalizadas  -  {period_text(period)}",
            headers,
        )
    else:
        workbook, sheet = _new_sheet(
            "Fatigas en curso",
            f"Pruebas de fatiga en curso  -  {dates.display(date.today())}",
            headers,
        )

    # --- filas -----------------------------------------------------------
    rig_column_indexes = [
        len(base) + slot * COLUMNS_PER_SAMPLE + 1 for slot in range(SAMPLE_SLOTS)
    ]

    for test in tests:
        row = [test.id, test.test_batch, test.customer, test.requester or "",
               dates.display(test.start_date)]
        if finished:
            row.append(_date(test.end_date))
        row += [test.qty_samples, _comments(test.comments)]

        for numero, sample in enumerate(test.samples, start=1):
            # El mantenimiento se pregunta primero: la pieza parada tiene el
            # banco vacio, asi que tambien cumple la condicion de suspendida.
            if (test.id, numero) in detenidas:
                banco = MAINTENANCE_LABEL
            elif not test.is_finished and sample.is_suspended:
                banco = SUSPENDED_LABEL
            else:
                banco = "" if sample.rig == EMPTY_RIG else sample.rig
            row += [
                banco,
                sample.result or "",
                sample.cycles if sample.cycles is not None else "",
                sample.failure_mode or "",
            ]
        row += [test.total_cycles, "Si" if test.wo_status else "No"]

        row_index = _append_row(
            sheet, row, len(headers),
            fill=None if test.wo_status else NO_WO_FILL,
        )

        # Color por rig, encima del resaltado de WO.
        for column in rig_column_indexes:
            cell = sheet.cell(row=row_index, column=column)
            valor = str(cell.value or "")
            if rig_colors.get(valor):
                _paint_rig(cell, rig_colors)
            elif valor == SUSPENDED_LABEL:
                cell.fill = SUSPENDED_FILL
                cell.font = SUSPENDED_FONT
            elif valor == MAINTENANCE_LABEL:
                cell.fill = MAINTENANCE_FILL
                cell.font = MAINTENANCE_FONT

    # --- totales ---------------------------------------------------------
    total_row = _totals(sheet, headers, {
        "Piezas": sum(t.qty_samples for t in tests),
        "Total ciclos": sum(t.total_cycles for t in tests),
    })

    # Nota al pie, solo si hace falta: un color sin explicacion en una hoja
    # impresa se queda sin significado en cuanto la mira alguien que no
    # estuvo en la captura.
    # Una pieza detenida por mantenimiento tambien cumple la condicion de
    # suspendida --esta fuera de banco-- asi que se descuenta al preguntar por
    # las suspendidas, o saldrian las dos notas por una sola pieza.
    hay_detenidas = any(
        (t.id, i) in detenidas
        for t in tests for i in range(1, SAMPLE_SLOTS + 1)
    )
    hay_suspendidas = any(
        s.is_suspended and (t.id, i) not in detenidas
        for t in tests if not t.is_finished
        for i, s in enumerate(t.samples, start=1)
    )

    notas = []
    if hay_suspendidas:
        notas.append((SUSPENDED_NOTE, SUSPENDED_FILL))
    if hay_detenidas:
        notas.append((MAINTENANCE_NOTE, MAINTENANCE_FILL))

    for posicion, (texto, relleno) in enumerate(notas):
        note_row = total_row + 2 + posicion
        sheet.merge_cells(start_row=note_row, start_column=1, end_row=note_row,
                          end_column=len(base))
        nota = sheet.cell(row=note_row, column=1, value=texto)
        nota.fill = relleno
        nota.font = Font(italic=True, size=10, color="1B2631")
        nota.alignment = Alignment(horizontal="left", vertical="center")

    # Congela encabezado y las tres primeras columnas de identificacion.
    return _save(workbook, sheet, headers, destination, COLUMN_WIDTHS, "D3",
                 total_row - 1)


def export_fatigue_ongoing(
    tests: list[FatigueTest],
    rig_colors: dict[str, str],
    destination: str | Path,
    paused: dict[tuple[int, int], object] | None = None,
) -> Path:
    """El reporte de fatigas en curso, el primero que tuvo la app."""
    return export_fatigue(tests, rig_colors, destination, paused=paused)


# --- Rotary -----------------------------------------------------------------
ROTARY_BASE_HEADERS = ["ID", "Test Batch", "Cliente", "Requester", "Inicio",
                       "Fin", "Piezas", "Comentarios", "Rotary Rig"]


def export_rotary(tests: list[RotaryTest], rig_colors: dict[str, str],
                  destination: str | Path, period: tuple | None = None) -> Path:
    """Las columnas de la vista completa de Rotary: tres por muestra."""
    headers = list(ROTARY_BASE_HEADERS)
    for slot in range(1, SAMPLE_SLOTS + 1):
        headers += [f"Revs {slot}", f"Estatus {slot}", f"Modo falla {slot}"]
    headers += ["Total revs", "Estatus"]

    workbook, sheet = _new_sheet(
        "Rotary", f"Pruebas Rotary  -  {period_text(period)}", headers
    )
    rig_column = headers.index("Rotary Rig") + 1

    for test in tests:
        row = [test.id, test.test_batch, test.customer, test.requester or "",
               _date(test.start_date), _date(test.end_date), test.qty_samples,
               _comments(test.comments), _rig(test.test_rig)]
        for sample in test.samples:
            row += [sample.revs if sample.revs is not None else "",
                    _rig(sample.status), sample.failure_mode or ""]
        row += [test.total_revs,
                STATUS_TEXT.get(test.test_status, test.test_status)]
        fila = _append_row(sheet, row, len(headers))
        _paint_rig(sheet.cell(row=fila, column=rig_column), rig_colors)

    total_row = _totals(sheet, headers, {
        "Piezas": sum(t.qty_samples for t in tests),
        "Total revs": sum(t.total_revs for t in tests),
    })
    return _save(workbook, sheet, headers, destination, COLUMN_WIDTHS, "D3",
                 total_row - 1)


# --- Torsion y Quasi --------------------------------------------------------
GENERIC_HEADERS = ["ID", "Test Batch", "Cliente", "Requester", "Fecha",
                   "Piezas", "Comentarios", "Test Rig"]


def export_generic(tests: list[GenericTest], label: str,
                   rig_colors: dict[str, str], destination: str | Path,
                   period: tuple | None = None) -> Path:
    """Torsion y Quasi: una fila por prueba, con su banco en color."""
    headers = list(GENERIC_HEADERS)
    workbook, sheet = _new_sheet(
        label, f"Pruebas de {label}  -  {period_text(period)}", headers
    )
    rig_column = headers.index("Test Rig") + 1

    for test in tests:
        fila = _append_row(sheet, [
            test.id, test.test_batch, test.customer, test.requester or "",
            _date(test.test_date), test.qty_samples, _comments(test.comments),
            _rig(test.test_rig),
        ], len(headers))
        _paint_rig(sheet.cell(row=fila, column=rig_column), rig_colors)

    total_row = _totals(sheet, headers, {
        "Piezas": sum(t.qty_samples for t in tests),
    })
    return _save(workbook, sheet, headers, destination, COLUMN_WIDTHS, "C3",
                 total_row - 1)


# --- Work Orders ------------------------------------------------------------
WORK_ORDER_HEADERS = ["#", "Tipo", "Test Batch", "Cliente", "Piezas",
                      "Requester", "Comentarios", "Creada", "Creada por",
                      "Estado", "Registro"]
WORK_ORDER_WIDTHS = {"#": 6, "Tipo": 11, "Test Batch": 15, "Cliente": 20,
                     "Piezas": 8, "Requester": 18, "Comentarios": 30,
                     "Creada": 12, "Creada por": 24, "Estado": 12,
                     "Registro": 10}


def export_work_orders(orders: list[WorkOrder], destination: str | Path,
                       type_labels: dict[str, str] | None = None) -> Path:
    """Las ordenes en el orden en que se ven: el de prioridad.

    El numero es la posicion en la fila de pendientes, como en pantalla, no el
    valor guardado: al comenzar o borrar ordenes ese valor deja huecos.
    """
    etiquetas = type_labels or {k: c.label for k, c in TEST_TYPES.items()}
    headers = list(WORK_ORDER_HEADERS)
    workbook, sheet = _new_sheet(
        "Work Orders", f"Work Orders  -  {dates.display(date.today())}", headers
    )

    posicion = 0
    for order in orders:
        if not order.is_started:
            posicion += 1
        _append_row(sheet, [
            "—" if order.is_started else posicion,
            etiquetas.get(order.test_type, order.test_type),
            order.test_batch, order.customer, order.qty_samples,
            order.requester, order.comments or "", _date(order.created_at),
            order.created_by or "", order.status,
            f"#{order.started_test_id}" if order.started_test_id else "",
        ], len(headers))

    total_row = _totals(sheet, headers, {
        "Piezas": sum(o.qty_samples for o in orders),
    })
    return _save(workbook, sheet, headers, destination, WORK_ORDER_WIDTHS,
                 "D3", total_row - 1)


# --- mantenimiento ----------------------------------------------------------
MAINTENANCE_HEADERS = ["Banco", "Bitácora", "Inicio", "Fin", "Días", "Motivo",
                       "Piezas detenidas", "Registró"]
MAINTENANCE_WIDTHS = {"Banco": 12, "Bitácora": 12, "Inicio": 12, "Fin": 12,
                      "Días": 8, "Motivo": 40, "Piezas detenidas": 16,
                      "Registró": 24}
OPEN_TEXT = "en curso"


def export_maintenance(records: list[RigMaintenance], destination: str | Path,
                       reference: date | None = None) -> Path:
    """Los periodos de mantenimiento, como en su historial."""
    headers = list(MAINTENANCE_HEADERS)
    hoy = reference or date.today()
    workbook, sheet = _new_sheet(
        "Mantenimiento",
        f"Historial de mantenimiento de bancos  -  {dates.display(hoy)}",
        headers,
    )
    fin_column = headers.index("Fin") + 1

    for record in records:
        dias = record.days(hoy)
        tipo = TEST_TYPES.get(record.test_type)
        fila = _append_row(sheet, [
            record.rig_name, tipo.label if tipo else record.test_type,
            _date(record.start_date),
            _date(record.end_date) if record.end_date else OPEN_TEXT,
            "" if dias is None else dias, record.reason or "",
            len(record.samples), record.created_by or "",
        ], len(headers))
        if record.is_open:
            sheet.cell(row=fila, column=fin_column).font = OPEN_FONT

    total_row = _totals(sheet, headers, {
        "Días": sum(r.days(hoy) or 0 for r in records),
        "Piezas detenidas": sum(len(r.samples) for r in records),
    })
    return _save(workbook, sheet, headers, destination, MAINTENANCE_WIDTHS,
                 "B3", total_row - 1)


def suggested_filename(prefix: str = "Fatigas_Ongoing") -> str:
    return f"{prefix}_{date.today().isoformat()}.xlsx"
