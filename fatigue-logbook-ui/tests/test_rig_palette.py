"""Las dos paletas de rigs, medidas contra su tema.

Un color de banco no es decoracion: identifica el rig, y de ahi salen la tira
de muestras, la tarjeta de ocupacion y la celda de la bitacora. Tiene que
cumplir tres cosas en el tema donde se use, y las tres se miden aqui:

1. **Leerse** sobre los tres fondos que puede tener una fila.
2. **No confundirse con la interfaz**: si un rig cae cerca del naranja de
   'suspendida' o del color de 'mantenimiento', el chip miente.
3. **No confundirse con otro rig.**

Y una cuarta que es de esta interfaz y no del original: el rig **conserva su
tono** entre temas. El banco que es verde en oscuro sigue siendo verde en
claro. Si no, el laboratorio tendria que aprenderse dos codigos de color.
"""

from __future__ import annotations

import colorsys

import harness  # noqa: F401  (deja sys.path listo)
from harness import Report

from theme.color import contrast, distance
from theme.rig_palette import load_table
from theme.tokens import FAMILIES, PALETTE_DARK, PALETTE_LIGHT
from tools.generate_light_palette import (
    MAX_HUE_DRIFT,
    MIN_BETWEEN_RIGS,
    MIN_CONTRAST,
    MIN_VS_RESERVED,
    plan,
)


def _hue_degrees(color: str) -> float:
    value = color.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def _hue_gap(one: str, other: str) -> float:
    diferencia = abs(_hue_degrees(one) - _hue_degrees(other)) % 360
    return min(diferencia, 360 - diferencia)


def _audit(report: Report, etiqueta: str, colores: dict, palette) -> None:
    """Las tres reglas, sobre una paleta y su tema."""
    peor = min(
        (min(contrast(c, bg) for bg in palette.row_backgrounds), nombre)
        for nombre, c in colores.items()
    )
    report.check(
        f"[{etiqueta}] todo banco se lee en fila, franja y seleccion",
        peor[0] >= MIN_CONTRAST,
        f"peor {peor[0]:.2f} : 1 en {peor[1]}  (minimo {MIN_CONTRAST})",
    )

    peor_reservado = min(
        (distance(c, r), nombre, r)
        for nombre, c in colores.items()
        for r in palette.reserved
    )
    report.check(
        f"[{etiqueta}] ningun banco se confunde con un color de la interfaz",
        peor_reservado[0] >= MIN_VS_RESERVED,
        f"dE {peor_reservado[0]:.1f} entre {peor_reservado[1]} y "
        f"{peor_reservado[2]}  (minimo {MIN_VS_RESERVED})",
    )

    nombres = list(colores)
    pares = [
        (distance(colores[a], colores[b]), a, b)
        for i, a in enumerate(nombres) for b in nombres[i + 1:]
    ]
    peor_par = min(pares)
    report.check(
        f"[{etiqueta}] ningun banco se confunde con otro banco",
        peor_par[0] >= MIN_BETWEEN_RIGS,
        f"dE {peor_par[0]:.1f} entre {peor_par[1]} y {peor_par[2]}  "
        f"(minimo {MIN_BETWEEN_RIGS})",
    )

    report.check(
        f"[{etiqueta}] no hay dos bancos del mismo color",
        len(set(colores.values())) == len(colores),
        f"{len(set(colores.values()))} colores para {len(colores)} bancos",
    )


