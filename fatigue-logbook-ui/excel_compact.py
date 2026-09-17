"""El reporte de fatigas en curso, una fila por pieza.

El de siempre --``app.services.excel_export.export_fatigue``-- escribe una fila
por prueba y **treinta y seis columnas de muestra**: las nueve ranuras por sus
cuatro datos (banco, resultado, ciclos, modo de falla), esten usadas o no. Con
7 columnas fijas y 2 de cola son 45, y como casi ninguna prueba pasa de tres
piezas, la mayor parte de la hoja va en blanco y hay que desplazarse de lado
para leer un solo registro.

Aqui la muestra baja en vez de crecer a lo ancho: **una fila por pieza** y
catorce columnas, con una pieza o con nueve. No se pierde ningun dato --los
mismos campos, los mismos colores y las mismas notas-- y los ciclos siguen
siendo un numero entero de verdad, escrito completo y con separador de miles;
la abreviatura ``8.1K`` es de los chips de la pantalla y no entra aqui.

Vive en la interfaz nueva y **no toca el proyecto original**: reutiliza sus
ayudantes (``_new_sheet``, ``_append_row``, ``_paint_rig``, ``_totals``,
``_save``) y sus colores, que es lo que pide el CLAUDE.md de alla --un reporte
nuevo no arma su hoja a mano--, sin cambiarle a nadie la forma de la suya.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl.styles import Alignment, Font

from app import dates
from app.models import EMPTY_RIG, FatigueTest
from app.services.excel_export import (
    COLUMN_WIDTHS,
    MAINTENANCE_FILL,
    MAINTENANCE_FONT,
    MAINTENANCE_LABEL,
    MAINTENANCE_NOTE,
    NO_WO_FILL,
    SUSPENDED_FILL,
    SUSPENDED_FONT,
    SUSPENDED_LABEL,
    SUSPENDED_NOTE,
    _append_row,
    _comments,
    _new_sheet,
    _paint_rig,
    _save,
    _totals,
)
from components.models import has_content

# Las columnas de la prueba se combinan sobre las filas de sus piezas. Es lo
# que hace legible e imprimible la hoja: sin esto, el ID y el cliente se
# repiten en cada renglon y cuesta ver donde empieza un registro.
#
# Lo que cuesta: Excel **no ordena** un rango con celdas combinadas, y el
# autofiltro solo ensenia el valor en la fila de arriba de cada combinacion.
# Se acepta porque la hoja de 45 columnas tampoco se podia ordenar por pieza
# --no habia una columna de pieza-- asi que no se pierde nada que hubiera. En
# False la hoja sale plana, con los datos repetidos, y entonces si se ordena y
# se puede resumir en una tabla dinamica.
MERGE_TEST_ROWS = True

# Fijas, luego la pieza y sus datos, luego la cola. Los nombres son los mismos
# del reporte de siempre a proposito: ``_totals`` localiza su columna por el
# texto de la cabecera, y quien ya lea "Total ciclos" lo sigue encontrando.
BASE_HEADERS = ["ID", "Test Batch", "Cliente", "Requester", "Inicio",
                "Piezas", "Comentarios"]
SAMPLE_HEADERS = ["Pieza", "Test Rig", "Resultado", "Ciclos", "Modo falla"]
TAIL_HEADERS = ["Total ciclos", "WO"]

# "Mantenimiento" son trece caracteres y es lo mas largo que cae en Test Rig;
# con los 13 de ancho por defecto se corta.
EXTRA_WIDTHS = {"Pieza": 7, "Test Rig": 16, "Resultado": 12, "Ciclos": 14}

# Los ciclos se leen de un vistazo o no se leen: 1234455 contra 1,234,455. Es
# formato de celda, no texto -- la celda sigue siendo un numero que suma.
CYCLES_FORMAT = "#,##0"

NOTE_FONT = Font(italic=True, size=10, color="1B2631")
NOTE_ALIGNMENT = Alignment(horizontal="left", vertical="center")


def build_headers() -> list[str]:
    """Las catorce columnas, siempre las mismas.

    El reporte de finalizadas mete ``Fin`` justo despues de ``Inicio``; si
    algun dia esta hoja tambien lo necesita, ese es el sitio.
    """
    return list(BASE_HEADERS) + list(SAMPLE_HEADERS) + list(TAIL_HEADERS)


def used_slots(test: FatigueTest) -> list[int]:
    """Las ranuras que alguien uso, en orden, empezando en 1.

    El criterio no se escribe aqui: es ``components.models.has_content``, el
    mismo que decide si la tabla dibuja un chip. Copiarlo dejaria el reporte
    ensenando unas piezas y la pantalla otras, que es justo lo que no puede
    pasar en un papel que se firma.
    """
    return [numero for numero, sample in enumerate(test.samples, start=1)
            if has_content(sample.rig, sample.cycles,
                           sample.result or sample.failure_mode)]


def _rig_label(test: FatigueTest, numero: int, sample, detenidas: dict) -> str:
    """Que dice la celda del banco.

    El orden de las preguntas es el del reporte original y el de los chips: el
    mantenimiento primero, porque la pieza parada tiene el banco vacio y por
    eso tambien cumple la condicion de suspendida. Al reves, una pieza que
    saco el mantenimiento se leeria como una que retiro el laboratorio.
    """
    if (test.id, numero) in detenidas:
        return MAINTENANCE_LABEL
    if not test.is_finished and sample.is_suspended:
        return SUSPENDED_LABEL
    return "" if sample.rig == EMPTY_RIG else (sample.rig or "")


def export_fatigue_ongoing_compact(
    tests: list[FatigueTest],
    rig_colors: dict[str, str],
    destination: str | Path,
    paused: dict[tuple[int, int], object] | None = None,
) -> Path:
    """Genera el archivo y devuelve su ruta.

    Misma firma que ``export_fatigue_ongoing``: ``paused`` son las piezas
    detenidas por el mantenimiento de su banco, con la clave ``(id de prueba,
    numero de pieza)`` que usa la tabla.
    """
    detenidas = paused or {}
    headers = build_headers()
    ancho = len(headers)

    workbook, sheet = _new_sheet(
        "Fatigas en curso",
        f"Pruebas de fatiga en curso  -  {dates.display(date.today())}",
        headers,
    )

    columna_rig = headers.index("Test Rig") + 1
    columna_ciclos = headers.index("Ciclos") + 1
    columna_total = headers.index("Total ciclos") + 1

    for test in tests:
        base = [test.id, test.test_batch, test.customer, test.requester or "",
                dates.display(test.start_date), test.qty_samples,
                _comments(test.comments)]
        cola = [test.total_cycles, "Si" if test.wo_status else "No"]
        relleno = None if test.wo_status else NO_WO_FILL

        ranuras = used_slots(test)
        primera = ultima = 0

        # Una prueba recien abierta no tiene ninguna pieza capturada. Aun asi
        # escribe su fila, con las columnas de pieza en blanco: si no, la
        # prueba desapareceria del reporte y nadie sabria que existe.
        for posicion, numero in enumerate(ranuras or [None]):
            if numero is None:
                muestra = ["", "", "", "", ""]
            else:
                sample = test.samples[numero - 1]
                muestra = [
                    numero,
                    _rig_label(test, numero, sample, detenidas),
                    sample.result or "",
                    sample.cycles if sample.cycles is not None else "",
                    sample.failure_mode or "",
                ]

            fila = _append_row(sheet, base + muestra + cola, ancho,
                               fill=relleno)
            if not posicion:
                primera = fila
            ultima = fila

            celda = sheet.cell(row=fila, column=columna_rig)
            valor = str(celda.value or "")
            if rig_colors.get(valor):
                # El color del banco va encima del resaltado de "sin WO": es
                # el dato mas concreto de la fila.
                _paint_rig(celda, rig_colors)
            elif valor == SUSPENDED_LABEL:
                celda.fill = SUSPENDED_FILL
                celda.font = SUSPENDED_FONT
            elif valor == MAINTENANCE_LABEL:
                celda.fill = MAINTENANCE_FILL
                celda.font = MAINTENANCE_FONT

            for columna in (columna_ciclos, columna_total):
                sheet.cell(row=fila, column=columna).number_format = (
                    CYCLES_FORMAT)

        if MERGE_TEST_ROWS and ultima > primera:
            _merge_test(sheet, headers, primera, ultima)

    total_row = _totals(sheet, headers, {
        "Piezas": sum(t.qty_samples for t in tests),
        # El mismo numero por dos caminos. Si dejaran de coincidir seria que
        # alguna pieza no llego a la hoja, y se ve sin abrir nada mas.
        "Ciclos": sum(t.total_cycles for t in tests),
        "Total ciclos": sum(t.total_cycles for t in tests),
    })
    for columna in (columna_ciclos, columna_total):
        sheet.cell(row=total_row, column=columna).number_format = CYCLES_FORMAT

    _notes(sheet, tests, detenidas, total_row, len(BASE_HEADERS))

    # Congela el encabezado y las tres columnas de identificacion, como los
    # otros seis reportes.
    return _save(workbook, sheet, headers, destination,
                 {**COLUMN_WIDTHS, **EXTRA_WIDTHS}, "D3", total_row - 1)


def _merge_test(sheet, headers: list[str], primera: int, ultima: int) -> None:
    """Combina las columnas de la prueba sobre las filas de sus piezas."""
    columnas = [headers.index(nombre) + 1
                for nombre in BASE_HEADERS + TAIL_HEADERS]
    for columna in columnas:
        sheet.merge_cells(start_row=primera, start_column=columna,
                          end_row=ultima, end_column=columna)


def _notes(sheet, tests: list[FatigueTest], detenidas: dict,
           total_row: int, ancho_nota: int) -> None:
    """Las notas al pie, solo si hacen falta.

    Un color sin explicacion en una hoja impresa se queda sin significado en
    cuanto la mira alguien que no estuvo en la captura. Las condiciones son las
    del reporte original, incluido el descuento: una pieza detenida tambien
    esta fuera de banco, asi que sin descontarla saldrian las dos notas por una
    sola pieza.
    """
    hay_detenidas = any((t.id, numero) in detenidas
                        for t in tests for numero in used_slots(t))
    hay_suspendidas = any(
        t.samples[numero - 1].is_suspended and (t.id, numero) not in detenidas
        for t in tests if not t.is_finished
        for numero in used_slots(t))

    notas = []
    if hay_suspendidas:
        notas.append((SUSPENDED_NOTE, SUSPENDED_FILL))
    if hay_detenidas:
        notas.append((MAINTENANCE_NOTE, MAINTENANCE_FILL))

    for posicion, (texto, relleno) in enumerate(notas):
        fila = total_row + 2 + posicion
        sheet.merge_cells(start_row=fila, start_column=1,
                          end_row=fila, end_column=ancho_nota)
        nota = sheet.cell(row=fila, column=1, value=texto)
        nota.fill = relleno
        nota.font = NOTE_FONT
        nota.alignment = NOTE_ALIGNMENT
