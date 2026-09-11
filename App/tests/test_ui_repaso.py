"""El repaso de interfaz, medido.

Ocho cosas que la pantalla hacia mal y que no se ven en ninguna otra prueba:
el ancho desperdiciado, las columnas que no informaban, la identidad de la
fila que se perdia al desplazarse, las etiquetas sin tildes, el color usado de
adorno en el dashboard, la falta de atajos y de un modo visible de abrir un
registro, los avisos que solo costaban un clic y los 27 campos que anunciaban
lo que no tenian.

Nada de numeros escritos a mano: se compara contra lo que diga la base y
contra lo que mide Qt.
"""

import ast
import pathlib
import re
import time

from harness import PROJECT, Report, database_copy

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.context import AppContext
from app.models import FATIGUE, QUASI, ROTARY, TORSION
from app.services.catalogs import DEFAULT_PALETTE
from app.ui import theme
from app.ui.main_window import COMPACT_SIZES, FULL_WIDTH_PAGES, MainWindow
from app.ui.models.table_models import (
    LEFT,
    RIG_COLOR_ROLE,
    RIGHT,
    STATUS_LABELS,
)

report = Report("Repaso de interfaz")

app = QApplication([])
theme.apply(app)
context = AppContext(AppConfig(database_path=str(database_copy()),
                               auto_backup=False))
context.prepare()
window = MainWindow(context)
window.start()


def settle(segundos: float = 0.6) -> None:
    """Con reloj de pared: maximizar una ventana no es instantaneo."""
    fin = time.time() + segundos
    while time.time() < fin:
        app.processEvents()


settle()

TABLAS = {
    "fatigue": lambda: window.pages["fatigue"].ongoing.table,
    "torsion": lambda: window.pages["torsion"].table,
    "quasi": lambda: window.pages["quasi"].table,
    "rotary": lambda: window.pages["rotary"].table,
}

# ======================================================================
report.section("1. La ventana se usa entera")

for clave, obtener in TABLAS.items():
    window.show_page(clave)
    settle()
    tabla = obtener()
    usado = sum(tabla.columnWidth(c) for c in range(tabla.model().columnCount()))
    disponible = tabla.viewport().width()
    sobra = disponible - usado
    report.note(f"{clave:<8} ventana {window.width()}  columnas {usado} "
                f"de {disponible}  sobra {sobra}")
    report.check(f"{clave}: las columnas llenan el ancho", sobra <= 0,
                 f"sobran {sobra} px")

report.check("Torsión y Quasi ya no se maximizan",
             {"torsion", "quasi"}.isdisjoint(FULL_WIDTH_PAGES),
             str(sorted(FULL_WIDTH_PAGES)))
report.check("y tienen su propio tamaño",
             {"torsion", "quasi"} <= set(COMPACT_SIZES),
             str(COMPACT_SIZES.get("torsion")))

# La columna que se lleva el sobrante es la que de verdad cambia de fila a
# fila; antes se quedaba cortada a 240 px mientras el resto era hueco.
window.show_page("torsion")
settle()
tabla = window.pages["torsion"].table
modelo = tabla.source_model()
comentarios = modelo.headers.index("Comentarios")
report.check("es Comentarios la que crece", modelo.stretch_column == comentarios)
report.check("y pasa del tope de 240 px que tenian las demas",
             tabla.columnWidth(comentarios) > 240,
             f"{tabla.columnWidth(comentarios)} px")

# ======================================================================
report.section("2. Ninguna columna repite el mismo valor en todas las filas")

for clave, obtener in TABLAS.items():
    window.show_page(clave)
    settle(0.3)
    tabla = obtener()
    proxy = tabla.model()
    filas = min(proxy.rowCount(), 200)
    if filas < 4:
        continue
    chips = getattr(tabla.source_model(), "chips_column", None)
    constantes = []
    for columna in range(proxy.columnCount()):
        if columna == chips:      # la pinta un delegado, su texto va vacio
            continue
        # 'Requester' nace vacia por construccion: el dato existe desde que las
        # pruebas se comienzan desde una Work Order, asi que los registros
        # anteriores no lo tienen y se llena con el uso. Una columna nueva no
        # puede probar que no es constante el dia que se agrega.
        if tabla.source_model().headers[columna] == "Requester":
            continue
        valores = {proxy.index(f, columna).data() for f in range(filas)}
        if len(valores) == 1:
            constantes.append(tabla.source_model().headers[columna])
    report.check(f"{clave}: sin columnas constantes", not constantes,
                 str(constantes))

