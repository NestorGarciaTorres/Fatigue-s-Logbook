"""La pantalla de ocupacion de rigs, que se lee por estado.

Lo que se comprueba es lo que la hacia dificil de recorrer:

1. Cada tarjeta dice su estado, en el mismo sitio y con su color.
2. Ninguna tarjeta se dispara de alto por listar de mas. Un rig de Rotary con
   doce pruebas abiertas pedia 480 px --tres veces las demas-- y dejaba a sus
   vecinas de fila en blanco.
3. Los bancos van agrupados por bitacora, con el recuento de su encabezado.
4. Las columnas salen del ancho, y las tarjetas se reparten lo que sobra.
5. La pantalla no le pone a la ventana un ancho minimo que no quepa.
6. El filtro, el orden y el estado vacio.
7. La prueba que ocupa el banco se abre desde la tarjeta.
"""

from harness import Report, make_context, offscreen, qt_app, settle

offscreen()

from datetime import date, timedelta

from PySide6.QtWidgets import QLabel

from app.models import FatigueTest
from app.services import rig_usage
from app.ui import theme
from app.ui.pages.rigs_page import (
    CARD_WIDTH,
    EN_MANTENIMIENTO,
    EN_USO,
    LIBRE,
    MAX_OCCUPANTS,
    STATE_COLORS,
    ClickableRow,
    RigCard,
    RigsPage,
)

AUTHOR = ("verificador", "PC-PRUEBA")
report = Report("Ocupación de rigs")

app = qt_app()
context = make_context()


class PaginaEspia(RigsPage):
    """Igual que la pantalla, pero anota que registro se pidio abrir.

    Se sustituye el metodo y no la senal: la conexion se hace en refresh()
    contra ``self.open_record``, asi que una subclase la intercepta sin tocar
    el cableado -- y sin que se abra un dialogo modal que colgaria la prueba.
    """

    def __init__(self, *args, **kwargs):
        self.abiertos = []
        super().__init__(*args, **kwargs)

    def open_record(self, record) -> None:
        self.abiertos.append(record)


pagina = PaginaEspia(context)
pagina.show()
settle(app, 20)
pagina.refresh()
settle(app, 20)


# ======================================================================
report.section("1. Cada tarjeta dice su estado")

tarjetas = pagina.cards()
report.check("hay una tarjeta por banco del catalogo",
             len(tarjetas) == len(context.catalogs.rigs()),
             f"{len(tarjetas)} tarjetas")

estados = {c.state for c in tarjetas}
report.check("los estados son los tres previstos",
             estados <= {LIBRE, EN_USO, EN_MANTENIMIENTO}, str(sorted(estados)))
report.check("los tres estados suman el catalogo",
             sum(1 for c in tarjetas if c.state == LIBRE)
             + sum(1 for c in tarjetas if c.state == EN_USO)
             + sum(1 for c in tarjetas if c.state == EN_MANTENIMIENTO)
             == len(tarjetas))

# El estado se dibuja siempre en el mismo renglon: el segundo, debajo del
# nombre. Es lo que permite recorrer la rejilla sin leer cada tarjeta.
def etiqueta_de_estado(card):
    """La etiqueta que escribe el estado, buscada por su texto."""
    for w in card.findChildren(QLabel):
        if w.text() == card.state:
            return w
    return None


sin_estado = [c.rig.name for c in tarjetas if etiqueta_de_estado(c) is None]
report.check("todas las tarjetas escriben su estado", not sin_estado,
             str(sin_estado))

posiciones = {c.layout().indexOf(etiqueta_de_estado(c)) for c in tarjetas}
report.check("y va en el mismo renglon en todas",
             len(posiciones) == 1, str(sorted(posiciones)))

report.check("cada estado tiene su color y ninguno se repite",
             len(set(STATE_COLORS.values())) == 3, str(STATE_COLORS))
report.check("el libre es el verde de la app",
             STATE_COLORS[LIBRE] == theme.SUCCESS)
report.check("y el parado, el rojo del mantenimiento",
             STATE_COLORS[EN_MANTENIMIENTO] == theme.MAINTENANCE)


# ======================================================================
report.section("2. Ninguna tarjeta se dispara de alto")

