"""Las cuatro paletas, medidas.

No se comprueba que los colores existan --eso lo dice el interprete-- sino que
cumplen lo que tienen que cumplir para que la pantalla se lea. Cada
comprobacion lleva la medida en el detalle (``4.61 : 1``, ``dE 44.0``) para que
al fallar se vea cuanto falta y no solo que fallo.

Los umbrales no son inventados: son los mismos que el proyecto original fija en
``tests/test_table_colors.py`` y ``tests/test_maintenance.py``, aplicados ahora
a las **cuatro familias** en sus dos modos -- ocho paletas -- en vez de a una.

Se miden todas y no solo la activa: una familia que se elija en Ajustes dentro
de seis meses tiene que cumplir lo mismo que la de hoy, y nadie se va a acordar
de comprobarlo a mano.
"""

from __future__ import annotations

import harness  # noqa: F401  (deja sys.path listo)
from harness import Report, ratio

from theme import qss
from theme.color import contrast, distance
from theme.tokens import FAMILIES

# --- umbrales, heredados del proyecto original ----------------------------
TEXTO = 4.5          # AA para texto normal
NO_TEXTO = 3.0       # AA para elementos graficos: chips, puntos, bordes
FILA_VS_ALTERNA = 9.0
SELECCION_VS_FILA = 15.0
ENTRE_ESTADOS_DE_FILA = 7.0
ENTRE_SIGNIFICADOS = 24.0


