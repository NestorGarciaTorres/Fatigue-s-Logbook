"""Piezas de interfaz compartidas."""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QVBoxLayout,
)

from app.models import SAMPLE_SLOTS
from app.services.validation import TEST_BATCH_LENGTH
from app.ui import theme

# 6 digitos + 3 letras + 2 digitos, validado mientras se escribe. Sustituye al
# manejador de <KeyRelease> que recortaba el texto a mano despues de teclear.
BATCH_REGEX = QRegularExpression(r"[0-9]{0,6}[A-Za-z]{0,3}[0-9]{0,2}")


class CenteredComboBox(QComboBox):
    """Combo cerrado que dibuja su texto centrado.

    Qt pinta el valor de un combo no editable con ``CE_ComboBoxLabel``, que
    alinea a la izquierda sin opcion de cambiarlo: ni la hoja de estilos ni el
    modelo llegan a esa alineacion. La alternativa habitual --volverlo editable
    con un QLineEdit de solo lectura centrado-- haria que ``isEditable()``
    respondiera True y cambiaria como se cargan los valores fuera de catalogo,
    asi que aqui solo se cambia el dibujado.
    """

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
        painter.setPen(self.palette().color(self.foregroundRole()))

        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)

        # El marco y la flecha los pinta el estilo; el texto se dibuja aparte
        # para poder centrarlo.
        text = option.currentText
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


def editable_combo(values: list[str]) -> QComboBox:
    """Combo que ademas acepta teclear un valor fuera del catalogo."""
    combo = CenteredComboBox()
    combo.setEditable(True)
    combo.addItems(values)
    combo.setCurrentIndex(-1)
    return combo


def set_combo_value(combo: QComboBox, value: str | None) -> None:
    """Selecciona un valor, agregandolo si no estaba en la lista."""
    if not value:
        combo.setCurrentIndex(-1)
        return

    index = combo.findText(value)
    if index >= 0:
        combo.setCurrentIndex(index)
    elif combo.isEditable():
        combo.setCurrentText(value)
    else:
        combo.addItem(value)
        combo.setCurrentIndex(combo.count() - 1)


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
