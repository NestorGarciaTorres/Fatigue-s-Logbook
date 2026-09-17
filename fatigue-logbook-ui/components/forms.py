"""Lo que hace que un formulario largo quepa en una pantalla chica.

Tres piezas, y las tres existen por la misma razon medida: Fatiga pedia 967 px
de alto y Rotary 850, y en un portatil de 768 el boton de guardar quedaba
**debajo del borde de la pantalla**, sin forma de llegar a el.

- :func:`scroll_body` desplaza el cuerpo, no la ventana: el titulo y los
  botones se quedan fijos.
- :func:`visible_rows_height` calcula el alto de las primeras filas de piezas.
  Las nueve siguen en el formulario; lo que cambia es con cuantas nace la
  ventana.
- :func:`fit_dialog_to_screen` decide el alto a mano, porque
  ``QScrollArea.sizeHint()`` esta topado por Qt y un dialogo que le deja elegir
  nace con barra aunque sobre pantalla.

Y :class:`SampleBox`, el recuadro de una pieza. Su estado --normal, apagada, de
mas-- va por **propiedad** y lo pinta la hoja de estilos; el proyecto anterior
lo hacia con tres ``setStyleSheet`` cuyos colores quedaban congelados.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.models import SAMPLE_SLOTS
from components import fields, labels

# Alto minimo del area desplazable, y margen que se le deja a la pantalla.
SCROLL_MIN_HEIGHT = 220
SCREEN_MARGIN = 60

# Con cuantas filas de piezas nace el formulario. Lo normal en un test batch
# son seis piezas; con las nueve, la ventana nace del alto de la pantalla.
VISIBLE_SAMPLE_ROWS = 2

# Una pieza capturada fuera del numero declarado no se oculta: se ensenia con
# este aviso, porque perderla de vista seria peor que la incoherencia.
EXTRA_HINT = ("Esta pieza está capturada por encima del número declarado.\n"
              "Sube 'No. de piezas' o borra sus datos.")
INACTIVE_HINT = ("La prueba declara menos piezas que esta.\n"
                 "Sube 'No. de piezas' para capturarla.")


# --------------------------------------------------------------------------
# Rejilla de datos generales
# --------------------------------------------------------------------------

def add_field(grid, row: int, column: int, caption: str, widget) -> QLabel:
    """Coloca una pareja etiqueta/campo en la columna logica ``column``.

    Cada columna logica ocupa dos de la rejilla: la etiqueta a la derecha y el
    campo a su lado. Asi los datos generales se reparten en varias columnas en
    vez de apilarse en una lista larga, donde un campo de dos caracteres se
    estiraba a lo ancho de toda la ventana.
    """
    etiqueta = labels.muted(caption)
    grid.addWidget(etiqueta, row, column * 2,
                   alignment=Qt.AlignmentFlag.AlignRight
                   | Qt.AlignmentFlag.AlignVCenter)
    grid.addWidget(widget, row, column * 2 + 1)
    return etiqueta


def balance_field_columns(grid, columns: int) -> None:
    """Reparte el ancho sobrante entre las columnas de campos, no de etiquetas."""
    for columna in range(columns):
        grid.setColumnStretch(columna * 2, 0)
        grid.setColumnStretch(columna * 2 + 1, 1)


def quantity_combo() -> QComboBox:
    combo = fields.SearchableComboBox()
    combo.addItems([str(i) for i in range(1, SAMPLE_SLOTS + 1)])
    return combo


# --------------------------------------------------------------------------
# Cuerpo desplazable
# --------------------------------------------------------------------------

def scroll_body(*widgets: QWidget) -> tuple[QScrollArea, QWidget]:
    """Apila los bloques de un formulario dentro de un area desplazable."""
    cuerpo = QWidget()
    layout = QVBoxLayout(cuerpo)
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
    # contenido, asi que nunca se recorta.
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setMinimumHeight(SCROLL_MIN_HEIGHT)
    area.setWidget(cuerpo)
    return area, cuerpo


def _activate_layouts(root: QWidget) -> None:
    """Obliga a calcular la geometria sin tener que mostrar la ventana.

    Antes de ``show()`` cada hijo tiene la geometria por omision (640x480) y
    medir sobre ella no dice nada. Activando los layouts de arriba abajo, Qt
    coloca todo y las posiciones ya son las definitivas.
    """
    if root.layout() is not None:
        root.layout().activate()
    for hijo in root.findChildren(QWidget):
        if hijo.layout() is not None:
            hijo.layout().activate()


def visible_rows_height(body: QWidget, boxes: list, grid, rows: int,
                        per_row: int = 3) -> int:
    """Lo que mide el cuerpo ensenando solo las primeras ``rows`` filas.

    Se **mide** donde acaba la ultima fila que se quiere ver, en vez de restar
    filas estimadas del total. La estimacion usaba ``sizeHint()`` de una caja
    --236 px-- cuando la fila ya colocada mide 215, asi que restaba de menos y
    la tercera fila asomaba 72 px por abajo: seis tarjetas y media, que se lee
    como un corte accidental en vez de como 'aqui hay mas, desplaza'.

    Se suma el espaciado de la rejilla para que el corte caiga en el hueco
    entre filas y no pegado al borde de la ultima tarjeta.
    """
    total = body.sizeHint().height()
    if not boxes:
        return total
    filas = -(-len(boxes) // per_row)
    if filas <= rows:
        return total

    _activate_layouts(body)
    ultima = boxes[min(rows * per_row, len(boxes)) - 1]
    fondo = ultima.mapTo(body, ultima.rect().bottomLeft()).y()
    if fondo > 0:
        return fondo + max(grid.verticalSpacing(), 0)

    # Respaldo por si la geometria no llego a calcularse: la estimacion de
    # antes, que se queda larga pero nunca corta de mas.
    alto_fila = max(caja.sizeHint().height() for caja in boxes)
    sobran = filas - rows
    return max(1, total - sobran * (alto_fila + grid.verticalSpacing()))


def fit_dialog_to_screen(dialog, area: QScrollArea, body: QWidget,
                         available_height: int | None = None,
                         preferred_body: int | None = None) -> None:
    """Da al formulario el alto que pide, sin pasar del de la pantalla.

    Se calcula a mano porque ``QScrollArea.sizeHint()`` esta topado por Qt.
    ``available_height`` existe para las pruebas, que simulan la pantalla de un
    portatil en un monitor grande.
    """
    dialog.ensurePolished()
    body.ensurePolished()

    # El contenido no se recorta en horizontal: el area mide al menos lo que
    # el, mas la barra vertical que puede aparecer.
    barra = area.verticalScrollBar().sizeHint().width()
    area.setMinimumWidth(body.minimumSizeHint().width() + barra)

    # Un formulario corto no se queda con el suelo fijo: la Work Order tiene
    # 189 px de datos, y con un minimo de 220 nacia con 31 px de hueco entre
    # los datos y los botones.
    area.setMinimumHeight(min(SCROLL_MIN_HEIGHT,
                              max(1, body.sizeHint().height() // 2)))

    if available_height is None:
        padre = dialog.parentWidget()
        pantalla = (padre.screen() if padre is not None else None) \
            or QGuiApplication.primaryScreen()
        if pantalla is None:                  # pragma: no cover - sin pantalla
            return
        available_height = pantalla.availableGeometry().height()

    # Todo lo que no es el area: titulo, botones, margenes y espaciado. Se
    # resta el alto que el **layout** le reserva al area --que ya cuenta su
    # minimo-- y no ``area.sizeHint()``: cuando el minimo era mayor que el
    # contenido, el cromo salia inflado justo en esa diferencia.
    layout = dialog.layout()
    reservado = layout.itemAt(layout.indexOf(area)).sizeHint().height()
    cromo = dialog.sizeHint().height() - reservado
    deseado = (body.sizeHint().height() if preferred_body is None
               else preferred_body)
    quiere = cromo + deseado + 2 * area.frameWidth()
    alto = max(dialog.minimumSizeHint().height(),
               min(quiere, available_height - SCREEN_MARGIN))
    ancho = max(dialog.sizeHint().width(), dialog.minimumSizeHint().width(),
                dialog.minimumWidth())
    dialog.resize(ancho, alto)


# --------------------------------------------------------------------------
# Recuadro de una pieza
# --------------------------------------------------------------------------

class SampleBox(QGroupBox):
    """Las capturas de una pieza, agrupadas y rotuladas con su numero.

    Son cuatro campos en Fatiga (banco, resultado, ciclos y modo de falla) y
    tres en Rotary (revoluciones, estatus y modo): la caja no sabe cuales, solo
    los coloca y los apaga en bloque.

    Las piezas que sobran del numero declarado **se apagan, no se ocultan**:
    las nueve siguen a la vista, que es como se pidio, pero no se puede
    capturar en una pieza que la prueba no tiene.
    """

    def __init__(self, number: int, rows: list[tuple[str, QWidget]],
                 parent=None):
        super().__init__(f"Pieza {number}", parent)
        self.number = number
        self._fields = [widget for _, widget in rows]

        form = QFormLayout(self)
        self._form = form
        form.setContentsMargins(12, 8, 12, 10)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter)

        for caption, widget in rows:
            form.addRow(labels.muted(caption), widget)

        self._labels = [form.labelForField(w) for _, w in rows]
        # Filas de apoyo (add_row): se apagan con la pieza pero no son datos.
        self._aux: list[QWidget] = []
        self._active = True
        self._extra = False

    # --- estado ------------------------------------------------------------
    def has_data(self) -> bool:
        """Si el usuario capturo algo en esta pieza.

        Se lee el **valor**, no el texto: la opcion en blanco de un combo tiene
        etiqueta visible --``(vacio)``-- y contarla como texto haria que toda
        pieza pareciera capturada.
        """
        return any(field_value(campo) for campo in self._fields)

    def values(self) -> list[str]:
        return [field_value(campo) for campo in self._fields]

    def set_active(self, active: bool) -> None:
        self._active = active
        for widget in self._fields:
            widget.setEnabled(active)
        for etiqueta in self._labels:
            if etiqueta is not None:
                etiqueta.setEnabled(active)
        for widget in self._aux:
            widget.setEnabled(active)
        self._restyle()

    def is_active(self) -> bool:
        return self._active

    def add_row(self, caption: str, widget: QWidget) -> None:
        """Una fila de apoyo que **no** es un dato de la pieza.

        No cuenta para ``has_data()``: la fecha de 'Movida el' siempre tiene
        valor, y contarla haria que toda pieza detenida pareciera capturada.
        """
        etiqueta = labels.muted(caption)
        self._form.addRow(etiqueta, widget)
        self._aux += [etiqueta, widget]
        etiqueta.setEnabled(self._active)
        widget.setEnabled(self._active)

    def set_row_visible(self, widget: QWidget, visible: bool) -> None:
        self._form.setRowVisible(widget, visible)

    def is_row_visible(self, widget: QWidget) -> bool:
        return self._form.isRowVisible(widget)

    def mark_extra(self, extra: bool) -> None:
        """Resalta la pieza cuando queda fuera del numero declarado."""
        self._extra = extra
        self._restyle()

    def _restyle(self) -> None:
        """El estado va por propiedad; el color lo pone la hoja de estilos.

        En el proyecto anterior esto eran tres ``setStyleSheet`` con los
        colores escritos dentro, congelados al construir la caja.
        """
        if self._extra:
            estado, aviso, cola = "extra", EXTRA_HINT, "  (de más)"
        elif not self._active:
            estado, aviso, cola = "dimmed", INACTIVE_HINT, ""
        else:
            estado, aviso, cola = "", "", ""

        if self.property("slot") != estado:
            self.setProperty("slot", estado)
            self.style().unpolish(self)
            self.style().polish(self)
        self.setToolTip(aviso)
        self.setTitle(f"Pieza {self.number}{cola}")


def field_value(widget) -> str:
    """El valor de un campo, sea del tipo que sea.

    Un combo devuelve su dato --no su texto-- para que el centinela de vacio no
    cuente como captura.
    """
    from PySide6.QtWidgets import QDateEdit, QLineEdit

    if isinstance(widget, QComboBox):
        return fields.combo_value(widget)
    if isinstance(widget, QDateEdit):
        return widget.date().toString("yyyy-MM-dd")
    if isinstance(widget, QLineEdit):
        return widget.text().strip()
    return ""