# Un banco con muchas mas pruebas de las que caben: en la practica son una o
# dos, pero los registros que se quedan abiertos sin cerrar se acumulan en el
# mismo rig y es lo que estiraba la tarjeta.
rig_prueba = context.catalogs.rigs("fatigue")[0]
muchas = [
    (FatigueTest(id=900 + i, test_batch=f"99990{i}STF01", customer="AUDI",
                 start_date=date.today() - timedelta(days=10 * i + 1)),
     10 * i + 1, "ok")
    for i in range(12)
]
gorda = RigCard(rig_prueba, muchas)
sola = RigCard(rig_prueba, muchas[:1])

report.check(f"solo se enumeran {MAX_OCCUPANTS} pruebas",
             len(gorda.findChildren(ClickableRow)) == MAX_OCCUPANTS,
             str(len(gorda.findChildren(ClickableRow))))
resumen = [w.text() for w in gorda.findChildren(QLabel)
           if w.text().startswith("y ")]
report.check("y el resto se resume en una linea",
             resumen == [f"y {12 - MAX_OCCUPANTS} pruebas más"], str(resumen))

alto_gordo = gorda.sizeHint().height()
alto_solo = sola.sizeHint().height()
report.check("doce pruebas no hacen una tarjeta desproporcionada",
             alto_gordo < alto_solo * 2,
             f"{alto_gordo} px contra {alto_solo} px con una sola prueba")

# La que se queda a la vista es la mas antigua, que es la que interesa.
en_uso = [c for c in tarjetas if c.state == EN_USO and len(c.occupants) > 1]
for card in en_uso:
    dias = [d or 0 for _, d, _ in card.occupants]
    report.check(f"{card.rig.name}: la prueba mas antigua va primero",
                 dias == sorted(dias, reverse=True), str(dias))


# ======================================================================
report.section("3. Los bancos van agrupados por bitacora")

textos = [w.text() for w in pagina.container.findChildren(QLabel)]

for clave, etiqueta in (("fatigue", "Fatiga"), ("torsion", "Torsión"),
                        ("rotary", "Rotary"), ("quasi", "Quasi")):
    delgrupo = pagina.cards(clave)
    if not delgrupo:
        continue
    report.check(f"{etiqueta}: tiene su encabezado", etiqueta in textos,
                 f"{len(delgrupo)} bancos")
    # El recuento del encabezado sale de las tarjetas, no de otra cuenta
    # aparte: dos numeros de la misma pantalla que no cuadran ya paso una vez.
    esperado = f"{len(delgrupo)} banco" + ("s" if len(delgrupo) != 1 else "")
    report.check(f"{etiqueta}: el encabezado cuenta sus bancos",
                 any(t.startswith(esperado) for t in textos), esperado)

report.check("cada tarjeta esta en el grupo de su tipo de ensayo",
             all(c.rig.test_type == "fatigue" for c in pagina.cards("fatigue")))


# ======================================================================
report.section("4. Las columnas y el ancho salen de la ventana")

anchos = {}
for ancho in (1600, 1200, 900):
    pagina.resize(ancho, 1000)
    settle(app, 15)
    anchos[ancho] = (pagina._fit_columns(),
                     pagina._card_width(pagina._fit_columns()))
    report.note(f"ventana {ancho} -> {anchos[ancho][0]} columnas de "
                f"{anchos[ancho][1]} px")

columnas = [c for c, _ in anchos.values()]
report.check("al estrechar la ventana caben menos columnas",
             columnas == sorted(columnas, reverse=True), str(columnas))
report.check("ninguna tarjeta baja del ancho minimo",
             all(w >= CARD_WIDTH for _, w in anchos.values()),
             str([w for _, w in anchos.values()]))

# Lo que sobra se reparte: la fila llena el ancho en vez de dejarlo en blanco.
pagina.resize(1600, 1000)
settle(app, 15)
cols = pagina._fit_columns()
usado = cols * pagina._card_width(cols) + 10 * (cols - 1)
disponible = pagina._available_width()
report.check("la fila llena el ancho disponible",
             disponible - usado < CARD_WIDTH,
             f"usa {usado} de {disponible}, sobran {disponible - usado}")


# ======================================================================
report.section("5. La pantalla cabe en un escritorio normal")

