"""Modelos de dominio.

Sustituyen a las tuplas indexadas por posicion que se pasaban entre las
ventanas y los formularios de la version en Tkinter. Ahi un cambio en el
``SELECT`` obligaba a recalcular los offsets a mano en cada formulario.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

# Numero de muestras por prueba. Es fijo en el esquema: las tablas tienen
# columnas 1..9 en lugar de una tabla hija.
SAMPLE_SLOTS = 9

ONGOING = "Ongoing"
FINISHED = "Finished"
TEST_STATUSES = (ONGOING, FINISHED)

EMPTY_RIG = "--"

# El resultado de pieza que significa 'suspendida'. Sale del catalogo de
# sample_statuses, pero se nombra aqui porque cambia como se lee una pieza:
# es el unico resultado que no cierra nada.
SUSPENDED_RESULT = "Susp"


def is_blank(value: str | None) -> bool:
    """Si un campo de banco o de estatus esta vacio.

    Tres cosas significan lo mismo y hay que comprobar las tres: ``None`` en
    los registros nuevos, ``""`` desde que el campo se puede vaciar a
    proposito, y ``"--"`` en las columnas viejas, que no guardaban nulos.
    """
    return not value or value == EMPTY_RIG

# Estados de una Work Order. La WO no desaparece al comenzar la prueba: queda
# marcada y enlazada al registro que la origino.
WO_PENDING = "Pendiente"
WO_STARTED = "Comenzada"
WO_STATUSES = (WO_PENDING, WO_STARTED)


# --------------------------------------------------------------------------
# Catalogos
# --------------------------------------------------------------------------

@dataclass
class Customer:
    name: str
    id: int | None = None
    active: bool = True


@dataclass
class Rig:
    """Banco de pruebas. ``color`` es el identificador visual configurable."""

    name: str
    test_type: str
    color: str = "#5DADE2"
    id: int | None = None
    active: bool = True


@dataclass
class TestCode:
    """Clave de tres letras que valida el ``test_batch`` (STF, SRF, ...)."""

    code: str
    test_type: str
    id: int | None = None


@dataclass
class SampleStatus:
    """Resultado de una muestra de Rotary: Falla / Susp / S/Falla."""

    label: str
    id: int | None = None


@dataclass
class Requester:
    """Persona que solicita una prueba. Sale del catalogo de Ajustes."""

    name: str
    id: int | None = None
    active: bool = True


@dataclass
class FailureMode:
    """Modo de falla de una muestra: como fallo, no si fallo.

    Es un catalogo editable desde Ajustes, igual que clientes y rigs. Nace
    vacio de significado a proposito: los modos los define el laboratorio.
    """

    label: str
    id: int | None = None
    active: bool = True


# --------------------------------------------------------------------------
# Pruebas
# --------------------------------------------------------------------------

@dataclass
class FatigueSample:
    """Una pieza: donde corrio, cuanto aguanto, como acabo y por que.

    ``rig`` y ``result`` vivian en la misma columna hasta la migracion 008: el
    formulario anterior ofrecia los resultados dentro del desplegable de banco
    y el equipo anoto ahi si la pieza fallo. Ahora son campos distintos.
    """

    rig: str = EMPTY_RIG
    result: str = ""
    cycles: int | None = None
    # Columna nueva, sin historia detras: se guarda NULL cuando no se captura,
    # en lugar del "--" que arrastran las columnas viejas.
    failure_mode: str = ""

    @property
    def is_suspended(self) -> bool:
        """Pieza que corrio y hoy no esta en ningun banco.

        Se reconoce por lo que falta y lo que sobra: hay ciclos acumulados y no
        hay banco. Ese es el rastro que deja vaciar el Test Rig de una pieza que
        ya estaba corriendo.

        El resultado la descarta salvo que sea ``Susp``. Una pieza que fallo o
        que aguanto termino, y no espera volver al banco; una marcada como
        suspendida, por definicion, no esta corriendo en ninguno -- y asi es
        como se captura en la practica: se vacia el banco y se anota 'Susp'.
        Sin ciclos tampoco cuenta: eso es una ranura que nadie ha usado.
        """
        if not self.cycles or not is_blank(self.rig):
            return False
        return (not self.result
                or self.result.strip().casefold()
                == SUSPENDED_RESULT.casefold())


@dataclass
class FatigueTest:
    test_batch: str = ""
    customer: str = ""
    start_date: date | None = None
    end_date: date | None = None
    qty_samples: int = 1
    comments: str = "--"
    wo_status: bool = True
    test_status: str = ONGOING
    samples: list[FatigueSample] = field(
        default_factory=lambda: [FatigueSample() for _ in range(SAMPLE_SLOTS)]
    )
    id: int | None = None

    @property
    def total_cycles(self) -> int:
        return sum(s.cycles or 0 for s in self.samples)

    @property
    def is_finished(self) -> bool:
        return self.test_status == FINISHED


@dataclass
class RotarySample:
    revs: int | None = None
    status: str = EMPTY_RIG
    failure_mode: str = ""

    @property
    def is_running(self) -> bool:
        """Pieza con revoluciones y sin estatus: corrio y no ha concluido."""
        return bool(self.revs) and is_blank(self.status)


@dataclass
class RotaryTest:
    test_batch: str = ""
    customer: str = ""
    start_date: date | None = None
    end_date: date | None = None
    qty_samples: int = 1
    comments: str = "--"
    test_rig: str = EMPTY_RIG
    test_status: str = ONGOING
    samples: list[RotarySample] = field(
        default_factory=lambda: [RotarySample() for _ in range(SAMPLE_SLOTS)]
    )
    id: int | None = None

    @property
    def total_revs(self) -> int:
        return sum(s.revs or 0 for s in self.samples)

    @property
    def is_finished(self) -> bool:
        return self.test_status == FINISHED

    @property
    def is_suspended(self) -> bool:
        """Prueba fuera de banco: sigue abierta y su Rotary Rig quedo vacio.

        En Rotary el banco es de la prueba, no de la pieza, asi que al vaciarlo
        se suspenden todas las piezas que todavia estaban corriendo.

        Hace falta que haya alguna corriendo: una prueba recien capturada, sin
        banco y sin revoluciones, no esta suspendida sino a medio llenar.
        """
        return (
            not self.is_finished
            and is_blank(self.test_rig)
            and any(s.is_running for s in self.samples)
        )


@dataclass
class GenericTest:
    """Torsion y Quasi comparten forma: una sola fecha y un solo rig."""

    test_batch: str = ""
    customer: str = ""
    test_date: date | None = None
    qty_samples: int = 1
    comments: str = "--"
    test_rig: str = EMPTY_RIG
    id: int | None = None


# --------------------------------------------------------------------------
# Work Orders
# --------------------------------------------------------------------------

@dataclass
class WorkOrder:
    """El documento que autoriza una prueba, antes de que la prueba exista.

    Lo captura quien prepara las ordenes; quien corre la prueba pulsa
    'Comenzar prueba' y el formulario se abre con estos datos ya puestos.
    """

    test_type: str = "fatigue"
    test_batch: str = ""
    customer: str = ""
    qty_samples: int = 1
    requester: str = ""
    comments: str = ""
    status: str = WO_PENDING
    # Lugar en la fila: el numero mas bajo corre primero. No se muestra tal
    # cual -- la pantalla numera 1, 2, 3 segun la posicion -- porque al
    # comenzar o eliminar una orden quedan huecos que no significan nada.
    priority: int = 0
    started_test_id: int | None = None
    created_at: date | None = None
    created_by: str = ""
    id: int | None = None

    @property
    def is_started(self) -> bool:
        return self.status == WO_STARTED

    @property
    def can_start(self) -> bool:
        """Solo Fatiga y Rotary tienen formulario enlazado por ahora."""
        return not self.is_started and self.test_type in STARTABLE_TEST_TYPES


# --------------------------------------------------------------------------
# Auditoria
# --------------------------------------------------------------------------

@dataclass
class AuditEntry:
    table_name: str
    record_id: int
    test_batch: str
    action: str           # created | updated | closed | reopened | deleted
    field: str
    old_value: str | None
    new_value: str | None
    changed_by: str
    machine: str
    changed_at: datetime
    id: int | None = None


# --------------------------------------------------------------------------
# Configuracion por tipo de prueba
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TestTypeConfig:
    """Lo que antes era la lista ``form_config`` de indices magicos.

    En la version anterior se accedia como ``self.table_to_edit[5]`` y una de
    esas entradas apuntaba a una columna de Excel inexistente sin que nadie lo
    notara, porque Rotary no la leia.
    """

    key: str          # fatigue | torsion | rotary | quasi
    table: str        # nombre de la tabla en SQLite
    label: str        # titulo visible
    accent: str       # color de acento de la seccion


FATIGUE = TestTypeConfig("fatigue", "fatigue_tests", "Fatiga", "#5DADE2")
TORSION = TestTypeConfig("torsion", "torsion_tests", "Torsión", "#F0AD4E")
ROTARY = TestTypeConfig("rotary", "rotary_tests", "Rotary", "#F08080")
QUASI = TestTypeConfig("quasi", "quasi_tests", "Quasi", "#6EC6FF")

TEST_TYPES = {c.key: c for c in (FATIGUE, TORSION, ROTARY, QUASI)}

# Lista blanca de tablas. Todo nombre de tabla que se interpole en un SQL debe
# validarse contra esto: antes se concatenaba directo desde la configuracion.
ALLOWED_TABLES = frozenset(c.table for c in TEST_TYPES.values())

# Tipos cuyo formulario se puede abrir desde una Work Order. Torsion y Quasi se
# capturan como WO -- el documento fisico las contempla -- pero de momento su
# bitacora sigue con su propio boton de alta.
STARTABLE_TEST_TYPES = frozenset({"fatigue", "rotary"})
