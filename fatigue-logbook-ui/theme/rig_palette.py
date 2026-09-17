"""El color de cada banco, en el tema que este activo.

La base guarda dos colores por rig: ``color`` (el de siempre, para el tema
oscuro) y ``color_light``, que anade ``tools/generate_light_palette.py``. Hacen
falta los dos porque **ningun color contrasta 3:1 contra una fila clara y una
oscura a la vez** -- las bandas de luminancia son disjuntas y la interseccion
esta vacia.

Por que no se usa ``CatalogService`` del proyecto original: su cache es
``nombre -> color``, con el nombre solo. Y el nombre solo no identifica un
banco -- hay un ``I-25`` en Torsion, otro en Quasi y otro en Rotary, asi que
esos tres colapsan en una sola entrada (16 rigs, 14 entradas). Aqui la clave es
``(nombre, tipo)``, la misma que usan ``rig_usage`` y ``maintenance``.

Se lee con ``app.db.connection.Database`` y no con ``sqlite3`` a pelo: esa capa
es la que esta afinada para que la base viva en un recurso de red.
"""

from __future__ import annotations

import colorsys
import json
import logging
from pathlib import Path

from theme.color import contrast
from theme.manager import theme
from theme.tokens import FAMILIES, palette_for

log = logging.getLogger(__name__)

# El mismo minimo que exige la paleta generada: un chip tiene que leerse sobre
# los tres fondos que puede tener una fila.
MIN_CONTRAST = 3.0

FALLBACK = "#7C7C7C"

# La tabla que genera ``tools/generate_light_palette.py --table``: un color
# claro por banco y por familia de paleta. Hace falta una por familia porque el
# acento de una cae encima de un banco calibrado para otra --medido, dE 8.7--
# y ese chip se leeria como un color de interfaz.
TABLE_FILE = Path(__file__).resolve().parent / "rig_light_palettes.json"


