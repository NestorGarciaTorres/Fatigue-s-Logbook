"""Repositorios: lo unico del proyecto que habla SQL.

En la version en Tkinter cada ventana y cada formulario armaba sus propias
consultas -- ``fatigue_curr_logbook.py``, ``fatigue_cmplt_logbook.py``,
``edit_fatigue_form.py`` y ``close_fatigue_record.py`` repetian la misma lista
de 26 columnas con variaciones. Aqui se declara una sola vez.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from app import dates
from app.db.connection import Database
from app.models import (
    ALLOWED_TABLES,
    EMPTY_RIG,
    FINISHED,
    ONGOING,
    SAMPLE_SLOTS,
    TEST_TYPES,
    WO_PENDING,
    WO_STARTED,
    AuditEntry,
    Customer,
    FailureMode,
    FatigueSample,
    FatigueTest,
    GenericTest,
    MaintenanceSample,
    Rig,
    RigMaintenance,
    RotarySample,
    RotaryTest,
    Requester,
    SampleStatus,
    TestCode,
    WorkOrder,
    is_blank,
)

_SLOTS = range(1, SAMPLE_SLOTS + 1)

# Que hacer con un campo que dos equipos cambiaron a la vez (ver
# _values_to_save). Van aqui arriba y no con el resto: son el valor por
# omision de los update, y ese se evalua al definir cada clase.
CONFLICT_RAISE = "raise"      # avisar y no guardar nada
KEEP_MINE = "mine"            # queda lo del formulario
KEEP_THEIRS = "theirs"        # queda lo que ya estaba guardado

FATIGUE_COLUMNS = (
    ["id", "test_batch", "customer", "requester", "start_date", "end_date",
     "qty_samples", "comments"]
    + [name for i in _SLOTS
       for name in (f"test_rig{i}", f"result{i}", f"cycles{i}",
                    f"failure_mode{i}")]
    + ["wo_status", "test_status"]
)

ROTARY_COLUMNS = (
    ["id", "test_batch", "customer", "requester", "start_date", "end_date",
     "qty_samples", "comments", "test_rig"]
    + [name for i in _SLOTS
       for name in (f"revs{i}", f"status{i}", f"failure_mode{i}")]
    + ["test_status"]
)

GENERIC_COLUMNS = [
    "id", "test_batch", "customer", "requester", "test_date", "qty_samples",
    "comments", "test_rig",
]


def _select(columns: list[str], table: str) -> str:
    joined = ", ".join(columns)
    return f"SELECT {joined} FROM {table}"


def _checked_table(table: str) -> str:
    """Nombre de tabla listo para interpolar en un SQL.

    Las columnas de banco viven en la tabla de cada bitacora, asi que el nombre
    llega como dato y no escrito en el codigo. Se valida contra la lista blanca
    antes de concatenarlo.
    """
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Tabla no permitida: {table!r}")
    return table


def _rig_column(slot: int) -> str:
    """Columna de banco de una pieza, con el numero validado.

    El numero tambien se interpola: viene del apunte de un mantenimiento, no
    de una constante.
    """
    if not isinstance(slot, int) or not 1 <= slot <= SAMPLE_SLOTS:
        raise ValueError(f"Pieza fuera de rango: {slot!r}")
    return f"test_rig{slot}"


def _release_moved_samples(
    conn: sqlite3.Connection, table: str, record_id: int, samples, when: date,
    moved_on: dict[int, date] | None = None,
) -> None:
    """Libera del mantenimiento las piezas que ya volvieron a tener banco.

    Es la pieza que se lleva a otro banco para seguir probandola mientras el
    suyo sigue en mantenimiento. Desde ese momento no esta detenida: ni su chip
    va en rojo ni a su prueba se le descuentan dias. Solo toca mantenimientos
    abiertos y piezas que el apunte aun retiene.

    ``moved_on`` es el dia que el formulario anoto para cada pieza. Sin el se
    tomaba el de guardar, y el cambio que se capturaba dias despues seguia
    contando esos dias como detenida.
    """
    con_banco = [i for i, s in enumerate(samples, start=1)
                 if not is_blank(s.rig)]
    if not con_banco:
        return

    por_dia: dict[date, list[int]] = {}
    for slot in con_banco:
        por_dia.setdefault((moved_on or {}).get(slot, when), []).append(slot)

    for dia, slots in por_dia.items():
        marcas = ", ".join("?" for _ in slots)
        conn.execute(
            f"UPDATE rig_maintenance_samples SET released_date = ? "
            f"WHERE table_name = ? AND record_id = ? "
            f"AND released_date IS NULL AND restored = 0 "
            f"AND slot IN ({marcas}) "
            f"AND maintenance_id IN "
            f"(SELECT id FROM rig_maintenance WHERE end_date IS NULL)",
            (dates.to_db(dia), table, record_id, *slots),
        )


def _as_int(value) -> int | None:
    """Los ciclos y revoluciones llegan como texto desde los formularios."""
    if value in (None, "", "--"):
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


# ==========================================================================
# Auditoria
# ==========================================================================

class AuditRepository:
    """Escribe el historial de cambios.

    ``record`` recibe la conexion de quien llama para unirse a su transaccion:
    asi el cambio y su registro se confirman o se deshacen juntos.
    """

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def record(conn: sqlite3.Connection, entries: list[AuditEntry]) -> None:
        conn.executemany(
            """
            INSERT INTO audit_log (
                table_name, record_id, test_batch, action, field,
                old_value, new_value, changed_by, machine, changed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    e.table_name, e.record_id, e.test_batch, e.action, e.field,
                    e.old_value, e.new_value, e.changed_by, e.machine,
                    e.changed_at.isoformat(timespec="seconds"),
                )
                for e in entries
            ],
        )

    def for_record(self, table: str, record_id: int) -> list[AuditEntry]:
        rows = self.db.query(
            "SELECT * FROM audit_log WHERE table_name = ? AND record_id = ? "
            "ORDER BY changed_at DESC, id DESC",
            (table, record_id),
        )
        return [self._to_entry(r) for r in rows]

    def last_id(self) -> int:
        """El ultimo apunte del historial: hasta donde se ha visto."""
        row = self.db.query_one("SELECT COALESCE(MAX(id), 0) AS n FROM audit_log")
        return int(row["n"]) if row else 0

    def changes_since(
        self,
        after_id: int,
        exclude_machine: str | None = None,
        tables=None,
        limit: int = 200,
    ) -> list[AuditEntry]:
        """Lo guardado despues de ``after_id``, del mas reciente al mas antiguo.

        Sirve para avisar de que otro equipo cambio algo. Toda alta, edicion,
        cierre o mantenimiento deja aqui su apunte con el equipo que lo hizo,
        asi que basta con preguntar al historial: sin tocar el esquema y sin
        vigilar el archivo, que en un recurso de red cambia tambien con las
        escrituras propias. ``tables`` limita a lo que muestra una pantalla;
        una coleccion vacia no devuelve nada.
        """
        clauses = ["id > ?"]
        params: list = [after_id]
        if exclude_machine:
            clauses.append("(machine IS NULL OR machine != ?)")
            params.append(exclude_machine)
        if tables is not None:
            tables = sorted(tables)
            if not tables:
                return []
            clauses.append(
                f"table_name IN ({', '.join('?' for _ in tables)})"
            )
            params += tables
        sql = ("SELECT * FROM audit_log WHERE " + " AND ".join(clauses)
               + " ORDER BY id DESC LIMIT ?")
        params.append(limit)
        return [self._to_entry(r) for r in self.db.query(sql, tuple(params))]

    def search(
        self,
        changed_by: str | None = None,
        test_batch: str | None = None,
        limit: int = 500,
    ) -> list[AuditEntry]:
        clauses: list[str] = []
        params: list = []
        if changed_by:
            clauses.append("changed_by = ?")
            params.append(changed_by)
        if test_batch:
            clauses.append("test_batch LIKE ?")
            params.append(f"%{test_batch}%")

        sql = "SELECT * FROM audit_log"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY changed_at DESC, id DESC LIMIT ?"
        params.append(limit)

        return [self._to_entry(r) for r in self.db.query(sql, tuple(params))]

    def distinct_users(self) -> list[str]:
        rows = self.db.query(
            "SELECT DISTINCT changed_by FROM audit_log ORDER BY changed_by"
        )
        return [r["changed_by"] for r in rows]

    @staticmethod
    def _to_entry(row: sqlite3.Row) -> AuditEntry:
        return AuditEntry(
            id=row["id"],
            table_name=row["table_name"],
            record_id=row["record_id"],
            test_batch=row["test_batch"],
            action=row["action"],
            field=row["field"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            changed_by=row["changed_by"],
            machine=row["machine"],
            changed_at=datetime.fromisoformat(row["changed_at"]),
        )


# ==========================================================================
# Catalogos
# ==========================================================================

class CatalogRepository:
    """Reemplaza la lectura de ``excel_files/Auxiliar.xlsx``.

    Antes cada validacion abria el Excel completo con pandas, incluso para
    comprobar una sola clave de tres letras.
    """

    def __init__(self, db: Database):
        self.db = db

    # --- clientes --------------------------------------------------------
    def customers(self, active_only: bool = True) -> list[Customer]:
        sql = "SELECT id, name, active FROM customers"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY name"
        return [
            Customer(id=r["id"], name=r["name"], active=bool(r["active"]))
            for r in self.db.query(sql)
        ]

    def customer_names(self) -> list[str]:
        return [c.name for c in self.customers()]

    def save_customer(self, customer: Customer) -> None:
        with self.db.write() as conn:
            if customer.id is None:
                conn.execute(
                    "INSERT INTO customers (name, active) VALUES (?, ?)",
                    (customer.name, int(customer.active)),
                )
            else:
                conn.execute(
                    "UPDATE customers SET name = ?, active = ? WHERE id = ?",
                    (customer.name, int(customer.active), customer.id),
                )

    # --- rigs ------------------------------------------------------------
    def rigs(
        self, test_type: str | None = None, active_only: bool = True
    ) -> list[Rig]:
        clauses: list[str] = []
        params: list = []
        if test_type:
            clauses.append("test_type = ?")
            params.append(test_type)
        if active_only:
            clauses.append("active = 1")

        sql = "SELECT id, name, test_type, color, active FROM rigs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY test_type, name"

        return [
            Rig(
                id=r["id"], name=r["name"], test_type=r["test_type"],
                color=r["color"], active=bool(r["active"]),
            )
            for r in self.db.query(sql, tuple(params))
        ]

    def rig_names(self, test_type: str) -> list[str]:
        return [r.name for r in self.rigs(test_type)]

    def rig_colors(self) -> dict[str, str]:
        """Diccionario ``nombre -> color`` que consumen tabla, grafica y Excel."""
        rows = self.db.query("SELECT name, color FROM rigs")
        return {r["name"]: r["color"] for r in rows}

    def save_rig(self, rig: Rig) -> None:
        with self.db.write() as conn:
            if rig.id is None:
                conn.execute(
                    "INSERT INTO rigs (name, test_type, color, active) "
                    "VALUES (?, ?, ?, ?)",
                    (rig.name, rig.test_type, rig.color, int(rig.active)),
                )
            else:
                conn.execute(
                    "UPDATE rigs SET name = ?, test_type = ?, color = ?, "
                    "active = ? WHERE id = ?",
                    (rig.name, rig.test_type, rig.color, int(rig.active), rig.id),
                )

    def set_rig_color(self, rig_id: int, color: str) -> None:
        with self.db.write() as conn:
            conn.execute("UPDATE rigs SET color = ? WHERE id = ?", (color, rig_id))

    # --- claves de prueba ------------------------------------------------
    def codes(self, test_type: str) -> list[str]:
        rows = self.db.query(
            "SELECT code FROM test_codes WHERE test_type = ? ORDER BY code",
            (test_type,),
        )
        return [r["code"] for r in rows]

    def all_codes(self) -> list[TestCode]:
        rows = self.db.query(
            "SELECT id, code, test_type FROM test_codes ORDER BY test_type, code"
        )
        return [
            TestCode(id=r["id"], code=r["code"], test_type=r["test_type"])
            for r in rows
        ]

    def add_code(self, code: str, test_type: str) -> None:
        with self.db.write() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO test_codes (code, test_type) VALUES (?, ?)",
                (code.upper(), test_type),
            )

    def remove_code(self, code_id: int) -> None:
        with self.db.write() as conn:
            conn.execute("DELETE FROM test_codes WHERE id = ?", (code_id,))

    # --- estados de muestra ----------------------------------------------
    def sample_statuses(self) -> list[SampleStatus]:
        rows = self.db.query("SELECT id, label FROM sample_statuses ORDER BY id")
        return [SampleStatus(id=r["id"], label=r["label"]) for r in rows]

    def status_labels(self) -> list[str]:
        return [s.label for s in self.sample_statuses()]

    # --- modos de falla --------------------------------------------------
    def failure_modes(self, active_only: bool = True) -> list[FailureMode]:
        sql = "SELECT id, label, active FROM failure_modes"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY label"
        return [
            FailureMode(id=r["id"], label=r["label"], active=bool(r["active"]))
            for r in self.db.query(sql)
        ]

    def failure_mode_labels(self) -> list[str]:
        return [m.label for m in self.failure_modes()]

    def save_failure_mode(self, mode: FailureMode) -> None:
        with self.db.write() as conn:
            if mode.id is None:
                conn.execute(
                    "INSERT INTO failure_modes (label, active) VALUES (?, ?)",
                    (mode.label, int(mode.active)),
                )
            else:
                conn.execute(
                    "UPDATE failure_modes SET label = ?, active = ? WHERE id = ?",
                    (mode.label, int(mode.active), mode.id),
                )

    def failure_mode_usage(self, label: str) -> int:
        """Cuantas muestras usan ese modo, para no borrarlo a ciegas."""
        total = 0
        for table in ("fatigue_tests", "rotary_tests"):
            clauses = " OR ".join(f"failure_mode{i} = ?" for i in _SLOTS)
            row = self.db.query_one(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {clauses}",
                tuple(label for _ in _SLOTS),
            )
            total += row["n"]
        return total

    def remove_failure_mode(self, mode_id: int) -> None:
        with self.db.write() as conn:
            conn.execute("DELETE FROM failure_modes WHERE id = ?", (mode_id,))

    # --- solicitantes ----------------------------------------------------
    def requesters(self, active_only: bool = True) -> list[Requester]:
        sql = "SELECT id, name, active FROM requesters"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY name"
        return [
            Requester(id=r["id"], name=r["name"], active=bool(r["active"]))
            for r in self.db.query(sql)
        ]

    def requester_names(self) -> list[str]:
        return [r.name for r in self.requesters()]

    def save_requester(self, requester: Requester) -> None:
        with self.db.write() as conn:
            if requester.id is None:
                conn.execute(
                    "INSERT INTO requesters (name, active) VALUES (?, ?)",
                    (requester.name, int(requester.active)),
                )
            else:
                conn.execute(
                    "UPDATE requesters SET name = ?, active = ? WHERE id = ?",
                    (requester.name, int(requester.active), requester.id),
                )

    def remove_requester(self, requester_id: int) -> None:
        with self.db.write() as conn:
            conn.execute("DELETE FROM requesters WHERE id = ?", (requester_id,))


