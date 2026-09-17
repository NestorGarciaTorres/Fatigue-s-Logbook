"""Genera la paleta de rigs del tema claro y la guarda en la base.

Por que hace falta una segunda paleta y no vale la que ya hay: **ningun color
puede contrastar 3:1 contra un fondo de fila claro y uno oscuro a la vez.** Las
bandas de luminancia son disjuntas -- contra una fila clara hace falta
L <= 0.267, contra una oscura L >= 0.312 -- asi que la interseccion esta vacia.
Se comprobo barriendo el circulo de tono entero contra tres juegos de fondos
claros distintos: cero candidatos. Los dieciseis colores actuales, que dan
5.34:1 sobre la fila oscura, se quedan en 2.15:1 como mucho sobre blanco.

Por eso la paleta clara va en una **columna nueva**, ``rigs.color_light``, y la
columna ``color`` no se toca. Es deliberado y es lo que mantiene intacta la app
original: su ``CatalogRepository.rigs()`` hace
``SELECT id, name, test_type, color, active``, con las columnas nombradas una a
una, asi que una columna anadida le es invisible. Sigue viendose igual y sus
pruebas de color siguen pasando.

Cada rig conserva su **tono**: el banco que hoy es el verde sigue siendo el
verde en el tema claro, mas oscuro y mas saturado. Un rig se reconoce por el
color, y cambiarselo entre temas seria pedirle al laboratorio que aprenda dos
codigos.

    python tools/generate_light_palette.py --dry-run     # solo enseniar
    python tools/generate_light_palette.py               # escribir

No toca ``PRAGMA user_version``: la cadena de migraciones del proyecto original
se queda donde esta y su runner no ve nada raro.
"""

from __future__ import annotations

import argparse
import colorsys
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bridge  # noqa: E402

bridge.install()

from theme.color import contrast, distance, lab  # noqa: E402
from theme.tokens import PALETTE_LIGHT  # noqa: E402

# Los mismos umbrales medidos que usa la migracion 010 del proyecto original,
# recalibrados contra los fondos de fila del tema claro.
MIN_CONTRAST = 3.0        # el chip tiene que leerse en las tres filas
MIN_VS_RESERVED = 24.0    # y no confundirse con un color de la interfaz

# Separacion entre dos bancos. Se intenta la mayor y se va cediendo hasta la
# primera que permita colocar los dieciseis; el script dice cual consiguio.
# El piso son los 18 de la migracion 010 del proyecto original, que es el
# umbral que ya se acepto ahi tras medirlo -- el catalogo real se queda hoy en
# 20.7 en su par mas cercano. Ceder por debajo seria empeorar lo que hay.
SEPARATION_TARGETS = (26.0, 24.0, 22.0, 20.0, 18.0)
MIN_BETWEEN_RIGS = SEPARATION_TARGETS[-1]

# Cuanto se deja girar el tono para separar dos rigs que en oscuro ya eran
# parecidos. Mas de esto y el banco deja de reconocerse por su color.
#
# Que se cedio, medido: con este giro los dieciseis entran a dE 18, no a 20.
# Seis de los rigs caen en la franja verde-menta (tonos 76, 88, 106, 120, 160 y
# 164 grados) y ademas el verde de 'success' se lleva su propio radio de 24.
# Subiendo el giro a 40 grados si se llega a dE 20 -- pero 40 grados convierten
# un banco verde en uno amarillo verdoso, y entonces el rig deja de
# reconocerse por su color, que es justo lo que esta paleta existe para
# conservar. Entre separar mas y seguir siendo el mismo banco, gana lo segundo:
# 18 es ademas el umbral que la migracion 010 del proyecto original ya acepto
# tras medirlo.
MAX_HUE_DRIFT = 20


def _hsv(color: str) -> tuple[float, float, float]:
    value = color.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)


