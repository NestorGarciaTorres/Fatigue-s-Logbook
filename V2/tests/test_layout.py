"""Verifica tamanos de ventana, menu agrupado, boton de WO y dashboard."""

from harness import (
    Report, database_copy, empty_database, make_context, offscreen,
    qt_app, settle,
)


import sys
from pathlib import Path


from PySide6.QtWidgets import QApplication, QPushButton

from app.config import AppConfig
from app.context import AppContext
from app.models import FINISHED, Requester, WorkOrder
from app.ui import theme
from app.ui.main_window import COMPACT_SIZES, FULL_WIDTH_PAGES, MainWindow
from app.ui.pages import menu_page
from app.ui.pages.work_orders_page import ACTION_WIDTH, ROW_HEIGHT

COPY = database_copy()
failures = []


def check(label, condition, detail=""):
    print(("OK    " if condition else "FALLO ") + label +
          (f"   {detail}" if detail else ""))
    if not condition:
        failures.append(label)


app = QApplication(sys.argv)
theme.apply(app)
context = AppContext(AppConfig(database_path=str(COPY), auto_backup=False))
context.prepare()

# La copia puede traer ordenes reales ya comenzadas, asi que se crean siempre
# las que esta prueba necesita en vez de darlas por supuestas.
if "Ana Torres" not in context.catalogs.requesters():
    context.catalogs.save_requester(Requester(name="Ana Torres"))
for tipo, batch in (("fatigue", "990030STF01"), ("rotary", "990031SRF01"),
                    ("torsion", "990032STO01")):
    if not context.work_orders.batch_exists(batch):
        context.work_orders.create(
            WorkOrder(test_type=tipo, test_batch=batch, customer="AUDI",
                      qty_samples=4, requester="Ana Torres"), ("v", "PC"))

# start() y no show(): es lo que hace main.py. Probar con show() dejaba pasar
# que el arranque real llamara a showMaximized() y abriera a pantalla completa.
window = MainWindow(context)
window.start()
for _ in range(10):
    app.processEvents()

print("=== 0. El arranque abre en el menu, no a pantalla completa ===")
check("main.py arranca con start()",
      "window.start()" in (Path(r"C:\Users\Nestor\Desktop\AI Projects"
                                r"\fatigue-logbook\main.py")
                           .read_text(encoding="utf-8")))
check("y no con showMaximized()",
      "showMaximized" not in (Path(r"C:\Users\Nestor\Desktop\AI Projects"
                                   r"\fatigue-logbook\main.py")
                              .read_text(encoding="utf-8")))
print(f"      al abrir: {window.width()}x{window.height()}  "
      f"maximizada={window.isMaximized()}")
check("la ventana no nace maximizada", not window.isMaximized(),
      f"{window.width()}x{window.height()}")
check("nace con el tamano del menu",
      (window.width(), window.height()) == COMPACT_SIZES["menu"],
      f"{window.width()}x{window.height()} vs {COMPACT_SIZES['menu']}")


# ======================================================================
print("=== 1. El boton 'Comenzar prueba' se ve entero ===")
window.show_page("work_orders")
page = window.pages["work_orders"]
page.status_filter.setCurrentText("Todas")
page.refresh()
for _ in range(10):
    app.processEvents()

boton = next(
    page.table.cellWidget(r, page.ACTION_COLUMN)
    for r in range(page.table.rowCount())
    if isinstance(page.table.cellWidget(r, page.ACTION_COLUMN), QPushButton)
)
hint = boton.sizeHint()
print(f"      pide {hint.width()}x{hint.height()}, "
      f"recibe {boton.width()}x{boton.height()}")
print(f"      fila {page.table.rowHeight(0)} px, "
      f"columna {page.table.columnWidth(page.ACTION_COLUMN)} px")
check("el boton recibe al menos el alto que pide",
      boton.height() >= hint.height(),
      f"{boton.height()} vs {hint.height()}")
check("y al menos el ancho que pide",
      boton.width() >= hint.width(), f"{boton.width()} vs {hint.width()}")
check("la fila da sitio al boton", page.table.rowHeight(0) >= ROW_HEIGHT - 2,
      str(page.table.rowHeight(0)))
check("el texto cabe sin recortarse",
      boton.fontMetrics().horizontalAdvance(boton.text()) < boton.width(),
      f"texto {boton.fontMetrics().horizontalAdvance(boton.text())} px "
      f"en {boton.width()} px")
check("la columna de accion tiene ancho fijo",
      page.table.columnWidth(page.ACTION_COLUMN) == ACTION_WIDTH,
      str(page.table.columnWidth(page.ACTION_COLUMN)))

# ======================================================================
print("\n=== 2. Tamano de ventana por pantalla ===")
pantalla = window.screen().availableGeometry()
print(f"      pantalla disponible: {pantalla.width()}x{pantalla.height()}")

medidas = {}
for key in ("work_orders", "dashboard", "rigs", "settings",
            "fatigue", "torsion", "rotary", "quasi"):
    window.show_page(key)
    for _ in range(12):
        app.processEvents()
    medidas[key] = (window.width(), window.height(), window.isMaximized())
    print(f"      {key:<12} {window.width()}x{window.height()}  "
          f"maximizada={window.isMaximized()}")

window.show_menu()
for _ in range(12):
    app.processEvents()
