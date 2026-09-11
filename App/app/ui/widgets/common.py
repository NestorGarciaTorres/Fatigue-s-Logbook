"""Piezas de interfaz compartidas."""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QGuiApplication, QPalette, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QScrollArea,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from app.models import SAMPLE_SLOTS
from app.services.validation import TEST_BATCH_LENGTH
from app.ui import theme

# 6 digitos + 3 letras + 2 digitos, validado mientras se escribe. Sustituye al
# manejador de <KeyRelease> que recortaba el texto a mano despues de teclear.
BATCH_REGEX = QRegularExpression(r"[0-9]{0,6}[A-Za-z]{0,3}[0-9]{0,2}")

# Texto de la opcion que vacia un combo cerrado. Se ve, a proposito: una fila
# de verdad en blanco es indistinguible del hueco entre opciones.
BLANK_LABEL = "(vacío)"

# Filas que ensenia una lista desplegable antes de poner barra. Con Fusion la
# lista se abria centrada sobre el campo e ignoraba este tope: la de clientes
# media 516 px y crecia con cada cliente nuevo. La hoja de estilos
# (combobox-popup: 0) es la que hace que Qt lo respete.
MAX_VISIBLE_ITEMS = 10

# Lo que se deja libre al ajustar un formulario a la pantalla, el mismo margen
# que usa MainWindow._fit_window para la ventana principal.
SCREEN_MARGIN = 60

# Alto por debajo del cual el cuerpo desplazable de un formulario no encoge: con
# menos no se llega a leer ni un recuadro de pieza entero.
SCROLL_MIN_HEIGHT = 220