def _hex(h: float, s: float, v: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


# Claridad a la que se apunta en Lab. Cumplir el contraste no basta para que un
# color se vea bien: los candidatos mas oscuros lo cumplen de sobra y salen
# embarrados (un verde a L* 24 se lee como negro sucio, no como verde). Se
# apunta a media claridad, que es donde un tono se reconoce como tono.
TARGET_LIGHTNESS = 42.0
# Y croma suficiente para que se distinga del gris. Por debajo de esto, dos
# bancos de tonos distintos se ven como dos grises distintos.
MIN_CHROMA = 22.0


def _quality(color: str) -> float:
    """Cuanto se aleja un color del ideal: media claridad y croma suficiente.

    Es una penalizacion, asi que menos es mejor.
    """
    lightness, a, b = lab(color)
    chroma = (a * a + b * b) ** 0.5
    castigo = abs(lightness - TARGET_LIGHTNESS)
    if chroma < MIN_CHROMA:
        castigo += (MIN_CHROMA - chroma) * 2
    return castigo


def _usable(color: str, taken: list[str], palette, separation: float) -> bool:
    """Si un color sirve: legible en las tres filas y lejos de todo lo demas."""
    if min(contrast(color, bg) for bg in palette.row_backgrounds) < MIN_CONTRAST:
        return False
    if any(distance(color, r) < MIN_VS_RESERVED for r in palette.reserved):
        return False
    return all(distance(color, t) >= separation for t in taken)


def _best_for(dark_color: str, taken: list[str], palette,
              separation: float) -> str | None:
    """La version clara de ese color: mismo tono, mas oscuro y mas saturado.

    Se prefiere el candidato que menos gire el tono; a igualdad de giro, el que
    quede **lo mas cerca posible** de lo ya elegido sin bajar del minimo. Suena
    al reves y no lo es: eligiendo el mas lejano, los primeros rigs se comen los
    extremos del espacio disponible y el ultimo verde se queda sin hueco --
    medido, se colocaban 14 de 16--. Empaquetando ajustado entran los dieciseis.
    """
    hue, _, _ = _hsv(dark_color)
    mejor: tuple[float, float, str] | None = None

    for giro in range(0, MAX_HUE_DRIFT + 1):
        for signo in ((0,) if giro == 0 else (-1, 1)):
            h = hue + signo * giro / 360
            for s100 in range(45, 101, 3):
                for v100 in range(25, 86, 3):
                    candidato = _hex(h, s100 / 100, v100 / 100)
                    if not _usable(candidato, taken, palette, separation):
                        continue
                    holgura = min(
                        [distance(candidato, t) for t in taken] or [999.0]
                    )
                    marca = (float(giro), holgura, candidato)
                    if mejor is None or marca < mejor:
                        mejor = marca
        if mejor is not None:
            # Encontrado con el giro mas pequenio posible: no hace falta
            # seguir abriendo el abanico.
            return mejor[-1]
    return None


def _attempt(rigs, palette, separation: float) -> dict | None:
    """Un intento de colocar los dieciseis con esa separacion minima."""
    # Se asignan primero los tonos mas "apretados" --los que tienen vecinos
    # cerca en el circulo-- porque son los que menos sitio tienen para moverse.
    # Dejarlos para el final los deja sin hueco.
    def apretura(entrada) -> float:
        hue = _hsv(entrada[2])[0]
        otros = [_hsv(o[2])[0] for o in rigs if o is not entrada]
        return min((min(abs(hue - h), 1 - abs(hue - h)) for h in otros),
                   default=1.0)

    asignado: dict[tuple[str, str], str] = {}
    taken: list[str] = []
    for nombre, tipo, oscuro in sorted(rigs, key=apretura):
        claro = _best_for(oscuro, taken, palette, separation)
        if claro is None:
            return None
        asignado[(nombre, tipo)] = claro
        taken.append(claro)
    return asignado


def _polish(asignado: dict, rigs, palette, separation: float) -> dict:
    """Mejora cada color sin romper la solucion ya encontrada.

    Colocar y elegir bonito son dos objetivos que se estorban: cuando el
    criterio de calidad entraba en la busqueda, el empaquetado dejaba de
    funcionar y volvian a faltar dos rigs. Asi que primero se coloca --con el
    unico criterio de que quepan los dieciseis-- y despues se recorre la lista
    cambiando cada color por el mejor de su mismo tono que **siga cumpliendo**
    contra todos los demas ya fijados. Como cada cambio se valida contra el
    resto, la solucion nunca deja de ser valida.

    Sin esta pasada salian colores embarrados: un verde a L* 24 (#16400A) se
    lee como negro sucio y deja de identificar al banco.
    """
    oscuro_de = {(n, t): c for n, t, c in rigs}
    mejorado = dict(asignado)

    for clave, actual in asignado.items():
        otros = [c for k, c in mejorado.items() if k != clave]
        hue, _, _ = _hsv(oscuro_de[clave])
        mejor = (_quality(actual), actual)

        for giro in range(0, MAX_HUE_DRIFT + 1):
            for signo in ((0,) if giro == 0 else (-1, 1)):
                h = hue + signo * giro / 360
                for s100 in range(45, 101, 2):
                    for v100 in range(25, 86, 2):
                        candidato = _hex(h, s100 / 100, v100 / 100)
                        if not _usable(candidato, otros, palette, separation):
                            continue
                        marca = (_quality(candidato), candidato)
                        if marca < mejor:
                            mejor = marca
        mejorado[clave] = mejor[1]

    return mejorado


def plan(rigs: list[tuple[str, str, str]],
         palette=PALETTE_LIGHT) -> tuple[dict, float]:
    """``(nombre, tipo, color oscuro)`` -> color claro, y la separacion lograda.

    Se prueba la separacion mas exigente primero y se cede solo lo necesario.
    Devolver cual se consiguio no es un detalle: si un dia hay que anadir un
    rig diecisiete, lo primero que se quiere saber es cuanto margen quedaba.

    Es una funcion pura para que las pruebas puedan comprobar la paleta sin
    escribir nada en ninguna parte.
    """
    for separacion in SEPARATION_TARGETS:
        asignado = _attempt(rigs, palette, separacion)
        if asignado is not None:
            return _polish(asignado, rigs, palette, separacion), separacion

    raise RuntimeError(
        f"No se pudo colocar {len(rigs)} rigs ni con la separacion minima de "
        f"{MIN_BETWEEN_RIGS}. Sube MAX_HUE_DRIFT y vuelve a medir, o revisa si "
        f"el catalogo crecio de mas."
    )


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------

def has_column(database, table: str, column: str) -> bool:
    return column in database.columns(table)


def run(database_path: str | None = None, dry_run: bool = False,
        regenerate: bool = False) -> int:
    from app.config import AppConfig
    from app.db.connection import Database
    from app.services import backup

    config = AppConfig.load()
    ruta = Path(database_path) if database_path else config.database
    database = Database(ruta)

    if not database.exists():
        print(f"No existe la base: {ruta}")
        return 1

    rigs = [
        (row["name"], row["test_type"], row["color"])
        for row in database.query(
            "SELECT name, test_type, color FROM rigs ORDER BY test_type, name"
        )
    ]
    if not rigs:
        print("El catalogo de rigs esta vacio: no hay nada que generar.")
        return 0

    asignado, separacion = plan(rigs)

    print(f"Base: {ruta}")
    print(f"{len(rigs)} rigs, separacion lograda dE >= {separacion:.0f}\n")
    print(f"{'Banco':<12} {'Bitacora':<10} {'oscuro':<9} {'claro':<9} "
          f"contraste claro")
    for nombre, tipo, oscuro in rigs:
        claro = asignado[(nombre, tipo)]
        peor = min(contrast(claro, bg)
                   for bg in PALETTE_LIGHT.row_backgrounds)
        print(f"{nombre:<12} {tipo:<10} {oscuro:<9} {claro:<9} {peor:5.2f} : 1")

    if dry_run:
        print("\n--dry-run: no se escribio nada.")
        return 0

    # El respaldo va antes de tocar la base, no despues. Es la misma regla que
    # el arranque del proyecto original aplica antes de migrar.
    if ruta == config.database:
        copia = backup.pre_migration_backup(ruta, config.backups)
        print(f"\nRespaldo previo: {copia}")

    with database.write() as conn:
        if not has_column(database, "rigs", "color_light"):
            conn.execute("ALTER TABLE rigs ADD COLUMN color_light TEXT")
            print("Columna 'color_light' anadida.")

        escritos = 0
        for (nombre, tipo), claro in asignado.items():
            if regenerate:
                # Se pisa lo que hubiera. Hace falta al cambiar el tema claro:
                # la paleta de bancos se calibra contra SUS fondos de fila y
                # sus colores de interfaz, asi que la anterior ya no vale.
                condicion, extra = "", ()
            else:
                # Solo donde esta vacio: una segunda pasada no pisa lo que
                # alguien haya ajustado a mano desde Ajustes.
                condicion = " AND (color_light IS NULL OR color_light = '')"
                extra = ()
            cursor = conn.execute(
                "UPDATE rigs SET color_light = ? "
                "WHERE name = ? AND test_type = ?" + condicion,
                (claro, nombre, tipo, *extra),
            )
            escritos += cursor.rowcount

    print(f"\n{escritos} rigs actualizados "
          f"({len(asignado) - escritos} ya tenian color claro).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="otra base (para probar en copia)")
    parser.add_argument("--dry-run", action="store_true",
                        help="ensenia la paleta sin escribir nada")
    parser.add_argument("--regenerate", action="store_true",
                        help="pisa los colores claros que ya hubiera; hace "
                             "falta al cambiar la paleta del tema claro")
    parser.add_argument("--table", action="store_true",
                        help="genera la tabla de colores de banco de TODAS las "
                             "familias de paleta y la guarda en theme/")
    args = parser.parse_args()

    if args.table:
        from app.config import AppConfig
        from app.db.connection import Database

        database = Database(Path(args.database) if args.database
                            else AppConfig.load().database)
        rigs = [(r["name"], r["test_type"], r["color"])
                for r in database.query(
                    "SELECT name, test_type, color FROM rigs "
                    "ORDER BY test_type, name")]
        print(f"{len(rigs)} rigs")
        print(f"Tabla escrita en {write_table(rigs)}")
        return 0

    return run(args.database, args.dry_run, args.regenerate)



# ==========================================================================
# Una paleta clara por familia
# ==========================================================================
# No vale con una sola para las cuatro, y esta medido: el acento de 'acero'
# queda a dE 8.7 de uno de los bancos claros calibrados para 'pizarra', y el de
# 'carbon' a 9.6. Ese chip se leeria como un color de interfaz.
#
# Tampoco vale generar una que cumpla contra la union de las cuatro: solo entra
# girando el tono 40 grados, que convierte un banco verde en uno amarillo
# verdoso y rompe justo lo que esta paleta existe para conservar.
#
# Asi que se precalculan las cuatro, una vez, y se guardan en una tabla. Cambiar
# de familia en Ajustes es entonces reescribir 16 celdas, no recalcular nada.

TABLE_FILE = Path(__file__).resolve().parent.parent / "theme" / \
    "rig_light_palettes.json"


def build_table(rigs) -> dict:
    """``familia -> {"banco/tipo": color claro}`` para todas las familias."""
    from theme.tokens import FAMILIES

    tabla: dict[str, dict[str, str]] = {}
    for clave, familia in FAMILIES.items():
        asignado, separacion = plan(rigs, familia.light)
        tabla[clave] = {f"{nombre}/{tipo}": color
                        for (nombre, tipo), color in asignado.items()}
        print(f"  {clave:<10} {len(asignado)} bancos, dE >= {separacion:.0f}")
    return tabla


def write_table(rigs) -> Path:
    import json

    tabla = build_table(rigs)
    TABLE_FILE.write_text(
        json.dumps(tabla, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    return TABLE_FILE

if __name__ == "__main__":
    raise SystemExit(main())
