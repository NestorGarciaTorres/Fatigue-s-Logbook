"""Ajustes: catalogos, base de datos y apariencia.

Los catalogos se editan contra ``CatalogService`` del proyecto original, que ya
notifica a quien este escuchando: la pantalla visible se repinta sola al
guardar uno.

Dos cosas propias de esta interfaz:

- **El color de un rig se guarda en sus dos variantes.** La base lleva un color
  para el tema oscuro y otro para el claro, porque ningun color contrasta con
  los dos fondos a la vez. Se elige uno y el otro se deriva, en vez de pedir
  dos al usuario: nadie quiere elegir dos veces el color del mismo banco.
- **El tema y el tamano de letra viven aqui**, en ``ui_theme.json``, y no en la
  configuracion del proyecto original.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.models import TEST_TYPES, Customer, FailureMode, Requester, Rig
from app.services import backup
from app.services.catalogs import color_for_index
from app.services.identity import author_label
from components import buttons, fields, labels
from components.models import RIG_COLOR_ROLE
from components.table import RigChipDelegate
from pages.base import Page
from theme import qss
from theme.manager import theme
from theme.rig_palette import derive_light
from theme.tokens import DARK, FAMILIES, LIGHT

TYPE_LABELS = {clave: config.label for clave, config in TEST_TYPES.items()}

# Cuantos caracteres de una ruta se ensenian antes de acortarla por el centro.
PATH_CHARS = 62


def _table(headers: list[str]) -> QTableWidget:
    tabla = QTableWidget(0, len(headers))
    tabla.setHorizontalHeaderLabels(headers)
    tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tabla.verticalHeader().setVisible(False)
    tabla.setAlternatingRowColors(True)
    tabla.setShowGrid(False)
    tabla.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.Stretch)
    tabla.horizontalHeader().setHighlightSections(False)
    return tabla


def _item(texto: str, center: bool = True) -> QTableWidgetItem:
    item = QTableWidgetItem(texto)
    if center:
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return item


class RigsTab(QWidget):
    """Bancos y sus colores.

    Doble clic sobre la muestra abre el selector. Se guarda la variante oscura
    tal como se elige y la clara se **deriva**: mismo tono, mas oscuro, hasta
    alcanzar el contraste sobre fondo claro. Pedir dos colores por banco seria
    pedirle al usuario que resuelva un problema que la app sabe resolver.
    """

    def __init__(self, context, rig_palette, parent=None):
        super().__init__(parent)
        self.context = context
        self.rig_palette = rig_palette
        self._rigs: list[Rig] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addLayout(buttons.button_row(
            buttons.button("Agregar rig", buttons.PRIMARY,
                           on_click=self.add_rig),
            buttons.button("Activar / desactivar", on_click=self.toggle_active),
            buttons.button("Cambiar color", on_click=self.pick_color_selected),
        ))

        self.table = _table(["Banco", "Bitácora", "Color (tema activo)",
                             "Activo"])
        # La muestra de color la pinta el mismo delegado que dibuja el banco en
        # las bitacoras. No es solo por reusar: con una hoja de estilos
        # aplicada a la vista, Qt **ignora** el setBackground() de un item, asi
        # que las muestras salian en blanco sobre blanco. Ademas asi el color
        # se pide a la paleta al pintar y sigue al tema.
        self.table.setItemDelegateForColumn(2, RigChipDelegate(self.table))
        self.table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

        layout.addWidget(labels.muted(
            "El color identifica al banco en toda la app. Se guarda una "
            "variante para cada tema, porque ningún color se lee sobre fondo "
            "claro y sobre fondo oscuro a la vez.", wrap=True))

    def refresh(self) -> None:
        self._rigs = self.context.catalog_repository.rigs(active_only=False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._rigs))
        for fila, rig in enumerate(self._rigs):
            self.table.setItem(fila, 0, _item(rig.name))
            self.table.setItem(fila, 1, _item(
                TYPE_LABELS.get(rig.test_type, rig.test_type)))

            color = self.rig_palette.color(rig.name, rig.test_type) or rig.color
            muestra = _item(color, center=False)
            muestra.setData(RIG_COLOR_ROLE, color)
            par = self.rig_palette.pair(rig.name, rig.test_type)
            if par:
                muestra.setToolTip(
                    f"Tema oscuro: {par[0]}\nTema claro: {par[1]}\n\n"
                    f"Doble clic para cambiarlo")
            self.table.setItem(fila, 2, muestra)

            self.table.setItem(fila, 3, _item("Sí" if rig.active else "No"))

    def _on_double_click(self, fila: int, columna: int) -> None:
        if columna == 2:
            self.pick_color(fila)

    def pick_color_selected(self) -> None:
        fila = self.table.currentRow()
        if fila >= 0:
            self.pick_color(fila)

    def pick_color(self, fila: int) -> None:
        rig = self._rigs[fila]
        par = self.rig_palette.pair(rig.name, rig.test_type)
        actual = par[0] if par else rig.color

        elegido = QColorDialog.getColor(QColor(actual), self,
                                        f"Color para {rig.name}")
        if not elegido.isValid():
            return

        oscuro = elegido.name().upper()
        claro = derive_light(oscuro)
        try:
            self.rig_palette.set_color(rig.name, rig.test_type, oscuro, claro)
        except Exception as error:             # pragma: no cover - depende de red
            QMessageBox.warning(self, "No se pudo guardar el color",
                                str(error))
            return

        # El catalogo en memoria del proyecto original tambien guarda el color
        # oscuro: se recarga para que la tabla y los chips coincidan.
        self.context.catalogs.reload()
        self.refresh()

    def add_rig(self) -> None:
        nombre, ok = QInputDialog.getText(self, "Nuevo rig", "Nombre del rig:")
        if not ok or not nombre.strip():
            return

        etiquetas = list(TYPE_LABELS.values())
        etiqueta, ok = QInputDialog.getItem(
            self, "Nuevo rig", "Tipo de prueba:", etiquetas, 0, False)
        if not ok:
            return

        clave = next(k for k, v in TYPE_LABELS.items() if v == etiqueta)
        indice = len(self.context.catalog_repository.rigs(active_only=False))
        oscuro = color_for_index(indice)

        try:
            self.context.catalogs.save_rig(
                Rig(name=nombre.strip(), test_type=clave, color=oscuro))
            # Y su variante clara, para que el banco nuevo se vea en los dos
            # temas desde el primer momento.
            self.rig_palette.set_color(nombre.strip(), clave, oscuro,
                                       derive_light(oscuro))
        except Exception as error:
            QMessageBox.warning(self, "No se pudo agregar", str(error))
            return
        self.refresh()

    def toggle_active(self) -> None:
        fila = self.table.currentRow()
        if fila < 0:
            return
        rig = self._rigs[fila]
        rig.active = not rig.active
        self.context.catalogs.save_rig(rig)
        self.refresh()


class _NamesTab(QWidget):
    """Lo comun a clientes, modos de falla y solicitantes: una lista de nombres.

    Los tres se editaban con tres pestanias casi identicas en el proyecto
    anterior. Aqui la diferencia se declara y el resto se comparte.
    """

    CAPTION = ""
    ADD_TITLE = ""
    HINT = ""

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self._items: list = []

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addLayout(buttons.button_row(
            buttons.button(f"Agregar {self.CAPTION}", buttons.PRIMARY,
                           on_click=self.add_item),
            buttons.button("Activar / desactivar", on_click=self.toggle_active),
        ))

        self.table = _table([self.CAPTION.capitalize(), "Activo"])
        layout.addWidget(self.table, 1)
        if self.HINT:
            layout.addWidget(labels.muted(self.HINT, wrap=True))

    # --- para redefinir ----------------------------------------------------
    def load(self) -> list:
        raise NotImplementedError

    def save(self, item) -> None:
        raise NotImplementedError

    def make(self, name: str):
        raise NotImplementedError

    # --- comun -------------------------------------------------------------
    def refresh(self) -> None:
        self._items = self.load()
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._items))
        for fila, item in enumerate(self._items):
            nombre = getattr(item, "name", None) or getattr(item, "label", "")
            self.table.setItem(fila, 0, _item(nombre, center=False))
            activo = getattr(item, "active", True)
            self.table.setItem(fila, 1, _item("Sí" if activo else "No"))

    def add_item(self) -> None:
        nombre, ok = QInputDialog.getText(
            self, self.ADD_TITLE, f"Nombre del {self.CAPTION}:")
        if not ok or not nombre.strip():
            return
        try:
            self.save(self.make(nombre.strip()))
        except Exception as error:
            QMessageBox.warning(self, "No se pudo agregar", str(error))
            return
        self.refresh()

    def toggle_active(self) -> None:
        fila = self.table.currentRow()
        if fila < 0:
            return
        item = self._items[fila]
        if not hasattr(item, "active"):
            return
        item.active = not item.active
        self.save(item)
        self.refresh()


class CustomersTab(_NamesTab):
    CAPTION = "cliente"
    ADD_TITLE = "Nuevo cliente"

    def load(self):
        return self.context.catalog_repository.customers(active_only=False)

    def save(self, item):
        self.context.catalogs.save_customer(item)

    def make(self, name):
        return Customer(name=name)


class FailureModesTab(_NamesTab):
    CAPTION = "modo de falla"
    ADD_TITLE = "Nuevo modo de falla"
    HINT = ("Describen **cómo** falló la pieza, no si falló: eso ya lo dice el "
            "resultado. Por eso el modo solo se le exige a la pieza marcada "
            "como 'Falla'.")

    def load(self):
        return self.context.catalog_repository.failure_modes(active_only=False)

    def save(self, item):
        self.context.catalogs.save_failure_mode(item)

    def make(self, name):
        return FailureMode(label=name)


class RequestersTab(_NamesTab):
    CAPTION = "solicitante"
    ADD_TITLE = "Nuevo solicitante"
    HINT = ("El solicitante viaja de la Work Order al registro de la prueba y "
            "se queda ahí: es lo que se consulta años después.")

    def load(self):
        return self.context.catalog_repository.requesters(active_only=False)

    def save(self, item):
        self.context.catalogs.save_requester(item)

    def make(self, name):
        return Requester(name=name)


class CodesTab(QWidget):
    """Las claves de tres letras que validan el Test Batch."""

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self._codes: list = []

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addLayout(buttons.button_row(
            buttons.button("Agregar clave", buttons.PRIMARY,
                           on_click=self.add_code),
            buttons.button("Eliminar", buttons.DANGER,
                           on_click=self.remove_code),
        ))

        self.table = _table(["Clave", "Bitácora"])
        layout.addWidget(self.table, 1)
        layout.addWidget(labels.muted(
            "Un Test Batch son 6 dígitos + la clave de 3 letras + 2 dígitos, "
            "por ejemplo 242314STF09. La clave tiene que existir para el tipo "
            "de ensayo.", wrap=True))

    def refresh(self) -> None:
        self._codes = self.context.catalog_repository.all_codes()
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._codes))
        for fila, code in enumerate(self._codes):
            self.table.setItem(fila, 0, _item(code.code))
            self.table.setItem(fila, 1, _item(
                TYPE_LABELS.get(code.test_type, code.test_type)))

    def add_code(self) -> None:
        clave, ok = QInputDialog.getText(self, "Nueva clave",
                                         "Clave de 3 letras:")
        if not ok or len(clave.strip()) != 3:
            if ok:
                QMessageBox.warning(self, "Clave inválida",
                                    "La clave son exactamente 3 letras.")
            return
        etiquetas = list(TYPE_LABELS.values())
        etiqueta, ok = QInputDialog.getItem(self, "Nueva clave",
                                            "Tipo de prueba:", etiquetas, 0,
                                            False)
        if not ok:
            return
        tipo = next(k for k, v in TYPE_LABELS.items() if v == etiqueta)
        try:
            self.context.catalogs.add_code(clave.strip().upper(), tipo)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo agregar", str(error))
            return
        self.refresh()

    def remove_code(self) -> None:
        fila = self.table.currentRow()
        if fila < 0:
            return
        code = self._codes[fila]
        confirmar = QMessageBox.question(
            self, "Confirmación",
            f"¿Eliminar la clave {code.code} de "
            f"{TYPE_LABELS.get(code.test_type, code.test_type)}?")
        if confirmar != QMessageBox.StandardButton.Yes:
            return
        self.context.catalogs.remove_code(code.id)
        self.refresh()


class DatabaseTab(QWidget):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        grupo = QGroupBox("Base de datos")
        form = QFormLayout(grupo)

        self.path_label = labels.secondary("")
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Ruta actual", self.path_label)

        self.status_label = labels.secondary("")
        form.addRow("Estado", self.status_label)
        self.size_label = labels.secondary("")
        form.addRow("Tamaño", self.size_label)
        self.backup_label = labels.secondary("")
        form.addRow("Último respaldo", self.backup_label)
        form.addRow("Usuario", labels.secondary(author_label()))
        layout.addWidget(grupo)

        # Rotulos cortos y el detalle en el tooltip: los cuatro escritos
        # enteros dejaban esta pantalla a 4 px del ancho de un portatil.
        layout.addLayout(buttons.button_row(
            buttons.button("Cambiar base",
                           tooltip="Apuntar la app a otro archivo de base de "
                                   "datos",
                           on_click=self.change_database),
            buttons.button("Probar conexión",
                           on_click=lambda: self.test_connection(False)),
            buttons.button("Respaldar ahora", buttons.SUCCESS,
                           on_click=self.make_backup),
            buttons.button("Historial", buttons.GHOST,
                           tooltip="Historial de cambios de toda la base",
                           on_click=self.show_history),
        ))
        layout.addWidget(labels.muted(
            "Esta interfaz guarda su configuración aparte de la aplicación "
            "original: cambiar aquí la base no toca la suya.", wrap=True))
        layout.addStretch(1)

    def refresh(self) -> None:
        self._show_path(self.context.config.database)
        self.test_connection(quiet=True)
        self._describe_file()
        self._describe_backup()

    def _show_path(self, ruta) -> None:
        """La ruta acortada por el centro; entera en el tooltip.

        Por el centro y no por el final porque lo que identifica una base es el
        principio (el servidor o la unidad) y el final (el archivo).
        """
        self.path_label.setText(labels.elide(str(ruta), PATH_CHARS))
        self.path_label.setToolTip(str(ruta))

    def _describe_file(self) -> None:
        base = Path(self.context.config.database)
        if not base.is_file():
            self.size_label.setText("El archivo no existe todavía")
            return
        megas = base.stat().st_size / (1024 * 1024)
        self.size_label.setText(f"{megas:,.1f} MB")

    def _describe_backup(self) -> None:
        ultimo = backup.latest_backup(Path(self.context.config.backups))
        if ultimo is None:
            self.backup_label.setText("Todavía no hay respaldos")
            return
        cuando = datetime.fromtimestamp(ultimo.stat().st_mtime)
        dias = (datetime.now() - cuando).days
        antiguedad = ("hoy" if dias == 0 else
                      "ayer" if dias == 1 else f"hace {dias} días")
        self.backup_label.setText(
            f"{cuando:%d/%m/%Y %H:%M}  ({antiguedad})  ·  {ultimo.name}")

    def change_database(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Selecciona la base de datos",
            str(self.context.config.database.parent), "SQLite (*.db)")
        if not ruta:
            return
        try:
            self.context.reload_database(ruta)
        except Exception as error:
            QMessageBox.critical(self, "Error", str(error))
            return
        QMessageBox.information(
            self, "Listo",
            "La app quedó apuntando a la nueva base. Cambia de pantalla para "
            "recargar las bitácoras.")
        self.refresh()

    def test_connection(self, quiet: bool = False) -> None:
        try:
            tablas = self.context.database.table_names()
        except Exception as error:
            self.status_label.setText(f"Error: {error}")
            if not quiet:
                QMessageBox.critical(self, "Sin conexión", str(error))
            return
        self.status_label.setText(f"Conectada. {len(tablas)} tablas.")
        if not quiet:
            QMessageBox.information(
                self, "Conexión correcta",
                f"La base responde y tiene {len(tablas)} tablas.")

    def make_backup(self) -> None:
        try:
            destino = backup.manual_backup(
                Path(self.context.config.database),
                Path(self.context.config.backups))
        except Exception as error:
            QMessageBox.critical(self, "Error", str(error))
            return
        QMessageBox.information(self, "Respaldo creado", str(destino))

    def show_history(self) -> None:
        from dialogs.history import HistoryDialog

        HistoryDialog(self.context.audit, parent=self).exec()


class PaletteSwatch(QWidget):
    """Tira de muestras de una familia: fondo, superficie, accion y estados.

    Una lista de nombres no dice nada --'Acero' y 'Pizarra' suenan igual de
    grises-- asi que la eleccion se hace mirando los colores, no leyendo.
    """

    HEIGHT = 18

    def __init__(self, family, dark: bool, parent=None):
        super().__init__(parent)
        self.family = family
        self.dark = dark
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(150)
        paleta = family.palette(dark)
        self.setToolTip(
            f"{family.label}\nfondo {paleta.bg}  ·  "
            f"acción {paleta.accent}")

    def paintEvent(self, event) -> None:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter

        paleta = self.family.palette(self.dark)
        muestras = [paleta.bg, paleta.surface, paleta.accent, paleta.success,
                    paleta.warning, paleta.danger, paleta.maintenance]

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        ancho = self.width() / len(muestras)
        for indice, color in enumerate(muestras):
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(
                QRectF(indice * ancho + 1, 0, ancho - 2, self.HEIGHT), 3, 3)
        painter.end()


class AppearanceTab(QWidget):
    """Paleta, modo y tamano de letra. Se guardan por equipo, no en la base.

    La misma base se abre en un portatil de 1366 y en un monitor de 27
    pulgadas, asi que el tamano no puede ser un dato compartido.

    Cambiar de **paleta** hace una cosa mas que repintar: reescribe los colores
    claros de los bancos. No es capricho -- el acento de una familia puede caer
    encima de un banco calibrado para otra (medido: dE 8.7), y entonces ese
    chip se lee como un color de interfaz en vez de como un banco.
    """

    PREVIEW = "241166STF09  ·  MERCEDES-BENZ  ·  182,130 ciclos"

    def __init__(self, context, rig_palette, parent=None):
        super().__init__(parent)
        self.context = context
        self.rig_palette = rig_palette

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        grupo = QGroupBox("Apariencia")
        form = QFormLayout(grupo)

        self.family_combo = fields.SearchableComboBox(centered=False)
        for clave, familia in FAMILIES.items():
            self.family_combo.addItem(familia.label, clave)
        self.family_combo.setMinimumContentsLength(24)
        self.family_combo.setCurrentIndex(
            max(0, self.family_combo.findData(theme().family)))
        self.family_combo.currentIndexChanged.connect(self.apply_family)
        form.addRow("Paleta", self.family_combo)

        # Las cuatro a la vista, en el modo activo: se elige mirando.
        self.swatches = QVBoxLayout()
        self.swatches.setSpacing(4)
        self.swatch_box = QWidget()
        self.swatch_box.setLayout(self.swatches)
        self._build_swatches()
        form.addRow("", self.swatch_box)

        self.theme_combo = fields.SearchableComboBox(centered=False)
        self.theme_combo.addItem("Claro", LIGHT)
        self.theme_combo.addItem("Oscuro", DARK)
        self.theme_combo.setMaximumWidth(220)
        self.theme_combo.setCurrentIndex(
            max(0, self.theme_combo.findData(theme().name)))
        # La conexion va DESPUES de elegir el valor inicial: si no, construir
        # la pestania repinta la app y guarda la configuracion sin que nadie
        # haya tocado nada.
        self.theme_combo.currentIndexChanged.connect(self.apply_theme)
        form.addRow("Tema", self.theme_combo)

        self.font_size = fields.SearchableComboBox(centered=False)
        self.font_size.setMaximumWidth(220)
        for puntos in range(qss.MIN_FONT_PT, qss.MAX_FONT_PT + 1):
            etiqueta = f"{puntos} pt"
            if puntos == qss.BASE_FONT_PT:
                etiqueta += "   (el de siempre)"
            self.font_size.addItem(etiqueta, puntos)
        self.font_size.setCurrentIndex(
            max(0, self.font_size.findData(theme().font_size)))
        self.font_size.currentIndexChanged.connect(self.apply_font)
        form.addRow("Tamaño de letra", self.font_size)

        self.preview = labels.secondary(self.PREVIEW, wrap=True)
        form.addRow("Vista previa", self.preview)
        layout.addWidget(grupo)

        layout.addWidget(labels.muted(
            "Se aplica al momento y se recuerda para la próxima vez, solo en "
            "este equipo. El color de cada banco cambia con el tema y con la "
            "paleta: se guarda una variante para fondo claro y otra para fondo "
            "oscuro, porque ninguna sirve para los dos.", wrap=True))
        layout.addStretch(1)

    # --- muestras ----------------------------------------------------------
    def _build_swatches(self) -> None:
        while self.swatches.count():
            item = self.swatches.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        oscuro = theme().is_dark
        for clave, familia in FAMILIES.items():
            corto = familia.label.split(":")[0]
            fila = QHBoxLayout()
            fila.setSpacing(8)
            fila.addWidget(PaletteSwatch(familia, oscuro))
            # La activa va en pastilla para que se vea cual esta puesta sin
            # tener que mirar el desplegable de arriba.
            fila.addWidget(labels.pill(corto, "info") if clave == theme().family
                           else labels.muted(corto))
            fila.addStretch(1)
            contenedor = QWidget()
            contenedor.setLayout(fila)
            self.swatches.addWidget(contenedor)

    # --- acciones ----------------------------------------------------------
    def apply_family(self) -> None:
        clave = self.family_combo.currentData()
        if not clave or clave == theme().family:
            return
        theme().set_family(clave)
        # Los colores claros de los bancos son de la **familia**, no del modo:
        # se reescriben desde la tabla precalculada, que es instantaneo. Sin
        # esto, el chip de un banco se leeria como el acento de la paleta.
        escritos = self.rig_palette.apply_family(clave)
        self.context.catalogs.reload()
        self._build_swatches()
        if not escritos:
            QMessageBox.information(
                self, "Paleta cambiada",
                "La paleta se aplicó, pero no había colores de banco "
                "precalculados para ella. Los bancos usan un color derivado: "
                "se ven, pero no están tan separados entre sí.\n\n"
                "Para generarlos:\n"
                "    python tools/generate_light_palette.py --table")

    def apply_theme(self) -> None:
        nombre = self.theme_combo.currentData()
        if nombre:
            theme().set_theme(nombre)
            self._build_swatches()

    def apply_font(self) -> None:
        puntos = self.font_size.currentData()
        if puntos is not None:
            theme().set_font_size(puntos)

    def refresh(self) -> None:
        """Los combos ya reflejan el estado; nada que releer."""


class SettingsPage(Page):
    def __init__(self, context, rig_palette, parent=None):
        super().__init__("Ajustes",
                         "Catálogos, base de datos y apariencia", parent)
        self.context = context

        self.tabs = QTabWidget()
        self.rigs_tab = RigsTab(context, rig_palette)
        self.customers_tab = CustomersTab(context)
        self.codes_tab = CodesTab(context)
        self.failure_modes_tab = FailureModesTab(context)
        self.requesters_tab = RequestersTab(context)
        self.database_tab = DatabaseTab(context)
        self.appearance_tab = AppearanceTab(context, rig_palette)

        for widget, titulo in (
            (self.rigs_tab, "Rigs y colores"),
            (self.customers_tab, "Clientes"),
            (self.codes_tab, "Claves"),
            (self.failure_modes_tab, "Modos de falla"),
            (self.requesters_tab, "Solicitantes"),
            (self.database_tab, "Base de datos"),
            (self.appearance_tab, "Apariencia"),
        ):
            self.tabs.addTab(widget, titulo)
        self.content.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        for indice in range(self.tabs.count()):
            self.tabs.widget(indice).refresh()
