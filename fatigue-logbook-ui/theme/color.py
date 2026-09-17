"""Medidas de color: luminancia, contraste WCAG y distancia en CIELab.

Un solo sitio para las tres cuentas que este proyecto usa para decidir un
color. Estaban repartidas entre la migracion 010 y tres suites de pruebas del
proyecto original, cada copia con su propia forma de redondear; aqui se
escriben una vez y las usan el tema, el generador de paleta y las pruebas.

Comparar en RGB miente: #60DB60 y #53BD9D distan poco en numeros y mucho a la
vista. Por eso la separacion entre colores se mide en Lab y no en RGB.
"""

from __future__ import annotations


def rgb(color: str) -> tuple[float, float, float]:
    """'#RRGGBB' -> tres canales de 0 a 1."""
    value = color.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def to_hex(channels: tuple[float, float, float]) -> str:
    return "#%02X%02X%02X" % tuple(
        max(0, min(255, round(c * 255))) for c in channels
    )


def _linear(channel: float) -> float:
    """Canal sRGB a lineal. El tramo recto de abajo no es un detalle: sin el,
    los colores muy oscuros dan una luminancia mas baja de la real."""
    return (channel / 12.92 if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4)


def luminance(color: str) -> float:
    """Luminancia relativa WCAG."""
    r, g, b = (_linear(c) for c in rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(one: str, other: str) -> float:
    """Razon de contraste WCAG, siempre >= 1."""
    first, second = sorted((luminance(one), luminance(other)), reverse=True)
    return (first + 0.05) / (second + 0.05)


def lab(color: str) -> tuple[float, float, float]:
    """sRGB a CIELab con iluminante D65."""
    r, g, b = (_linear(c) for c in rgb(color))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def distance(one: str, other: str) -> float:
    """Distancia CIE76 entre dos colores. Es la 'dE' de todo el proyecto."""
    return sum(
        (a - b) ** 2 for a, b in zip(lab(one), lab(other))
    ) ** 0.5


def ink_for(background: str) -> str:
    """Tinta legible sobre un fondo: la que mas contraste da, negra o blanca.

    Se elige midiendo y no por un umbral de luminancia escrito a mano, que es
    lo que hacia que algun amarillo saliera con tinta blanca.
    """
    return "#1C1917" if contrast("#1C1917", background) >= contrast(
        "#FFFFFF", background) else "#FFFFFF"


def mix(one: str, other: str, amount: float) -> str:
    """Mezcla lineal de dos colores. ``amount`` 0 devuelve el primero."""
    a, b = rgb(one), rgb(other)
    return to_hex(tuple(x + (y - x) * amount for x, y in zip(a, b)))