class CenteredComboBox(QComboBox):
    """Combo cerrado que dibuja su texto centrado.

    Qt pinta el valor de un combo no editable con ``CE_ComboBoxLabel``, que
    alinea a la izquierda sin opcion de cambiarlo: ni la hoja de estilos ni el
    modelo llegan a esa alineacion. La alternativa habitual --volverlo editable
    con un QLineEdit de solo lectura centrado-- haria que ``isEditable()``
    respondiera True y cambiaria como se cargan los valores fuera de catalogo,
    asi que aqui solo se cambia el dibujado.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(MAX_VISIBLE_ITEMS)
        # Sin WheelFocus: la rueda sobre un combo cambiaba su valor aunque el
        # foco estuviera en otro campo. En un formulario que se desplaza con la
        # rueda, bajar por el cambiaba Test Rig o Resultado sin que nadie los
        # tocara.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:
        """Solo cambia de valor con la rueda si el combo tiene el foco.

        Sin foco se ignora el evento, y Qt lo pasa al padre: dentro de un area
        desplazable, la rueda desplaza el formulario en vez de elegir opcion.
        """
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)

    def showPopup(self) -> None:
        """Centra tambien las opciones de la lista.

        Se hace aqui y no al construir el combo porque los items llegan en
        varios momentos: al crearlo, y luego uno mas si el registro trae un
        valor que ya no esta en el catalogo.
        """
        for index in range(self.count()):
            self.setItemData(index, Qt.AlignmentFlag.AlignCenter,
                             Qt.ItemDataRole.TextAlignmentRole)
        super().showPopup()

    def paintEvent(self, event) -> None:
        painter = QStylePainter(self)

        option = QStyleOptionComboBox()
        self.initStyleOption(option)

        # El grupo de color va explicito. Como el texto lo dibuja esta clase y
        # no el estilo, un combo deshabilitado se pintaba con el color de uno
        # activo: las piezas apagadas se leian igual de nitidas que las
        # capturables, y lo unico que cambiaba era el borde del recuadro.
        group = (QPalette.ColorGroup.Normal if self.isEnabled()
                 else QPalette.ColorGroup.Disabled)
        painter.setPen(option.palette.color(group, self.foregroundRole()))
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)

        # El marco y la flecha los pinta el estilo; el texto se dibuja aparte
        # para poder centrarlo.
        #
        # El centinela de 'sin valor' se dibuja vacio. Hace falta como opcion
        # de la lista --es la unica forma de volver a dejar el campo en
        # blanco-- pero como texto seleccionado convertia el formulario en 27
        # campos anunciando lo que no tienen: nueve '(sin banco)', nueve '(sin
        # resultado)' y nueve '(sin modo)'. Un campo vacio ya se lee vacio.
        text = "" if combo_value(self) == "" else option.currentText
        option.currentText = ""
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)

        rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option,
            QStyle.SubControl.SC_ComboBoxEditField, self,
        )
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         painter.fontMetrics().elidedText(
                             text, Qt.TextElideMode.ElideRight, rect.width()))


def center_text(widget):
    """Centra el texto de un campo, sea del tipo que sea.

    QLineEdit y QDateEdit se centran con setAlignment; el QDateEdit lo hace
    sobre su propio QLineEdit interno.
    """
    if hasattr(widget, "lineEdit") and widget.lineEdit() is not None:
        widget.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
    elif hasattr(widget, "setAlignment"):
        widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget


def centered_line_edit(placeholder: str = "") -> QLineEdit:
    widget = QLineEdit()
    if placeholder:
        widget.setPlaceholderText(placeholder)
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget


def batch_edit() -> QLineEdit:
    widget = QLineEdit()
    widget.setMaxLength(TEST_BATCH_LENGTH)
    widget.setValidator(QRegularExpressionValidator(BATCH_REGEX))
    widget.setPlaceholderText("242314STF09")
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    # El batch siempre se guarda en mayusculas.
    widget.textChanged.connect(
        lambda text, w=widget: _force_upper(w, text)
    )
    return widget


def _force_upper(widget: QLineEdit, text: str) -> None:
    upper = text.upper()
    if upper != text:
        position = widget.cursorPosition()
        widget.blockSignals(True)
        widget.setText(upper)
        widget.setCursorPosition(position)
        widget.blockSignals(False)


def add_field(grid, row: int, column: int, caption: str, widget) -> QLabel:
    """Coloca una pareja etiqueta/campo en la columna logica ``column``.

    Cada columna logica ocupa dos de la rejilla: la etiqueta alineada a la
    derecha y el campo a su lado. Asi los datos generales se reparten en varias
    columnas en vez de apilarse en una sola lista larga, donde un campo de
    dos caracteres se estiraba a lo ancho de toda la ventana.
    """
    label = QLabel(caption)
    grid.addWidget(
        label, row, column * 2,
        alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    )
    grid.addWidget(widget, row, column * 2 + 1)
    return label


def balance_field_columns(grid, columns: int) -> None:
    """Reparte el ancho sobrante entre las columnas de campos, no de etiquetas."""
    for column in range(columns):
        grid.setColumnStretch(column * 2, 0)
        grid.setColumnStretch(column * 2 + 1, 1)


def quantity_combo() -> QComboBox:
    combo = CenteredComboBox()
    combo.addItems([str(i) for i in range(1, SAMPLE_SLOTS + 1)])
    return combo


def closed_combo(values: list[str]) -> QComboBox:
    """Lista cerrada: se elige de las opciones, no se teclea.

    Los valores heredados que ya no estan en el catalogo no se pierden:
    :func:`set_combo_value` los agrega a la lista al cargar el registro.
    """
    combo = CenteredComboBox()
    combo.addItems(values)
    combo.setCurrentIndex(-1)
    return combo


def clearable_combo(values: list[str], blank_label: str = BLANK_LABEL) -> QComboBox:
    """Lista cerrada que ademas se puede volver a dejar en blanco.

    Un ``QComboBox`` no editable no tiene forma de volver a "sin seleccion"
    una vez que se elige algo: ``setCurrentIndex(-1)`` es cosa del codigo, no
    del usuario. Y hace falta -- una pieza que se suspende sale de su banco, y
    quien captura tiene que poder borrar el Test Rig que ya habia puesto.

    La opcion en blanco es un elemento mas de la lista, el primero, con cadena
    vacia como dato. :func:`combo_value` lee el dato, no el texto, para que la
    etiqueta que se ve no acabe guardada como si fuera un valor.
    """
    combo = CenteredComboBox()
    combo.addItem(blank_label, "")
    for value in values:
        combo.addItem(value, value)
    combo.setCurrentIndex(0)
    return combo


def editable_combo(values: list[str]) -> QComboBox:
    """Combo que ademas acepta teclear un valor fuera del catalogo."""
    combo = CenteredComboBox()
    combo.setEditable(True)
    combo.addItems(values)
    combo.setCurrentIndex(-1)
    return combo


def combo_value(combo: QComboBox) -> str:
    """Lo que vale el combo, distinguiendo la opcion en blanco de un valor.

    Los elementos de :func:`clearable_combo` llevan su valor en el dato; los de
    los combos de siempre no llevan dato ninguno y valen por su texto. Los
    valores heredados que :func:`set_combo_value` agrega al vuelo tampoco
    llevan dato, de ahi el respaldo al texto.
    """
    if combo.currentIndex() < 0:
        return combo.currentText().strip()

    data = combo.currentData()
    if data is None:
        return combo.currentText().strip()
    return str(data).strip()


def field_value(widget) -> str:
    """El valor de un campo del formulario, sea combo o caja de texto."""
    if isinstance(widget, QComboBox):
        return combo_value(widget)
    if hasattr(widget, "text"):
        return widget.text().strip()
    return ""


def set_combo_value(combo: QComboBox, value: str | None) -> None:
    """Selecciona un valor, agregandolo si no estaba en la lista."""
    if not value:
        # Si el combo tiene opcion en blanco se elige esa, no el indice -1:
        # con -1 el combo se dibuja vacio pero sin nada seleccionado, y al
        # desplegarlo no hay ninguna fila marcada.
        blank = combo.findData("")
        combo.setCurrentIndex(blank if blank >= 0 else -1)
        return

    index = combo.findText(value)
    if index >= 0:
        combo.setCurrentIndex(index)
    elif combo.isEditable():
        combo.setCurrentText(value)
    else:
        combo.addItem(value, value)
        combo.setCurrentIndex(combo.count() - 1)


def scroll_body(*widgets: QWidget) -> tuple[QScrollArea, QWidget]:
    """Apila los bloques de un formulario dentro de un area desplazable.

    Lo que queda fuera --el titulo y la fila de botones-- no se desplaza: el
    formulario de fatiga pedia 967 px de alto, un portatil deja unos 700, y el
    boton de guardar quedaba debajo del borde de la pantalla sin forma de
    llegar a el.
    """
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    for widget in widgets:
        layout.addWidget(widget)
    # Si la ventana se agranda, los bloques se quedan arriba y el hueco abajo.
    layout.addStretch(1)

    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    # En horizontal no se desplaza: el ancho minimo del area cubre el del
    # contenido (lo fija fit_dialog_to_screen), asi que nunca se recorta.
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setMinimumHeight(SCROLL_MIN_HEIGHT)
    area.setWidget(body)
    return area, body


def fit_dialog_to_screen(dialog, area: QScrollArea, body: QWidget,
                         available_height: int | None = None) -> None:
    """Da al formulario el alto que pide, sin pasar del de la pantalla.

    Se calcula a mano porque ``QScrollArea.sizeHint()`` esta topado por Qt:
    dejando que el dialogo tomara su tamano, nacia con barra aunque la
    pantalla tuviera sitio de sobra. ``available_height`` existe para las
    pruebas, que simulan la pantalla de un portatil en un monitor grande.
    """
    dialog.ensurePolished()
    body.ensurePolished()

    # El contenido no se recorta en horizontal: el area mide al menos lo que
    # el, mas la barra vertical que puede aparecer.
    scrollbar = area.verticalScrollBar().sizeHint().width()
    area.setMinimumWidth(body.minimumSizeHint().width() + scrollbar)

    # Un formulario corto no se queda con el suelo fijo: la Work Order tiene
    # 189 px de datos, y con un minimo de 220 nacia con 31 px de hueco entre
    # los datos y los botones. Puede encoger hasta la mitad de lo suyo, asi
    # que tampoco pierde la barra en una pantalla muy baja.
    area.setMinimumHeight(min(SCROLL_MIN_HEIGHT,
                              max(1, body.sizeHint().height() // 2)))

    if available_height is None:
        parent = dialog.parentWidget()
        screen = (parent.screen() if parent is not None else None) \
            or QGuiApplication.primaryScreen()
        if screen is None:                    # pragma: no cover - sin pantalla
            return
        available_height = screen.availableGeometry().height()

    # Todo lo que no es el area: titulo, botones, margenes y espaciado. Se
    # resta el alto que el layout le reserva al area --que ya cuenta su
    # minimo--, no area.sizeHint(): cuando el minimo era mayor que el
    # contenido, el cromo salia inflado justo en esa diferencia.
    layout = dialog.layout()
    reservado = layout.itemAt(layout.indexOf(area)).sizeHint().height()
    chrome = dialog.sizeHint().height() - reservado
    wanted = chrome + body.sizeHint().height() + 2 * area.frameWidth()
    height = max(dialog.minimumSizeHint().height(),
                 min(wanted, available_height - SCREEN_MARGIN))
    width = max(dialog.sizeHint().width(), dialog.minimumSizeHint().width(),
                dialog.minimumWidth())
    dialog.resize(width, height)


class StatCard(QFrame):
    """Tarjeta de metrica para el dashboard y las cabeceras de bitacora."""

    def __init__(self, title: str, value: str = "0", accent: str = theme.INFO,
                 parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ background-color: {theme.SURFACE};"
            f" border: 1px solid {theme.BORDER}; border-radius: 8px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 10pt; border: none;"
        )

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(
            f"color: {accent}; font-size: 20pt; font-weight: bold; border: none;"
        )

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value) -> None:
        if isinstance(value, int):
            self.value_label.setText(f"{value:,}")
        else:
            self.value_label.setText(str(value))


def heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("heading", "true")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def subheading(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("subheading", "true")
    return label
