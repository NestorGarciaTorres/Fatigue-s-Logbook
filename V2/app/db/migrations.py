"""Migraciones de esquema, versionadas con ``PRAGMA user_version``.

Cada migracion es idempotente: correr el runner dos veces seguidas no cambia
nada la segunda vez. Ninguna borra datos de las tablas de pruebas.
"""

from __future__ import annotations

import logging
import sqlite3

from app.db.connection import Database
from app.models import SAMPLE_SLOTS

log = logging.getLogger(__name__)


def _columns(template: str) -> str:
    """Expande una plantilla con ``{i}`` a las 9 ranuras de muestra."""
    return ",\n    ".join(template.format(i=i) for i in range(1, SAMPLE_SLOTS + 1))


# Se calculan aparte porque incrustar una expresion con barra invertida dentro
# de una f-string solo es legal desde Python 3.12, y no vale la pena atar el
# modulo a esa version.
_FATIGUE_SAMPLE_COLUMNS = _columns("test_rig{i} TEXT,\n    cycles{i} INTEGER")
_ROTARY_SAMPLE_COLUMNS = _columns("revs{i} INTEGER,\n    status{i} TEXT")


FATIGUE_DDL = f"""
CREATE TABLE IF NOT EXISTS fatigue_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_batch TEXT NOT NULL,
    customer TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    qty_samples INTEGER NOT NULL,
    comments TEXT,
    {_FATIGUE_SAMPLE_COLUMNS},
    wo_status BOOLEAN NOT NULL,
    test_status TEXT NOT NULL CHECK(test_status IN ('Ongoing', 'Finished'))
)
"""

ROTARY_DDL = f"""
CREATE TABLE IF NOT EXISTS rotary_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_batch TEXT,
    customer TEXT,
    start_date DATE,
    end_date DATE,
    qty_samples INTEGER,
    comments TEXT,
    test_rig TEXT,
    {_ROTARY_SAMPLE_COLUMNS},
    test_status TEXT CHECK(test_status IN ('Ongoing', 'Finished'))
)
"""

GENERIC_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_batch TEXT NOT NULL,
    customer TEXT NOT NULL,
    test_date DATE NOT NULL,
    qty_samples INTEGER NOT NULL,
    comments TEXT,
    test_rig TEXT
)
"""


# --------------------------------------------------------------------------
# 001 - Linea base
# --------------------------------------------------------------------------

def _migration_001_baseline(conn: sqlite3.Connection) -> None:
    """Asegura las cuatro tablas de pruebas y limpia la tabla huerfana.

    ``rotary_tests_new`` quedo de una migracion manual a medias: existe en el
    archivo pero ninguna consulta la referencia.
    """
    conn.execute(FATIGUE_DDL)
    conn.execute(ROTARY_DDL)
    for table in ("torsion_tests", "quasi_tests"):
        conn.execute(GENERIC_DDL.format(table=table))

    row = conn.execute(
        "SELECT COUNT(*) AS n FROM sqlite_master "
        "WHERE type='table' AND name='rotary_tests_new'"
    ).fetchone()
    if row["n"]:
        leftover = conn.execute("SELECT COUNT(*) AS n FROM rotary_tests_new").fetchone()
        log.info("Eliminando rotary_tests_new (%s filas huerfanas)", leftover["n"])
        conn.execute("DROP TABLE rotary_tests_new")


# --------------------------------------------------------------------------
# 002 - Catalogos (reemplazan a Auxiliar.xlsx)
# --------------------------------------------------------------------------

def _migration_002_catalogs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rigs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            test_type TEXT NOT NULL
                CHECK(test_type IN ('fatigue', 'torsion', 'rotary', 'quasi')),
            color TEXT NOT NULL DEFAULT '#5DADE2',
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(name, test_type)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS test_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            test_type TEXT NOT NULL
                CHECK(test_type IN ('fatigue', 'torsion', 'rotary', 'quasi')),
            UNIQUE(code, test_type)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sample_statuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL UNIQUE
        )
        """
    )

    # Los tres estados de muestra de Rotary son fijos y venian del Excel.
    for label in ("Falla", "Susp", "S/Falla"):
        conn.execute(
            "INSERT OR IGNORE INTO sample_statuses (label) VALUES (?)", (label,)
        )


# --------------------------------------------------------------------------
# 003 - Auditoria
# --------------------------------------------------------------------------

def _migration_003_audit(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            test_batch TEXT,
            action TEXT NOT NULL,
            field TEXT,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT NOT NULL,
            machine TEXT,
            changed_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_record "
        "ON audit_log(table_name, record_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_changed_at ON audit_log(changed_at)"
    )


# --------------------------------------------------------------------------
# 004 - Indices de consulta
# --------------------------------------------------------------------------