# ==========================================================================
# Pruebas de fatiga
# ==========================================================================

class FatigueRepository:
    table = "fatigue_tests"

    def __init__(self, db: Database, audit: AuditRepository):
        self.db = db
        self.audit = audit

    # --- lectura ---------------------------------------------------------
    def list(self, status: str | None = None) -> list[FatigueTest]:
        sql = _select(FATIGUE_COLUMNS, self.table)
        params: tuple = ()
        if status:
            sql += " WHERE test_status = ?"
            params = (status,)
        sql += " ORDER BY id DESC"
        return [self._to_model(r) for r in self.db.query(sql, params)]

    def get(self, test_id: int) -> FatigueTest | None:
        row = self.db.query_one(
            _select(FATIGUE_COLUMNS, self.table) + " WHERE id = ?", (test_id,)
        )
        return self._to_model(row) if row else None

    def batch_exists(self, test_batch: str, exclude_id: int | None = None) -> bool:
        sql = f"SELECT COUNT(*) AS n FROM {self.table} WHERE test_batch = ?"
        params: list = [test_batch]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        return bool(self.db.query_one(sql, tuple(params))["n"])

    # --- escritura -------------------------------------------------------
    def create(self, test: FatigueTest, author: tuple[str, str]) -> int:
        values = self._to_values(test)
        columns = [c for c in FATIGUE_COLUMNS if c != "id"]
        placeholders = ", ".join("?" for _ in columns)
        column_list = ", ".join(columns)

        with self.db.write() as conn:
            cursor = conn.execute(
                f"INSERT INTO {self.table} ({column_list}) VALUES ({placeholders})",
                [values[c] for c in columns],
            )
            new_id = cursor.lastrowid
            self.audit.record(
                conn,
                [_entry(self.table, new_id, test.test_batch, "created",
                        "registro", None, test.test_batch, author)],
            )
        return new_id

    def update(
        self,
        test: FatigueTest,
        author: tuple[str, str],
        base: FatigueTest | None = None,
        on_conflict: str = CONFLICT_RAISE,
        moved_on: dict[int, date] | None = None,
    ) -> None:
        """Guarda la prueba.

        Con ``base`` --la prueba como estaba al abrir el formulario-- se
        combina con lo que otro equipo haya guardado mientras tanto, y levanta
        :class:`EditConflict` si los dos cambiaron el mismo campo.
        """
        if test.id is None:
            raise ValueError("No se puede actualizar una prueba sin id")

        columns = [c for c in FATIGUE_COLUMNS if c != "id"]
        assignments = ", ".join(f"{c} = ?" for c in columns)

        with self.db.write() as conn:
            values, previous = _values_to_save(
                conn, self.table, FATIGUE_COLUMNS, test.id, self._to_model,
                self._to_values, test, base, on_conflict, test.test_batch,
            )
            conn.execute(
                f"UPDATE {self.table} SET {assignments} WHERE id = ?",
                [values[c] for c in columns] + [test.id],
            )
            # La pieza que se llevo a otro banco mientras el suyo estaba en
            # mantenimiento deja de estar detenida hoy. Va en la misma
            # transaccion que el cambio de banco: son la misma cosa. Se mira
            # el banco que de verdad queda guardado, que tras combinar con
            # otro equipo puede no ser el del formulario.
            guardadas = [FatigueSample(rig=values.get(f"test_rig{i}"))
                         for i in _SLOTS]
            _release_moved_samples(conn, self.table, test.id, guardadas,
                                   date.today(), moved_on)
            if previous:
                changes = _diff(
                    previous, values, self.table, test.id,
                    test.test_batch, "updated", author,
                )
                if changes:
                    self.audit.record(conn, changes)

    def close(
        self, test_id: int, end_date: date, author: tuple[str, str]
    ) -> None:
        """Marca la prueba como finalizada."""
        previous = self.get(test_id)
        batch = previous.test_batch if previous else ""
        old_end = dates.to_db(previous.end_date) if previous else None

        with self.db.write() as conn:
            conn.execute(
                f"UPDATE {self.table} SET end_date = ?, test_status = ? WHERE id = ?",
                (dates.to_db(end_date), FINISHED, test_id),
            )
            self.audit.record(
                conn,
                [
                    _entry(self.table, test_id, batch, "closed", "test_status",
                           ONGOING, FINISHED, author),
                    _entry(self.table, test_id, batch, "closed", "end_date",
                           old_end, dates.to_db(end_date), author),
                ],
            )

    def reopen(self, test_id: int, author: tuple[str, str]) -> None:
        """Devuelve la prueba a 'En curso' (el 'Quitar de finalizados')."""
        previous = self.get(test_id)
        batch = previous.test_batch if previous else ""
        with self.db.write() as conn:
            conn.execute(
                f"UPDATE {self.table} SET test_status = ? WHERE id = ?",
                (ONGOING, test_id),
            )
            self.audit.record(
                conn,
                [_entry(self.table, test_id, batch, "reopened", "test_status",
                        FINISHED, ONGOING, author)],
            )

    # --- mapeo -----------------------------------------------------------
    @staticmethod
    def _to_model(row: sqlite3.Row) -> FatigueTest:
        samples = [
            FatigueSample(
                rig=row[f"test_rig{i}"] or EMPTY_RIG,
                result=row[f"result{i}"] or "",
                cycles=_as_int(row[f"cycles{i}"]),
                failure_mode=row[f"failure_mode{i}"] or "",
            )
            for i in _SLOTS
        ]
        return FatigueTest(
            id=row["id"],
            test_batch=row["test_batch"],
            customer=row["customer"],
            requester=row["requester"] or "",
            start_date=dates.from_db(row["start_date"]),
            end_date=dates.from_db(row["end_date"]),
            qty_samples=_as_int(row["qty_samples"]) or 0,
            comments=row["comments"] or "",
            wo_status=bool(row["wo_status"]),
            test_status=row["test_status"],
            samples=samples,
        )

    @staticmethod
    def _to_values(test: FatigueTest) -> dict:
        values = {
            "test_batch": test.test_batch,
            "customer": test.customer,
            "requester": test.requester or None,
            "start_date": dates.to_db(test.start_date),
            "end_date": dates.to_db(test.end_date),
            "qty_samples": test.qty_samples,
            "comments": test.comments or "--",
            "wo_status": int(test.wo_status),
            "test_status": test.test_status,
        }
        for index, sample in enumerate(test.samples, start=1):
            values[f"test_rig{index}"] = sample.rig or EMPTY_RIG
            # Como failure_mode: columna nueva, NULL cuando no se captura.
            values[f"result{index}"] = sample.result or None
            values[f"cycles{index}"] = sample.cycles
            # Columna nueva: sin modo de falla se guarda NULL, no "--".
            values[f"failure_mode{index}"] = sample.failure_mode or None
        return values