def load_table() -> dict:
    """La tabla precalculada, o vacia si todavia no se ha generado."""
    if not TABLE_FILE.is_file():
        return {}
    try:
        return json.loads(TABLE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        log.warning("No se pudo leer %s: %s", TABLE_FILE, error)
        return {}


def derive_light(dark_color: str, family: str | None = None) -> str:
    """Version clara de un color oscuro, cuando la base no la tiene.

    Es la red de seguridad para un rig dado de alta despues de correr el
    generador, o para una base donde no se corrio nunca: la app tiene que
    dibujar algo legible igual, no un chip invisible.

    Conserva el tono y baja la claridad hasta alcanzar el contraste. No
    sustituye al generador, que ademas separa los colores entre si; esto solo
    garantiza que se vea.
    """
    try:
        value = dark_color.lstrip("#")
        r, g, b = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return FALLBACK

    claro = palette_for(family or theme().family, "light")
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = min(1.0, max(s, 0.55))

    for paso in range(0, 61):
        candidato_v = max(0.18, v - paso * 0.012)
        rr, gg, bb = colorsys.hsv_to_rgb(h, s, candidato_v)
        candidato = "#%02X%02X%02X" % (
            round(rr * 255), round(gg * 255), round(bb * 255)
        )
        if min(contrast(candidato, bg)
               for bg in claro.row_backgrounds) >= MIN_CONTRAST:
            return candidato
    return FALLBACK


class RigPalette:
    """Los dos colores de cada banco, cacheados.

    Se recarga cuando se recarga el catalogo, no en cada pintado: la base vive
    en un recurso de red y un delegado pinta cientos de celdas por segundo.
    """

    def __init__(self, database):
        self.database = database
        self._colors: dict[tuple[str, str], tuple[str, str]] = {}
        self._by_name: dict[str, tuple[str, str]] = {}
        self.load()

    # --- carga -----------------------------------------------------------
    def load(self) -> None:
        self._colors = {}
        self._by_name = {}

        tiene_claro = "color_light" in self.database.columns("rigs")
        columnas = "name, test_type, color" + (
            ", color_light" if tiene_claro else ""
        )
        try:
            filas = self.database.query(f"SELECT {columnas} FROM rigs")
        except Exception as error:            # pragma: no cover - red caida
            log.warning("No se pudieron leer los colores de rig: %s", error)
            return

        for fila in filas:
            oscuro = fila["color"] or FALLBACK
            claro = (fila["color_light"] if tiene_claro else None) or \
                derive_light(oscuro)
            par = (oscuro, claro)
            self._colors[(fila["name"], fila["test_type"])] = par
            # Segundo indice por nombre, para los sitios que no saben de que
            # bitacora es el banco -- la columna test_rigN de Fatiga guarda el
            # nombre a secas. Si hay varios tipos con ese nombre gana el
            # primero, que es lo que ya hacia el proyecto original.
            self._by_name.setdefault(fila["name"], par)

    # --- consulta --------------------------------------------------------
    def pair(self, name: str | None,
             test_type: str | None = None) -> tuple[str, str] | None:
        """``(oscuro, claro)`` de ese banco, o None si no esta en el catalogo."""
        if not name:
            return None
        if test_type is not None:
            par = self._colors.get((name, test_type))
            if par is not None:
                return par
        return self._by_name.get(name)

    def color(self, name: str | None,
              test_type: str | None = None) -> str | None:
        """El color del banco **en el tema activo**.

        Se resuelve al pedirlo y no se guarda en ninguna constante: es lo que
        hace que cambiar de tema repinte los chips sin reiniciar.
        """
        par = self.pair(name, test_type)
        if par is None:
            return None
        return par[0] if theme().is_dark else par[1]

    def colors(self, test_type: str | None = None) -> dict[str, str]:
        """``nombre -> color del tema activo``, para reportes y leyendas."""
        oscuro = theme().is_dark
        if test_type is None:
            return {n: (par[0] if oscuro else par[1])
                    for n, par in self._by_name.items()}
        return {
            nombre: (par[0] if oscuro else par[1])
            for (nombre, tipo), par in self._colors.items()
            if tipo == test_type
        }

    def known(self, name: str | None, test_type: str | None = None) -> bool:
        return self.pair(name, test_type) is not None

    # --- escritura -------------------------------------------------------
    def set_color(self, name: str, test_type: str, dark: str,
                  light: str | None = None) -> None:
        """Guarda las dos variantes de un banco.

        Siempre las dos. Guardar solo la oscura dejaria al rig con un color
        claro que ya no corresponde a su tono, y el banco se veria de un color
        en un tema y de otro distinto en el otro.
        """
        claro = light or derive_light(dark)
        with self.database.write() as conn:
            self._ensure_column(conn)
            conn.execute(
                "UPDATE rigs SET color = ?, color_light = ? "
                "WHERE name = ? AND test_type = ?",
                (dark, claro, name, test_type),
            )
        self.load()

    def _ensure_column(self, conn) -> None:
        if "color_light" not in self.database.columns("rigs"):
            conn.execute("ALTER TABLE rigs ADD COLUMN color_light TEXT")

    def apply_family(self, family: str) -> int:
        """Reescribe los colores claros con los de esa familia de paleta.

        Devuelve cuantos bancos se actualizaron.

        Hace falta porque el color claro de un banco **depende de la familia**:
        el acento de 'acero' queda a dE 8.7 de un banco calibrado para
        'pizarra', y ese chip se leeria como un color de interfaz. Como las
        cuatro estan precalculadas en ``rig_light_palettes.json``, cambiar de
        familia es reescribir dieciseis celdas y no recalcular nada -- que es la
        diferencia entre un cambio instantaneo y uno de doce segundos.

        Un banco que no este en la tabla --dado de alta despues de generarla--
        se resuelve con ``derive_light``: se vera legible aunque no este tan
        separado de los demas como los generados.
        """
        tabla = load_table().get(family)
        if not tabla:
            log.warning("No hay colores precalculados para la familia '%s'",
                        family)
            return 0

        escritos = 0
        with self.database.write() as conn:
            self._ensure_column(conn)
            for (nombre, tipo), (oscuro, _) in self._colors.items():
                claro = tabla.get(f"{nombre}/{tipo}") \
                    or derive_light(oscuro, family)
                cursor = conn.execute(
                    "UPDATE rigs SET color_light = ? "
                    "WHERE name = ? AND test_type = ?",
                    (claro, nombre, tipo),
                )
                escritos += cursor.rowcount
        self.load()
        return escritos
