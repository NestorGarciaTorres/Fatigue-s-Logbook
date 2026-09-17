"""Campos de captura.

El aspecto sale entero de la hoja de estilos; lo que hay aqui es el
**comportamiento**, y casi todo es conocimiento ganado a golpes en el proyecto
anterior que seria absurdo volver a descubrir:

- Buscar escribiendo dentro de un desplegable, por prefijo **y** por contenido.
  Qt solo hace lo primero, asi que a 'MERCEDES-BENZ' se llegaba por la M y
  escribir 'BENZ' no llevaba a ningun sitio.
- La rueda no cambia un combo ni una fecha que **no tienen el foco**. Con la
  politica ``WheelFocus`` que Qt trae de fabrica, bajar con la rueda por un
  formulario dentro de un area desplazable cambiaba el Test Rig al pasar por
  encima.
- El combo **no se vuelve editable** para centrar su texto: ``isEditable()``
  cambia como se cargan los valores fuera de catalogo. Se dibuja el texto
  aparte, y por eso hay que elegir el ``QPalette.ColorGroup`` a mano o un campo
  deshabilitado se pinta como si estuviera activo.

El centrado del texto se conserva del proyecto anterior, donde fue una decision
deliberada del laboratorio: ``CENTER_FORM_TEXT`` lo gobierna desde un solo
sitio por si algun dia se quiere lo contrario.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRegularExpression, Qt, QTimer
from PySide6.QtGui import QIntValidator, QPalette, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QLineEdit,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
)

# Los campos de formulario van centrados, como en el proyecto anterior.
CENTER_FORM_TEXT = True

# Tope de filas visibles en un desplegable. Con Fusion hay que acompaniarlo de
# 'combobox-popup: 0' en la hoja, o Qt lo ignora y la lista mide todo el
# catalogo -- la de clientes llegaba a 516 px.
MAX_VISIBLE_ITEMS = 10

# Lo que se lleva tecleado se olvida despues de esto, como en el explorador de
# archivos: si no, teclear 'M' dos minutos despues seguiria buscando 'MM'.
SEARCH_RESET_MS = 1500

# Centinela de 'sin valor'. Hace falta como opcion de la lista --es la unica
# forma de volver a dejar el campo en blanco-- pero como texto seleccionado
# convertia el formulario en veintisiete campos anunciando lo que no tienen.
BLANK_LABEL = "(vacio)"

# 6 digitos + clave de 3 letras + 2 digitos. Ejemplo real: 242314STF09.
BATCH_REGEX = QRegularExpression(r"[0-9]{0,6}[A-Za-z]{0,3}[0-9]{0,2}")


class SearchableComboBox(QComboBox):
    """Combo cerrado con busqueda por teclado y guardia de rueda."""

    def __init__(self, centered: bool = CENTER_FORM_TEXT, parent=None):
        super().__init__(parent)
        self.centered = centered
        self.setMaxVisibleItems(MAX_VISIBLE_ITEMS)

        self._search = ""
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_RESET_MS)
        self._search_timer.timeout.connect(self.clear_search)
        self._watching_view = False

        # Sin WheelFocus a proposito: ver el docstring del modulo.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # --- rueda -----------------------------------------------------------
    def wheelEvent(self, event) -> None:
        if not self.hasFocus():
            # Ignorado, Qt se lo pasa al padre: dentro de un area desplazable
            # la rueda desplaza el formulario en vez de elegir opcion.
            event.ignore()
            return
        super().wheelEvent(event)

    # --- buscar escribiendo ----------------------------------------------
    def find_option(self, texto: str) -> int:
        """Primero por como empieza, luego por lo que contiene. -1 si nada."""
        objetivo = texto.casefold().strip()
        if not objetivo:
            return -1
        opciones = [(i, self.itemText(i).casefold())
                    for i in range(self.count())]
        for indice, etiqueta in opciones:
            if etiqueta.startswith(objetivo):
                return indice
        for indice, etiqueta in opciones:
            if objetivo in etiqueta:
                return indice
        return -1

    def search_text(self) -> str:
        return self._search

    def clear_search(self) -> None:
        self._search = ""
        self._search_timer.stop()

    def _search_key(self, event) -> bool:
        """Atiende una tecla de busqueda. True si ya se uso aqui."""
        if event.key() == Qt.Key.Key_Escape:
            self.clear_search()
            return False
        if event.key() == Qt.Key.Key_Backspace:
            if not self._search:
                return False
            self._search = self._search[:-1]
        else:
            texto = event.text()
            prohibidos = (Qt.KeyboardModifier.ControlModifier
                          | Qt.KeyboardModifier.AltModifier)
            if (not texto or not texto.isprintable()
                    or bool(event.modifiers() & prohibidos)):
                return False
            self._search += texto

        self._search_timer.start()
        indice = self.find_option(self._search)
        # Sin coincidencia la tecla se consume igual: saltar a otra opcion por
        # la ultima letra tecleada es peor que no moverse.
        if indice >= 0:
            self._select(indice)
        return True

    def _select(self, indice: int) -> None:
        vista = self.view()
        if vista is not None and vista.isVisible():
            vista.setCurrentIndex(self.model().index(indice,
                                                     self.modelColumn()))
        else:
            self.setCurrentIndex(indice)

    def keyPressEvent(self, event) -> None:
        if self._search_key(event):
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event) -> bool:
        # Con la lista desplegada las teclas van a la vista, no al combo, asi
        # que hay que atenderlas en los dos sitios.
        if (event.type() == QEvent.Type.KeyPress
                and obj is self.view()
                and self._search_key(event)):
            return True
        return super().eventFilter(obj, event)

    def showPopup(self) -> None:
        if self.centered:
            # Se hace aqui y no al construir porque los items llegan en varios
            # momentos: al crear el combo, y uno mas si el registro trae un
            # valor que ya no esta en el catalogo.
            for index in range(self.count()):
                self.setItemData(index, Qt.AlignmentFlag.AlignCenter,
                                 Qt.ItemDataRole.TextAlignmentRole)
        self.clear_search()
        if not self._watching_view and self.view() is not None:
            self.view().installEventFilter(self)
            self._watching_view = True
        super().showPopup()

    # --- pintado ---------------------------------------------------------
    def paintEvent(self, event) -> None:
        if not self.centered:
            super().paintEvent(event)
            return

        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)

        # El grupo de color va explicito: como el texto lo dibuja esta clase y
        # no el estilo, un combo deshabilitado se pintaba con el color de uno
        # activo y las piezas apagadas se leian igual de nitidas que las
        # capturables.
        group = (QPalette.ColorGroup.Normal if self.isEnabled()
                 else QPalette.ColorGroup.Disabled)
        painter.setPen(option.palette.color(group, self.foregroundRole()))
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)

        texto = "" if combo_value(self) == "" else option.currentText
        option.currentText = ""
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)

        rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option,
            QStyle.SubControl.SC_ComboBoxEditField, self,
        )
        painter.drawText(
            rect, Qt.AlignmentFlag.AlignCenter,
            painter.fontMetrics().elidedText(
                texto, Qt.TextElideMode.ElideRight, rect.width()),
        )


class DateEdit(QDateEdit):
    """Selector de fecha con la misma guardia de rueda que el combo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