# ==========================================================================
# Rotary
# ==========================================================================

class RotaryRepository:
    table = "rotary_tests"

    def __init__(self, db: Database, audit: AuditRepository):
        self.db = db
        self.audit = audit

    def list(self, status: str | None = None) -> list[RotaryTest]:
        sql = _select(ROTARY_COLUMNS, self.table)
        params: tuple = ()
        if status:
            sql += " WHERE test_status = ?"
            params = (status,)
        sql += " ORDER BY id DESC"
        return [self._to_model(r) for r in self.db.query(sql, params)]

    def get(self, test_id: int) -> RotaryTest | None:
        row = self.db.query_one(
            _select(ROTARY_COLUMNS, self.table) + " WHERE id = ?", (test_id,)
        )
        return self._to_model(row) if row else None

    def batch_exists(self, test_batch: str, exclude_id: int | None = None) -> bool:
        sql = f"SELECT COUNT(*) AS n FROM {self.table} WHERE test_batch = ?"
        params: list = [test_batch]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        return bool(self.db.query_one(sql, tuple(params))["n"])

    def create(self, test: RotaryTest, author: tuple[str, str]) -> int:
        values = self._to_values(test)
        columns = [c for c in ROTARY_COLUMNS if c != "id"]
        placeholders = ", ".join("?" for _ in columns)
        column_list = ", ".join(columns)

        with self.db.write() as conn:
            cursor = conn.execute(
                f"INSERT INTO {self.table} ({column_list}) VALUES ({placeholders})",
                [values[c] for c in columns],
            )
            new_id = cursor.lastrowid
            self.audit.record(
                conn,
                [_entry(self.table, new_id, test.test_batch, "created",
                        "registro", None, test.test_batch, author)],
            )
        return new_id

    def update(
        self,
        test: RotaryTest,
        author: tuple[str, str],
        base: RotaryTest | None = None,
        on_conflict: str = CONFLICT_RAISE,
    ) -> None:
        """Guarda la prueba; con ``base`` combina, igual que en Fatiga."""
        if test.id is None:
            raise ValueError("No se puede actualizar una prueba sin id")

        columns = [c for c in ROTARY_COLUMNS if c != "id"]
        assignments = ", ".join(f"{c} = ?" for c in columns)

        with self.db.write() as conn:
            values, previous = _values_to_save(
                conn, self.table, ROTARY_COLUMNS, test.id, self._to_model,
                self._to_values, test, base, on_conflict, test.test_batch,
            )
            conn.execute(
                f"UPDATE {self.table} SET {assignments} WHERE id = ?",
                [values[c] for c in columns] + [test.id],
            )
            if previous:
                changes = _diff(
                    previous, values, self.table, test.id,
                    test.test_batch, "updated", author,
                )
                if changes:
                    self.audit.record(conn, changes)

    def close(
        self, test_id: int, end_date: date, author: tuple[str, str]
    ) -> None:
        previous = self.get(test_id)
        batch = previous.test_batch if previous else ""
        with self.db.write() as conn:
            conn.execute(
                f"UPDATE {self.table} SET end_date = ?, test_status = ? WHERE id = ?",
                (dates.to_db(end_date), FINISHED, test_id),
            )
            self.audit.record(
                conn,
                [_entry(self.table, test_id, batch, "closed", "test_status",
                        ONGOING, FINISHED, author)],
            )

    def reopen(self, test_id: int, author: tuple[str, str]) -> None:
        previous = self.get(test_id)
        batch = previous.test_batch if previous else ""
        with self.db.write() as conn:
            conn.execute(
                f"UPDATE {self.table} SET test_status = ? WHERE id = ?",
                (ONGOING, test_id),
            )
            self.audit.record(
                conn,
                [_entry(self.table, test_id, batch, "reopened", "test_status",
                        FINISHED, ONGOING, author)],
            )

    @staticmethod
    def _to_model(row: sqlite3.Row) -> RotaryTest:
        samples = [
            RotarySample(
                revs=_as_int(row[f"revs{i}"]),
                status=row[f"status{i}"] or EMPTY_RIG,
                failure_mode=row[f"failure_mode{i}"] or "",
            )
            for i in _SLOTS
        ]
        return RotaryTest(
            id=row["id"],
            test_batch=row["test_batch"] or "",
            customer=row["customer"] or "",
            requester=row["requester"] or "",
            start_date=dates.from_db(row["start_date"]),
            end_date=dates.from_db(row["end_date"]),
            qty_samples=_as_int(row["qty_samples"]) or 0,
            comments=row["comments"] or "",
            test_rig=row["test_rig"] or EMPTY_RIG,
            test_status=row["test_status"] or ONGOING,
            samples=samples,
        )

    @staticmethod
    def _to_values(test: RotaryTest) -> dict:
        values = {
            "test_batch": test.test_batch,
            "customer": test.customer,
            "requester": test.requester or None,
            "start_date": dates.to_db(test.start_date),
            "end_date": dates.to_db(test.end_date),
            "qty_samples": test.qty_samples,
            "comments": test.comments or "--",
            "test_rig": test.test_rig or EMPTY_RIG,
            "test_status": test.test_status,
        }
        for index, sample in enumerate(test.samples, start=1):
            values[f"revs{index}"] = sample.revs
            values[f"status{index}"] = sample.status or EMPTY_RIG
            values[f"failure_mode{index}"] = sample.failure_mode or None
        return values


