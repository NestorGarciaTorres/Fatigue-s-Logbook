"""Compara los archivos .db y ayuda a elegir cual es el bueno.

En ``db/`` hay 17 archivos y en ``db backups/`` otros 9, con nombres como
``test_records-DLCELPC303-2.db``: copias de conflicto que genera OneDrive
cuando dos equipos escriben el mismo archivo sincronizado.

Este script es de solo lectura. Imprime un resumen de cada archivo para que se
pueda decidir cual conservar. Con ``--archive`` mueve el resto a
``db/_conflictos/`` sin borrar nada.

    python tools/pick_database.py
    python tools/pick_database.py --archive db/test_records.db
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import dates  # noqa: E402
from app.config import PROJECT_ROOT  # noqa: E402

TEST_TABLES = ("fatigue_tests", "rotary_tests", "torsion_tests", "quasi_tests")
DATE_COLUMNS = {
    "fatigue_tests": ("end_date", "start_date"),
    "rotary_tests": ("end_date", "start_date"),
    "torsion_tests": ("test_date",),
    "quasi_tests": ("test_date",),
}


def find_databases() -> list[Path]:
    roots = [PROJECT_ROOT / "db", PROJECT_ROOT / "db backups"]
    found: list[Path] = []
    for root in roots:
        if root.is_dir():
            found.extend(sorted(p for p in root.rglob("*.db") if p.is_file()))
    return found


def inspect(path: Path) -> dict:
    """Resumen de un archivo. Nunca escribe."""
    report = {
        "path": path,
        "size": path.stat().st_size,
        "tables": {},
        "total_rows": 0,
        "latest": None,
        "error": None,
        "notes": [],
    }

    if report["size"] == 0:
        report["error"] = "archivo vacio (0 bytes)"
        return report

    try:
        # mode=ro garantiza que no se toque el archivo. as_uri() produce la
        # forma file:///C:/... que SQLite entiende en Windows.
        uri = f"{path.as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        report["error"] = f"no se pudo abrir: {exc}"
        return report

    try:
        existing = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        latest: str | None = None
        for table in TEST_TABLES:
            if table not in existing:
                continue

            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            max_id = conn.execute(f"SELECT MAX(id) FROM {table}").fetchone()[0]
            report["tables"][table] = {"rows": count, "max_id": max_id}
            report["total_rows"] += count

            # Los respaldos mas viejos traen el esquema anterior: rotary_tests
            # tenia test_date en lugar de start_date/end_date. No estan
            # corruptos, solo hay que mirar las columnas que si existen.
            present = {
                r["name"]
                for r in conn.execute(f'PRAGMA table_info("{table}")')
            }
            usable = [c for c in DATE_COLUMNS[table] if c in present]
            if not usable:
                report["notes"].append(f"{table}: esquema anterior")
                continue

            for column in usable:
                rows = conn.execute(
                    f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"
                ).fetchall()
                for row in rows:
                    parsed = dates.from_db(row[0])
                    if parsed and (latest is None or parsed.isoformat() > latest):
                        latest = parsed.isoformat()

        report["latest"] = latest
    except sqlite3.DatabaseError as exc:
        report["error"] = f"base ilegible o corrupta: {exc}"
    finally:
        conn.close()

    return report


def print_report(reports: list[dict]) -> None:
    print()
    print(f"{'ARCHIVO':<52} {'FILAS':>7} {'MAX ID':>8} {'ULTIMA FECHA':>14}")
    print("-" * 86)

    for report in reports:
        relative = report["path"].relative_to(PROJECT_ROOT)
        if report["error"]:
            print(f"{str(relative):<52} {report['error']}")
            continue

        max_id = max(
            (t["max_id"] or 0 for t in report["tables"].values()), default=0
        )
        latest = report["latest"] or "-"
        note = f"   ({'; '.join(report['notes'])})" if report["notes"] else ""
        print(
            f"{str(relative):<52} {report['total_rows']:>7} "
            f"{max_id:>8} {latest:>14}{note}"
        )

    print()
    print("Detalle por tabla del candidato con mas registros:")
    valid = [r for r in reports if not r["error"]]
    if not valid:
        print("  (ningun archivo legible)")
        return

    best = max(valid, key=lambda r: (r["total_rows"], r["latest"] or ""))
    print(f"  {best['path'].relative_to(PROJECT_ROOT)}")
    for table, info in best["tables"].items():
        print(f"    {table:<16} {info['rows']:>6} filas   max id {info['max_id']}")
    print()
    print("Revisa el resumen y confirma cual conservar. Para archivar el resto:")
    print(f"  python tools/pick_database.py --archive "
          f"\"{best['path'].relative_to(PROJECT_ROOT)}\"")


def archive_others(chosen: Path, reports: list[dict]) -> None:
    chosen = chosen.resolve()
    target_dir = PROJECT_ROOT / "db" / "_conflictos" / datetime.now().strftime("%Y-%m-%d")
    target_dir.mkdir(parents=True, exist_ok=True)

    moved = 0
    for report in reports:
        path = report["path"].resolve()
        if path == chosen:
            continue
        # Los respaldos fechados se dejan donde estan: son historial, no
        # conflictos.
        if "db backups" in path.parts:
            continue

        destination = target_dir / path.name
        shutil.move(str(path), str(destination))
        moved += 1
        print(f"  movido: {path.name}")

    print(f"\n{moved} archivo(s) archivados en {target_dir.relative_to(PROJECT_ROOT)}")
    print(f"Conservado: {chosen.relative_to(PROJECT_ROOT)}")
    print("\nActualiza settings.json si la ruta elegida no es la predeterminada.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        metavar="RUTA_DB",
        help="archiva todos los .db de db/ salvo el indicado",
    )
    args = parser.parse_args()

    databases = find_databases()
    if not databases:
        print("No se encontraron archivos .db")
        return 1

    reports = [inspect(path) for path in databases]
    print_report(reports)

    if args.archive:
        chosen = Path(args.archive)
        if not chosen.is_absolute():
            chosen = PROJECT_ROOT / chosen
        if not chosen.is_file():
            print(f"\nERROR: no existe {chosen}")
            return 1

        print(f"\nArchivando los demas .db de db/ ...")
        archive_others(chosen, reports)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
