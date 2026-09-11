"""Reglas de validacion de registros.

Antes vivian duplicadas en ``generic_form.py``, ``edit_fatigue_form.py`` y
``edit_rotary_form.py``, cada copia con su propio mensaje de error. Aqui se
declaran una vez y devuelven texto, sin abrir cuadros de dialogo: quien llama
decide como mostrarlos.
"""

from __future__ import annotations

import re

# 6 digitos + clave de 3 letras + 2 digitos. Ejemplo real: 242314STF09.
# El mensaje original decia "7 digitos"; la expresion siempre pidio 6.
TEST_BATCH_PATTERN = re.compile(r"^(\d{6})([A-Z]{3})(\d{2})$")
TEST_BATCH_LENGTH = 11


class ValidationError(Exception):
    """Error de validacion con mensaje listo para mostrar."""


def normalize_batch(test_batch: str) -> str:
    return (test_batch or "").strip().upper()


def batch_code(test_batch: str) -> str | None:
    """Extrae la clave de tres letras, o None si el formato no cuadra."""
    match = TEST_BATCH_PATTERN.match(normalize_batch(test_batch))
    return match.group(2) if match else None


def validate_test_batch(test_batch: str, valid_codes: list[str]) -> None:
    """Formato y clave. Lanza :class:`ValidationError` con el detalle."""
    value = normalize_batch(test_batch)

    if not value:
        raise ValidationError("El campo Test Batch es obligatorio.")

    match = TEST_BATCH_PATTERN.match(value)
    if not match:
        raise ValidationError(
            "El Test Batch no cumple el formato requerido: "
            "6 dígitos + clave de 3 letras + 2 dígitos (ejemplo: 242314STF09)."
        )

    code = match.group(2)
    if valid_codes and code not in valid_codes:
        options = ", ".join(valid_codes)
        raise ValidationError(
            f"La clave '{code}' no es valida para este tipo de prueba. "
            f"Usa alguna de las siguientes: {options}."
        )


def validate_required(customer: str, qty_samples) -> None:
    if not (customer or "").strip():
        raise ValidationError("El campo Cliente es obligatorio.")

    try:
        quantity = int(qty_samples)
    except (TypeError, ValueError):
        raise ValidationError("El número de piezas debe ser un número.") from None

    if quantity < 1:
        raise ValidationError("El número de piezas debe ser al menos 1.")


def validate_unique_batch(
    test_batch: str, batch_exists: bool, editing: bool = False
) -> None:
    """``batch_exists`` lo resuelve el repositorio, que es quien ve la base."""
    if batch_exists:
        action = "otro registro" if editing else "un registro"
        raise ValidationError(
            f"Ya existe {action} con el Test Batch '{normalize_batch(test_batch)}'."
        )


def validate_dates(start_date, end_date) -> None:
    if start_date and end_date and end_date < start_date:
        raise ValidationError(
            "La fecha de fin no puede ser anterior a la fecha de inicio."
        )


# --------------------------------------------------------------------------
# Completitud para cerrar una prueba
# --------------------------------------------------------------------------

# El unico resultado que deja algo que contar sobre como fallo la pieza.
FAILURE_RESULT = "Falla"


def requires_failure_mode(result: str) -> bool:
    """Si con este resultado hay que declarar ademas el modo de falla.

    Solo cuando la pieza fallo. El catalogo de modos describe *como* fallo, no
    *si* fallo -- eso ya lo dice el resultado -- asi que exigirlo en una pieza
    marcada 'S/Falla' seria pedir que se invente un dato.
    """
    return (result or "").strip().casefold() == FAILURE_RESULT.casefold()


def validate_complete_for_finish(
    general: dict[str, object],
    samples: list[tuple[int, dict[str, object]]],
) -> None:
    """Todo lo que hace falta para dar una prueba por terminada.

    Mientras la prueba corre se guarda con lo que se tenga: una pieza puede
    estar suspendida y sin banco, y los ciclos se van anotando conforme se
    leen. Al cerrarla ya no: el registro pasa a ser historico y se consulta
    durante anios, asi que se pide completo.

    ``general`` es ``{etiqueta: valor}`` de Datos generales y ``samples`` una
    lista de ``(numero de pieza, {etiqueta: valor})`` **hasta la cantidad
    declarada**: las piezas por encima pueden quedar vacias. Quien llama decide
    que campos entran -- de ahi que el modo de falla solo aparezca en las
    piezas que fallaron.

    Se juntan todos los faltantes en un solo mensaje. Pedirlos de uno en uno
    obliga a cerrar el aviso, llenar un campo y volver a chocar con el
    siguiente.
    """
    faltan = missing_for_finish(general, samples)
    if not faltan:
        return

    problems: list[str] = []
    generales = [caption for number, caption in faltan if number is None]
    if generales:
        problems.append("Datos generales: " + ", ".join(generales))

    por_pieza: dict[int, list[str]] = {}
    for number, caption in faltan:
        if number is not None:
            por_pieza.setdefault(number, []).append(caption)
    for number, captions in por_pieza.items():
        problems.append(f"Pieza {number}: " + ", ".join(captions))

    raise ValidationError(
        "No se puede finalizar la prueba: faltan datos por capturar.\n\n"
        + "\n".join(problems)
        + "\n\nLas piezas por encima de la cantidad declarada pueden quedar "
          "vacias."
    )


def missing_for_finish(
    general: dict[str, object],
    samples: list[tuple[int, dict[str, object]]],
) -> list[tuple[int | None, str]]:
    """Cada dato que falta para cerrar: ``(None o numero de pieza, etiqueta)``.

    La misma regla que :func:`validate_complete_for_finish`, pero dato por
    dato: el formulario marca cada campo que falta sobre el propio campo, y
    para eso necesita saber cual es, no solo leer el mensaje.
    """
    faltan: list[tuple[int | None, str]] = [
        (None, caption) for caption, value in general.items() if _blank(value)
    ]
    for number, fields in samples:
        faltan += [(number, caption)
                   for caption, value in fields.items() if _blank(value)]
    return faltan


def _blank(value) -> bool:
    """Vacio de verdad. El cero no lo es: una pieza puede fallar sin un ciclo."""
    if value is None:
        return True
    return not str(value).strip()
