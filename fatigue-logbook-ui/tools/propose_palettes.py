"""Propuestas de paleta, medidas y renderizadas sobre la pantalla real.

No es codigo de la app: es la herramienta para **elegir** el tema. Define
varios candidatos, los pasa por las mismas comprobaciones que
``tests/test_tokens.py`` y despues dibuja la bitacora de Fatiga con cada uno,
en claro y en oscuro, con los datos de verdad.

Elegir un tema mirando cuadraditos de color no funciona: lo que importa es como
se lee una tabla de once filas con chips, semaforo y franja alterna. Por eso se
renderiza la pantalla entera.

    python tools/propose_palettes.py            mide y renderiza
    python tools/propose_palettes.py --measure  solo mide (rapido)

Lo que **no** se mueve entre propuestas: los dieciseis colores de banco del
tema oscuro, que estan guardados en la base y son la identidad de cada rig. El
acento y los estados de cada propuesta tienen que mantenerse a dE 24 de todos
ellos, y eso es lo primero que se comprueba.

La paleta clara de bancos si se recalcula para cada propuesta, porque depende
de los fondos de fila y de los colores de interfaz de esa propuesta.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bridge  # noqa: E402

bridge.install()

from theme.color import contrast, distance  # noqa: E402
from theme.tokens import PALETTE_DARK, PALETTE_LIGHT, Palette  # noqa: E402
from tools.generate_light_palette import plan  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "_propuestas"

TEXTO = 4.5
NO_TEXTO = 3.0
ENTRE_SIGNIFICADOS = 24.0
FILA_VS_ALTERNA = 9.0
SELECCION_VS_FILA = 15.0
# Entre dos fondos de fila cualesquiera, incluido el encabezado.
ENTRE_FONDOS = 7.0


# ==========================================================================
# Las propuestas
# ==========================================================================

def _pair(name, light_kwargs, dark_kwargs):
    return (Palette(name=f"{name}-light", is_dark=False, **light_kwargs),
            Palette(name=f"{name}-dark", is_dark=True, **dark_kwargs))


# --- 0. La actual: piedra e indigo ----------------------------------------
ACTUAL = (PALETTE_LIGHT, PALETTE_DARK)


# --- 1. Acero: grises frios y azul de instrumento -------------------------
# La mas cercana a lo que es la app: un instrumento de laboratorio. Neutros
# gris azulado, sin calidez, y un azul de accion que se lee como control y no
# como decoracion. Bordes definidos y superficies planas.
ACERO = _pair(
    "acero",
    dict(
        bg="#F2F5F7", surface="#FFFFFF", sunken="#E6EBF0", overlay="#FFFFFF",
        text="#101828", text_secondary="#475467", text_muted="#4D5969",
        text_disabled="#A9B4C0", text_on_accent="#FFFFFF",
        border="#D6DEE6", divider="#E8EDF2",
        accent="#0B5FD1", accent_hover="#0A4FAE", accent_pressed="#08408C",
        accent_soft="#E4EDFB",
        success="#0F7A4A", warning="#B45309", danger="#C0123C",
        info="#0E7490", maintenance="#9333EA",
        row="#FFFFFF", row_alt="#E6EBF0", selection="#D6E4FA",
        header_bg="#C9D4E0", header_text="#0A4FAE", grid="#DFE6EE",
        shadow="#0E1E3322",
    ),
    dict(
        bg="#0E1419", surface="#18212A", sunken="#090E12", overlay="#1F2A34",
        text="#F2F6FA", text_secondary="#C4D0DC", text_muted="#A3B2C2",
        text_disabled="#5E6B7A", text_on_accent="#08131F",
        border="#2C3A47", divider="#222E39",
        accent="#4FA3F7", accent_hover="#78BAFA", accent_pressed="#3A86D8",
        accent_soft="#132436",
        success="#3FBF6F", warning="#FBBF24", danger="#FB7185",
        info="#67E8F9", maintenance="#E879F9",
        row="#18212A", row_alt="#26333F", selection="#123152",
        header_bg="#0B1218", header_text="#78BAFA", grid="#2C3A47",
        shadow="#00000066",
    ),
)


# --- 2. Pizarra: gris verdoso y azul apagado ------------------------------
# Neutros con una pizca de verde, que bajan la tension de una pantalla que se
# mira ocho horas, y un azul de accion sin estridencia. Es la propuesta mas
# tranquila: nada compite con los colores de los bancos, que son lo que hay
# que leer.
#
# Nacio con un teal de accion y hubo que cambiarlo: medido, un acento teal mas
# el verde de success se llevan por delante la franja verde-menta donde caen
# seis de los dieciseis bancos, y entonces la paleta clara de rigs ya no cabe.
# El teal es bonito en esta app y no se puede usar.
PIZARRA = _pair(
    "pizarra",
    dict(
        bg="#F1F4F2", surface="#FFFFFF", sunken="#E5EAE7", overlay="#FFFFFF",
        text="#14201C", text_secondary="#44554E", text_muted="#4B5C55",
        text_disabled="#A6B3AD", text_on_accent="#FFFFFF",
        border="#D5DEDA", divider="#E7ECE9",
        accent="#2F5D8A", accent_hover="#264C72", accent_pressed="#1D3B59",
        accent_soft="#E2EAF3",
        success="#166534", warning="#B45309", danger="#BE123C",
        info="#7C3AED", maintenance="#A21CAF",
        row="#FFFFFF", row_alt="#E5EAE7", selection="#D2E8E8",
        header_bg="#C6D2CD", header_text="#0C5A5C", grid="#DDE5E1",
        shadow="#0C201B22",
    ),
    dict(
        bg="#101614", surface="#1B2422", sunken="#0A100E", overlay="#232D2A",
        text="#F3F7F5", text_secondary="#C8D4CF", text_muted="#A5B3AD",
        text_disabled="#60706A", text_on_accent="#061615",
        border="#2E3A36", divider="#242E2B",
        accent="#8FB6DD", accent_hover="#AECBE9", accent_pressed="#6E9AC4",
        accent_soft="#18242E",
        success="#5FBF6F", warning="#FBBF24", danger="#FB7185",
        info="#C4A6FA", maintenance="#E879F9",
        row="#1B2422", row_alt="#2A3633", selection="#123A38",
        header_bg="#0D1211", header_text="#6FDCD6", grid="#2E3A36",
        shadow="#00000066",
    ),
)


# --- 3. Carbon: papel y tinta, con violeta de mas presencia ---------------
# La de mas contraste: papel casi blanco puro contra tinta casi negra, neutros
# sin temperatura y un violeta mas saturado que el actual. Es la que mas
# "producto" parece y la que mas fuerte marca la jerarquia; tambien la que mas
# cansa si la pantalla se mira todo el dia.
CARBON = _pair(
    "carbon",
    dict(
        bg="#FAFAFA", surface="#FFFFFF", sunken="#F0F0F0", overlay="#FFFFFF",
        text="#0A0A0A", text_secondary="#525252", text_muted="#646464",
        text_disabled="#ABABAB", text_on_accent="#FFFFFF",
        border="#DCDCDC", divider="#EBEBEB",
        accent="#6D28D9", accent_hover="#5B21B6", accent_pressed="#4C1D95",
        accent_soft="#EFE7FD",
        success="#15803D", warning="#B45309", danger="#BE123C",
        info="#0369A1", maintenance="#BE185D",
        row="#FFFFFF", row_alt="#EDEDED", selection="#E4DAFB",
        header_bg="#D4D4D4", header_text="#5B21B6", grid="#E4E4E4",
        shadow="#00000026",
    ),
    dict(
        bg="#0C0C0D", surface="#171718", sunken="#070708", overlay="#1F1F21",
        text="#FAFAFA", text_secondary="#D4D4D4", text_muted="#B0B0B0",
        text_disabled="#666666", text_on_accent="#0C0A16",
        border="#2E2E30", divider="#232325",
        accent="#A78BFA", accent_hover="#C4B5FD", accent_pressed="#8B5CF6",
        accent_soft="#1F1A33",
        success="#3FBF6F", warning="#FBBF24", danger="#FB7185",
        info="#38BDF8", maintenance="#F472B6",
        row="#171718", row_alt="#2A2A2C", selection="#241E42",
        header_bg="#0A0A0B", header_text="#C4B5FD", grid="#2E2E30",
        shadow="#00000077",
    ),
)


FINALES: dict = {}

PROPOSALS = {
    "actual": ("Piedra e índigo (la actual)", ACTUAL),
    "acero": ("Acero: grises fríos y azul de instrumento", ACERO),
    "pizarra": ("Pizarra: gris verdoso y azul apagado", PIZARRA),
    "carbon": ("Carbón: papel y tinta, violeta con presencia", CARBON),
}


# ==========================================================================
# Medicion
# ==========================================================================

def measure(clave: str, titulo: str, par, rigs) -> list[str]:
    """Devuelve la lista de fallos. Vacia significa que la propuesta sirve."""
    claro, oscuro = par
    fallos: list[str] = []
    oscuros = [c for _, _, c in rigs]

    for paleta in (claro, oscuro):
        etiqueta = "claro" if not paleta.is_dark else "oscuro"

        for campo in ("bg", "surface", "sunken", "row", "row_alt", "selection",
                      "header_bg"):
            valor = contrast(paleta.text, getattr(paleta, campo))
            if valor < TEXTO:
                fallos.append(f"{etiqueta}: texto sobre {campo} {valor:.2f}:1")
        for campo in ("text_secondary", "text_muted"):
            for fondo in ("surface", "bg", "row_alt"):
                valor = contrast(getattr(paleta, campo), getattr(paleta, fondo))
                if valor < TEXTO:
                    fallos.append(
                        f"{etiqueta}: {campo} sobre {fondo} {valor:.2f}:1")

        valor = contrast(paleta.text_on_accent, paleta.accent)
        if valor < TEXTO:
            fallos.append(f"{etiqueta}: texto sobre accent {valor:.2f}:1")
        valor = contrast(paleta.header_text, paleta.header_bg)
        if valor < TEXTO:
            fallos.append(f"{etiqueta}: encabezado {valor:.2f}:1")

        for estado in ("success", "warning", "danger", "info", "maintenance",
                       "accent"):
            peor = min(contrast(getattr(paleta, estado), bg)
                       for bg in paleta.row_backgrounds)
            if peor < NO_TEXTO:
                fallos.append(f"{etiqueta}: {estado} en fila {peor:.2f}:1")

        for uno, otro in (("warning", "maintenance"), ("warning", "danger"),
                          ("danger", "maintenance"), ("accent", "warning"),
                          ("accent", "danger"), ("accent", "info")):
            d = distance(getattr(paleta, uno), getattr(paleta, otro))
            if d < ENTRE_SIGNIFICADOS:
                fallos.append(f"{etiqueta}: {uno} vs {otro} dE {d:.1f}")

        d = distance(paleta.row, paleta.row_alt)
        if d < FILA_VS_ALTERNA:
            fallos.append(f"{etiqueta}: fila vs franja dE {d:.1f}")
        d = distance(paleta.row, paleta.selection)
        if d < SELECCION_VS_FILA:
            fallos.append(f"{etiqueta}: fila vs seleccion dE {d:.1f}")

    # Lo que no se puede negociar: los bancos del tema oscuro estan guardados
    # en la base y no se tocan, asi que es la propuesta la que tiene que
    # apartarse de ellos.
    for estado in ("accent", "success", "warning", "danger", "info",
                   "maintenance"):
        color = getattr(oscuro, estado)
        d = min(distance(color, r) for r in oscuros)
        if d < ENTRE_SIGNIFICADOS:
            fallos.append(f"oscuro: {estado} choca con un banco, dE {d:.1f}")

    return fallos


# ==========================================================================
# Reparacion
# ==========================================================================
# Una propuesta se escribe a ojo y despues se mide; lo normal es que algo
# choque. Repararla a mano es un bucle de adivinar hexadecimales, asi que se
# hace midiendo: para cada color en conflicto se busca el mas cercano **en su
# propia familia de tono** que si cumpla. Asi la propuesta conserva su caracter
# --un azul sigue siendo azul-- y deja de mentir.

import colorsys  # noqa: E402


def _hsv(color: str):
    v = color.lstrip("#")
    r, g, b = (int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)


def _hex(h, s, v) -> str:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)),
                                  max(0.0, min(1.0, v)))
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def _nearest_usable(original: str, evitar: list[str], fondos,
                    drift: int = 26) -> str | None:
    """El color mas parecido al original que se lee y no choca con nada.

    Se prefiere el que menos se aleje del original en Lab: la propuesta la
    escribio alguien con una intencion, y la reparacion tiene que respetarla lo
    mas posible.
    """
    hue, sat, val = _hsv(original)
    mejor = None
    for giro in range(0, drift + 1, 2):
        for signo in ((0,) if giro == 0 else (-1, 1)):
            h = hue + signo * giro / 360
            for s100 in range(30, 101, 4):
                for v100 in range(35, 101, 4):
                    candidato = _hex(h, s100 / 100, v100 / 100)
                    if min(contrast(candidato, bg) for bg in fondos) < NO_TEXTO:
                        continue
                    if any(distance(candidato, x) < ENTRE_SIGNIFICADOS
                           for x in evitar):
                        continue
                    coste = distance(candidato, original)
                    if mejor is None or coste < mejor[0]:
                        mejor = (coste, candidato)
    return mejor[1] if mejor else None


def _separate(base: str, otro: str, objetivo: float) -> str:
    """Aleja ``otro`` de ``base`` moviendole la claridad hasta la distancia
    pedida. Es lo que arregla una franja alterna que no se distingue."""
    hue, sat, val = _hsv(otro)
    base_val = _hsv(base)[2]
    paso = 0.012 if val >= base_val else -0.012
    for intento in range(80):
        candidato = _hex(hue, sat, val + paso * intento)
        if distance(base, candidato) >= objetivo:
            return candidato
    return otro


def repair(par, rigs, verbose: bool = True):
    """Devuelve la propuesta con lo que chocaba ya corregido, y los cambios."""
    from dataclasses import replace

    claro, oscuro = par
    oscuros = [c for _, _, c in rigs]
    cambios: list[str] = []

    nuevas = []
    for paleta in (claro, oscuro):
        etiqueta = "claro" if not paleta.is_dark else "oscuro"
        ajustes: dict = {}

        # 1. Los fondos de fila, que tienen que distinguirse entre si.
        fila = paleta.row
        franja = paleta.row_alt
        if distance(fila, franja) < FILA_VS_ALTERNA:
            franja = _separate(fila, franja, FILA_VS_ALTERNA + 0.5)
            ajustes["row_alt"] = franja
            cambios.append(f"{etiqueta}: franja alterna "
                           f"{paleta.row_alt} -> {franja}")
        seleccion = paleta.selection
        if distance(fila, seleccion) < SELECCION_VS_FILA:
            seleccion = _separate(fila, seleccion, SELECCION_VS_FILA + 0.5)
            ajustes["selection"] = seleccion
            cambios.append(f"{etiqueta}: seleccion "
                           f"{paleta.selection} -> {seleccion}")

        # Y contra el encabezado. Separar la seleccion solo de la fila y de la
        # franja no basta: en la primera pasada de 'pizarra' quedo a dE 5.0 del
        # encabezado, asi que una fila seleccionada se confundia con la cabecera
        # de la tabla. Los cuatro fondos tienen que distinguirse entre si, los
        # seis pares.
        estados = {"row": fila, "row_alt": franja, "selection": seleccion,
                   "header_bg": paleta.header_bg}
        nombres = list(estados)
        for i, uno in enumerate(nombres):
            for otro in nombres[i + 1:]:
                if distance(estados[uno], estados[otro]) >= ENTRE_FONDOS:
                    continue
                # Se mueve la seleccion si esta en el par; es el unico de los
                # cuatro que no tiene un significado estructural fijo.
                movible = "selection" if "selection" in (uno, otro) else otro
                antes = estados[movible]
                base = estados[uno if movible == otro else otro]
                nuevo = _separate(base, antes, ENTRE_FONDOS + 0.5)
                estados[movible] = nuevo
                ajustes[movible] = nuevo
                cambios.append(f"{etiqueta}: {movible} {antes} -> {nuevo} "
                               f"(se confundia con {uno if movible == otro else otro})")
        franja, seleccion = estados["row_alt"], estados["selection"]

        fondos = (fila, franja, seleccion)

        # 2. Los colores con significado. En el tema oscuro compiten ademas
        #    con los dieciseis bancos guardados, que no se pueden mover.
        prohibidos_base = list(oscuros) if paleta.is_dark else []
        orden = ("accent", "warning", "danger", "success", "info",
                 "maintenance")
        elegidos: dict[str, str] = {}
        for estado in orden:
            actual = ajustes.get(estado, getattr(paleta, estado))
            evitar = prohibidos_base + list(elegidos.values())
            choca = (min(contrast(actual, bg) for bg in fondos) < NO_TEXTO
                     or any(distance(actual, x) < ENTRE_SIGNIFICADOS
                            for x in evitar))
            if not choca:
                elegidos[estado] = actual
                continue
            reparado = _nearest_usable(actual, evitar, fondos)
            if reparado is None:
                cambios.append(f"{etiqueta}: {estado} SIN ARREGLO posible")
                elegidos[estado] = actual
                continue
            elegidos[estado] = reparado
            ajustes[estado] = reparado
            cambios.append(f"{etiqueta}: {estado} {actual} -> {reparado}")

        nuevas.append(replace(paleta, **ajustes) if ajustes else paleta)

    if verbose and cambios:
        print(f"  reparado ({len(cambios)}):")
        for cambio in cambios:
            print(f"    · {cambio}")
    return (nuevas[0], nuevas[1]), cambios


def light_rigs(par, rigs):
    """La paleta clara de bancos que le tocaria a esta propuesta."""
    claro, _ = par
    asignado, separacion = plan(rigs, claro)
    return asignado, separacion


# ==========================================================================
# Render
# ==========================================================================

def render(clave: str, par, asignado, rigs) -> list[Path]:
    from PySide6.QtWidgets import QApplication

    from theme import manager, tokens
    from window import MainWindow

    claro, oscuro = par
    # Se sustituyen las paletas del gestor por las de la propuesta. Es una
    # herramienta de eleccion, no la app: aqui si vale tocar el diccionario.
    tokens.PALETTES[tokens.LIGHT] = claro
    tokens.PALETTES[tokens.DARK] = oscuro

    app = QApplication.instance() or QApplication(sys.argv)
    manager.theme().attach(app)

    context, _ = bridge.build_context()
    ventana = MainWindow(context)

    # Y los colores de banco del tema claro, que dependen de la propuesta.
    for (nombre, tipo, oscuro_hex) in rigs:
        ventana.rig_palette._colors[(nombre, tipo)] = (
            oscuro_hex, asignado[(nombre, tipo)])
        ventana.rig_palette._by_name.setdefault(
            nombre, (oscuro_hex, asignado[(nombre, tipo)]))

    ventana.start()
    for _ in range(40):
        app.processEvents()
    ventana.grab()   # el primer grab de un proceso sale en blanco

    OUT.mkdir(parents=True, exist_ok=True)
    hechas = []
    for nombre_tema in (tokens.LIGHT, tokens.DARK):
        manager.theme().set_theme(nombre_tema)
        ventana.sidebar.update_theme_button()
        for _ in range(40):
            app.processEvents()
        destino = OUT / f"{clave}_{nombre_tema}.png"
        ventana.grab().save(str(destino))
        hechas.append(destino)
    ventana.close()
    return hechas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measure", action="store_true",
                        help="solo mide, sin renderizar")
    parser.add_argument("--only", help="una sola propuesta, por su clave")
    args = parser.parse_args()

    from app.db.connection import Database
    from app.config import AppConfig

    database = Database(AppConfig.load().database)
    rigs = [(r["name"], r["test_type"], r["color"])
            for r in database.query(
                "SELECT name, test_type, color FROM rigs "
                "ORDER BY test_type, name")]

    claves = [args.only] if args.only else list(PROPOSALS)
    for clave in claves:
        titulo, par = PROPOSALS[clave]
        print(f"\n=== {clave}: {titulo} ===")
        fallos = measure(clave, titulo, par, rigs)
        if fallos:
            print(f"  {len(fallos)} problemas al escribirla a ojo:")
            for fallo in fallos:
                print(f"    - {fallo}")
            par, _ = repair(par, rigs)
            fallos = measure(clave, titulo, par, rigs)
            print(f"  despues de reparar: "
                  + ("todas las medidas pasan" if not fallos
                     else f"{len(fallos)} sin resolver"))
            for fallo in fallos:
                print(f"    - {fallo}")
        else:
            print("  todas las medidas pasan")
        FINALES[clave] = par

        try:
            asignado, separacion = light_rigs(par, rigs)
        except RuntimeError as error:
            print(f"  SIN paleta clara de bancos: {error}")
            continue
        print(f"  paleta clara de bancos: dE >= {separacion:.0f}")

        if not args.measure and not fallos:
            for ruta in render(clave, par, asignado, rigs):
                print(f"  {ruta}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