# ==========================================================================
# Torsion y Quasi
# ==========================================================================

class GenericRepository:
    """Una sola implementacion para Torsion y Quasi.

    Sustituye a ``logbook_torsion.py`` y ``logbook_quasi.py``, que eran copias
    identicas salvo el nombre de la tabla y el color.
    """

    def __init__(self, db: Database, audit: AuditRepository, table: str):
        if table not in ALLOWED_TABLES:
            raise ValueError(f"Tabla no permitida: {table!r}")
        self.db = db
        self.audit = audit
        self.table = table

    def list(self) -> list[GenericTest]:
        rows = self.db.query(
            _select(GENERIC_COLUMNS, self.table) + " ORDER BY id DESC"
        )
        return [self._to_model(r) for r in rows]

    def get(self, test_id: int) -> GenericTest | None:
        row = self.db.query_one(
            _select(GENERIC_COLUMNS, self.table) + " WHERE id = ?", (test_id,)
        )
        return self._to_model(row) if row else None

    def batch_exists(self, test_batch: str, exclude_id: int | None = None) -> bool:
        sql = f"SELECT COUNT(*) AS n FROM {self.table} WHERE test_batch = ?"
        params: list = [test_batch]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        return bool(self.db.query_one(sql, tuple(params))["n"])

    def create(self, test: GenericTest, author: tuple[str, str]) -> int:
        values = self._to_values(test)
        columns = [c for c in GENERIC_COLUMNS if c != "id"]
        placeholders = ", ".join("?" for _ in columns)
        column_list = ", ".join(columns)

        with self.db.write() as conn:
            cursor = conn.execute(
                f"INSERT INTO {self.table} ({column_list}) VALUES ({placeholders})",
                [values[c] for c in columns],
            )
            new_id = cursor.lastrowid
            self.audit.record(
                conn,
                [_entry(self.table, new_id, test.test_batch, "created",
                        "registro", None, test.test_batch, author)],
            )
        return new_id

    def update(
        self,
        test: GenericTest,
        author: tuple[str, str],
        base: GenericTest | None = None,
        on_conflict: str = CONFLICT_RAISE,
    ) -> None:
        """Guarda la prueba; con ``base`` combina, igual que en Fatiga."""
        if test.id is None:
            raise ValueError("No se puede actualizar una prueba sin id")

        columns = [c for c in GENERIC_COLUMNS if c != "id"]
        assignments = ", ".join(f"{c} = ?" for c in columns)

        with self.db.write() as conn:
            values, previous = _values_to_save(
                conn, self.table, GENERIC_COLUMNS, test.id, self._to_model,
                self._to_values, test, base, on_conflict, test.test_batch,
            )
            conn.execute(
                f"UPDATE {self.table} SET {assignments} WHERE id = ?",
                [values[c] for c in columns] + [test.id],
            )
            if previous:
                changes = _diff(
                    previous, values, self.table, test.id,
                    test.test_batch, "updated", author,
                )
                if changes:
                    self.audit.record(conn, changes)

    def delete(self, test_id: int, author: tuple[str, str]) -> None:
        previous = self.get(test_id)
        batch = previous.test_batch if previous else ""
        with self.db.write() as conn:
            conn.execute(f"DELETE FROM {self.table} WHERE id = ?", (test_id,))
            self.audit.record(
                conn,
                [_entry(self.table, test_id, batch, "deleted", "registro",
                        batch, None, author)],
            )

    @staticmethod
    def _to_model(row: sqlite3.Row) -> GenericTest:
        return GenericTest(
            id=row["id"],
            test_batch=row["test_batch"],
            customer=row["customer"],
            requester=row["requester"] or "",
            test_date=dates.from_db(row["test_date"]),
            qty_samples=_as_int(row["qty_samples"]) or 0,
            comments=row["comments"] or "",
            test_rig=row["test_rig"] or EMPTY_RIG,
        )

    @staticmethod
    def _to_values(test: GenericTest) -> dict:
        return {
            "test_batch": test.test_batch,
            "customer": test.customer,
            "requester": test.requester or None,
            "test_date": dates.to_db(test.test_date),
            "qty_samples": test.qty_samples,
            "comments": test.comments or "--",
            "test_rig": test.test_rig or EMPTY_RIG,
        }


