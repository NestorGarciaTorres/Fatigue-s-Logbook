"""Que hay en cada banco y cuanto ha sacado cada banco.

Dos preguntas parecidas que se responden distinto:

- **Ocupacion**: que pruebas *en curso* estan corriendo ahora en cada banco.
- **Piezas terminadas**: cuantas piezas acabaron en cada banco, contando solo
  pruebas ya cerradas. Es el trabajo hecho, no lo que hay puesto.

Viven aqui y no en las paginas porque las dos pantallas que las usan --la de
ocupacion de rigs y el dashboard-- las calculaban por separado y no daban lo
mismo: la primera contaba Fatiga y Rotary cruzando por (nombre, tipo), y la
tarjeta del dashboard solo Fatiga y cruzando por nombre. Una decia 11 bancos
ocupados y la otra 10.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from app.models import FINISHED, GenericTest, Rig, is_blank

# La clave de un banco es (nombre, tipo de ensayo) y nunca solo el nombre: hay
# un I-25 en Torsion, otro en Quasi y otro en Rotary. Cruzando por nombre, una
# prueba de Rotary ocupaba los tres.
RigKey = tuple[str, str]


def catalog_keys(rigs: list[Rig]) -> set[RigKey]:
    return {(rig.name, rig.test_type) for rig in rigs}


def occupancy(
    fatigue_ongoing: list, rotary_ongoing: list, catalog: set[RigKey]
) -> tuple[dict[RigKey, list], dict[str, int]]:
    """Que prueba en curso ocupa cada banco, y que nombres no estan en el catalogo.

    En Fatiga el banco es de cada pieza, asi que una prueba puede ocupar varios
    bancos; se lista una sola vez por banco aunque la use en varias piezas. En
    Rotary el banco es de la prueba entera.
    """
    ocupados: dict[RigKey, list] = defaultdict(list)
    fuera_de_catalogo: dict[str, int] = defaultdict(int)

    for test in fatigue_ongoing:
        vistos: set[RigKey] = set()
        for sample in test.samples:
            if is_blank(sample.rig):
                continue
            key = (sample.rig, "fatigue")
            if key not in catalog:
                fuera_de_catalogo[sample.rig] += 1
                continue
            if key in vistos:
                continue
            vistos.add(key)
            ocupados[key].append(test)

    for test in rotary_ongoing:
        if is_blank(test.test_rig):
            continue
        key = (test.test_rig, "rotary")
        if key not in catalog:
            fuera_de_catalogo[test.test_rig] += 1
            continue
        ocupados[key].append(test)

    return ocupados, fuera_de_catalogo


@dataclass(frozen=True)
class FinishedPieces:
    """Piezas terminadas por banco, y cuantas se pudieron atribuir.

    ``attributed`` y ``total`` no sobran: en Fatiga, casi todo lo anterior a
    2026 tiene resultado pero no banco --el formulario viejo ofrecia los
    resultados dentro del desplegable de Test Rig, y la migracion 008 dejo el
    banco vacio al separarlos--. Sin ese par, la grafica se leeria como
    'estos bancos no han hecho nada'.
    """

    by_rig: dict[RigKey, int]
    attributed: int
    total: int

    @property
    def coverage(self) -> float:
        return self.attributed / self.total if self.total else 0.0


def _fatigue_used(sample) -> bool:
    """Ranura de fatiga que se uso: la que tiene algo anotado."""
    return bool(sample.cycles or sample.result or sample.failure_mode
                or not is_blank(sample.rig))


def finished_pieces(
    fatigue: list, rotary: list, generic: dict[str, list[GenericTest]]
) -> FinishedPieces:
    """Cuantas piezas acabaron en cada banco, solo de pruebas finalizadas.

    Torsion y Quasi no llevan estatus: lo que esta registrado esta hecho, y sus
    piezas van todas al banco de la prueba porque no se anota banco por pieza.
    """
    conteo: dict[RigKey, int] = defaultdict(int)
    atribuidas = 0
    total = 0

    for test in fatigue:
        if test.test_status != FINISHED:
            continue
        for sample in test.samples:
            if not _fatigue_used(sample):
                continue
            total += 1
            if not is_blank(sample.rig):
                conteo[(sample.rig, "fatigue")] += 1
                atribuidas += 1

    for test in rotary:
        if test.test_status != FINISHED:
            continue
        piezas = sum(1 for s in test.samples
                     if s.revs or not is_blank(s.status))
        total += piezas
        if not is_blank(test.test_rig):
            conteo[(test.test_rig, "rotary")] += piezas
            atribuidas += piezas

    for tipo, registros in generic.items():
        for test in registros:
            piezas = test.qty_samples or 0
            total += piezas
            if not is_blank(test.test_rig):
                conteo[(test.test_rig, tipo)] += piezas
                atribuidas += piezas

    return FinishedPieces(dict(conteo), atribuidas, total)


def last_used(
    fatigue: list, rotary: list, generic: dict[str, list[GenericTest]]
) -> dict[RigKey, date]:
    """Cuando acabo la ultima prueba que corrio en cada banco.

    Es la otra mitad de "que banco esta libre": uno que se desocupo ayer y otro
    que lleva dos meses parado se ven igual en la pantalla y no significan lo
    mismo.

    Se toma la fecha de **cierre**, no la de inicio: es cuando el banco quedo
    disponible. Torsion y Quasi no llevan estatus, asi que su fecha de prueba
    es a la vez el principio y el final.
    """
    ultimo: dict[RigKey, date] = {}

    def anotar(key: RigKey, cuando: date | None) -> None:
        if cuando is None:
            return
        previo = ultimo.get(key)
        if previo is None or cuando > previo:
            ultimo[key] = cuando

    for test in fatigue:
        if test.test_status != FINISHED:
            continue
        for sample in test.samples:
            if not is_blank(sample.rig):
                anotar((sample.rig, "fatigue"),
                       test.end_date or test.start_date)

    for test in rotary:
        if test.test_status != FINISHED or is_blank(test.test_rig):
            continue
        anotar((test.test_rig, "rotary"), test.end_date or test.start_date)

    for tipo, registros in generic.items():
        for test in registros:
            if not is_blank(test.test_rig):
                anotar((test.test_rig, tipo), test.test_date)

    return ultimo
