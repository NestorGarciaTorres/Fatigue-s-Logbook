"""Acceso a SQLite afinado para una base sobre recurso de red (SMB).

La version anterior abria ``sqlite3.connect("./db/test_records.db")`` dentro de
cada metodo de cada ventana -- ocho lugares distintos, con rutas relativas al
directorio de trabajo y sin timeout. Aqui todo pasa por un solo punto.

Nota sobre ``journal_mode``: NO se usa WAL. WAL necesita memoria compartida
entre procesos y SQLite lo declara no soportado sobre sistemas de archivos de
red. Sobre SMB va el journal por defecto (DELETE) con un ``busy_timeout``
generoso.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

BUSY_TIMEOUT_MS = 15000
CONNECT_TIMEOUT_S = 15.0

# Reintentos ante bloqueo. El busy_timeout cubre la mayoria de los casos; esto
# es la red de seguridad para cuando el share tarda en liberar el lock.
MAX_RETRIES = 3
RETRY_DELAY_S = 0.5

_LOCK_MESSAGES = ("database is locked", "database table is locked")


class DatabaseLocked(RuntimeError):
    """La base siguio bloqueada despues de agotar los reintentos."""


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=FULL")


def _is_lock_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return any(m in message for m in _LOCK_MESSAGES)


class Database:
    """Fabrica de conexiones a un archivo SQLite concreto."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.is_file()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Conexion de solo lectura o escritura suelta, en autocommit.

        ``isolation_level=None`` desactiva el manejo implicito de
        transacciones de sqlite3: las escrituras se agrupan explicitamente
        con :meth:`write`.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.path), timeout=CONNECT_TIMEOUT_S, isolation_level=None
        )
        try:
            _configure(conn)
            yield conn
        finally:
            conn.close()

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """Transaccion de escritura con ``BEGIN IMMEDIATE``.

        Toma el lock de escritura al abrir en lugar de a medio camino, que es
        lo que provoca los fallos por 'database is locked' cuando dos equipos
        guardan a la vez.
        """
        with self.connect() as conn:
            last_error: sqlite3.OperationalError | None = None

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    break
                except sqlite3.OperationalError as exc:
                    if not _is_lock_error(exc):
                        raise
                    last_error = exc
                    log.warning(
                        "Base bloqueada (intento %s/%s), reintentando...",
                        attempt,
                        MAX_RETRIES,
                    )
                    time.sleep(RETRY_DELAY_S * attempt)
            else:
                raise DatabaseLocked(
                    "La base de datos esta ocupada por otro equipo. "
                    "Intenta de nuevo en unos segundos."
                ) from last_error

            try:
                yield conn
            except Exception:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    # --- utilidades de lectura -------------------------------------------
    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchone()

    def table_names(self) -> set[str]:
        rows = self.query("SELECT name FROM sqlite_master WHERE type='table'")
        return {row["name"] for row in rows}

    def columns(self, table: str) -> list[str]:
        """Columnas reales de una tabla, en orden de declaracion."""
        with self.connect() as conn:
            rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        return [row["name"] for row in rows]
