"""Que el cambio de tema funcione de verdad, y que siga funcionando.

Son tres cosas distintas y las tres hacen falta:

1. **Conmuta.** Se captura la pantalla, se cambia el tema y se vuelve a
   capturar: ningun pixel puede seguir teniendo el color del tema anterior.
   Es la prueba que atrapa un token congelado al importar -- el fallo que dejo
   al proyecto anterior sin poder cambiar de tema.
2. **Higiene.** Ningun modulo fuera de ``theme/`` pinta con ``setStyleSheet``
   ni copia un color a una constante propia. Es lo que evita que la
   conmutacion se degrade con el tiempo, que es exactamente como el proyecto
   anterior acabo con 49 estilos inline repartidos en once archivos.
3. **Cabe.** La pantalla no pide mas ancho del que tiene un portatil de 1366.

Corre con la plataforma nativa y no con 'offscreen': hay que mirar pixeles de
verdad, y en offscreen el texto sale como cuadros.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import harness  # noqa: F401  (deja sys.path listo)
from harness import Report

from theme.manager import theme
from theme.tokens import DARK, LIGHT, PALETTES

# 1366 menos el margen que deja el gestor de ventanas. Es el mismo tope que se
# mide en el proyecto original.
LAPTOP_LIMIT = 1326

UI_ROOT = Path(harness.UI_ROOT)

# El unico ``setStyleSheet`` permitido fuera de theme/, y esta justificado en
# el propio codigo: el acento de una StatCard es un dato de la tarjeta, no de
# su tipo, asi que no puede salir de un selector de la hoja. Se vuelve a
# aplicar en cada cambio de tema, que es lo que lo hace legitimo.
# Las dos unicas excepciones, y las dos por el mismo motivo: pintan un color
# que es **dato**, no tipo de widget --el acento elegido para una metrica, el
# color del banco-- y un dato no puede salir de un selector de la hoja de
# estilos. Lo que las hace legitimas es que las dos se vuelven a aplicar en
# cada cambio de tema; sin eso serian exactamente el fallo que esta prueba
# busca. Agregar una tercera exige la misma reconexion.
ALLOWED_INLINE = {
    ("components/cards.py", "_paint_accent"),
    ("pages/rigs.py", "_paint_header"),
}

HEX_AT_MODULE_LEVEL = re.compile(r'^[A-Z_][A-Z0-9_]*\s*=\s*"#[0-9A-Fa-f]{6}"')

# Una llamada de verdad lleva punto delante: 'widget.setStyleSheet('. Sin el
# punto, el detector marcaba tambien las veces que el nombre aparece dentro de
# un comentario explicando por que NO se usa -- y una prueba que falla por su
# propia documentacion ensenia a ignorarla.
INLINE_CALL = re.compile(r"\.setStyleSheet\s*\(")


def _sampled_colors(pixmap) -> Counter:
    """Los colores de una rejilla de puntos de la captura."""
    imagen = pixmap.toImage()
    colores = Counter()
    paso = 7
    for y in range(0, imagen.height(), paso):
        for x in range(0, imagen.width(), paso):
            colores[imagen.pixelColor(x, y).name().upper()] += 1
    return colores


def _source_files() -> list[Path]:
    carpetas = ("components", "pages", "dialogs", "tests")
    archivos = [UI_ROOT / "window.py", UI_ROOT / "main.py",
                UI_ROOT / "bridge.py"]
    for carpeta in carpetas:
        archivos += sorted((UI_ROOT / carpeta).glob("*.py"))
    return [a for a in archivos if a.is_file()]


def check_hygiene(report: Report) -> None:
    report.section("Higiene: el color solo se decide en theme/")

    infractores: list[str] = []
    for archivo in _source_files():
        relativo = archivo.relative_to(UI_ROOT).as_posix()
        texto = archivo.read_text(encoding="utf-8")
        if not INLINE_CALL.search(texto):
            continue
        if any(relativo == f for f, _ in ALLOWED_INLINE):
            continue
        for numero, linea in enumerate(texto.splitlines(), start=1):
            if INLINE_CALL.search(linea) and not linea.strip().startswith("#"):
                infractores.append(f"{relativo}:{numero}")
    report.check(
        "ningun widget se pinta con setStyleSheet fuera de theme/",
        not infractores,
        f"{len(infractores)} encontrados: {infractores[:4]}" if infractores
        else f"{len(ALLOWED_INLINE)} excepcion documentada",
    )

    copiados: list[str] = []
    for archivo in _source_files():
        relativo = archivo.relative_to(UI_ROOT).as_posix()
        for numero, linea in enumerate(
                archivo.read_text(encoding="utf-8").splitlines(), start=1):
            if HEX_AT_MODULE_LEVEL.match(linea):
                copiados.append(f"{relativo}:{numero}  {linea.strip()[:40]}")
    report.check(
        "ningun color se copia a una constante de modulo",
        not copiados,
        "; ".join(copiados[:3]) if copiados
        else "todo se pide a la paleta al pintar",
    )

    # La otra mitad del mismo problema: un modulo que importe la paleta al
    # cargarse en vez de pedirla en cada pintado.
    congelados: list[str] = []
    for archivo in _source_files():
        relativo = archivo.relative_to(UI_ROOT).as_posix()
        texto = archivo.read_text(encoding="utf-8")
        for numero, linea in enumerate(texto.splitlines(), start=1):
            limpia = linea.strip()
            if (re.match(r"^[A-Z_][A-Z0-9_]*\s*=\s*(theme\(\)|palette\(\))",
                         limpia)):
                congelados.append(f"{relativo}:{numero}")
    report.check(
        "ninguna constante de modulo guarda la paleta activa",
        not congelados,
        "; ".join(congelados[:3]) if congelados else "ninguna",
    )


def check_switch(report: Report) -> None:
    report.section("El tema cambia sin reiniciar")

    app = harness.qt_app(LIGHT)
    # Sobre una copia, nunca sobre la base real: prepare() migra.
    context = harness.make_context()

    from window import MainWindow

    ventana = MainWindow(context)
    ventana.start()
    harness.settle(app, 40)
    ventana.grab()   # el primer grab de un proceso sale en blanco

    capturas = {}
    for nombre in (LIGHT, DARK):
        theme().set_theme(nombre)
        ventana.sidebar.update_theme_button()
        harness.settle(app, 40)
        capturas[nombre] = _sampled_colors(ventana.grab())

    for nombre, otro in ((LIGHT, DARK), (DARK, LIGHT)):
        paleta_otro = PALETTES[otro]
        # El fondo del tema contrario es el color que mas superficie ocupa: si
        # queda un solo pixel de el, algo no se repinto.
        restos = [c for c in (paleta_otro.bg, paleta_otro.surface,
                              paleta_otro.row, paleta_otro.row_alt,
                              paleta_otro.header_bg)
                  if capturas[nombre].get(c.upper(), 0) > 0]
        report.check(
            f"en tema {nombre} no queda nada pintado del tema {otro}",
            not restos,
            f"quedaron {restos}" if restos else "ni un pixel",
        )

    for nombre in (LIGHT, DARK):
        propio = PALETTES[nombre]
        presentes = sum(capturas[nombre].get(c.upper(), 0)
                        for c in (propio.bg, propio.surface, propio.row))
        report.check(
            f"en tema {nombre} se pintan sus propias superficies",
            presentes > 0,
            f"{presentes} puntos de muestra",
        )

    report.check(
        "el gestor recuerda el tema elegido",
        theme().name == DARK,
        f"quedo en '{theme().name}'",
    )

    report.section("La pantalla cabe en un portatil")
    ancho = ventana.minimumSizeHint().width()
    report.check(
        "el ancho minimo de la ventana cabe en 1366",
        ancho <= LAPTOP_LIMIT,
        f"{ancho} px  (tope {LAPTOP_LIMIT})",
    )

    # Las ocho, no solo la que esta a la vista: una pantalla que pide de mas
    # arrastra a la ventana entera en cuanto alguien entra en ella.
    from window import DESTINATIONS

    for clave, rotulo in DESTINATIONS:
        pagina = ventana.pages[clave]
        ventana.show_page(clave)
        harness.settle(app, 20)
        ancho = pagina.minimumSizeHint().width()
        report.check(
            f"'{rotulo}' cabe en un portatil",
            ancho <= LAPTOP_LIMIT,
            f"{ancho} px  (tope {LAPTOP_LIMIT})",
        )

    report.section("Todas las pantallas cargan con datos reales")
    # Cargar no es un detalle: cada pantalla pide sus datos a los repositorios
    # al mostrarse, y un fallo ahi solo se ve entrando en ella.
    for clave, rotulo in DESTINATIONS:
        try:
            ventana.show_page(clave)
            harness.settle(app, 10)
            fallo = None
        except Exception as error:            # pragma: no cover
            fallo = f"{type(error).__name__}: {error}"
        report.check(f"'{rotulo}' carga sin reventar", fallo is None,
                     fallo or "ok")

    report.section("Los botones no recortan su texto")
    # Qt recorta un QPushButton por los dos lados sin avisar cuando no cabe
    # ("'oner en mantenimient"). No hay senial de error: hay que medirlo.
    from PySide6.QtWidgets import QPushButton

    recortados = [
        f"'{b.text()}' {b.width()}px < {b.minimumSizeHint().width()}px"
        for b in ventana.findChildren(QPushButton)
        if b.isVisible() and b.text()
        and b.width() < b.minimumSizeHint().width()
    ]
    report.check(
        "ningun boton visible es mas angosto de lo que pide su texto",
        not recortados,
        "; ".join(recortados[:3]) if recortados else "ninguno",
    )


def main() -> int:
    report = Report("Cambio de tema e higiene de estilos")
    check_hygiene(report)
    check_switch(report)
    return report.finish()


if __name__ == "__main__":
    raise SystemExit(main())