# ==========================================================================
# Auxiliares de auditoria
# ==========================================================================

def _entry(
    table: str,
    record_id: int,
    test_batch: str,
    action: str,
    field: str,
    old_value,
    new_value,
    author: tuple[str, str],
) -> AuditEntry:
    user, machine = author
    return AuditEntry(
        table_name=table,
        record_id=record_id,
        test_batch=test_batch,
        action=action,
        field=field,
        old_value=None if old_value is None else str(old_value),
        new_value=None if new_value is None else str(new_value),
        changed_by=user,
        machine=machine,
        changed_at=datetime.now(),
    )


def _diff(
    before: dict,
    after: dict,
    table: str,
    record_id: int,
    test_batch: str,
    action: str,
    author: tuple[str, str],
) -> list[AuditEntry]:
    """Una entrada de historial por cada campo que realmente cambio."""
    entries: list[AuditEntry] = []
    for field, new_value in after.items():
        old_value = before.get(field)
        if old_value != new_value:
            entries.append(
                _entry(table, record_id, test_batch, action, field,
                       old_value, new_value, author)
            )
    return entries


# ==========================================================================
# Edicion concurrente
# ==========================================================================

class RecordDeleted(Exception):
    """El registro que se estaba editando ya no existe en la base."""

    def __init__(self, table: str, record_id: int, test_batch: str = ""):
        super().__init__(f"{table} #{record_id} ya no existe")
        self.table = table
        self.record_id = record_id
        self.test_batch = test_batch


class EditConflict(Exception):
    """Dos equipos cambiaron los mismos campos del mismo registro.

    ``fields`` va por columna: ``(como estaba al abrir, lo del formulario,
    lo que hay guardado)``.
    """

    def __init__(self, table: str, record_id: int, test_batch: str,
                 fields: dict[str, tuple]):
        super().__init__(
            f"{table} #{record_id}: {', '.join(fields)} cambiaron en otro equipo"
        )
        self.table = table
        self.record_id = record_id
        self.test_batch = test_batch
        self.fields = fields


def _merge_values(base: dict, mine: dict, theirs: dict) -> tuple[dict, dict]:
    """Combina campo a campo lo del formulario con lo que hay guardado.

    - Lo que el formulario no toco (sigue como al abrir) se queda como esta
      guardado: si otro equipo lo cambio, ese cambio no se pisa.
    - Lo que solo cambio el formulario se guarda.
    - Lo que cambiaron los dos a valores distintos es un conflicto.
    """
    merged: dict = {}
    conflicts: dict = {}
    for column, value in mine.items():
        before = base.get(column)
        now = theirs.get(column)
        if value == before or value == now:
            merged[column] = now
        elif now == before:
            merged[column] = value
        else:
            merged[column] = value
            conflicts[column] = (before, value, now)
    return merged, conflicts


