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
    WO_PENDING,
    WO_STARTED,
    AuditEntry,
    Customer,
    FailureMode,
    FatigueSample,
    FatigueTest,
    GenericTest,
    Rig,
    RotarySample,
    RotaryTest,
    Requester,
    SampleStatus,
    TestCode,
    WorkOrder,
)

_SLOTS = range(1, SAMPLE_SLOTS + 1)

FATIGUE_COLUMNS = (
    ["id", "test_batch", "customer", "start_date", "end_date", "qty_samples",
     "comments"]
    + [name for i in _SLOTS
       for name in (f"test_rig{i}", f"result{i}", f"cycles{i}",
                    f"failure_mode{i}")]
    + ["wo_status", "test_status"]
)

ROTARY_COLUMNS = (
    ["id", "test_batch", "customer", "start_date", "end_date", "qty_samples",
     "comments", "test_rig"]
    + [name for i in _SLOTS
       for name in (f"revs{i}", f"status{i}", f"failure_mode{i}")]
    + ["test_status"]
)

GENERIC_COLUMNS = [
    "id", "test_batch", "customer", "test_date", "qty_samples", "comments",
    "test_rig",
]


def _select(columns: list[str], table: str) -> str:
    joined = ", ".join(columns)
    return f"SELECT {joined} FROM {table}"


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

    def update(self, test: FatigueTest, author: tuple[str, str]) -> None:
        if test.id is None:
            raise ValueError("No se puede actualizar una prueba sin id")

        previous = self.get(test.id)
        values = self._to_values(test)
        columns = [c for c in FATIGUE_COLUMNS if c != "id"]
        assignments = ", ".join(f"{c} = ?" for c in columns)

        with self.db.write() as conn:
            conn.execute(
                f"UPDATE {self.table} SET {assignments} WHERE id = ?",
                [values[c] for c in columns] + [test.id],
            )
            if previous:
                changes = _diff(
                    self._to_values(previous), values, self.table, test.id,
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

    def update(self, test: RotaryTest, author: tuple[str, str]) -> None:
        if test.id is None:
            raise ValueError("No se puede actualizar una prueba sin id")

        previous = self.get(test.id)
        values = self._to_values(test)
        columns = [c for c in ROTARY_COLUMNS if c != "id"]
        assignments = ", ".join(f"{c} = ?" for c in columns)

        with self.db.write() as conn:
            conn.execute(
                f"UPDATE {self.table} SET {assignments} WHERE id = ?",
                [values[c] for c in columns] + [test.id],
            )
            if previous:
                changes = _diff(
                    self._to_values(previous), values, self.table, test.id,
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

    def update(self, test: GenericTest, author: tuple[str, str]) -> None:
        if test.id is None:
            raise ValueError("No se puede actualizar una prueba sin id")

        previous = self.get(test.id)
        values = self._to_values(test)
        columns = [c for c in GENERIC_COLUMNS if c != "id"]
        assignments = ", ".join(f"{c} = ?" for c in columns)

        with self.db.write() as conn:
            conn.execute(
                f"UPDATE {self.table} SET {assignments} WHERE id = ?",
                [values[c] for c in columns] + [test.id],
            )
            if previous:
                changes = _diff(
                    self._to_values(previous), values, self.table, test.id,
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
# Work Orders
# ==========================================================================

WORK_ORDER_COLUMNS = [
    "id", "test_type", "test_batch", "customer", "qty_samples", "requester",
    "comments", "status", "started_test_id", "created_at", "created_by",
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
        # Las pendientes primero, y dentro de cada grupo la mas reciente arriba.
        sql += " ORDER BY status DESC, id DESC"
        return [self._to_model(r) for r in self.db.query(sql, tuple(params))]

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

    def update(self, order: WorkOrder, author: tuple[str, str]) -> None:
        if order.id is None:
            raise ValueError("No se puede actualizar una WO sin id")

        previous = self.get(order.id)
        values = self._to_values(order)
        columns = [c for c in WORK_ORDER_COLUMNS if c != "id"]
        assignments = ", ".join(f"{c} = ?" for c in columns)

        with self.db.write() as conn:
            conn.execute(
                f"UPDATE {self.table} SET {assignments} WHERE id = ?",
                [values[c] for c in columns] + [order.id],
            )
            if previous:
                changes = _diff(
                    self._to_values(previous), values, self.table, order.id,
                    order.test_batch, "updated", author,
                )
                if changes:
                    self.audit.record(conn, changes)

    def mark_started(
        self, work_order_id: int, test_id: int, author: tuple[str, str]
    ) -> None:
        """Enlaza la WO con el registro que salio de ella.

        Se hace despues de guardar la prueba, no antes: si el usuario cancela
        el formulario la WO tiene que seguir pendiente.
        """
        previous = self.get(work_order_id)
        batch = previous.test_batch if previous else ""

        with self.db.write() as conn:
            conn.execute(
                f"UPDATE {self.table} SET status = ?, started_test_id = ? "
                f"WHERE id = ?",
                (WO_STARTED, test_id, work_order_id),
            )
            self.audit.record(
                conn,
                [
                    _entry(self.table, work_order_id, batch, "started", "status",
                           WO_PENDING, WO_STARTED, author),
                    _entry(self.table, work_order_id, batch, "started",
                           "started_test_id", None, str(test_id), author),
                ],
            )

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
            "started_test_id": order.started_test_id,
            "created_at": dates.to_db(order.created_at or date.today()),
            "created_by": order.created_by,
        }