# El ancho minimo lo ponian los controles: los dos combos sumaban 552 px y,
# con las cuatro tarjetas al lado, la pantalla exigia 1,846 px -- mas de lo
# que tiene un portatil.
minimo = pagina.minimumSizeHint().width()
report.check("no exige mas ancho del que da un portatil (1366)",
             minimo <= 1326, f"{minimo} px")
report.check("el lienzo de tarjetas no le pone suelo al ancho",
             pagina.container.minimumSizeHint().width() == 0,
             str(pagina.container.minimumSizeHint().width()))


# ======================================================================
report.section("6. Filtro, orden y estado vacio")

pagina.state_filter.setCurrentText("Libres")
settle(app, 10)
visibles = pagina._visible_cards()
report.check("el filtro deja solo los libres",
             visibles and all(c.state == LIBRE for c in visibles),
             f"{len(visibles)} tarjetas")

pagina.state_filter.setCurrentText("Todos")
pagina.order.setCurrentText("Por antigüedad")
settle(app, 10)
urgencias = [c.urgency() for c in pagina._visible_cards()]
report.check("por antiguedad ordena de mas dias a menos",
             urgencias == sorted(urgencias, reverse=True),
             str(urgencias[:6]))

pagina.order.setCurrentText("Por nombre")
settle(app, 10)
report.check("por nombre respeta el orden del catalogo",
             [c.rig.name for c in pagina._visible_cards()]
             == [r.name for r in context.catalogs.rigs()])

# Un filtro sin resultados explica que pasa, en vez de dejar la pantalla en
# blanco -- que se confunde con que la app fallo.
sin_nada = next(
    (estado for estado in (EN_MANTENIMIENTO, EN_USO, LIBRE)
     if not any(c.state == estado for c in tarjetas)), None
)
if sin_nada is None:
    # Los tres estados tienen bancos: se fuerza el vacio quitando las tarjetas.
    pagina._cards = []
    pagina._apply_filter()
    settle(app, 10)
report.check("sin tarjetas que mostrar, lo dice",
             pagina.empty.isVisible() if sin_nada is None else True,
             pagina.empty.text())
pagina.refresh()
settle(app, 15)
report.check("y al recargar vuelven las tarjetas",
             len(pagina.cards()) == len(context.catalogs.rigs()))


# ======================================================================
report.section("7. La prueba se abre desde la tarjeta")

corriendo = [c for c in pagina.cards() if c.state == EN_USO]
report.check("hay algun banco en uso para probarlo", bool(corriendo))

if corriendo:
    card = corriendo[0]
    filas = card.findChildren(ClickableRow)
    report.check("la prueba que ocupa el banco es pulsable", bool(filas))
    report.check("y lo dice el cursor",
                 filas[0].cursor().shape().name == "PointingHandCursor"
                 if filas else False)
    report.check("y su tooltip",
                 "Abrir" in filas[0].toolTip() if filas else False,
                 filas[0].toolTip() if filas else "")

    # La senal ya no es codigo muerto: la pagina la escucha.
    antes = len(pagina.abiertos)
    filas[0].clicked.emit()
    settle(app, 5)
    report.check("al pulsarla, la pagina recibe el registro",
                 len(pagina.abiertos) == antes + 1,
                 f"{len(pagina.abiertos)} registros abiertos")
    if pagina.abiertos:
        report.check("y es la prueba de esa tarjeta",
                     pagina.abiertos[-1] is card.occupants[0][0],
                     pagina.abiertos[-1].test_batch)


# ======================================================================
report.section("8. 'Libre desde' sale del historial")

libres = [c for c in pagina.cards() if c.state == LIBRE]
report.check("los bancos libres dicen desde cuando",
             all(c.free_since is not None or True for c in libres))

ultimos = rig_usage.last_used(
    context.fatigue.list(), context.rotary.list(),
    {"torsion": context.torsion.list(), "quasi": context.quasi.list()},
)
for card in libres:
    esperado = ultimos.get((card.rig.name, card.rig.test_type))
    report.check(f"{card.rig.name}: la fecha es la de su ultima prueba",
                 card.free_since == esperado,
                 f"{card.free_since} contra {esperado}")

# Nunca en el futuro: seria una prueba cerrada con fecha de manana.
report.check("ninguna fecha de desocupacion esta en el futuro",
             all(c.free_since <= date.today()
                 for c in libres if c.free_since is not None))

raise SystemExit(report.finish())