# --------------------------------------------------------------------------
# Fabricas
# --------------------------------------------------------------------------

def line_edit(placeholder: str = "", centered: bool = CENTER_FORM_TEXT,
              read_only: bool = False) -> QLineEdit:
    campo = QLineEdit()
    if placeholder:
        campo.setPlaceholderText(placeholder)
    if centered:
        campo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    campo.setReadOnly(read_only)
    return campo


def number_edit(maximum: int = 2_000_000_000) -> QLineEdit:
    """Campo de enteros. Los ciclos y las revoluciones llegan como texto."""
    campo = QLineEdit()
    campo.setValidator(QIntValidator(0, maximum))
    campo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return campo


def batch_edit() -> QLineEdit:
    """Campo de Test Batch: formato guiado y mayusculas automaticas."""
    campo = line_edit("242314STF09")
    campo.setMaxLength(11)
    campo.setValidator(QRegularExpressionValidator(BATCH_REGEX))
    campo.textChanged.connect(lambda texto, w=campo: _force_upper(w, texto))
    return campo


def _force_upper(widget: QLineEdit, text: str) -> None:
    arriba = text.upper()
    if arriba == text:
        return
    # Se conserva el cursor: sin esto, corregir una letra en medio manda el
    # cursor al final en cada pulsacion.
    posicion = widget.cursorPosition()
    widget.blockSignals(True)
    widget.setText(arriba)
    widget.setCursorPosition(posicion)
    widget.blockSignals(False)


def date_edit(initial=None) -> DateEdit:
    from datetime import date as _date

    from PySide6.QtCore import QDate

    campo = DateEdit()
    campo.setDisplayFormat("dd/MM/yyyy")
    campo.setCalendarPopup(True)
    campo.setDate(QDate(initial or _date.today()))
    if CENTER_FORM_TEXT:
        interno = campo.findChild(QLineEdit)
        if interno is not None:
            interno.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return campo


def to_date(widget: QDateEdit):
    return widget.date().toPython()


def closed_combo(values: list[str]) -> SearchableComboBox:
    """Desplegable sin opcion en blanco, para lo que es obligatorio."""
    combo = SearchableComboBox()
    combo.addItems(values)
    # Mide por caracteres y no por su elemento mas largo: el de clientes pedia
    # 292 px por 'MERCEDES-BENZ', y el nombre completo se sigue viendo entero
    # al desplegar la lista.
    combo.setMinimumContentsLength(12)
    combo.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    return combo


def clearable_combo(values: list[str],
                    blank_label: str = BLANK_LABEL) -> SearchableComboBox:
    """Desplegable que se puede volver a dejar en blanco.

    En el banco no es un detalle: una pieza que se suspende sale del rig y
    vuelve despues, y quien captura tiene que poder borrar lo que ya anoto.
    """
    combo = closed_combo([])
    combo.addItem(blank_label, userData="")
    for valor in values:
        combo.addItem(valor, userData=valor)
    return combo


def combo_value(combo: QComboBox) -> str:
    """El valor de un combo, con el centinela de vacio ya traducido."""
    dato = combo.currentData()
    if dato is not None:
        return str(dato)
    return combo.currentText()


def set_combo_value(combo: QComboBox, value: str | None) -> None:
    """Selecciona un valor, agregandolo si no esta en el catalogo.

    Un registro viejo puede traer un banco o un cliente que ya no existe. Si no
    se agrega, abrir el formulario lo cambiaria por otro en silencio y guardar
    lo perderia.
    """
    texto = (value or "").strip()
    if not texto or texto == "--":
        indice = combo.findData("")
        combo.setCurrentIndex(indice if indice >= 0 else 0)
        return

    indice = combo.findData(texto)
    if indice < 0:
        indice = combo.findText(texto)
    if indice < 0:
        combo.addItem(texto, userData=texto)
        indice = combo.count() - 1
    combo.setCurrentIndex(indice)