def _values_to_save(conn, table: str, columns: list[str], record_id: int,
                    to_model, to_values, record, base, on_conflict: str,
                    test_batch: str) -> tuple[dict, dict | None]:
    """Lo que ``update`` escribe, y lo que habia antes para el historial.

    Sin ``base`` se escribe el registro tal cual, como siempre se hizo. Con
    ``base`` --el registro como estaba al abrir el formulario-- lo guardado se
    lee dentro de la misma transaccion y se combina. Entre leer y escribir
    nadie mas puede guardar: la transaccion ya tiene el lock de escritura.

    Antes se escribian todas las columnas desde el formulario, y lo que otro
    equipo hubiera guardado mientras tanto se perdia sin aviso.
    """
    row = conn.execute(
        _select(columns, table) + " WHERE id = ?", (record_id,)
    ).fetchone()
    previous = to_values(to_model(row)) if row else None
    values = to_values(record)
    if base is None:
        return values, previous
    if previous is None:
        raise RecordDeleted(table, record_id, test_batch)

    # Los tres pasan por el mismo mapeo, asi que se comparan en la misma
    # representacion: un NULL guardado y un '--' leido no cuentan como cambio.
    merged, conflicts = _merge_values(to_values(base), values, previous)
    if conflicts:
        if on_conflict not in (KEEP_MINE, KEEP_THEIRS):
            raise EditConflict(table, record_id, test_batch, conflicts)
        for column, (_, mine, theirs) in conflicts.items():
            merged[column] = mine if on_conflict == KEEP_MINE else theirs
    return merged, previous


# ==========================================================================
# Work Orders
# ==========================================================================

WORK_ORDER_COLUMNS = [
    "id", "test_type", "test_batch", "customer", "qty_samples", "requester",
    "comments", "status", "priority", "started_test_id", "created_at",
    "created_by",
]


class WorkOrderRepository:
    """Las ordenes de trabajo: lo que autoriza una prueba antes de que exista."""

    table = "work_orders"

    def __init__(self, db: Database, audit: AuditRepository):
        self.db = db
        self.audit = audit

    # --- lectura ---------------------------------------------------------
    def list(
        self, status: str | None = None, test_type: str | None = None
    ) -> list[WorkOrder]:
        clauses: list[str] = []
        params: list = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if test_type:
            clauses.append("test_type = ?")
            params.append(test_type)

        sql = _select(WORK_ORDER_COLUMNS, self.table)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        # Las pendientes primero y en el orden de prioridad que haya puesto el
        # usuario; las comenzadas van al final, ahi ya manda la fecha. El
        # desempate por id evita que dos ordenes con la misma prioridad se
        # intercambien de sitio entre una carga y la siguiente.
        sql += (
            " ORDER BY status DESC,"
            " CASE WHEN status = ? THEN priority ELSE -id END,"
            " id"
        )
        return [
            self._to_model(r)
            for r in self.db.query(sql, tuple(params) + (WO_PENDING,))
        ]

    def pending_in_order(self) -> list[WorkOrder]:
        """Las pendientes, de la mas urgente a la que puede esperar."""
        return self.list(status=WO_PENDING)

    def get(self, work_order_id: int) -> WorkOrder | None:
        row = self.db.query_one(
            _select(WORK_ORDER_COLUMNS, self.table) + " WHERE id = ?",
            (work_order_id,),
        )
        return self._to_model(row) if row else None

    def batch_exists(self, test_batch: str, exclude_id: int | None = None) -> bool:
        sql = f"SELECT COUNT(*) AS n FROM {self.table} WHERE test_batch = ?"
        params: list = [test_batch]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        return bool(self.db.query_one(sql, tuple(params))["n"])

    def pending_count(self) -> int:
        row = self.db.query_one(
            f"SELECT COUNT(*) AS n FROM {self.table} WHERE status = ?",
            (WO_PENDING,),
        )
        return row["n"] if row else 0

    def requester_usage(self, name: str) -> int:
        row = self.db.query_one(
            f"SELECT COUNT(*) AS n FROM {self.table} WHERE requester = ?",
            (name,),
        )
        return row["n"] if row else 0

    def next_priority(self) -> int:
        """Donde entra una orden nueva: al final de la fila.

        Quien captura la orden no siempre sabe todavia si corre antes o
        despues que las demas; se acomoda luego desde la lista.
        """
        row = self.db.query_one(
            f"SELECT COALESCE(MAX(priority), 0) AS top FROM {self.table}"
        )
        return (row["top"] if row else 0) + 1

    # --- escritura -------------------------------------------------------
    def create(self, order: WorkOrder, author: tuple[str, str]) -> int:
        values = self._to_values(order)
        columns = [c for c in WORK_ORDER_COLUMNS if c != "id"]
        placeholders = ", ".join("?" for _ in columns)

        with self.db.write() as conn:
            cursor = conn.execute(
                f"INSERT INTO {self.table} ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                [values[c] for c in columns],
            )
            new_id = cursor.lastrowid
            self.audit.record(
                conn,
                [_entry(self.table, new_id, order.test_batch, "created",
                        "work order", None, order.test_batch, author)],
            )
        return new_id

    def update(
        self,
        order: WorkOrder,
        author: tuple[str, str],
        base: WorkOrder | None = None,
        on_conflict: str = CONFLICT_RAISE,
    ) -> None:
        """Guarda la orden; con ``base`` combina, igual que las bitacoras.

        Aqui importa por partida doble: otro equipo puede haberla comenzado o
        movido de prioridad mientras el formulario estaba abierto, y guardar
        la orden entera le devolvia el estado y el lugar de antes.
        """
        if order.id is None:
            raise ValueError("No se puede actualizar una WO sin id")

        columns = [c for c in WORK_ORDER_COLUMNS if c != "id"]
        assignments = ", ".join(f"{c} = ?" for c in columns)

        with self.db.write() as conn:
            values, previous = _values_to_save(
                conn, self.table, WORK_ORDER_COLUMNS, order.id, self._to_model,
                self._to_values, order, base, on_conflict, order.test_batch,
            )
            conn.execute(
                f"UPDATE {self.table} SET {assignments} WHERE id = ?",
                [values[c] for c in columns] + [order.id],
            )
            if previous:
                changes = _diff(
                    previous, values, self.table, order.id,
                    order.test_batch, "updated", author,
                )
                if changes:
                    self.audit.record(conn, changes)

    def move(
        self, work_order_id: int, delta: int, author: tuple[str, str]
    ) -> bool:
        """Sube o baja una orden en la fila de pendientes.

        ``delta`` es -1 para subir y +1 para bajar. Devuelve False si la orden
        ya esta en el extremo o si no esta pendiente: las comenzadas no se
        reacomodan, su lugar en la fila ya no significa nada.
        """
        pendientes = self.pending_in_order()
        posiciones = {order.id: i for i, order in enumerate(pendientes)}
        origen = posiciones.get(work_order_id)
        if origen is None:
            return False

        destino = origen + delta
        if not 0 <= destino < len(pendientes):
            return False

        pendientes[origen], pendientes[destino] = (
            pendientes[destino], pendientes[origen],
        )
        self._renumber(pendientes, work_order_id, origen, destino, author)
        return True

    def move_to_top(
        self, work_order_id: int, author: tuple[str, str]
    ) -> bool:
        """Pone una orden a la cabeza. Para lo que entra de urgencia."""
        pendientes = self.pending_in_order()
        posiciones = {order.id: i for i, order in enumerate(pendientes)}
        origen = posiciones.get(work_order_id)
        if origen is None or origen == 0:
            return False

        pendientes.insert(0, pendientes.pop(origen))
        self._renumber(pendientes, work_order_id, origen, 0, author)
        return True

    def _renumber(
        self, ordered: list[WorkOrder], moved_id: int,
        origen: int, destino: int, author: tuple[str, str],
    ) -> None:
        """Reescribe las prioridades como 1..N sobre el orden recibido.

        Se renumera entero y no solo las dos filas que cambiaron: asi la
        columna nunca acumula huecos de las ordenes que se comenzaron o se
        borraron, y la prioridad guardada coincide con la posicion que se ve.
        """
        movida = next((o for o in ordered if o.id == moved_id), None)
        batch = movida.test_batch if movida else ""

        with self.db.write() as conn:
            conn.executemany(
                f"UPDATE {self.table} SET priority = ? WHERE id = ?",
                [(n, order.id) for n, order in enumerate(ordered, start=1)],
            )
            self.audit.record(
                conn,
                [_entry(self.table, moved_id, batch, "updated", "prioridad",
                        str(origen + 1), str(destino + 1), author)],
            )

    def _started_batch(self, test_type: str, test_id: int) -> str | None:
        """El Test Batch con el que acabo guardandose la prueba.

        Se lee de la propia bitacora y no de lo que traia la orden: el
        formulario deja corregir el Test Batch al comenzar --para eso se dejo
        editable-- y lo que vale es con que se guardo.
        """
        config = TEST_TYPES.get(test_type)
        if config is None:
            return None
        row = self.db.query_one(
            f"SELECT test_batch FROM {_checked_table(config.table)} "
            f"WHERE id = ?",
            (test_id,),
        )
        return row["test_batch"] if row else None

    def mark_started(
        self, work_order_id: int, test_id: int, author: tuple[str, str]
    ) -> None:
        """Enlaza la WO con el registro que salio de ella.

        Se hace despues de guardar la prueba, no antes: si el usuario cancela
        el formulario la WO tiene que seguir pendiente.

        Si al comenzar se corrigio el Test Batch, la orden se queda con el de
        la prueba. Antes no, y eso dejaba dos cosas rotas: la orden y su prueba
        decian Test Batch distintos --justo lo que la app evita al no dejar
        editar una orden ya comenzada-- y el batch viejo, que no existe en
        ninguna bitacora, bloqueaba para siempre el alta de una orden nueva con
        ese numero.
        """
        previous = self.get(work_order_id)
        batch = previous.test_batch if previous else ""
        real = self._started_batch(previous.test_type, test_id) if previous             else None
        corregido = bool(real) and real != batch

        with self.db.write() as conn:
            asignaciones = "status = ?, started_test_id = ?"
            valores: list = [WO_STARTED, test_id]
            if corregido:
                asignaciones += ", test_batch = ?"
                valores.append(real)

            conn.execute(
                f"UPDATE {self.table} SET {asignaciones} WHERE id = ?",
                (*valores, work_order_id),
            )

            registro = real if corregido else batch
            entries = [
                _entry(self.table, work_order_id, registro, "started", "status",
                       WO_PENDING, WO_STARTED, author),
                _entry(self.table, work_order_id, registro, "started",
                       "started_test_id", None, str(test_id), author),
            ]
            if corregido:
                entries.append(
                    _entry(self.table, work_order_id, registro, "started",
                           "test_batch", batch, real, author)
                )
            self.audit.record(conn, entries)

    def delete(self, work_order_id: int, author: tuple[str, str]) -> None:
        previous = self.get(work_order_id)
        batch = previous.test_batch if previous else ""
        with self.db.write() as conn:
            conn.execute(f"DELETE FROM {self.table} WHERE id = ?", (work_order_id,))
            self.audit.record(
                conn,
                [_entry(self.table, work_order_id, batch, "deleted",
                        "work order", batch, None, author)],
            )

    # --- mapeo -----------------------------------------------------------
    @staticmethod
    def _to_model(row: sqlite3.Row) -> WorkOrder:
        return WorkOrder(
            id=row["id"],
            test_type=row["test_type"],
            test_batch=row["test_batch"] or "",
            customer=row["customer"] or "",
            qty_samples=_as_int(row["qty_samples"]) or 1,
            requester=row["requester"] or "",
            comments=row["comments"] or "",
            status=row["status"] or WO_PENDING,
            priority=_as_int(row["priority"]) or 0,
            started_test_id=row["started_test_id"],
            created_at=dates.from_db(row["created_at"]),
            created_by=row["created_by"] or "",
        )

    @staticmethod
    def _to_values(order: WorkOrder) -> dict:
        return {
            "test_type": order.test_type,
            "test_batch": order.test_batch,
            "customer": order.customer,
            "qty_samples": order.qty_samples,
            "requester": order.requester,
            "comments": order.comments or "",
            "status": order.status,
            "priority": order.priority,
            "started_test_id": order.started_test_id,
            "created_at": dates.to_db(order.created_at or date.today()),
            "created_by": order.created_by,
        }


