"""Corre todas las pruebas y resume.

    python tests/run_all.py            todas
    python tests/run_all.py schema     solo las que empiezan por 'test_schema'

Cada archivo se lanza en su propio proceso: varias necesitan una QApplication y
dos QApplication en el mismo proceso no conviven.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def suites(pattern: str | None) -> list[Path]:
    found = sorted(TESTS.glob("test_*.py"))
    if pattern:
        found = [p for p in found if pattern in p.stem]
    return found


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    files = suites(pattern)
    if not files:
        print(f"No hay pruebas que coincidan con {pattern!r}")
        return 1

    print(f"Corriendo {len(files)} suites con {sys.executable}\n")
    failed: list[str] = []
    started = time.time()

    for path in files:
        begin = time.time()
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True, text=True, cwd=str(TESTS.parent),
        )
        elapsed = time.time() - begin
        last = [line for line in result.stdout.splitlines() if line.strip()]
        summary = last[-1] if last else "(sin salida)"

        mark = "OK  " if result.returncode == 0 else "FALLO"
        print(f"{mark} {path.stem:<28} {elapsed:5.1f}s  {summary}")

        if result.returncode != 0:
            failed.append(path.stem)
            for line in result.stdout.splitlines():
                if line.startswith("FALLO") or line.startswith("  - "):
                    print(f"        {line}")
            if result.stderr.strip():
                for line in result.stderr.strip().splitlines()[-6:]:
                    print(f"        {line}")

    print("\n" + "=" * 70)
    total = time.time() - started
    if failed:
        print(f"FALLARON {len(failed)} de {len(files)} suites "
              f"en {total:.1f}s: {', '.join(failed)}")
        return 1
    print(f"Las {len(files)} suites pasaron en {total:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
