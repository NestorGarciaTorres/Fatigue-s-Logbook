"""Ventana principal: barra lateral, pila de pantallas y aviso de cambios.

La navegacion cambia respecto al proyecto anterior. Alli habia un menu de ocho
botones y cada pantalla llevaba su propio 'Regresar al menu': para pasar de
Fatiga a Work Orders habia que volver al menu y entrar otra vez. Aqui la barra
lateral esta siempre a la vista y se salta de una a otra directamente.

Lo que **no** cambia es como se entera la app de que otro equipo guardo algo:
se pregunta al ``audit_log``, no se vigila el archivo. Cada escritura deja su
apunte con el equipo que la hizo, asi que lo propio se descarta por ``machine``
y cada pantalla pide solo sus tablas. Vigilar el ``.db`` por fecha o tamano no
distingue lo propio de lo ajeno, y ``PRAGMA data_version`` no sirve con
conexiones de vida corta.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.identity import author_label, current_author
# El mapeo pantalla -> tablas vigiladas se importa en vez de reescribirse: si
# se copiara, una pantalla nueva quedaria avisando de lo que no le importa.
from app.ui.main_window import CHANGES_POLL_MS, WATCHED_TABLES
from components import buttons, labels
from components.banner import ChangesBanner
from theme.manager import theme
from theme.rig_palette import RigPalette

log = logging.getLogger(__name__)

SIDEBAR_WIDTH = 210

# (clave, rotulo). El orden es el de uso: primero lo que se abre a diario.
DESTINATIONS = [
    ("work_orders", "Work Orders"),
    ("fatigue", "Fatiga"),
    ("rotary", "Rotary"),
    ("torsion", "Torsión"),
    ("quasi", "Quasi"),
    ("rigs", "Ocupación de rigs"),
    ("dashboard", "Dashboard"),
    ("settings", "Ajustes"),
]


class Sidebar(QFrame):
    """Navegacion permanente."""

    def __init__(self, on_navigate, on_toggle_theme, database_name: str,
                 parent=None):
        super().__init__(parent)
        self.setProperty("role", "sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(4)

        layout.addWidget(labels.subheading("Bitácora"))
        layout.addWidget(labels.muted("de Pruebas"))
        layout.addSpacing(14)

        self.buttons: dict[str, object] = {}
        for clave, rotulo in DESTINATIONS:
            boton = buttons.nav_button(
                rotulo, lambda k=clave: on_navigate(k))
            layout.addWidget(boton)
            self.buttons[clave] = boton

        layout.addStretch(1)
        layout.addWidget(labels.divider())

        self.theme_button = buttons.button(
            "", buttons.GHOST,
            tooltip="Cambiar entre tema claro y oscuro",
            on_click=on_toggle_theme)
        layout.addWidget(self.theme_button)
        self.update_theme_button()

        pie = labels.muted(author_label())
        pie.setWordWrap(True)
        layout.addWidget(pie)
        base = labels.muted(database_name)
        base.setToolTip(database_name)
        layout.addWidget(base)

    def update_theme_button(self) -> None:
        # El boton dice a donde lleva, no donde esta. 'Tema oscuro' estando en
        # claro es lo que el usuario quiere pulsar; decir 'Tema claro' seria
        # informar del estado y dejarle adivinar el efecto.
        self.theme_button.setText(
            "Tema claro" if theme().is_dark else "Tema oscuro")

    def set_active(self, key: str) -> None:
        for clave, boton in self.buttons.items():
            buttons.set_active(boton, clave == key)


class MainWindow(QMainWindow):
    def __init__(self, context):
        super().__init__()
        self.context = context
        self.rig_palette = RigPalette(context.database)

        self.setWindowTitle("Bitácora de Pruebas")
        self.resize(1400, 880)
        self.setMinimumSize(1024, 640)

        self._current_key = ""
        self._seen_id = 0
        self._seen_database = None

        central = QWidget()
        fila = QHBoxLayout(central)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(0)

        self.sidebar = Sidebar(self.show_page, self.toggle_theme,
                               context.config.database.name)
        fila.addWidget(self.sidebar)

        derecha = QVBoxLayout()
        derecha.setContentsMargins(0, 0, 0, 0)
        derecha.setSpacing(0)

        self.banner = ChangesBanner()
        self.banner.refreshRequested.connect(self.refresh_current)
        derecha.addWidget(self.banner)

        self.stack = QStackedWidget()
        derecha.addWidget(self.stack, 1)
        fila.addLayout(derecha, 1)
        self.setCentralWidget(central)

        self.pages: dict[str, QWidget] = {}
        self._build_pages()

        # Un cambio de catalogo repinta lo que este visible sin reiniciar.
        context.catalogs.subscribe(self._on_catalogs_changed)

        for pagina in self.pages.values():
            senal = getattr(pagina, "refreshed", None)
            if senal is not None:
                senal.connect(self.mark_seen)

        self.mark_seen()
        self.changes_timer = QTimer(self)
        self.changes_timer.setInterval(CHANGES_POLL_MS)
        self.changes_timer.timeout.connect(self.check_for_changes)
        self.changes_timer.start()

    # --- pantallas --------------------------------------------------------
    def _build_pages(self) -> None:
        from app.models import QUASI, TORSION
        from pages.dashboard import DashboardPage
        from pages.fatigue import FatiguePage
        from pages.generic import GenericPage
        from pages.rigs import RigsPage
        from pages.rotary import RotaryPage
        from pages.settings import SettingsPage
        from pages.work_orders import WorkOrdersPage

        self.pages["work_orders"] = WorkOrdersPage(self.context,
                                                   self.rig_palette)
        self.pages["fatigue"] = FatiguePage(self.context, self.rig_palette)
        self.pages["rotary"] = RotaryPage(self.context, self.rig_palette)
        self.pages["torsion"] = GenericPage(self.context, self.rig_palette,
                                            TORSION)
        self.pages["quasi"] = GenericPage(self.context, self.rig_palette,
                                          QUASI)
        self.pages["rigs"] = RigsPage(self.context, self.rig_palette)
        self.pages["dashboard"] = DashboardPage(self.context,
                                                self.rig_palette)
        self.pages["settings"] = SettingsPage(self.context,
                                              self.rig_palette)

        for pagina in self.pages.values():
            self.stack.addWidget(pagina)

    def show_page(self, key: str) -> None:
        pagina = self.pages.get(key)
        if pagina is None:
            return
        self._current_key = key
        # La marca va **antes** de cargar: lo que se guarde mientras la pagina
        # lee queda por ver, en vez de darse por visto sin estar en pantalla.
        self.mark_seen()
        pagina.refresh()
        self.stack.setCurrentWidget(pagina)
        self.sidebar.set_active(key)

    def start(self) -> None:
        self.show_page("fatigue")
        self.show()

    # --- tema -------------------------------------------------------------
    def toggle_theme(self) -> None:
        theme().toggle()
        self.sidebar.update_theme_button()
        # Los colores de banco los resuelve RigPalette segun el tema, asi que
        # no hay que recargar nada de la base: basta con repintar.
        actual = self.stack.currentWidget()
        if actual is not None:
            actual.update()

    def _on_catalogs_changed(self) -> None:
        self.rig_palette.load()
        self.refresh_current()

    # --- datos nuevos de otros equipos ------------------------------------
    def mark_seen(self) -> None:
        """Lo guardado hasta ahora ya esta en pantalla: el aviso se oculta."""
        try:
            self._seen_id = self.context.audit.last_id()
        except Exception:                     # pragma: no cover - red caida
            return
        self._seen_database = self.context.database.path
        self.banner.hide()

    def pending_changes(self) -> list:
        tablas = WATCHED_TABLES.get(self._current_key, frozenset())
        if not self._current_key or tablas == frozenset():
            return []
        if self.context.database.path != self._seen_database:
            # Otra base desde Ajustes: sus numeros de historial no tienen nada
            # que ver con los de la anterior.
            self.mark_seen()
            return []
        return self.context.audit.changes_since(
            self._seen_id, exclude_machine=current_author()[1], tables=tablas)

    def check_for_changes(self) -> None:
        try:
            cambios = self.pending_changes()
        except Exception:                     # pragma: no cover - red caida
            # Sin red no hay nada que avisar; el siguiente intento lo dira.
            return
        self.banner.show_changes(cambios)

    def refresh_current(self) -> None:
        actual = self.stack.currentWidget()
        self.mark_seen()
        if hasattr(actual, "refresh"):
            actual.refresh()


class _Pending(QWidget):
    """Sitio reservado de una pantalla que todavia no se ha redisenado."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        layout.addWidget(labels.heading(title),
                         0, Qt.AlignmentFlag.AlignCenter)
        nota = labels.secondary(
            "Esta pantalla se redisenia en la siguiente fase.")
        nota.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(nota)

    def refresh(self) -> None:
        """Nada que recargar todavia."""