def _migration_004_indexes(conn: sqlite3.Connection) -> None:
    """Toda consulta de las bitacoras hacia scan completo de tabla."""
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_fatigue_status "
        "ON fatigue_tests(test_status)",
        "CREATE INDEX IF NOT EXISTS idx_fatigue_batch ON fatigue_tests(test_batch)",
        "CREATE INDEX IF NOT EXISTS idx_rotary_status ON rotary_tests(test_status)",
        "CREATE INDEX IF NOT EXISTS idx_rotary_batch ON rotary_tests(test_batch)",
        "CREATE INDEX IF NOT EXISTS idx_torsion_batch ON torsion_tests(test_batch)",
        "CREATE INDEX IF NOT EXISTS idx_quasi_batch ON quasi_tests(test_batch)",
    ]
    for statement in statements:
        conn.execute(statement)


# --------------------------------------------------------------------------
# 005 - Colores de rig que se confunden con los resultados de pieza
# --------------------------------------------------------------------------

# Copia congelada de la paleta y del criterio de choque tal como estaban el
# 01/09/2026, cuando esta migracion corrio sobre la base real. Antes se
# importaban de ``app.services.catalogs``, y eso hacia que una migracion ya
# aplicada cambiara de comportamiento cada vez que se tocaba la paleta: una
# base nueva no habria quedado igual que la real. Una migracion no debe
# depender de codigo vivo.
_M005_PALETTE = (
    "#5DADE2", "#BB8FCE", "#6EC6FF", "#7FB3D5", "#A569BD",
    "#5D6D7E", "#85C1E9", "#C39BD3", "#909497", "#4A69BD",
)
# Los colores que tenian entonces Falla, S/Falla y Susp. Se guardan en hex y el
# tono se calcula: escribir los grados a mano invita a equivocarse.
_M005_STATUS_COLORS = ("#F08080", "#58D68D", "#F0AD4E")
_M005_HUE_TOLERANCE = 30.0
_M005_GREY_SATURATION = 0.25


def _m005_hsv(color: str):
    """(tono en grados, saturacion) o None si el color no es un #RRGGBB."""
    import colorsys

    value = (color or "").lstrip("#")
    if len(value) != 6:
        return None
    try:
        channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return None

    hue, saturation, _ = colorsys.rgb_to_hsv(*channels)
    return hue * 360, saturation


def _m005_clashes(color: str) -> bool:
    """Si ese tono se confundiria con un resultado de pieza."""
    measured = _m005_hsv(color)
    if measured is None:
        return False

    degrees, saturation = measured
    if saturation < _M005_GREY_SATURATION:
        return False       # un gris no se confunde con rojo, verde ni ambar

    for reserved_color in _M005_STATUS_COLORS:
        reserved = _m005_hsv(reserved_color)
        if reserved is None:
            continue
        gap = abs(degrees - reserved[0]) % 360
        if min(gap, 360 - gap) < _M005_HUE_TOLERANCE:
            return True
    return False


def _migration_005_rig_colors(conn: sqlite3.Connection) -> None:
    """Recolorea los rigs cuyo tono chocaba con Falla, S/Falla o Susp.

    La paleta original incluia esos mismos tres colores, y entonces bancos y
    resultados se pintaban igual en el mismo campo: un rig rojo era
    indistinguible de una pieza con falla. Hoy los resultados ya no llevan
    color, pero la migracion se conserva tal cual: cambiarla reescribiria una
    historia que las bases existentes ya aplicaron.
    """
    rows = conn.execute(
        "SELECT id, name, color FROM rigs ORDER BY test_type, name"
    ).fetchall()

    conflicting = [r for r in rows if _m005_clashes(r["color"])]
    if not conflicting:
        return

    # Se respetan los colores que ya estaban bien; solo se reemplazan los que
    # chocan, tomando de la paleta los tonos aun sin usar.
    keep = {r["color"].upper() for r in rows if not _m005_clashes(r["color"])}
    available = [c for c in _M005_PALETTE if c.upper() not in keep]

    for index, row in enumerate(conflicting):
        if available:
            color = available[index % len(available)]
        else:
            color = _M005_PALETTE[index % len(_M005_PALETTE)]
        log.info("Rig %s: %s -> %s", row["name"], row["color"], color)
        conn.execute("UPDATE rigs SET color = ? WHERE id = ?", (color, row["id"]))


# --------------------------------------------------------------------------
# 006 - Modo de falla por muestra
# --------------------------------------------------------------------------