# ==========================================================================
# Mantenimiento de rigs
# ==========================================================================

MAINTENANCE_COLUMNS = [
    "id", "rig_id", "rig_name", "test_type", "start_date", "end_date",
    "reason", "created_by", "created_at",
]

MAINTENANCE_SAMPLE_COLUMNS = [
    "id", "maintenance_id", "table_name", "record_id", "test_batch", "slot",
    "rig_name", "restored", "released_date",
]


class MaintenanceRepository:
    """Los periodos con un banco fuera de servicio, y sus consecuencias.

    Es el unico repositorio que escribe en la tabla de otra bitacora: poner un
    banco en mantenimiento vacia el ``test_rigN`` de las piezas que corrian en
    el. Va junto y en una sola transaccion porque las dos mitades por separado
    mienten -- un banco parado con sus piezas asignadas seguiria contando como
    ocupado, y unas piezas sin banco sin nada que lo explique se leerian como
    suspensiones sueltas.
    """

    table = "rig_maintenance"
    samples_table = "rig_maintenance_samples"

    def __init__(self, db: Database, audit: AuditRepository):
        self.db = db
        self.audit = audit

    # --- lectura ---------------------------------------------------------
    def list(
        self,
        rig_name: str | None = None,
        test_type: str | None = None,
        open_only: bool = False,
    ) -> list[RigMaintenance]:
        clauses: list[str] = []
        params: list = []
        if rig_name:
            clauses.append("rig_name = ?")
            params.append(rig_name)
        if test_type:
            clauses.append("test_type = ?")
            params.append(test_type)
        if open_only:
            clauses.append("end_date IS NULL")

        sql = _select(MAINTENANCE_COLUMNS, self.table)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        # Lo que sigue parado primero: es lo que se viene a consultar. Despues,
        # de lo mas reciente a lo mas antiguo.
        sql += " ORDER BY end_date IS NULL DESC, start_date DESC, id DESC"

        records = [self._to_model(r) for r in self.db.query(sql, tuple(params))]
        self._attach_samples(records)
        return records

    def open_records(self) -> list[RigMaintenance]:
        """Los mantenimientos en curso: bancos que hoy no estan disponibles."""
        return self.list(open_only=True)

    def get(self, maintenance_id: int) -> RigMaintenance | None:
        row = self.db.query_one(
            _select(MAINTENANCE_COLUMNS, self.table) + " WHERE id = ?",
            (maintenance_id,),
        )
        if row is None:
            return None
        record = self._to_model(row)
        self._attach_samples([record])
        return record

    def _attach_samples(self, records: list[RigMaintenance]) -> None:
        """Las piezas afectadas de todos los mantenimientos, en una consulta.

        Una consulta por mantenimiento serian tantas idas a la base como filas,
        y la base vive en un recurso de red: cada ida cuesta una conexion.
        """
        ids = [r.id for r in records if r.id is not None]
        if not ids:
            return

        marks = ", ".join("?" for _ in ids)
        rows = self.db.query(
            _select(MAINTENANCE_SAMPLE_COLUMNS, self.samples_table)
            + f" WHERE maintenance_id IN ({marks})"
            + " ORDER BY record_id, slot",
            tuple(ids),
        )

        por_mantenimiento: dict[int, list[MaintenanceSample]] = {}
        for row in rows:
            por_mantenimiento.setdefault(row["maintenance_id"], []).append(
                self._to_sample(row)
            )
        for record in records:
            record.samples = por_mantenimiento.get(record.id, [])

    # --- escritura -------------------------------------------------------
    def start(
        self,
        maintenance: RigMaintenance,
        samples: list[MaintenanceSample],
        author: tuple[str, str],
    ) -> int:
        """Abre el mantenimiento y saca del banco las piezas que corrian ahi."""
        values = self._to_values(maintenance)
        columns = [c for c in MAINTENANCE_COLUMNS if c != "id"]
        placeholders = ", ".join("?" for _ in columns)

        with self.db.write() as conn:
            cursor = conn.execute(
                f"INSERT INTO {self.table} ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                [values[c] for c in columns],
            )
            new_id = cursor.lastrowid

            entries = [
                _entry(self.table, new_id, maintenance.rig_name, "created",
                       "mantenimiento", None,
                       maintenance.reason or maintenance.rig_name, author)
            ]

            for sample in samples:
                table = _checked_table(sample.table_name)
                column = _rig_column(sample.slot)

                conn.execute(
                    f"INSERT INTO {self.samples_table} "
                    f"(maintenance_id, table_name, record_id, test_batch, "
                    f"slot, rig_name, restored) VALUES (?, ?, ?, ?, ?, ?, 0)",
                    (new_id, table, sample.record_id, sample.test_batch,
                     sample.slot, sample.rig_name),
                )
                # El banco se vacia con "--" y no con NULL: es lo que guarda el
                # formulario al dejar la ranura en blanco, y models.is_blank()
                # trata los tres casos igual.
                conn.execute(
                    f"UPDATE {table} SET {column} = ? WHERE id = ?",
                    (EMPTY_RIG, sample.record_id),
                )
                entries.append(
                    _entry(table, sample.record_id, sample.test_batch,
                           "maintenance", column, sample.rig_name, None, author)
                )

            self.audit.record(conn, entries)

        return new_id

    def finish(
        self,
        maintenance_id: int,
        end_date: date,
        author: tuple[str, str],
        restore: bool = True,
    ) -> int:
        """Cierra el mantenimiento y devuelve las piezas a su banco.

        Devuelve cuantas piezas se repusieron. Con ``restore=False`` solo se
        cierra el periodo: sirve para el banco que sale de mantenimiento
        cuando esas pruebas ya se movieron a otro sitio.
        """
        previous = self.get(maintenance_id)
        if previous is None:
            raise ValueError(f"No existe el mantenimiento {maintenance_id}")

        repuestas = 0
        with self.db.write() as conn:
            conn.execute(
                f"UPDATE {self.table} SET end_date = ? WHERE id = ?",
                (dates.to_db(end_date), maintenance_id),
            )
            entries = [
                _entry(self.table, maintenance_id, previous.rig_name, "closed",
                       "end_date", None, dates.to_db(end_date), author)
            ]

            pendientes = previous.samples if restore else []
            for sample in pendientes:
                # Ni lo ya repuesto ni lo que se llevaron a otro banco: esa
                # pieza dejo de depender de este mantenimiento, aunque despues
                # se haya vuelto a quedar sin banco por otro motivo.
                if not sample.is_held:
                    continue
                table = _checked_table(sample.table_name)
                column = _rig_column(sample.slot)

                row = conn.execute(
                    f"SELECT {column} AS rig FROM {table} WHERE id = ?",
                    (sample.record_id,),
                ).fetchone()
                if row is None:
                    continue
                # Solo se repone la ranura que sigue vacia. Si mientras el
                # banco estaba parado alguien movio la pieza a otro banco, ese
                # dato es mas reciente que este apunte y manda.
                if not is_blank(row["rig"]):
                    continue

                conn.execute(
                    f"UPDATE {table} SET {column} = ? WHERE id = ?",
                    (sample.rig_name, sample.record_id),
                )
                conn.execute(
                    f"UPDATE {self.samples_table} SET restored = 1 WHERE id = ?",
                    (sample.id,),
                )
                entries.append(
                    _entry(table, sample.record_id, sample.test_batch,
                           "restored", column, None, sample.rig_name, author)
                )
                repuestas += 1

            # Al cerrar no se anota released_date: esa fecha dice que la pieza
            # se llevo a otro banco antes del cierre. Si se estampara tambien
            # aqui, una pieza movida el mismo dia en que cierra el
            # mantenimiento no se distinguiria de una que se quedo sin reponer.

            self.audit.record(conn, entries)

        return repuestas

    # --- mapeo -----------------------------------------------------------
    @staticmethod
    def _to_model(row: sqlite3.Row) -> RigMaintenance:
        return RigMaintenance(
            id=row["id"],
            rig_id=row["rig_id"],
            rig_name=row["rig_name"],
            test_type=row["test_type"],
            start_date=dates.from_db(row["start_date"]),
            end_date=dates.from_db(row["end_date"]),
            reason=row["reason"] or "",
            created_by=row["created_by"] or "",
        )

    @staticmethod
    def _to_sample(row: sqlite3.Row) -> MaintenanceSample:
        return MaintenanceSample(
            id=row["id"],
            maintenance_id=row["maintenance_id"],
            table_name=row["table_name"],
            record_id=row["record_id"],
            test_batch=row["test_batch"] or "",
            slot=_as_int(row["slot"]) or 0,
            rig_name=row["rig_name"],
            restored=bool(row["restored"]),
            released_date=dates.from_db(row["released_date"]),
        )

    @staticmethod
    def _to_values(maintenance: RigMaintenance) -> dict:
        return {
            "rig_id": maintenance.rig_id,
            "rig_name": maintenance.rig_name,
            "test_type": maintenance.test_type,
            "start_date": dates.to_db(maintenance.start_date or date.today()),
            "end_date": dates.to_db(maintenance.end_date),
            "reason": maintenance.reason or "",
            "created_by": maintenance.created_by,
            "created_at": dates.to_db(date.today()),
        }
