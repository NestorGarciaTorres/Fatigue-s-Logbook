"""Corre todas las pruebas de la interfaz y resume.

    python tests/run_all.py            todas
    python tests/run_all.py theme      solo las que lleven 'theme' en el nombre

Cada archivo se lanza en su propio proceso: varias necesitan una QApplication y
dos QApplication no conviven en el mismo interprete.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def suites(pattern: str | None) -> list[Path]:
    encontradas = sorted(TESTS.glob("test_*.py"))
    if pattern:
        encontradas = [p for p in encontradas if pattern in p.stem]
    return encontradas


def main() -> int:
    patron = sys.argv[1] if len(sys.argv) > 1 else None
    archivos = suites(patron)
    if not archivos:
        print(f"No hay pruebas que coincidan con {patron!r}")
        return 1

    print(f"Corriendo {len(archivos)} suites con {sys.executable}\n")
    fallidas: list[str] = []
    inicio = time.time()

    for ruta in archivos:
        empezo = time.time()
        resultado = subprocess.run(
            [sys.executable, str(ruta)],
            capture_output=True, text=True, cwd=str(TESTS.parent),
        )
        tardo = time.time() - empezo
        lineas = [l for l in resultado.stdout.splitlines() if l.strip()]
        resumen = lineas[-1] if lineas else "(sin salida)"

        marca = "OK  " if resultado.returncode == 0 else "FALLO"
        print(f"{marca} {ruta.stem:<26} {tardo:5.1f}s  {resumen}")

        if resultado.returncode != 0:
            fallidas.append(ruta.stem)
            for linea in resultado.stdout.splitlines():
                if linea.startswith("FALLO") or linea.startswith("  - "):
                    print(f"        {linea}")
            if resultado.stderr.strip():
                for linea in resultado.stderr.strip().splitlines()[-6:]:
                    print(f"        {linea}")

    print("\n" + "=" * 70)
    if fallidas:
        print(f"FALLARON {len(fallidas)} de {len(archivos)}: "
              f"{', '.join(fallidas)}")
        return 1
    print(f"Las {len(archivos)} suites pasaron en {time.time() - inicio:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