medidas["menu"] = (window.width(), window.height(), window.isMaximized())
print(f"      {'menu':<12} {window.width()}x{window.height()}")

for key in ("fatigue", "torsion", "rotary", "quasi"):
    check(f"{key} ocupa la pantalla", medidas[key][2], str(medidas[key]))

for key in ("menu", "work_orders", "dashboard", "rigs", "settings"):
    ancho, alto, maximizada = medidas[key]
    check(f"{key} NO ocupa la pantalla", not maximizada, str(medidas[key]))
    check(f"{key} es mas angosta que la pantalla",
          ancho < pantalla.width(), f"{ancho} vs {pantalla.width()}")
    pedido = COMPACT_SIZES.get(key, (1100, 700))
    check(f"{key} respeta el tamano pedido {pedido}",
          (ancho, alto) == (min(pedido[0], pantalla.width() - 40),
                            min(pedido[1], pantalla.height() - 60)),
          f"pedido {pedido}, real {(ancho, alto)}")

check("volver al menu encoge la ventana",
      medidas["menu"][0] < medidas["dashboard"][0],
      f"menu {medidas['menu'][0]}, dashboard {medidas['dashboard'][0]}")
check("solo las cuatro bitacoras van a pantalla completa",
      FULL_WIDTH_PAGES == {"fatigue", "torsion", "rotary", "quasi"},
      str(sorted(FULL_WIDTH_PAGES)))

# ======================================================================
print("\n=== 3. El menu distingue captura de gestion ===")
capturas = [k for k, _, _ in menu_page.LOGBOOKS]
gestion = [k for k, _, _ in menu_page.MANAGEMENT]
print(f"      captura: {capturas}")
print(f"      gestion: {gestion}")
check("las cuatro bitacoras van en 'Captura de pruebas'",
      capturas == ["fatigue", "torsion", "rotary", "quasi"], str(capturas))
check("el resto va en 'Gestion y consulta'",
      set(gestion) == {"work_orders", "rigs", "dashboard", "settings"},
      str(gestion))
check("los botones de captura son mas altos",
      menu_page.LOGBOOK_SIZE[1] > menu_page.MANAGEMENT_SIZE[1],
      f"{menu_page.LOGBOOK_SIZE} vs {menu_page.MANAGEMENT_SIZE}")

botones = {b.text(): b for b in window.menu.findChildren(QPushButton)}
check("estan los ocho botones", len(botones) == 8, str(sorted(botones)))
check("los de bitacora se dibujan mas grandes",
      botones["Fatiga"].minimumHeight() > botones["Ajustes"].minimumHeight(),
      f"{botones['Fatiga'].minimumHeight()} vs "
      f"{botones['Ajustes'].minimumHeight()}")
etiquetas = [w.text() for w in window.menu.findChildren(type(window.menu.
             findChildren(QPushButton)[0].parent().findChild(
                 __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel)))]
check("hay un rotulo por grupo",
      any("CAPTURA" in t for t in etiquetas)
      and any("GESTION" in t for t in etiquetas), str(etiquetas))

# ======================================================================
print("\n=== 4. Dashboard ===")
window.show_page("dashboard")
for _ in range(15):
    app.processEvents()
dash = window.pages["dashboard"]
vistas = [dash.grid.itemAt(i).widget() for i in range(dash.grid.count())]
titulos = [v.chart().title() for v in vistas]
print(f"      graficas: {titulos}")

check("quedan tres graficas", len(vistas) == 3, str(len(vistas)))
check("ya no esta la de uso por Test Rig",
      not any("Test Rig" in t for t in titulos), str(titulos))
check("no queda el metodo que la construia",
      not hasattr(dash, "_usage_by_rig"))

tipo_chart = next(v.chart() for v in vistas if "tipo de ensayo" in v.chart().title())
check("el titulo dice que son finalizadas",
      "finalizadas" in tipo_chart.title().lower(), tipo_chart.title())

series = tipo_chart.series()[0]
conjuntos = [bs.label() for bs in series.barSets()]
check("una sola serie, sin 'En curso'", conjuntos == ["Finalizadas"],
      str(conjuntos))

valores = [series.barSets()[0].at(i) for i in range(series.barSets()[0].count())]
print(f"      barras (Fatiga, Rotary, Torsion, Quasi): {valores}")

# Con el MISMO filtro de fechas que usa la grafica: el dashboard tiene un
# rango arriba, y contar la base entera comparaba cosas distintas.
from app.services import filtering
rango = dash._range_filter()
esperado = [
    sum(1 for t in filtering.apply(context.fatigue.list(), rango)
        if t.test_status == FINISHED),
    sum(1 for t in filtering.apply(context.rotary.list(), rango)
        if t.test_status == FINISHED),
    len(filtering.apply(context.torsion.list(), rango)),
    len(filtering.apply(context.quasi.list(), rango)),
]
print(f"      contado en la base:                     "
      f"{[float(v) for v in esperado]}")
check("las barras cuadran con las pruebas finalizadas de la base",
      valores == [float(v) for v in esperado],
      f"grafica {valores}, base {esperado}")
check("ninguna barra cuenta pruebas en curso",
      sum(valores) == sum(esperado), f"{sum(valores)} vs {sum(esperado)}")

app.quit()
print("\n" + "=" * 64)
if failures:
    print(f"FALLARON {len(failures)}:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("TODAS LAS COMPROBACIONES PASARON")
