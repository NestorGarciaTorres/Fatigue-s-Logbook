"""Antiguedad de las pruebas en curso.

La pregunta operativa de un laboratorio de fatiga es *que lleva demasiado
tiempo corriendo*, y hasta ahora no se podia responder: una prueba de ayer y
una de hace ocho meses se veian igual en la bitacora.

Los umbrales no estan escritos a mano: se calculan del historial de pruebas ya
cerradas de cada tipo de ensayo, asi que se ajustan solos si cambia el ritmo
del laboratorio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

OK = "ok"
WARNING = "warning"
CRITICAL = "critical"

# Respaldo cuando no hay historial suficiente. Salen de las pruebas de fatiga
# ya cerradas de esta base: p75 = 12 dias, p95 = 29.
DEFAULT_WARNING = 12
DEFAULT_CRITICAL = 30

# Por debajo de esto la muestra es demasiado chica para inferir nada.
MINIMUM_SAMPLE = 20


def _percentile(ordered: list[int], percent: float) -> int:
    if not ordered:
        return 0
    index = min(len(ordered) - 1, int(len(ordered) * percent / 100))
    return ordered[index]


@dataclass(frozen=True)
class DurationThresholds:
    """A partir de cuantos dias una prueba en curso llama la atencion."""

    warning: int = DEFAULT_WARNING
    critical: int = DEFAULT_CRITICAL
    calibrated: bool = False

    @classmethod
    def from_history(cls, durations: list[int]) -> "DurationThresholds":
        """p75 y p95 de las pruebas ya cerradas."""
        usable = sorted(d for d in durations if d is not None and d >= 0)
        if len(usable) < MINIMUM_SAMPLE:
            return cls()

        warning = max(1, _percentile(usable, 75))
        critical = max(warning + 1, _percentile(usable, 95))
        return cls(warning=warning, critical=critical, calibrated=True)

    def level(self, days: int | None) -> str:
        if days is None:
            return OK
        if days >= self.critical:
            return CRITICAL
        if days > self.warning:
            return WARNING
        return OK

    def describe(self) -> str:
        origin = "historial" if self.calibrated else "valores por omision"
        return (
            f"Días en curso: hasta {self.warning} normal, "
            f"{self.warning + 1} a {self.critical - 1} atencion, "
            f"{self.critical} o mas revisar  ({origin})"
        )


def days_running(
    start: date | None, reference: date | None = None, stopped: int = 0
) -> int | None:
    """Dias en curso descontando lo que estuvo detenida. None sin fecha.

    ``stopped`` son los dias que la prueba paso parada por mantenimiento de
    algun banco (lo calcula ``app.services.maintenance``). Se descuenta porque
    lo que mide el semaforo es tiempo de ensayo: una prueba que lleva 40 dias
    de los que 12 fueron mantenimiento no lleva mas ensayo que una de 28, y
    ponerla en rojo culpa a la prueba de un paro que no es suyo.
    """
    if start is None:
        return None
    today = reference or date.today()
    return max(0, (today - start).days - max(0, stopped))


def elapsed(
    start: date | None, end: date | None, stopped: int = 0
) -> int | None:
    """Duracion de una prueba ya cerrada, tambien sin el tiempo detenido."""
    if start is None or end is None:
        return None
    return max(0, (end - start).days - max(0, stopped))


def history_durations(tests, stopped: dict[int, int] | None = None) -> list[int]:
    """Duraciones de las pruebas cerradas, para calibrar los umbrales.

    Con el mismo descuento que la columna de dias: los umbrales se comparan
    contra ese numero, asi que tienen que salir de la misma medida. Calibrar
    con duraciones de calendario y medir en dias efectivos daria un semaforo
    sistematicamente optimista.
    """
    detenidas = stopped or {}
    values = []
    for test in tests:
        days = elapsed(test.start_date, test.end_date,
                       detenidas.get(test.id, 0))
        if days is not None and days >= 0:
            values.append(days)
    return values
