"""Reporte a Excel de las pruebas de fatiga en curso.

Aplica a cada celda de Test Rig el color configurado para ese rig, de modo que
el reporte impreso se lea igual que la pantalla.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app import dates
from app.models import EMPTY_RIG, SAMPLE_SLOTS, FatigueTest
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

TOTAL_FONT = Font(bold=True, size=11)
CENTER = Alignment(horizontal="center", vertical="center")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

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
    "Piezas": 8,
    "Comentarios": 30,
    "Total ciclos": 14,
    "WO": 6,
}

# El modo de falla es texto largo; 13 lo cortaria en casi todos los casos.
MODE_WIDTH = 20


def _hex(color: str) -> str:
    """openpyxl espera el color sin '#'."""
    return color.lstrip("#").upper()


def build_headers() -> list[str]:
    headers = list(BASE_HEADERS)
    for slot in range(1, SAMPLE_SLOTS + 1):
        headers += [
            f"Test Rig {slot}", f"Resultado {slot}", f"Ciclos {slot}",
            f"Modo falla {slot}",
        ]
    headers += TAIL_HEADERS
    return headers


def export_fatigue_ongoing(
    tests: list[FatigueTest],
    rig_colors: dict[str, str],
    destination: str | Path,
    paused: dict[tuple[int, int], object] | None = None,
) -> Path:
    """Genera el archivo y devuelve su ruta.

    ``paused`` son las piezas detenidas por mantenimiento del banco, con la
    misma clave que usa la tabla: ``(id de prueba, numero de pieza)``. Sin
    ellas el reporte impreso ensenia esas piezas como una suspension mas, y
    no es lo mismo: una la retiro la prueba y la otra el banco.
    """
    detenidas = paused or {}
    path = Path(destination)
    headers = build_headers()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Fatigas en curso"

    sheet.append([f"Pruebas de fatiga en curso  -  {dates.display(date.today())}"])
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

    # --- filas -----------------------------------------------------------
    # Tres columnas por muestra: rig, ciclos y modo de falla.
    rig_column_indexes: list[int] = []
    for slot in range(SAMPLE_SLOTS):
        rig_column_indexes.append(len(BASE_HEADERS) + slot * COLUMNS_PER_SAMPLE + 1)

    for test in tests:
        row = [
            test.id,
            test.test_batch,
            test.customer,
            test.requester or "",
            dates.display(test.start_date),
            test.qty_samples,
            "" if test.comments == "--" else test.comments,
        ]
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

        sheet.append(row)
        row_index = sheet.max_row

        for column in range(1, len(headers) + 1):
            cell = sheet.cell(row=row_index, column=column)
            cell.alignment = CENTER
            cell.border = BORDER
            if not test.wo_status:
                cell.fill = NO_WO_FILL

        # Color por rig, encima del resaltado de WO.
        for column in rig_column_indexes:
            cell = sheet.cell(row=row_index, column=column)
            valor = str(cell.value or "")
            color = rig_colors.get(valor)
            if color:
                cell.fill = PatternFill("solid", fgColor=_hex(color))
                cell.font = Font(color=_hex(contrasting_text_color(color)))
            elif valor == SUSPENDED_LABEL:
                cell.fill = SUSPENDED_FILL
                cell.font = SUSPENDED_FONT
            elif valor == MAINTENANCE_LABEL:
                cell.fill = MAINTENANCE_FILL
                cell.font = MAINTENANCE_FONT

    # --- totales ---------------------------------------------------------
    total_row = sheet.max_row + 1
    sheet.cell(row=total_row, column=1, value="TOTALES").font = TOTAL_FONT

    samples_column = BASE_HEADERS.index("Piezas") + 1
    total_samples = sum(t.qty_samples for t in tests)
    total_cycles = sum(t.total_cycles for t in tests)

    cell = sheet.cell(row=total_row, column=samples_column, value=total_samples)
    cell.font = TOTAL_FONT
    cell.alignment = CENTER

    cycles_column = headers.index("Total ciclos") + 1
    cell = sheet.cell(row=total_row, column=cycles_column, value=total_cycles)
    cell.font = TOTAL_FONT
    cell.alignment = CENTER

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
                          end_column=len(BASE_HEADERS))
        nota = sheet.cell(row=note_row, column=1, value=texto)
        nota.fill = relleno
        nota.font = Font(italic=True, size=10, color="1B2631")
        nota.alignment = Alignment(horizontal="left", vertical="center")

    # --- formato ---------------------------------------------------------
    for index, header in enumerate(headers, start=1):
        letter = get_column_letter(index)
        default = MODE_WIDTH if header.startswith("Modo falla") else 13
        sheet.column_dimensions[letter].width = COLUMN_WIDTHS.get(header, default)

    # Congela encabezado y las tres primeras columnas de identificacion.
    sheet.freeze_panes = "D3"
    sheet.auto_filter.ref = (
        f"A2:{get_column_letter(len(headers))}{max(total_row - 1, 2)}"
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


def suggested_filename() -> str:
    return f"Fatigas_Ongoing_{date.today().isoformat()}.xlsx"