# Semilla de arranque para que el desplegable no nazca vacio. Son genericos a
# proposito: el catalogo se edita en Ajustes -> Modos de falla y se espera que
# el laboratorio los reemplace por su propia nomenclatura.
SEED_FAILURE_MODES = (
    "Fractura",
    "Fisura",
    "Deformacion permanente",
    "Desgaste",
    "Aflojamiento",
    "Fuga",
    "Falla de soldadura",
)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _migration_006_failure_modes(conn: sqlite3.Connection) -> None:
    """Catalogo de modos de falla y una columna por muestra que lo referencia.

    Las columnas se agregan con ALTER TABLE en vez de tocar el DDL de la
    migracion 001: asi la base existente y una recien creada terminan igual, y
    correr esto dos veces no falla.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS failure_modes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    for label in SEED_FAILURE_MODES:
        conn.execute(
            "INSERT OR IGNORE INTO failure_modes (label) VALUES (?)", (label,)
        )

    for table in ("fatigue_tests", "rotary_tests"):
        for i in range(1, SAMPLE_SLOTS + 1):
            column = f"failure_mode{i}"
            if not _has_column(conn, table, column):
                log.info("Agregando %s.%s", table, column)
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")


# --------------------------------------------------------------------------
# 007 - Work Orders y catalogo de solicitantes
# --------------------------------------------------------------------------

def _migration_007_work_orders(conn: sqlite3.Connection) -> None:
    """La orden de trabajo que autoriza una prueba, antes de que exista.

    ``started_test_id`` apunta a la fila de la bitacora que salio de esta WO.
    No se declara como clave foranea porque la tabla destino depende de
    ``test_type``: SQLite no admite una referencia condicional.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS requesters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_type TEXT NOT NULL
                CHECK(test_type IN ('fatigue', 'torsion', 'rotary', 'quasi')),
            test_batch TEXT NOT NULL,
            customer TEXT NOT NULL,
            qty_samples INTEGER NOT NULL,
            requester TEXT NOT NULL,
            comments TEXT,
            status TEXT NOT NULL DEFAULT 'Pendiente'
                CHECK(status IN ('Pendiente', 'Comenzada')),
            started_test_id INTEGER,
            created_at DATE NOT NULL,
            created_by TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_orders_status "
        "ON work_orders(status, test_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_orders_batch "
        "ON work_orders(test_batch)"
    )
    # El catalogo de solicitantes nace vacio a proposito: son personas reales
    # del laboratorio y no hay forma de adivinar sus nombres.


# --------------------------------------------------------------------------
# 008 - Separar el resultado de la pieza del banco en que corrio
# --------------------------------------------------------------------------

# Los tres resultados tal como estaban el 02/09/2026, congelados: si manana se
# agrega un cuarto al catalogo, esta migracion ya aplicada no debe cambiar de
# criterio y mover valores distintos en una base nueva.
_M008_RESULTS = ("Falla", "S/Falla", "Susp")


def _migration_008_sample_results(conn: sqlite3.Connection) -> None:
    """Saca de ``test_rigN`` los resultados de pieza y los pasa a ``resultN``.

    El formulario anterior ofrecia 'Falla', 'S/Falla' y 'Susp' en el
    desplegable de Test Rig -- por el bug de lectura de ``Auxiliar.xlsx``, que
    tomaba las celdas B11:B13 de la columna de rigs como si fueran bancos -- y
    el equipo uso esa columna para anotar si la pieza fallo. En el momento de
    escribir esto la columna guardaba 2 777 resultados contra 45 nombres de
    banco.

    Separarlos permite por fin saber en que banco corrio cada pieza. La
    migracion es idempotente: en la segunda pasada ya no queda ningun resultado
    en ``test_rigN`` y las UPDATE no tocan ninguna fila.
    """
    for i in range(1, SAMPLE_SLOTS + 1):
        column = f"result{i}"
        if not _has_column(conn, "fatigue_tests", column):
            log.info("Agregando fatigue_tests.%s", column)
            conn.execute(f"ALTER TABLE fatigue_tests ADD COLUMN {column} TEXT")

    marcadores = ", ".join("?" for _ in _M008_RESULTS)
    movidos = 0
    for i in range(1, SAMPLE_SLOTS + 1):
        cursor = conn.execute(
            f"UPDATE fatigue_tests "
            f"   SET result{i} = test_rig{i}, test_rig{i} = '--' "
            f" WHERE test_rig{i} IN ({marcadores})",
            _M008_RESULTS,
        )
        movidos += cursor.rowcount

    if movidos:
        log.info("Resultados movidos de test_rigN a resultN: %s", movidos)


MIGRATIONS = (
    (1, "baseline", _migration_001_baseline),
    (2, "catalogs", _migration_002_catalogs),
    (3, "audit", _migration_003_audit),
    (4, "indexes", _migration_004_indexes),
    (5, "rig_colors", _migration_005_rig_colors),
    (6, "failure_modes", _migration_006_failure_modes),
    (7, "work_orders", _migration_007_work_orders),
    (8, "sample_results", _migration_008_sample_results),
)

LATEST_VERSION = MIGRATIONS[-1][0]


def current_version(db: Database) -> int:
    row = db.query_one("PRAGMA user_version")
    return int(row[0]) if row else 0


def migrate(db: Database) -> list[str]:
    """Aplica las migraciones pendientes. Devuelve las que se ejecutaron."""
    version = current_version(db)
    pending = [m for m in MIGRATIONS if m[0] > version]

    if not pending:
        log.info("Esquema al dia (version %s)", version)
        return []

    applied: list[str] = []
    with db.write() as conn:
        for number, name, function in pending:
            log.info("Aplicando migracion %03d_%s", number, name)
            function(conn)
            # user_version no acepta parametros enlazados.
            conn.execute(f"PRAGMA user_version = {number}")
            applied.append(f"{number:03d}_{name}")

    return applied