fatiga = window.pages["fatigue"]
report.check("Fatiga ya no lleva WO ni Estatus",
             not {"WO", "Estatus"} & set(fatiga.ongoing.model.headers),
             str(fatiga.ongoing.model.headers))
report.check("las finalizadas tampoco",
             not {"WO", "Estatus"} & set(fatiga.finished.model.headers),
             str(fatiga.finished.model.headers))
# Rotary si la conserva: es la unica que mezcla abiertas y cerradas.
rotary_model = window.pages["rotary"].table.source_model()
report.check("Rotary conserva Estatus, que ahi si distingue",
             "Estatus" in rotary_model.headers)
report.check("y lo muestra en español",
             set(STATUS_LABELS.values()) == {"En curso", "Finalizada"},
             str(STATUS_LABELS))

# ======================================================================
report.section("2b. La alineacion es la misma regla en las cuatro bitacoras")

# Dos alineaciones y ninguna mas: numeros a la derecha, todo lo demas a la
# izquierda. Y decidida por columna, no por celda -- antes se miraba el valor,
# asi que una celda vacia se alineaba distinto que sus vecinas y la tabla se
# veia descuadrada sin que ninguna regla lo explicara.
IZQUIERDA, DERECHA = int(LEFT), int(RIGHT)

for clave, obtener in TABLAS.items():
    window.show_page(clave)
    settle(0.3)
    tabla = obtener()
    proxy = tabla.model()
    modelo = tabla.source_model()
    filas = min(proxy.rowCount(), 30)
    if filas < 2:
        continue

    def alineaciones(columna, proxy=proxy, filas=filas):
        return {proxy.index(f, columna).data(Qt.ItemDataRole.TextAlignmentRole)
                for f in range(filas)}

    sueltas = set()
    irregulares = []
    descuadrados = []
    for columna in range(proxy.columnCount()):
        usadas = alineaciones(columna)
        sueltas |= usadas - {IZQUIERDA, DERECHA}
        if len(usadas) > 1:
            irregulares.append(modelo.headers[columna])
        encabezado = proxy.headerData(columna, Qt.Orientation.Horizontal,
                                      Qt.ItemDataRole.TextAlignmentRole)
        if encabezado not in usadas:
            descuadrados.append(modelo.headers[columna])

    report.check(f"{clave}: solo izquierda y derecha", not sueltas,
                 str(sorted(sueltas)))
    report.check(f"{clave}: cada columna se alinea igual en todas sus filas",
                 not irregulares, str(irregulares))
    report.check(f"{clave}: el encabezado va como su columna",
                 not descuadrados, str(descuadrados))

# Y en la vista de columnas completas, que es donde mas columnas hay que
# cuadrar: 45 en Fatiga.
window.show_page("fatigue")
pestania = window.pages["fatigue"].ongoing
pestania.view_toggle.setChecked(True)
settle(0.3)
completa = pestania.table.model()
usadas_completa = {
    completa.index(f, c).data(Qt.ItemDataRole.TextAlignmentRole)
    for c in range(completa.columnCount())
    for f in range(min(completa.rowCount(), 20))
}
report.check("fatiga completa: la regla no cambia al abrir las 45 columnas",
             usadas_completa <= {IZQUIERDA, DERECHA},
             str(sorted(usadas_completa)))
pestania.view_toggle.setChecked(False)
settle(0.3)


# ======================================================================
report.section("2c. Ninguna pantalla exige mas ancho del que hay")

# El escritorio mas chico donde corre esto es un portatil de 1366, y
# _fit_window recorta a 40 px menos. Una pantalla cuyo minimo pase de ahi nace
# mas ancha que el escritorio, y no hay forma de encogerla.
#
# Pasaba en seis de las ocho: filas horizontales que no encogen --botones,
# tarjetas de metrica, combos que miden por su elemento mas largo-- y una
# etiqueta con la ruta de la base, que ella sola pedia 1,136 px.
TOPE_PORTATIL = 1366 - 40

anchos = {}
for clave in ("work_orders", "fatigue", "torsion", "rotary", "rigs", "quasi",
              "dashboard", "settings"):
    window.show_page(clave)
    settle(0.2)
    anchos[clave] = window.pages[clave].minimumSizeHint().width()

