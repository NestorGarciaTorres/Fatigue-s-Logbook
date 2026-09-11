"""Migraciones de esquema, versionadas con ``PRAGMA user_version``.

Cada migracion es idempotente: correr el runner dos veces seguidas no cambia
nada la segunda vez. Ninguna borra datos de las tablas de pruebas.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date

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


# --------------------------------------------------------------------------
# 009 - Orden de prioridad de las Work Orders
# --------------------------------------------------------------------------

def _migration_009_work_order_priority(conn: sqlite3.Connection) -> None:
    """Da a cada Work Order un lugar en la fila.

    Hasta aqui la lista se ordenaba por fecha de captura, que no dice nada de
    urgencia: la orden que hay que correr manana puede haberse capturado
    despues de tres que pueden esperar. ``priority`` es un entero donde el
    numero mas bajo va primero.

    A las ordenes que ya existen se les reparte por antiguedad, que es el orden
    en que se venian mostrando: nadie ve un cambio al abrir la app, y a partir
    de ahi se reacomodan a mano.
    """
    if not _has_column(conn, "work_orders", "priority"):
        log.info("Agregando work_orders.priority")
        conn.execute("ALTER TABLE work_orders ADD COLUMN priority INTEGER")

    # Se numeran solo las que no tengan valor: si la migracion se repite, las
    # prioridades que el usuario ya haya acomodado se quedan como estan.
    pendientes = [
        row[0] for row in conn.execute(
            "SELECT id FROM work_orders WHERE priority IS NULL ORDER BY id"
        )
    ]
    if not pendientes:
        return

    base = conn.execute(
        "SELECT COALESCE(MAX(priority), 0) FROM work_orders"
    ).fetchone()[0]
    conn.executemany(
        "UPDATE work_orders SET priority = ? WHERE id = ?",
        [(base + n, wo_id) for n, wo_id in enumerate(pendientes, start=1)],
    )
    log.info("Prioridad asignada a %s work orders", len(pendientes))


# --------------------------------------------------------------------------
# 010 - Repartir los colores de rig sin choques ni repetidos
# --------------------------------------------------------------------------

# Copia congelada de la paleta y de los colores reservados de la interfaz, tal
# como estaban el 02/09/2026. Una migracion no depende de codigo vivo: si
# manana se retoca el tema o la paleta, esta migracion ya aplicada tiene que
# seguir dando el mismo resultado sobre una base nueva.
_M010_PALETTE = (
    "#FAAA82", "#CCAD8F", "#FAE6AF", "#CCC26A",
    "#FAF173", "#E2FAA0", "#A4DB65", "#9DCC8F",
    "#73FA73", "#8FCCB8", "#73FAD6", "#6CDAEB",
    "#A0ACFA", "#DAA4EB", "#EC91FA", "#FAAFCF",
)

# Colores que la interfaz usa para otra cosa. Un rig no puede llevarlos: el
# primero de la paleta vieja era PRIMARY, el azul de la seleccion y del
# encabezado, asi que ese chip desaparecia al seleccionar la fila.
_M010_RESERVED = (
    "#5DADE2",  # PRIMARY
    "#6EC6FF",  # INFO
    "#58D68D",  # SUCCESS, semaforo de dias
    "#F0AD4E",  # WARNING
    "#F08080",  # DANGER
    "#2C3E70",  # SELECTION
    "#2B3E50",  # BACKGROUND
    "#34495E",  # ROW
    "#43617E",  # ROW_ALT
    "#223343",  # HEADER_BG
)

# Los tres fondos que puede tener una fila. Un chip tiene que leerse en
# cualquiera de ellos, no solo en la fila normal: la primera version de esta
# paleta se probo contra la fila y la seleccion, y al aclarar la franja
# alterna nueve de dieciseis colores se quedaron por debajo del minimo justo
# en esa franja.
_M010_ROW_BACKGROUNDS = ("#34495E", "#43617E", "#2C3E70")
_M010_MIN_CONTRAST = 3.0

# Distancia minima en Lab contra un color reservado. Por debajo de esto el
# chip se confunde con el fondo sobre el que se pinta.
_M010_MIN_DISTANCE = 24.0

# Y separacion minima entre dos rigs. Que cada color sea unico no basta:
# #BB8FCE y #C39BD3 son dos entradas distintas de la paleta vieja y estan a
# dE 5.8, o sea que a la vista son el mismo morado. Si dos bancos no se
# distinguen, colorear por banco no sirve de nada.
_M010_MIN_SEPARATION = 18.0


def _m010_lab(color: str) -> tuple[float, float, float]:
    """sRGB a CIELab. Comparar en RGB miente: #60DB60 y #53BD9D distan poco
    en numeros y mucho a la vista."""
    value = color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(value[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def pivot(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = pivot(x), pivot(y), pivot(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _m010_distance(one: str, other: str) -> float:
    a, b = _m010_lab(one), _m010_lab(other)
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _m010_luminance(color: str) -> float:
    value = color.lstrip("#")
    total = 0.0
    for channel, weight in zip((0, 2, 4), (0.2126, 0.7152, 0.0722)):
        c = int(value[channel:channel + 2], 16) / 255
        total += weight * (
            c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        )
    return total


def _m010_contrast(one: str, other: str) -> float:
    a, b = _m010_luminance(one), _m010_luminance(other)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _m010_is_usable(color: str, taken: list[str]) -> bool:
    """Si un color sirve: lejos de la interfaz y lejos de los otros rigs."""
    if not color or not color.startswith("#") or len(color) != 7:
        return False
    try:
        if any(
            _m010_distance(color, reserved) < _M010_MIN_DISTANCE
            for reserved in _M010_RESERVED
        ):
            return False
        # Legible sobre la fila normal, sobre la franja alterna y sobre la
        # seleccion. Varios colores heredados pasaban la prueba de distancia y
        # aun asi se leian mal encima de una fila.
        if any(
            _m010_contrast(color, fondo) < _M010_MIN_CONTRAST
            for fondo in _M010_ROW_BACKGROUNDS
        ):
            return False
        return all(
            _m010_distance(color, other) >= _M010_MIN_SEPARATION
            for other in taken
        )
    except ValueError:
        return False


def _migration_010_rig_colors(conn: sqlite3.Connection) -> None:
    """Le da a cada rig un color propio que no choque con la interfaz.

    La paleta anterior tenia diez colores para dieciseis bancos, todos azules
    o morados sobre un fondo azul oscuro. El resultado, medido: cinco parejas
    de rigs compartiendo color --el chip dejaba de identificar el banco-- y
    los once colores distintos por debajo de 3:1 de contraste contra la fila
    seleccionada, dos de ellos identicos a ella.

    Se conserva el color de un rig cuando sigue siendo valido: unico entre los
    rigs y suficientemente lejos de los colores de la interfaz. Solo se
    reasigna lo que choca o esta repetido, para no borrar una eleccion hecha a
    mano desde Ajustes. Por eso tambien es idempotente: en la segunda pasada
    todos los colores ya son validos y no se toca ninguno.
    """
    rigs = list(conn.execute("SELECT id, name, color FROM rigs ORDER BY id"))
    if not rigs:
        return

    taken: list[str] = []
    keep: dict[int, str] = {}
    for row in rigs:
        color = (row["color"] or "").upper()
        if _m010_is_usable(color, taken):
            taken.append(color)
            keep[row["id"]] = color

    cambios = []
    for row in rigs:
        if row["id"] in keep:
            continue

        libres = [c for c in _M010_PALETTE if _m010_is_usable(c, taken)]
        if libres:
            nuevo = libres[0]
        else:
            # Mas rigs que colores separables: se recicla el que quede mas
            # lejos de lo ya usado, que es lo menos malo posible.
            nuevo = max(
                _M010_PALETTE,
                key=lambda c: min(
                    (_m010_distance(c, t) for t in taken), default=999.0
                ),
            )
        taken.append(nuevo.upper())
        cambios.append((nuevo, row["id"]))

    if not cambios:
        log.info("Colores de rig al dia: no hubo que reasignar ninguno")
        return

    conn.executemany("UPDATE rigs SET color = ? WHERE id = ?", cambios)
    log.info("Colores de rig reasignados: %s de %s", len(cambios), len(rigs))


# --------------------------------------------------------------------------
# 011 - Mantenimiento de rigs
# --------------------------------------------------------------------------

def _migration_011_rig_maintenance(conn: sqlite3.Connection) -> None:
    """Los periodos en que un banco estuvo fuera de servicio.

    Un mantenimiento no es un dato del rig --que este o no este disponible--
    sino un intervalo: empieza, dura y termina. Va en su propia tabla porque
    hay dos preguntas que responder con el, y las dos necesitan las fechas:
    cuanto tiempo estuvo parado el banco, y cuanto de ese tiempo le toco a
    cada prueba que estaba corriendo en el.

    ``rig_maintenance_samples`` apunta de que banco salio cada pieza. Al entrar
    el banco en mantenimiento se vacia su ``test_rigN`` --si no, la pieza
    seguiria contando como ocupante de un banco que no esta trabajando-- y sin
    este apunte no habria manera de devolverla a su sitio al terminar, ni de
    distinguir una pieza parada por mantenimiento de una suspendida por
    cualquier otro motivo.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rig_maintenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rig_id INTEGER REFERENCES rigs(id),
            rig_name TEXT NOT NULL,
            test_type TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE,
            reason TEXT,
            created_by TEXT,
            created_at TEXT
        )
        """
    )
    # El nombre se guarda ademas del id porque es lo que llevan las columnas
    # test_rigN de las pruebas: reponer una pieza es escribir ese texto. Con
    # solo el id, renombrar un rig reescribiria de que banco salio una pieza
    # hace ocho meses.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rig_maintenance_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            maintenance_id INTEGER NOT NULL
                REFERENCES rig_maintenance(id) ON DELETE CASCADE,
            table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            test_batch TEXT,
            slot INTEGER NOT NULL,
            rig_name TEXT NOT NULL,
            restored INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_maintenance_rig "
        "ON rig_maintenance(rig_name, test_type)",
        # Las consultas de la app preguntan casi siempre por los abiertos, y un
        # mantenimiento abierto es el que no tiene fecha de fin.
        "CREATE INDEX IF NOT EXISTS idx_maintenance_open "
        "ON rig_maintenance(end_date)",
        "CREATE INDEX IF NOT EXISTS idx_maintenance_samples "
        "ON rig_maintenance_samples(maintenance_id)",
        "CREATE INDEX IF NOT EXISTS idx_maintenance_slot "
        "ON rig_maintenance_samples(table_name, record_id, slot)",
    ]
    for statement in statements:
        conn.execute(statement)


# --------------------------------------------------------------------------
# 012 - El solicitante, tambien en el registro de la prueba
# --------------------------------------------------------------------------

# Tabla -> tipo de ensayo, congelado aqui. Una migracion no importa
# TEST_TYPES: si maniana se agrega un tipo, esta migracion tiene que seguir
# describiendo lo que hizo hoy.
_M012_TABLES = {
    "fatigue_tests": "fatigue",
    "rotary_tests": "rotary",
    "torsion_tests": "torsion",
    "quasi_tests": "quasi",
}


def _migration_012_requester(conn: sqlite3.Connection) -> None:
    """Copia el solicitante al registro de la prueba, en las cuatro bitacoras.

    Hasta ahora el requester vivia solo en la Work Order. Para saber quien
    pidio un ensayo habia que ir a la orden, y las pruebas anteriores a Work
    Orders no tienen ninguna a la que ir. El registro es lo que se consulta
    durante anios, asi que el dato va tambien ahi.

    Se rellena lo que se puede saber: las pruebas que nacieron de una orden lo
    copian de ella. El cruce lleva ``test_type`` a proposito --
    ``started_test_id`` es el id dentro de *su* bitacora, asi que sin filtrar
    por tipo una orden de fatiga con id 5 le pondria su solicitante a la
    prueba de torsion numero 5.
    """
    for table, tipo in _M012_TABLES.items():
        if not _has_column(conn, table, "requester"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN requester TEXT")

        # Solo donde esta vacio: una segunda pasada no debe pisar lo que
        # alguien haya corregido a mano en la app.
        conn.execute(
            f"""
            UPDATE {table} SET requester = COALESCE((
                SELECT wo.requester FROM work_orders wo
                 WHERE wo.started_test_id = {table}.id
                   AND wo.test_type = ?
                   AND wo.requester IS NOT NULL
                   AND wo.requester != ''
                 ORDER BY wo.id LIMIT 1
            ), requester)
            WHERE requester IS NULL OR requester = ''
            """,
            (tipo,),
        )


# --------------------------------------------------------------------------
# 013 - Cuando dejo el mantenimiento de retener a cada pieza
# --------------------------------------------------------------------------

# Ranuras por prueba, congelado aqui: una migracion no importa codigo vivo.
_M013_SLOTS = 9


def _migration_013_maintenance_release(conn: sqlite3.Connection) -> None:
    """Fecha en que un mantenimiento dejo de tener detenida a una pieza.

    El apunte sabia de que banco salio la pieza y si volvio a el al cerrar,
    pero no si antes de eso se la llevaron a otro banco para seguir
    probandola. Sin esa fecha la pieza seguia pintandose como detenida --rojo y
    trama-- corriendo ya en otro banco, y a su prueba se le seguian
    descontando dias hasta que el mantenimiento se cerrara.
    """
    if not _has_column(conn, "rig_maintenance_samples", "released_date"):
        conn.execute(
            "ALTER TABLE rig_maintenance_samples ADD COLUMN released_date DATE"
        )

    # Los mantenimientos ya cerrados no se tocan: la fecha solo dice que la
    # pieza se llevo a otro banco antes del cierre, y de los cerrados no hay
    # forma de saberlo. Su fin de periodo ya acota los dias detenida.
    #
    # La pieza de un mantenimiento abierto que ya tiene banco otra vez, en
    # cambio, se la llevaron a otro antes de esta migracion. No hay forma de
    # saber que dia; se toma el de hoy, que es cuando se entera la base. Solo
    # donde este vacio: una segunda pasada no cambia nada.
    hoy = date.today().strftime("%d/%m/%Y")
    for slot in range(1, _M013_SLOTS + 1):
        conn.execute(
            f"""
            UPDATE rig_maintenance_samples
               SET released_date = ?
             WHERE released_date IS NULL
               AND table_name = 'fatigue_tests'
               AND slot = ?
               AND maintenance_id IN (
                   SELECT id FROM rig_maintenance WHERE end_date IS NULL)
               AND EXISTS (
                   SELECT 1 FROM fatigue_tests f
                    WHERE f.id = rig_maintenance_samples.record_id
                      AND f.test_rig{slot} IS NOT NULL
                      AND f.test_rig{slot} NOT IN ('', '--'))
            """,
            (hoy, slot),
        )


MIGRATIONS = (
    (1, "baseline", _migration_001_baseline),
    (2, "catalogs", _migration_002_catalogs),
    (3, "audit", _migration_003_audit),
    (4, "indexes", _migration_004_indexes),
    (5, "rig_colors", _migration_005_rig_colors),
    (6, "failure_modes", _migration_006_failure_modes),
    (7, "work_orders", _migration_007_work_orders),
    (8, "sample_results", _migration_008_sample_results),
    (9, "work_order_priority", _migration_009_work_order_priority),
    (10, "rig_colors_v2", _migration_010_rig_colors),
    (11, "rig_maintenance", _migration_011_rig_maintenance),
    (12, "requester", _migration_012_requester),
    (13, "maintenance_release", _migration_013_maintenance_release),
)

LATEST_VERSION = MIGRATIONS[-1][0]


def current_version(db: Database) -> int:
    row = db.query_one("PRAGMA user_version")
    return int(row[0]) if row else 0


def pending(db: Database) -> list[str]:
    """Que migraciones faltan por aplicar. Se consulta antes de respaldar."""
    version = current_version(db)
    return [f"{n:03d}_{name}" for n, name, _ in MIGRATIONS if n > version]


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
