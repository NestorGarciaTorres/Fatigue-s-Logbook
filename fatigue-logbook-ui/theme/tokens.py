"""Los dos temas, como datos.

Un tema es una instancia de :class:`Palette`, no un monton de constantes de
modulo. La diferencia no es de estilo: en el proyecto anterior los colores eran
variables de modulo (``theme.WARNING = "#F0AD4E"``) y tres sitios las copiaban a
constantes propias al importar -- ``DAYS_COLORS``, ``SUSPENDED_COLOR``,
``MAINTENANCE_COLOR``--. Copiadas asi, cambiar de tema en caliente no las
actualiza nunca. Con una paleta que se pide al gestor cada vez que se pinta, eso
no puede pasar.

Los nombres son semanticos --``danger``, no ``rojo``-- porque el color aqui
significa algo y el significado no cambia entre temas aunque el hexadecimal si:

- ``warning``      pieza suspendida, fuera de banco
- ``danger``       revisar: la prueba lleva demasiado tiempo corriendo
- ``maintenance``  el banco de esa pieza esta fuera de servicio
- ``accent``       activo, con foco, o la accion principal

Cada valor de aqui esta medido, no elegido a ojo. ``tests/test_tokens.py``
vuelve a medirlo todo en cada corrida --las CUATRO familias, en sus dos modos--:
texto sobre fondo a 4.5:1, los colores de estado a 3:1 sobre los tres fondos de
fila de SU tema, y la separacion en Lab entre lo que tiene que distinguirse.

Una **familia** son dos paletas, la clara y la oscura, que comparten caracter.
Se eligen en Ajustes -> Apariencia y se combinan con el modo: cuatro familias
por dos modos, ocho aspectos.

Los valores no se escribieron a mano tal cual: se propusieron a ojo y despues
se **repararon midiendo**. Varios colores de estado chocaban con alguno de los
dieciseis bancos por debajo de dE 24 --el peor a 5.8-- y un chip de estado que
se parece a un banco miente. La rutina que los corrigio esta en
``tools/propose_palettes.py``, que tambien vuelve a dibujar las cuatro sobre la
pantalla real.
"""

from __future__ import annotations

from dataclasses import dataclass

LIGHT = "light"
DARK = "dark"


@dataclass(frozen=True)
class Palette:
    """Los colores de un tema. Inmutable: un tema no se edita, se sustituye."""

    name: str
    is_dark: bool

    # --- superficies -----------------------------------------------------
    # 'bg' es el lienzo de la ventana; 'surface' lo que se levanta sobre el
    # (tarjetas, campos, dialogos); 'sunken' lo que se hunde (areas de scroll,
    # encabezados). La elevacion se dibuja con sombra y no con borde duro.
    bg: str
    surface: str
    sunken: str
    overlay: str

    # --- texto -----------------------------------------------------------
    text: str
    text_secondary: str
    text_muted: str
    text_disabled: str
    text_on_accent: str

    # --- lineas ----------------------------------------------------------
    border: str
    divider: str

    # --- accion ----------------------------------------------------------
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str

    # --- estados ---------------------------------------------------------
    success: str
    warning: str
    danger: str
    info: str
    maintenance: str

    # --- tabla -----------------------------------------------------------
    # Los tres fondos que puede tener una fila. Un chip tiene que leerse en
    # cualquiera de los tres, no solo en el que se probo: la primera version
    # de la paleta del proyecto anterior se genero contra dos, y al aclarar la
    # franja alterna nueve de dieciseis se quedaron por debajo de 3:1.
    row: str
    row_alt: str
    selection: str
    header_bg: str
    header_text: str
    grid: str

    # --- sombra ----------------------------------------------------------
    shadow: str

    @property
    def row_backgrounds(self) -> tuple[str, str, str]:
        """Los tres fondos contra los que se mide cualquier color de la tabla."""
        return (self.row, self.row_alt, self.selection)

    @property
    def reserved(self) -> tuple[str, ...]:
        """Colores de interfaz de los que un color de banco debe mantenerse lejos.

        Si un rig cae cerca de alguno, su chip deja de leerse como 'banco' y
        pasa a leerse como estado: un chip del color de 'warning' diria
        'suspendida' sin serlo.
        """
        return (
            self.accent, self.info, self.success, self.warning, self.danger,
            self.maintenance, self.bg, self.surface, self.row, self.row_alt,
            self.selection, self.header_bg,
        )


@dataclass(frozen=True)
class Family:
    """Las dos paletas de un mismo caracter, clara y oscura."""

    key: str
    label: str
    light: Palette
    dark: Palette

    def palette(self, dark: bool) -> Palette:
        return self.dark if dark else self.light