for clave, ancho in sorted(anchos.items(), key=lambda kv: -kv[1]):
    report.note(f"{clave:<14} {ancho:>5} px")

anchas = {c: a for c, a in anchos.items() if a > TOPE_PORTATIL}
report.check(f"todas caben en un portatil de 1366 (tope {TOPE_PORTATIL})",
             not anchas, str(anchas))

window.show_menu()
settle(0.2)
report.check("y el menu tambien",
             window.menu.minimumSizeHint().width() <= TOPE_PORTATIL,
             str(window.menu.minimumSizeHint().width()))


# ======================================================================
report.section("3. Al desplazarse no se pierde de que fila se lee")

window.show_page("fatigue")
settle()
tab = fatiga.ongoing
tab.view_toggle.setChecked(True)      # vista de 46 columnas
settle()
tabla = tab.table
congeladas = tabla.source_model().frozen_columns
report.check("la vista completa congela columnas", congeladas >= 3,
             f"{congeladas} columnas")
report.check("la copia fija esta a la vista", tabla._frozen.isVisible())

barra = tabla.horizontalScrollBar()
barra.setValue(barra.maximum())
settle(0.3)

# La tabla de abajo ya va por las ultimas columnas...
primera_visible = tabla.columnAt(tabla._frozen.width() + 10)
encabezados = tabla.source_model().headers
report.note(f"tras desplazar, debajo de la copia fija va "
            f"'{encabezados[primera_visible]}'")
report.check("la tabla se desplazo de verdad", primera_visible > congeladas,
             encabezados[primera_visible])
# ...y la copia sigue enseñando el Test Batch en su sitio.
lote = tabla.source_model().batch_column
report.check("el Test Batch sigue fijo a la izquierda",
             not tabla._frozen.isColumnHidden(lote)
             and tabla._frozen.columnViewportPosition(lote) >= 0,
             f"x={tabla._frozen.columnViewportPosition(lote)}")
report.check("la copia solo enseña las congeladas",
             all(tabla._frozen.isColumnHidden(c)
                 for c in range(congeladas, len(encabezados))))
report.check("las dos tablas miran la misma fila",
             tabla._frozen.verticalScrollBar().value()
             == tabla.verticalScrollBar().value())

tab.view_toggle.setChecked(False)
settle(0.3)
report.check("en la vista compacta no hace falta y se retira",
             not tabla._frozen.isVisible())

# ======================================================================
report.section("4. Las etiquetas llevan tildes")

# Las mismas palabras que aparecian sin tilde en la pantalla. Se buscan solo
# en literales que no sean docstrings: el codigo y los comentarios siguen en
# ASCII a proposito.
SIN_TILDE = re.compile(
    r"\b(Bitacora|Ocupacion|Gestion|Torsion|Dias|Accion|Despues|Edicion"
    r"|Confirmacion|Conexion|conexion|vacio|vacia|catalogo|ningun|Ningun"
    r"|digitos|aqui|numero|Numero|seccion)\b"
)


def docstrings(tree):
    posiciones = set()
    for node in ast.walk(tree):
        cuerpo = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and cuerpo:
            primero = cuerpo[0]
            if isinstance(primero, ast.Expr) and \
               isinstance(primero.value, ast.Constant) and \
               isinstance(primero.value.value, str):
                posiciones.add((primero.value.lineno,
                                primero.value.col_offset))
    return posiciones


pendientes = []
for ruta in sorted((PROJECT / "app" / "ui").rglob("*.py")):
    texto = ruta.read_text(encoding="utf8")
    arbol = ast.parse(texto)
    docs = docstrings(arbol)
    for node in ast.walk(arbol):
        if not (isinstance(node, ast.Constant)
                and isinstance(node.value, str)):
            continue
        if (node.lineno, node.col_offset) in docs:
            continue
        valor = node.value
        # Se miran solo las cadenas que llegan a la pantalla: las claves de
        # pagina ('torsion', 'menu') son de una palabra y en minusculas.
        if "{" in valor or ";" in valor or " " not in valor:
            continue
        if SIN_TILDE.search(valor):
            pendientes.append(f"{ruta.name}:{node.lineno}  {valor[:50]}")

report.check("no queda texto de interfaz sin tildes", not pendientes,
             str(pendientes[:3]))
report.check("y el titulo de la ventana tambien",
             window.windowTitle() == "Bitácora de Pruebas",
             window.windowTitle())

