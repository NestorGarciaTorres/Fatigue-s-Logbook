"""Ventana principal.

Un ``QStackedWidget`` sustituye al esquema de ``Toplevel`` + ``withdraw()`` /
``deiconify()`` de la version anterior, donde cada bitacora abria una ventana
nueva, escondia la anterior y tenia que recolocarse a mano en el monitor
correcto con ``screeninfo``.
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from app.context import AppContext
from app.models import QUASI, TORSION
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.fatigue_page import FatiguePage
from app.ui.pages.generic_page import GenericPage
from app.ui.pages.menu_page import MenuPage
from app.ui.pages.rigs_page import RigsPage
from app.ui.pages.rotary_page import RotaryPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.work_orders_page import WorkOrdersPage


# Solo las bitacoras necesitan la pantalla entera: tienen tablas anchas, hasta
# 37 columnas en vista completa. El resto son formularios y listas cortas, y a
# pantalla completa quedaban con mas vacio que contenido.
FULL_WIDTH_PAGES = frozenset({"fatigue", "torsion", "rotary", "quasi"})

# Tamano de las pantallas que no van a pantalla completa.
COMPACT_SIZES = {
    "menu": (780, 660),
    "work_orders": (1180, 700),
    "dashboard": (1200, 780),
    "rigs": (1100, 720),
    "settings": (1080, 700),
}
DEFAULT_COMPACT = (1100, 700)


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

        self.setWindowTitle("Bitacora de Pruebas")
        self.resize(*COMPACT_SIZES["menu"])

        self.stack = PageStack()
        self.setCentralWidget(self.stack)

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

    def start(self) -> None:
        """Abre la aplicacion en el menu, con el tamano del menu.

        Existe para que el arranque pase por la misma logica de tamano que la
        navegacion: ``main.py`` llamaba a showMaximized() por su cuenta y la
        ventana nacia a pantalla completa por mucho que el menu pidiera 780.
        """
        self.show_menu()
        self.show()

    def show_menu(self) -> None:
        self.stack.setCurrentWidget(self.menu)
        self.stack.updateGeometry()
        self._fit_window("menu")

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
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
        current = self.stack.currentWidget()
        if current is not self.menu and hasattr(current, "refresh"):
            current.refresh()
