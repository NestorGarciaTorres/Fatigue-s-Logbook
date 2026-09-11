"""Ventana principal.

Un ``QStackedWidget`` sustituye al esquema de ``Toplevel`` + ``withdraw()`` /
``deiconify()`` de la version anterior, donde cada bitacora abria una ventana
nueva, escondia la anterior y tenia que recolocarse a mano en el monitor
correcto con ``screeninfo``.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from app.context import AppContext
from app.models import FATIGUE, QUASI, ROTARY, TORSION
from app.services.identity import current_author
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.fatigue_page import FatiguePage
from app.ui.pages.generic_page import GenericPage
from app.ui.pages.menu_page import MenuPage
from app.ui.pages.rigs_page import RigsPage
from app.ui.pages.rotary_page import RotaryPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.work_orders_page import WorkOrdersPage
from app.ui.widgets.changes_bar import ChangesBar


# Solo Fatiga y Rotary necesitan la pantalla entera: son las que tienen 46
# columnas en vista completa. Torsion y Quasi tienen siete, y maximizadas
# usaban 870 px de 2528 -- dos tercios de pantalla en blanco.
FULL_WIDTH_PAGES = frozenset({"fatigue", "rotary"})

# Tamano de las pantallas que no van a pantalla completa.
COMPACT_SIZES = {
    "menu": (780, 660),
    "work_orders": (1180, 700),
    # El dashboard crecio dos veces: primero con el panel de piezas por banco
    # --dieciseis renglones debajo de las graficas-- y despues con el historial
    # de mantenimiento. En una pantalla mas baja el area de desplazamiento se
    # encarga; aqui se pide lo que hace falta para verlo entero.
    "dashboard": (1400, 1300),
    # La ocupacion de rigs crecio al agrupar los bancos por bitacora: son
    # dieciseis tarjetas mas cuatro encabezados. Con 1100x720 la rejilla pedia
    # 1060 px de alto y se veian 512, asi que siempre cortaba a media tarjeta
    # -- que se lee peor que una fila entera asomando. Mas ancha caben cinco
    # columnas en vez de cuatro, y eso ya quita una fila.
    "rigs": (1500, 1170),
    "settings": (1080, 700),
    "torsion": (1240, 820),
    "quasi": (1240, 820),
}
DEFAULT_COMPACT = (1100, 700)

# Cada cuanto se pregunta al historial si otro equipo guardo algo. Es una
# consulta sobre un indice: medio minuto no se nota en la red y es poco tiempo
# para estar decidiendo con datos viejos.
CHANGES_POLL_MS = 30_000

# Que tablas del historial le importan a cada pantalla. None = todas; un
# conjunto vacio = ninguna (Ajustes edita catalogos, que no pasan por el
# historial). El mantenimiento vacia y devuelve bancos de Fatiga, asi que
# tambien cambia lo que ensenia su bitacora.
WATCHED_TABLES = {
    "work_orders": frozenset({"work_orders"}),
    "fatigue": frozenset({FATIGUE.table, "rig_maintenance"}),
    "rotary": frozenset({ROTARY.table}),
    "torsion": frozenset({TORSION.table}),
    "quasi": frozenset({QUASI.table}),
    "rigs": frozenset({FATIGUE.table, ROTARY.table, TORSION.table,
                       QUASI.table, "rig_maintenance"}),
    "dashboard": None,
    "settings": frozenset(),
}


class PageStack(QStackedWidget):
    """Pila que mide solo la pagina visible.

    QStackedWidget devuelve por omision el maximo de todas sus paginas, asi que
    el minimo del dashboard le ponia suelo al menu: se pedia una ventana de 780
    de alto y salia de 803, la mas alta de las siete.
    """

    def sizeHint(self):
        current = self.currentWidget()
        return current.sizeHint() if current else super().sizeHint()

    def minimumSizeHint(self):
        current = self.currentWidget()
        return current.minimumSizeHint() if current else super().minimumSizeHint()


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context

        self.setWindowTitle("Bitácora de Pruebas")
        self.resize(*COMPACT_SIZES["menu"])

        # El aviso de datos nuevos va encima de la pila, fuera de las paginas:
        # es de la ventana, no de una bitacora, y asi no hay que repetirlo en
        # ocho pantallas.
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self.changes_bar = ChangesBar()
        self.changes_bar.refreshRequested.connect(self.refresh_current)
        central_layout.addWidget(self.changes_bar)

        self.stack = PageStack()
        central_layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self._current_key = "menu"
        self._seen_id = 0
        self._seen_database = None

        self.menu = MenuPage(context.config.database.name)
        self.menu.navigate.connect(self.show_page)

        self.pages = {
            "work_orders": WorkOrdersPage(context),
            "fatigue": FatiguePage(context),
            "torsion": GenericPage(context, TORSION),
            "rotary": RotaryPage(context),
            "rigs": RigsPage(context),
            "quasi": GenericPage(context, QUASI),
            "dashboard": DashboardPage(context),
            "settings": SettingsPage(context),
        }

        self.stack.addWidget(self.menu)
        for page in self.pages.values():
            page.set_back_callback(self.show_menu)
            self.stack.addWidget(page)

        # Un cambio de catalogo repinta lo que este visible sin reiniciar.
        context.catalogs.subscribe(self._on_catalogs_changed)

        # Recargar a mano (F5) tambien pone al dia: el aviso sobra.
        for page in self.pages.values():
            refreshed = getattr(page, "refreshed", None)
            if refreshed is not None:
                refreshed.connect(self.mark_seen)

        self.mark_seen()
        self.changes_timer = QTimer(self)
        self.changes_timer.setInterval(CHANGES_POLL_MS)
        self.changes_timer.timeout.connect(self.check_for_changes)
        self.changes_timer.start()

    def start(self) -> None:
        """Abre la aplicacion en el menu, con el tamano del menu.

        Existe para que el arranque pase por la misma logica de tamano que la
        navegacion: ``main.py`` llamaba a showMaximized() por su cuenta y la
        ventana nacia a pantalla completa por mucho que el menu pidiera 780.
        """
        self.show_menu()
        self.show()

    def show_menu(self) -> None:
        self._current_key = "menu"
        self.changes_bar.hide()
        self.stack.setCurrentWidget(self.menu)
        self.stack.updateGeometry()
        self._fit_window("menu")

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self._current_key = key
        # La marca antes de cargar: lo que se guarde mientras la pagina lee
        # queda por ver, en vez de darse por visto sin estar en pantalla.
        self.mark_seen()
        page.refresh()
        self.stack.setCurrentWidget(page)
        # Sin esto la pila conserva el minimo de la pagina anterior y la
        # ventana no llega a encoger.
        self.stack.updateGeometry()
        self._fit_window(key)

    # --- tamano de la ventana --------------------------------------------
    def _fit_window(self, key: str) -> None:
        """Ajusta la ventana a lo que necesita la pantalla que se muestra."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:                    # pragma: no cover - sin pantalla
            return
        available = screen.availableGeometry()

        if key in FULL_WIDTH_PAGES:
            # El resize va antes del showMaximized y no sobra: cuando se pasa
            # del menu a una bitacora en el mismo instante --lo hacen las
            # pruebas, y a veces el primer clic-- el estado maximizado se
            # aplica pero la ventana se queda con el ancho que pide el layout
            # (1011 px de 2560). Dando la medida a mano, el ancho es correcto
            # aunque el gestor de ventanas se demore.
            self.resize(available.size())
            self.showMaximized()
            return

        # showNormal() antes de medir: si venimos de una bitacora maximizada,
        # resize() sobre una ventana maximizada no hace nada.
        if self.isMaximized():
            self.showNormal()

        width, height = COMPACT_SIZES.get(key, DEFAULT_COMPACT)
        width = min(width, available.width() - 40)
        height = min(height, available.height() - 60)
        self.resize(width, height)
        self.move(
            available.x() + (available.width() - width) // 2,
            available.y() + (available.height() - height) // 2,
        )

    def _on_catalogs_changed(self) -> None:
        self.refresh_current()

    # --- datos nuevos de otros equipos -------------------------------------
    def mark_seen(self) -> None:
        """Lo guardado hasta ahora ya esta en pantalla: el aviso se oculta."""
        try:
            self._seen_id = self.context.audit.last_id()
        except Exception:                      # pragma: no cover - red caida
            return
        self._seen_database = self.context.database.path
        self.changes_bar.hide()

    def pending_changes(self) -> list:
        """Lo que otros equipos guardaron desde la ultima carga, si le importa
        a la pantalla visible."""
        tablas = WATCHED_TABLES.get(self._current_key, frozenset())
        if self._current_key == "menu" or tablas == frozenset():
            return []
        # Otra base desde Ajustes: sus numeros de historial no tienen nada que
        # ver con los de la anterior.
        if self.context.database.path != self._seen_database:
            self.mark_seen()
            return []
        return self.context.audit.changes_since(
            self._seen_id, exclude_machine=current_author()[1], tables=tablas,
        )

    def check_for_changes(self) -> None:
        """Lo que hace el reloj cada medio minuto."""
        try:
            cambios = self.pending_changes()
        except Exception:                      # pragma: no cover - red caida
            # Sin red no hay nada que avisar; el siguiente intento lo dira.
            return
        self.changes_bar.show_changes(cambios)

    def refresh_current(self) -> None:
        """Recarga la pantalla visible (el boton 'Actualizar' del aviso)."""
        current = self.stack.currentWidget()
        self.mark_seen()
        if current is not self.menu and hasattr(current, "refresh"):
            current.refresh()