# ======================================================================
report.section("5. El color del dashboard significa algo o no esta")

window.show_page("dashboard")
settle(1.5)
dash = window.pages["dashboard"]

tarjetas = [dash.card_ongoing, dash.card_cycles, dash.card_samples,
            dash.card_rigs]
colores = {t.value_label.styleSheet().split("color:")[1].split(";")[0].strip()
           for t in tarjetas}
report.check("las cuatro tarjetas van del mismo color", len(colores) == 1,
             str(colores))
report.check("y no gastan el rojo ni el naranja, que avisan de algo",
             not {theme.DANGER.lower(), theme.WARNING.lower()}
             & {c.lower() for c in colores}, str(colores))

vistas = [dash.grid.itemAt(i).widget() for i in range(dash.grid.count())]
pastel = next(v.chart() for v in vistas if "cliente" in v.chart().title())
porciones = pastel.series()[0].slices()
report.note(f"porciones del pastel: {[p.label() for p in porciones]}")
report.check("el pastel cabe en su leyenda", len(porciones) <= 5,
             f"{len(porciones)} porciones")
paleta = {c.upper() for c in DEFAULT_PALETTE}
report.check("y sus colores salen de la paleta de rigs, que se distinguen",
             all(p.color().name().upper() in paleta for p in porciones),
             str([p.color().name() for p in porciones]))

tipos = next(v.chart() for v in vistas if "tipo de ensayo" in v.chart().title())
barras = tipos.series()[0].barSets()
report.check("una barra por tipo, con el color de su bitácora",
             [b.color().name().upper() for b in barras]
             == [c.accent.upper() for c in (FATIGUE, ROTARY, TORSION, QUASI)],
             str([b.label() for b in barras]))

# ======================================================================
report.section("6. Se puede abrir un registro sin saberlo de memoria")

for clave in ("fatigue", "torsion", "quasi", "rotary"):
    window.show_page(clave)
    settle(0.3)
    pagina = window.pages[clave]
    tab = pagina.ongoing if clave == "fatigue" else pagina
    tabla = TABLAS[clave]()
    report.check(f"{clave}: hay boton para abrir",
                 tab.open_button.text() == "Abrir registro")
    report.check(f"{clave}: apagado mientras no hay fila seleccionada",
                 not tab.open_button.isEnabled())
    tabla.selectRow(0)
    settle(0.2)
    report.check(f"{clave}: se enciende al seleccionar",
                 tab.open_button.isEnabled())
    report.check(f"{clave}: y la tabla ofrece menú con el botón derecho",
                 tabla.contextMenuPolicy()
                 == Qt.ContextMenuPolicy.CustomContextMenu)

abiertos = []
window.show_page("torsion")
settle(0.3)
tabla = TABLAS["torsion"]()
# Se desconecta a la pagina antes de probar: su ranura abre el formulario con
# exec(), que se queda esperando a que alguien lo cierre.
tabla.recordActivated.disconnect()
tabla.recordActivated.connect(lambda r: abiertos.append(r))
tabla.selectRow(0)
report.check("el botón abre lo seleccionado", tabla.open_selected())
report.check("y entrega el registro", len(abiertos) == 1,
             str(len(abiertos)))

# Atajos: antes habia dos en toda la app, las dos para reordenar Work Orders.
from PySide6.QtGui import QShortcut

for clave in ("torsion", "rotary", "work_orders", "dashboard"):
    teclas = {a.key().toString()
              for a in window.pages[clave].findChildren(QShortcut)}
    report.check(f"{clave}: Esc regresa y F5 actualiza",
                 {"Esc", "F5"} <= teclas, str(sorted(teclas)))

teclas_fatiga = {a.key().toString()
                 for a in window.pages["fatigue"].findChildren(QShortcut)}
report.check("Fatiga tiene los suyos aunque no herede de BasePage",
             {"Esc", "F5", "Ctrl+F"} <= teclas_fatiga, str(sorted(teclas_fatiga)))
report.check("Torsión: Ctrl+F busca y Ctrl+N da de alta",
             window.pages["torsion"].new_button.shortcut()
             == QKeySequence(QKeySequence.StandardKey.New))
report.check("Fatiga: Ctrl+E exporta",
             fatiga.ongoing.export_button.shortcut() == QKeySequence("Ctrl+E"))

