"""El gestor de temas: quien sabe que paleta esta activa y como cambiarla.

Es lo unico que la interfaz consulta para pintar. Un widget **nunca** guarda un
color en una constante propia: pide la paleta cada vez que pinta
(``theme().palette.danger``). Esa es la regla que hace posible cambiar de tema
sin reiniciar, y la que el proyecto anterior no podia cumplir porque tres
modulos copiaban los colores a constantes de modulo en el momento de importar
--``DAYS_COLORS``, ``SUSPENDED_COLOR``, ``MAINTENANCE_COLOR``-- y despues nadie
las volvia a tocar.

Cambiar de tema hace tres cosas, y las tres hacen falta:

1. Reconstruye la hoja y se la da a la ``QApplication``.
2. Recorre los widgets vivos con ``unpolish`` + ``polish``. Qt **no** vuelve a
   aplicar la hoja de estilos por su cuenta a un widget ya dibujado: sin esto,
   media pantalla se queda con los colores anteriores hasta que algo la obligue
   a repintarse.
3. Emite ``themeChanged``, al que se conectan las vistas con pintado propio
   (tablas y delegados) para repintar su viewport.

La preferencia vive en ``ui_theme.json``, en la carpeta de esta app y **no** en
el ``settings.json`` del proyecto original. Va en un archivo aparte del de
``AppConfig`` a proposito: ``AppConfig.save()`` serializa con ``asdict()``, asi
que reescribiria el archivo entero y se llevaria por delante cualquier clave
que no sea suya.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from theme import qss
from theme.tokens import (
    DARK,
    DEFAULT_FAMILY,
    FAMILIES,
    LIGHT,
    Palette,
    palette_for,
)

log = logging.getLogger(__name__)

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "ui_theme.json"

DEFAULT_THEME = LIGHT


class ThemeManager(QObject):
    """Tema activo, tamano de letra, y el aviso de que han cambiado."""

    themeChanged = Signal()
    # Se emite ademas de themeChanged cuando lo que cambia es la familia:
    # hay quien tiene que recalcular datos, no solo repintar.
    familyChanged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._app = None
        self._name = DEFAULT_THEME
        self._family = DEFAULT_FAMILY
        self._font_size = qss.BASE_FONT_PT
        self._load()

    # --- estado ----------------------------------------------------------
    @property
    def palette(self) -> Palette:
        """La paleta activa: la familia elegida, en el modo elegido."""
        return palette_for(self._family, self._name)

    @property
    def family(self) -> str:
        return self._family

    @property
    def name(self) -> str:
        return self._name

    @property
    def font_size(self) -> int:
        return self._font_size

    @property
    def is_dark(self) -> bool:
        return self.palette.is_dark

    # --- ciclo de vida ---------------------------------------------------
    def attach(self, app) -> None:
        """Toma la ``QApplication`` y pinta por primera vez."""
        self._app = app
        app.setStyle("Fusion")
        self._apply(repolish=False)

    def set_theme(self, name: str) -> None:
        if name not in (LIGHT, DARK) or name == self._name:
            return
        self._name = name
        self._save()
        self._apply()

    def set_family(self, key: str) -> None:
        """Cambia de familia de paleta conservando el modo.

        Los colores de banco del tema claro dependen de la familia --el acento
        de una puede caer encima de un banco de otra-- asi que quien cambia de
        familia tiene que reescribirlos. Lo hace ``RigPalette.apply_family``,
        que escucha esta senial.
        """
        if key not in FAMILIES or key == self._family:
            return
        self._family = key
        self._save()
        self._apply()
        self.familyChanged.emit(key)

    def toggle(self) -> str:
        """Cambia al otro tema y devuelve el que queda activo."""
        self.set_theme(DARK if self._name == LIGHT else LIGHT)
        return self._name

    def set_font_size(self, points: int) -> None:
        points = qss.clamp_font(points)
        if points == self._font_size:
            return
        self._font_size = points
        self._save()
        self._apply()

    def stylesheet(self) -> str:
        return qss.build(self.palette, self._font_size)

    # --- pintado ---------------------------------------------------------
    def _apply(self, repolish: bool = True) -> None:
        if self._app is None:
            return
        self._app.setStyleSheet(self.stylesheet())
        if repolish:
            self.repolish()
        self.themeChanged.emit()

    def repolish(self) -> None:
        """Obliga a cada widget vivo a releer la hoja de estilos.

        Se recorren todos y no solo las ventanas de primer nivel: un widget
        con una propiedad puesta (``variant``, ``pill``, ``invalid``) solo
        cambia de aspecto si su estilo lo despule y lo vuelve a pulir. Es el
        mismo par ``unpolish``/``polish`` que el proyecto original ya necesita
        para marcar en rojo un campo invalido.
        """
        if self._app is None:
            return
        for widget in self._app.allWidgets():
            estilo = widget.style()
            if estilo is None:               # pragma: no cover - widget muriendo
                continue
            estilo.unpolish(widget)
            estilo.polish(widget)
            # QWidget.update() y no widget.update(): una vista de items
            # (QListView, QTableView) redefine 'update' con otra firma --pide
            # un indice-- asi que llamarla sin argumentos revienta. La lista
            # desplegable de cualquier QComboBox es una de esas, y estan en
            # allWidgets() aunque no se vean.
            QWidget.update(widget)

    # --- persistencia ----------------------------------------------------
    def _load(self) -> None:
        if not SETTINGS_FILE.exists():
            return
        try:
            datos = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            # Un archivo corrupto no debe impedir abrir la app: se arranca con
            # el tema por omision y se reescribe al primer cambio.
            log.warning("No se pudo leer %s: %s", SETTINGS_FILE, error)
            return
        nombre = datos.get("theme")
        if nombre in (LIGHT, DARK):
            self._name = nombre
        familia = datos.get("family")
        if familia in FAMILIES:
            self._family = familia
        self._font_size = qss.clamp_font(datos.get("font_size",
                                                   self._font_size))

    def _save(self) -> None:
        try:
            SETTINGS_FILE.write_text(
                json.dumps({"theme": self._name, "family": self._family,
                            "font_size": self._font_size}, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as error:               # pragma: no cover - disco lleno
            log.warning("No se pudo guardar el tema: %s", error)


_instance: ThemeManager | None = None


def theme() -> ThemeManager:
    """El gestor. Uno solo por proceso."""
    global _instance
    if _instance is None:
        _instance = ThemeManager()
    return _instance


def palette() -> Palette:
    """Atajo para lo que mas se pide: la paleta activa."""
    return theme().palette