def main() -> int:
    report = Report("Tokens de tema")

    for familia in FAMILIES.values():
      for p in (familia.light, familia.dark):
        nombre = p.name
        report.section(f"{nombre}: texto legible sobre cada superficie")
        for campo in ("bg", "surface", "sunken", "overlay", "row", "row_alt",
                      "selection", "header_bg"):
            fondo = getattr(p, campo)
            valor = contrast(p.text, fondo)
            report.check(
                f"[{nombre}] texto sobre {campo}",
                valor >= TEXTO,
                f"{ratio(valor)}  (minimo {TEXTO})",
            )

        for campo in ("text_secondary", "text_muted"):
            for fondo_campo in ("surface", "bg", "row_alt"):
                valor = contrast(getattr(p, campo), getattr(p, fondo_campo))
                report.check(
                    f"[{nombre}] {campo} sobre {fondo_campo}",
                    valor >= TEXTO,
                    f"{ratio(valor)}  (minimo {TEXTO})",
                )

        valor = contrast(p.text_on_accent, p.accent)
        report.check(f"[{nombre}] texto sobre el color de accion",
                     valor >= TEXTO, f"{ratio(valor)}")
        valor = contrast(p.header_text, p.header_bg)
        report.check(f"[{nombre}] encabezado de tabla legible",
                     valor >= TEXTO, f"{ratio(valor)}")

        # Un campo apagado tiene que verse apagado: si contrasta igual que el
        # texto atenuado, el usuario no distingue lo que puede capturar.
        apagado = contrast(p.text_disabled, p.surface)
        atenuado = contrast(p.text_muted, p.surface)
        report.check(
            f"[{nombre}] lo deshabilitado se ve mas apagado que lo atenuado",
            apagado < atenuado,
            f"deshabilitado {ratio(apagado)} contra atenuado {ratio(atenuado)}",
        )

        report.section(f"Tema {nombre}: estados sobre los tres fondos de fila")
        # Tres fondos y no uno: un chip tiene que leerse en cualquier fila donde
        # caiga. La primera paleta del proyecto anterior se genero contra dos, y
        # al aclarar la franja alterna nueve de dieciseis cayeron por debajo.
        for estado in ("success", "warning", "danger", "info", "maintenance",
                       "accent"):
            color = getattr(p, estado)
            medidas = [contrast(color, fondo) for fondo in p.row_backgrounds]
            peor = min(medidas)
            report.check(
                f"[{nombre}] {estado} legible en fila, franja y seleccion",
                peor >= NO_TEXTO,
                f"peor {ratio(peor)}  (fila {medidas[0]:.2f}, "
                f"franja {medidas[1]:.2f}, seleccion {medidas[2]:.2f})",
            )

        report.section(f"Tema {nombre}: los significados no se confunden")
        # Naranja es 'suspendida', el de mantenimiento es 'el banco esta
        # parado' y el rojo es 'revisar'. Si dos se parecen, el color deja de
        # informar y pasa a estorbar.
        for uno, otro in (("warning", "maintenance"),
                          ("warning", "danger"),
                          ("danger", "maintenance"),
                          ("accent", "warning"),
                          ("accent", "danger")):
            d = distance(getattr(p, uno), getattr(p, otro))
            report.check(
                f"[{nombre}] {uno} se distingue de {otro}",
                d >= ENTRE_SIGNIFICADOS,
                f"dE {d:.1f}  (minimo {ENTRE_SIGNIFICADOS})",
            )

        report.section(f"Tema {nombre}: los estados de fila se distinguen")
        d = distance(p.row, p.row_alt)
        report.check("fila contra franja alterna", d >= FILA_VS_ALTERNA,
                     f"dE {d:.1f}  (minimo {FILA_VS_ALTERNA})")
        d = distance(p.row, p.selection)
        report.check("fila contra seleccion", d >= SELECCION_VS_FILA,
                     f"dE {d:.1f}  (minimo {SELECCION_VS_FILA})")
        estados = {"fila": p.row, "franja": p.row_alt,
                   "seleccion": p.selection, "encabezado": p.header_bg}
        nombres = list(estados)
        for i, uno in enumerate(nombres):
            for otro in nombres[i + 1:]:
                d = distance(estados[uno], estados[otro])
                report.check(
                    f"[{nombre}] {uno} contra {otro}",
                    d >= ENTRE_ESTADOS_DE_FILA,
                    f"dE {d:.1f}  (minimo {ENTRE_ESTADOS_DE_FILA})",
                )

    report.section("La hoja de estilos se deriva del tamano de letra")
    chico = qss.scale(qss.MIN_FONT_PT)
    grande = qss.scale(qss.MAX_FONT_PT)
    for clave in ("heading", "subheading", "small", "metric"):
        report.check(
            f"'{clave}' crece con el tamano base",
            grande[clave] > chico[clave],
            f"{chico[clave]}pt a {qss.MIN_FONT_PT}pt base, "
            f"{grande[clave]}pt a {qss.MAX_FONT_PT}pt",
        )
    report.check(
        "un tamano fuera de rango se recorta en vez de romper",
        qss.clamp_font(99) == qss.MAX_FONT_PT
        and qss.clamp_font(1) == qss.MIN_FONT_PT
        and qss.clamp_font("no es un numero") == qss.BASE_FONT_PT,
        f"99 -> {qss.clamp_font(99)}, 1 -> {qss.clamp_font(1)}, "
        f"texto -> {qss.clamp_font('x')}",
    )

    for familia in FAMILIES.values():
      for p in (familia.light, familia.dark):
        nombre = p.name
        hoja = qss.build(p, qss.BASE_FONT_PT)
        report.check(
            f"[{nombre}] la hoja se construye entera",
            "{" not in hoja.replace("{{", "").replace("}}", "")
            or hoja.count("{") == hoja.count("}"),
            f"{len(hoja):,} caracteres",
        )
        report.check(
            f"[{nombre}] la hoja usa los colores de SU paleta",
            p.accent in hoja and p.row_alt in hoja and p.maintenance in hoja,
            f"accent {p.accent}, franja {p.row_alt}",
        )
        otro = familia.dark if not p.is_dark else familia.light
        # Si un color del otro modo aparece en la hoja, hay un valor escrito a
        # mano en vez de salir de la paleta: justo lo que hace que al cambiar
        # de tema medio widget se quede como estaba.
        #
        # Se descartan los que la paleta activa **tambien** usa: en 'carbon' el
        # fondo claro y el texto oscuro son los dos #FAFAFA, y encontrarlo en
        # la hoja oscura no delata nada -- es su propio color de texto.
        propios = {getattr(p, campo.name) for campo in p.__dataclass_fields__.values()
                   if isinstance(getattr(p, campo.name), str)}
        colados = [c for c in (otro.bg, otro.surface, otro.row, otro.text)
                   if c in hoja and c not in propios]
        report.check(
            f"[{nombre}] no se cuela ningun color del otro tema",
            not colados,
            f"colados: {colados}" if colados else "ninguno",
        )

    return report.finish()


if __name__ == "__main__":
    raise SystemExit(main())
