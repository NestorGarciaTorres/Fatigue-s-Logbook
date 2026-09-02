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
            "6 digitos + clave de 3 letras + 2 digitos (ejemplo: 242314STF09)."
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
        raise ValidationError("El numero de piezas debe ser un numero.") from None

    if quantity < 1:
        raise ValidationError("El numero de piezas debe ser al menos 1.")


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
