"""Filtrado de registros.

La version anterior filtraba en SQL con ``substr(end_date, 4, 2) = ?`` sobre
fechas guardadas como texto ``dd/MM/yyyy``. Eso solo permitia mes y anio
exactos: un rango de fechas era imposible, porque ese formato no ordena.

Como los volumenes son de cientos de filas, aqui se filtra en Python sobre los
modelos ya convertidos a ``date``. Es correcto y permite cualquier
combinacion. El mismo filtro lo usan las bitacoras y el dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.models import EMPTY_RIG, FatigueTest, GenericTest, RotaryTest

ANY = "Todos"


@dataclass
class TestFilters:
    """Criterios de la barra de filtros. Todos son opcionales."""

    search: str = ""
    customer: str = ANY
    rig: str = ANY
    test_status: str = ANY
    wo_status: str = ANY          # Todos | Si | No
    date_from: date | None = None
    date_to: date | None = None

    def is_empty(self) -> bool:
        return (
            not self.search.strip()
            and self.customer == ANY
            and self.rig == ANY
            and self.test_status == ANY
            and self.wo_status == ANY
            and self.date_from is None
            and self.date_to is None
        )

    def clear(self) -> "TestFilters":
        return TestFilters()


@dataclass
class _Facets:
    """Vista uniforme de cualquier tipo de prueba, para poder filtrar igual."""

    batch: str
    customer: str
    rigs: list[str]
    comments: str
    status: str | None
    wo: bool | None
    primary_date: date | None
    secondary_date: date | None = None
    extra: list[str] = field(default_factory=list)
    # Quien pidio la prueba. Entra en la busqueda: "todo lo de Fulano" es una
    # de las preguntas que se le hacen a la bitacora.
    requester: str = ""


def facets(test) -> _Facets:
    if isinstance(test, FatigueTest):
        return _Facets(
            batch=test.test_batch,
            customer=test.customer,
            requester=test.requester,
            rigs=[s.rig for s in test.samples if s.rig and s.rig != EMPTY_RIG],
            comments=test.comments,
            status=test.test_status,
            wo=test.wo_status,
            # Las finalizadas se filtran por fecha de cierre, las abiertas por
            # su fecha de inicio. Es lo que mostraba cada pantalla.
            primary_date=test.end_date or test.start_date,
            secondary_date=test.start_date,
            extra=(
                [s.result for s in test.samples if s.result]
                + [s.failure_mode for s in test.samples if s.failure_mode]
            ),
        )

    if isinstance(test, RotaryTest):
        return _Facets(
            batch=test.test_batch,
            customer=test.customer,
            requester=test.requester,
            rigs=[test.test_rig] if test.test_rig != EMPTY_RIG else [],
            comments=test.comments,
            status=test.test_status,
            wo=None,
            primary_date=test.end_date or test.start_date,
            secondary_date=test.start_date,
            extra=(
                [s.status for s in test.samples if s.status != EMPTY_RIG]
                + [s.failure_mode for s in test.samples if s.failure_mode]
            ),
        )

    if isinstance(test, GenericTest):
        return _Facets(
            batch=test.test_batch,
            customer=test.customer,
            requester=test.requester,
            rigs=[test.test_rig] if test.test_rig != EMPTY_RIG else [],
            comments=test.comments,
            status=None,
            wo=None,
            primary_date=test.test_date,
        )

    raise TypeError(f"Tipo de prueba no soportado: {type(test)!r}")


def matches(test, filters: TestFilters) -> bool:
    data = facets(test)

    if filters.customer != ANY and data.customer != filters.customer:
        return False

    if filters.rig != ANY and filters.rig not in data.rigs:
        return False

    if filters.test_status != ANY and data.status != filters.test_status:
        return False

    if filters.wo_status != ANY and data.wo is not None:
        wanted = filters.wo_status == "Si"
        if data.wo != wanted:
            return False

    if filters.date_from and (
        data.primary_date is None or data.primary_date < filters.date_from
    ):
        return False

    if filters.date_to and (
        data.primary_date is None or data.primary_date > filters.date_to
    ):
        return False

    if filters.search.strip():
        needle = filters.search.strip().lower()
        haystack = " ".join(
            [data.batch, data.customer, data.requester, data.comments,
             *data.rigs, *data.extra]
        ).lower()
        if needle not in haystack:
            return False

    return True


def apply(tests: list, filters: TestFilters | None) -> list:
    if filters is None or filters.is_empty():
        return list(tests)
    return [t for t in tests if matches(t, filters)]