def main() -> int:
    report = Report("Paletas de rigs")

    context = harness.make_context()
    rigs = [
        (r.name, r.test_type, r.color)
        for r in context.catalog_repository.rigs(active_only=False)
    ]

    report.check("hay catalogo de rigs que medir", bool(rigs),
                 f"{len(rigs)} bancos")
    if not rigs:
        return report.finish()

    oscuros = {f"{n}/{t}": c for n, t, c in rigs}
    asignado, separacion = plan(rigs)
    claros = {f"{n}/{t}": asignado[(n, t)] for n, t, _ in rigs}

    report.section("Paleta oscura: la que ya esta guardada en la base")
    # Se mide contra el tema oscuro NUEVO. La paleta se genero en su dia contra
    # el azul pizarra del tema anterior, asi que no se da por hecho que siga
    # valiendo: se comprueba.
    _audit(report, "oscuro", oscuros, PALETTE_DARK)

    report.section("Paleta clara: la que genera el script")
    report.note(f"separacion lograda: dE >= {separacion:.0f}")
    _audit(report, "claro", claros, PALETTE_LIGHT)

    report.section("El banco se reconoce igual en los dos temas")
    # Un grado de gracia por el redondeo: el generador busca sobre un tono
    # continuo y despues lo cuantiza a un hex de 8 bits por canal, asi que el
    # tono que se vuelve a medir aqui no es exactamente el que se pidio.
    # Sin esta holgura, un banco que giro justo el maximo sale a 20.1 grados.
    REDONDEO = 1.0
    peor_giro = max(
        (_hue_gap(oscuros[k], claros[k]), k) for k in oscuros
    )
    report.check(
        "ningun banco cambia de familia de color al cambiar de tema",
        peor_giro[0] <= MAX_HUE_DRIFT + REDONDEO,
        f"giro maximo {peor_giro[0]:.1f} grados en {peor_giro[1]}  "
        f"(tope {MAX_HUE_DRIFT} mas {REDONDEO:.0f} de redondeo)",
    )

    report.section("La paleta clara es estable")
    otra_vez, otra_separacion = plan(rigs)
    report.check(
        "generar dos veces da exactamente lo mismo",
        otra_vez == asignado and otra_separacion == separacion,
        "el script se puede volver a correr sin cambiar colores",
    )

    report.section("Ningun color sirve para los dos temas a la vez")
    # Es la razon de que haya dos paletas y no una. Si esto dejara de ser
    # cierto, sobraria la mitad del trabajo -- asi que se comprueba en vez de
    # confiar en el comentario.
    sirven = [
        nombre for nombre, c in oscuros.items()
        if min(contrast(c, bg) for bg in PALETTE_LIGHT.row_backgrounds)
        >= MIN_CONTRAST
    ]
    report.check(
        "ningun color oscuro se lee sobre las filas claras",
        not sirven,
        f"mejor caso {max(min(contrast(c, bg) for bg in PALETTE_LIGHT.row_backgrounds) for c in oscuros.values()):.2f} : 1"
        f"  (haria falta {MIN_CONTRAST})",
    )
    sirven_al_reves = [
        nombre for nombre, c in claros.items()
        if min(contrast(c, bg) for bg in PALETTE_DARK.row_backgrounds)
        >= MIN_CONTRAST
    ]
    report.check(
        "ningun color claro se lee sobre las filas oscuras",
        not sirven_al_reves,
        f"mejor caso {max(min(contrast(c, bg) for bg in PALETTE_DARK.row_backgrounds) for c in claros.values()):.2f} : 1",
    )

    report.section("Cada familia tiene su tabla de colores de banco")
    # No vale una sola para las cuatro: el acento de 'acero' cae a dE 8.7 de un
    # banco calibrado para 'pizarra'. La tabla la genera
    # 'generate_light_palette.py --table' y la lee la app al cambiar de paleta.
    tabla = load_table()
    report.check(
        "la tabla existe y cubre las cuatro familias",
        set(tabla) == set(FAMILIES),
        f"familias en la tabla: {sorted(tabla)}",
    )

    for clave, familia in FAMILIES.items():
        colores = tabla.get(clave, {})
        if not colores:
            report.check(f"[{clave}] tiene colores", False, "tabla vacia")
            continue
        faltan = [f"{n}/{t}" for n, t, _ in rigs if f"{n}/{t}" not in colores]
        report.check(f"[{clave}] cubre todos los bancos del catalogo",
                     not faltan, f"faltan {faltan}" if faltan
                     else f"{len(colores)} bancos")
        _audit(report, clave, colores, familia.light)

    report.section("Y ninguna sirve para otra familia")
    # Es la razon de que haya cuatro tablas y no una. Si dejara de ser cierto,
    # sobraria la mitad de esta maquinaria.
    choques = []
    for clave, familia in FAMILIES.items():
        for otra, colores in tabla.items():
            if otra == clave:
                continue
            peor = min(distance(c, r) for c in colores.values()
                       for r in familia.light.reserved)
            if peor < MIN_VS_RESERVED:
                choques.append(f"{otra} en {clave}: dE {peor:.1f}")
    report.check(
        "al menos una tabla choca con la interfaz de otra familia",
        bool(choques),
        f"{len(choques)} choques, p.ej. {choques[0]}" if choques
        else "ninguna choca: sobraria tener cuatro tablas",
    )

    return report.finish()


if __name__ == "__main__":
    raise SystemExit(main())