# --- pizarra -----------------------------------------------------------
# Neutros con una pizca de verde y un azul de accion sin estridencia. La
# idea que la ordena es que **nada de la interfaz compita con los colores de
# los bancos**, que son lo que de verdad hay que leer en una jornada larga.
PIZARRA = Family(
    key="pizarra",
    label="Pizarra: gris verdoso y azul apagado",
    light=Palette(
        name="pizarra-light", is_dark=False,
        bg="#F1F4F2",
        surface="#FFFFFF",
        sunken="#E5EAE7",
        overlay="#FFFFFF",
        text="#14201C",
        text_secondary="#44554E",
        text_muted="#4B5C55",
        text_disabled="#A6B3AD",
        text_on_accent="#FFFFFF",
        border="#D5DEDA",
        divider="#E7ECE9",
        accent="#2F5D8A",
        accent_hover="#264C72",
        accent_pressed="#1D3B59",
        accent_soft="#E2EAF3",
        success="#166534",
        warning="#B45309",
        danger="#BE123C",
        info="#7C3AED",
        maintenance="#A21CAF",
        row="#FFFFFF",
        row_alt="#DFE4E1",
        selection="#CEE0F0",
        header_bg="#C6D2CD",
        header_text="#264C72",
        grid="#DDE5E1",
        shadow="#0C201B22",
    ),
    dark=Palette(
        name="pizarra-dark", is_dark=True,
        bg="#101614",
        surface="#1B2422",
        sunken="#0A100E",
        overlay="#232D2A",
        text="#F3F7F5",
        text_secondary="#C8D4CF",
        text_muted="#A5B3AD",
        text_disabled="#60706A",
        text_on_accent="#061615",
        border="#2E3A36",
        divider="#242E2B",
        accent="#78B2DE",
        accent_hover="#AECBE9",
        accent_pressed="#6E9AC4",
        accent_soft="#18242E",
        success="#50BF6E",
        warning="#FBBF24",
        danger="#FB7185",
        info="#9C83F2",
        maintenance="#F36AFC",
        row="#1B2422",
        row_alt="#2C3936",
        selection="#14403E",
        header_bg="#0D1211",
        header_text="#AECBE9",
        grid="#2E3A36",
        shadow="#00000066",
    ),
)


# --- acero -----------------------------------------------------------
# Neutros gris azulado, sin calidez, y un azul de accion que se lee como
# control y no como decoracion. Es la que mas parece un instrumento de
# medicion.
ACERO = Family(
    key="acero",
    label="Acero: grises fríos y azul de instrumento",
    light=Palette(
        name="acero-light", is_dark=False,
        bg="#F2F5F7",
        surface="#FFFFFF",
        sunken="#E6EBF0",
        overlay="#FFFFFF",
        text="#101828",
        text_secondary="#475467",
        text_muted="#4D5969",
        text_disabled="#A9B4C0",
        text_on_accent="#FFFFFF",
        border="#D6DEE6",
        divider="#E8EDF2",
        accent="#0B5FD1",
        accent_hover="#0A4FAE",
        accent_pressed="#08408C",
        accent_soft="#E4EDFB",
        success="#0F7A4A",
        warning="#B45309",
        danger="#C0123C",
        info="#0E7490",
        maintenance="#9333EA",
        row="#FFFFFF",
        row_alt="#E0E5EA",
        selection="#D6E4FA",
        header_bg="#C9D4E0",
        header_text="#0A4FAE",
        grid="#DFE6EE",
        shadow="#0E1E3322",
    ),
    dark=Palette(
        name="acero-dark", is_dark=True,
        bg="#0E1419",
        surface="#18212A",
        sunken="#090E12",
        overlay="#1F2A34",
        text="#F2F6FA",
        text_secondary="#C4D0DC",
        text_muted="#A3B2C2",
        text_disabled="#5E6B7A",
        text_on_accent="#08131F",
        border="#2C3A47",
        divider="#222E39",
        accent="#05A3F2",
        accent_hover="#78BAFA",
        accent_pressed="#3A86D8",
        accent_soft="#132436",
        success="#3FBF6F",
        warning="#FBBF24",
        danger="#FB7185",
        info="#9DCEFC",
        maintenance="#F36AFC",
        row="#18212A",
        row_alt="#283542",
        selection="#123152",
        header_bg="#0B1218",
        header_text="#78BAFA",
        grid="#2C3A47",
        shadow="#00000066",
    ),
)