# Ctrl+F de verdad deja el cursor en el buscador.
window.show_page("torsion")
settle(0.3)
window.pages["torsion"].filters.focus_search()
settle(0.2)
report.check("el buscador recibe el foco",
             window.pages["torsion"].filters.search.hasFocus())

# ======================================================================
report.section("7. El formulario no anuncia lo que no tiene")

from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.widgets.common import BLANK_LABEL, combo_value
from app.models import ONGOING

registro = context.fatigue.list(ONGOING)[0]
dialogo = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                        test=registro)
dialogo.show()
settle(0.4)

vacios = [i for i in range(9) if combo_value(dialogo.rigs[i]) == ""]
report.check("hay piezas sin banco que comprobar", bool(vacios), str(vacios))
combo = dialogo.rigs[vacios[-1]]
# El centinela tiene que seguir en la lista: es la unica forma de volver a
# dejar el campo en blanco. Lo que cambia es que ya no se dibuja al cerrarla.
report.check("el centinela sigue en la lista, que es donde hace falta",
             combo.itemData(0) == "" and combo.itemText(0).strip() != "",
             f"{combo.itemText(0)!r} -> {combo.itemData(0)!r}")


def tinta(widget):
    """Pixeles de texto en la banda central del campo.

    Se cuenta contra el color mas repetido de esa banda y no contra la esquina
    del widget: la esquina es borde, y midiendola cualquier combo --lleno o
    vacio-- daba el mismo numero.
    """
    from collections import Counter
    imagen = widget.grab().toImage()
    izquierda, derecha = 8, max(9, imagen.width() - 26)   # sin marco ni flecha
    arriba, abajo = 5, max(6, imagen.height() - 5)
    puntos = [imagen.pixelColor(x, y).name()
              for x in range(izquierda, derecha)
              for y in range(arriba, abajo)]
    fondo, _ = Counter(puntos).most_common(1)[0]
    return sum(1 for p in puntos if p != fondo)


vacio = tinta(combo)
con_banco = [dialogo.rigs[i] for i in range(9)
             if combo_value(dialogo.rigs[i])]
report.note(f"pixeles de texto: combo vacío {vacio}, "
            f"combo con banco {tinta(con_banco[0]) if con_banco else '--'}")
report.check("el combo vacío se dibuja vacío", vacio == 0, f"{vacio} pixeles")
if con_banco:
    report.check("y uno con banco sí dibuja su texto",
                 tinta(con_banco[0]) > 50, f"{tinta(con_banco[0])} pixeles")
dialogo.close()

# Los avisos que solo costaban un clic
fuente = (PROJECT / "app" / "ui" / "dialogs" / "fatigue_dialog.py").read_text(
    encoding="utf8")
report.check("cerrar una prueba ya no abre un cuadro para decir 'listo'",
             "Prueba cerrada" not in fuente)
report.check("reabrirla tampoco", "El registro volvió" not in fuente)

# ======================================================================
report.section("8. Los detalles del historial y de la base")

from app.ui.dialogs.history_dialog import HEADERS, HistoryDialog

report.check("el historial ya no gasta una columna en el equipo",
             "Equipo" not in HEADERS, str(HEADERS))
historial = HistoryDialog(context.audit, "fatigue_tests", registro.id,
                          registro.test_batch)
filas = historial.table.rowCount()
report.check("el historial trae movimientos", filas > 0, f"{filas} filas")
usuario = historial.table.item(0, 1)
report.check("el equipo vive en el tooltip del usuario",
             "Equipo:" in (usuario.toolTip() or ""), usuario.toolTip())
historial.close()

window.show_page("settings")
settle(0.4)
ajustes = window.pages["settings"]
pestanias = [ajustes.tabs.tabText(i) for i in range(ajustes.tabs.count())]
ajustes.tabs.setCurrentIndex(pestanias.index("Base de datos"))
settle(0.3)
db_tab = ajustes.tabs.currentWidget()
report.note(f"tamaño: {db_tab.size_label.text()!r}  "
            f"respaldo: {db_tab.backup_label.text()!r}")
report.check("Ajustes dice cuánto pesa la base",
             "MB" in db_tab.size_label.text(), db_tab.size_label.text())
report.check("y cuándo fue el último respaldo",
             bool(db_tab.backup_label.text()), db_tab.backup_label.text())

window.close()
app.quit()
raise SystemExit(report.finish())