# --- carbon -----------------------------------------------------------
# Papel casi blanco contra tinta casi negra, neutros sin temperatura y un
# violeta saturado. La de mas contraste y la que mas marca la jerarquia;
# tambien la que mas cansa en una jornada larga.
CARBON = Family(
    key="carbon",
    label="Carbón: papel y tinta, violeta con presencia",
    light=Palette(
        name="carbon-light", is_dark=False,
        bg="#FAFAFA",
        surface="#FFFFFF",
        sunken="#F0F0F0",
        overlay="#FFFFFF",
        text="#0A0A0A",
        text_secondary="#525252",
        text_muted="#646464",
        text_disabled="#ABABAB",
        text_on_accent="#FFFFFF",
        border="#DCDCDC",
        divider="#EBEBEB",
        accent="#6D28D9",
        accent_hover="#5B21B6",
        accent_pressed="#4C1D95",
        accent_soft="#EFE7FD",
        success="#15803D",
        warning="#B45309",
        danger="#BE123C",
        info="#0369A1",
        maintenance="#BF1366",
        row="#FFFFFF",
        row_alt="#E1E1E1",
        selection="#E4DAFB",
        header_bg="#CBCBCB",
        header_text="#5B21B6",
        grid="#E4E4E4",
        shadow="#00000026",
    ),
    dark=Palette(
        name="carbon-dark", is_dark=True,
        bg="#0C0C0D",
        surface="#171718",
        sunken="#070708",
        overlay="#1F1F21",
        text="#FAFAFA",
        text_secondary="#D4D4D4",
        text_muted="#B0B0B0",
        text_disabled="#666666",
        text_on_accent="#0C0A16",
        border="#2E2E30",
        divider="#232325",
        accent="#9B83F2",
        accent_hover="#C4B5FD",
        accent_pressed="#8B5CF6",
        accent_soft="#1F1A33",
        success="#3FBF6F",
        warning="#FBBF24",
        danger="#FB7185",
        info="#38BDF8",
        maintenance="#F472B6",
        row="#171718",
        row_alt="#2A2A2C",
        selection="#241E42",
        header_bg="#000000",
        header_text="#C4B5FD",
        grid="#2E2E30",
        shadow="#00000077",
    ),
)


# --- piedra -----------------------------------------------------------
# Neutros calidos de piedra y un indigo violeta de accion. Fue la primera
# direccion que se probo, y se conserva como alternativa mas calida.
PIEDRA = Family(
    key="piedra",
    label="Piedra e índigo",
    light=Palette(
        name="piedra-light", is_dark=False,
        bg="#F6F5F2",
        surface="#FFFFFF",
        sunken="#F0EEEA",
        overlay="#FFFFFF",
        text="#1C1917",
        text_secondary="#56504A",
        text_muted="#6E675F",
        text_disabled="#B3ABA2",
        text_on_accent="#FFFFFF",
        border="#E0DBD4",
        divider="#EDEAE5",
        accent="#4F46E5",
        accent_hover="#4338CA",
        accent_pressed="#3730A3",
        accent_soft="#EDEDFC",
        success="#15803D",
        warning="#B45309",
        danger="#BE123C",
        info="#0369A1",
        maintenance="#A21CAF",
        row="#FFFFFF",
        row_alt="#EAE7E0",
        selection="#DFDFFA",
        header_bg="#D6D0C4",
        header_text="#4338CA",
        grid="#E7E3DC",
        shadow="#00000022",
    ),
    dark=Palette(
        name="piedra-dark", is_dark=True,
        bg="#1A1715",
        surface="#262220",
        sunken="#141110",
        overlay="#2E2A27",
        text="#FAF9F7",
        text_secondary="#D4CEC7",
        text_muted="#B3AAA0",
        text_disabled="#6B635C",
        text_on_accent="#14121F",
        border="#3A3531",
        divider="#2F2A27",
        accent="#9B7DF7",
        accent_hover="#B39BF9",
        accent_pressed="#8465EC",
        accent_soft="#2A2440",
        success="#3FBF6F",
        warning="#FBBF24",
        danger="#FB7185",
        info="#38BDF8",
        maintenance="#EC4899",
        row="#262220",
        row_alt="#403833",
        selection="#2B2A55",
        header_bg="#141110",
        header_text="#B39BF9",
        grid="#3A3531",
        shadow="#00000055",
    ),
)


FAMILIES = {f.key: f for f in (PIZARRA, ACERO, CARBON, PIEDRA)}
DEFAULT_FAMILY = PIZARRA.key


def palette_for(family: str, mode: str) -> Palette:
    """La paleta de esa familia en ese modo. Cae a lo por omision si no existe."""
    familia = FAMILIES.get(family, FAMILIES[DEFAULT_FAMILY])
    return familia.palette(mode == DARK)


# Compatibilidad: las dos paletas de la familia por omision. Lo que necesite la
# **activa** debe pedirsela al gestor (``theme().palette``), no importar estas.
PALETTE_LIGHT = FAMILIES[DEFAULT_FAMILY].light
PALETTE_DARK = FAMILIES[DEFAULT_FAMILY].dark

PALETTES = {LIGHT: PALETTE_LIGHT, DARK: PALETTE_DARK}
