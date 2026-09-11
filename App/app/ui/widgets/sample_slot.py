"""Recuadro de una pieza dentro del formulario.

Antes las nueve piezas eran filas sueltas en una rejilla: `Pieza 4`, `Ciclos` y
`Modo de falla` quedaban separadas por el mismo espacio que separaba una pieza
de la siguiente, y nada indicaba donde terminaba una y empezaba otra.

Ademas, las ranuras por encima del numero de piezas declarado se "atenuaban"
poniendo ``color:`` sobre los campos. Un campo vacio no tiene texto que
colorear, asi que lo unico que cambiaba de color era el rotulo `Pieza N`: con
una pieza declarada se seguian viendo veintisiete campos identicos.

Ahora las nueve siguen siempre a la vista, pero las que sobran del numero
declarado se apagan. Las que sobran *y ademas traen datos* -- hay registros
antiguos asi -- se quedan encendidas y en ambar, o no habria forma de
corregirlas.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QWidget

from app.ui import theme
from app.ui.widgets.common import field_value

# Una pieza capturada fuera del numero declarado no se oculta: se muestra con
# este aviso, porque perderla de vista seria peor que la incoherencia.
EXTRA_HINT = (
    "Esta pieza está capturada por encima del número declarado.\n"
    "Sube 'No. de piezas' o borra sus datos."
)

# Las piezas que sobran del numero declarado se apagan en vez de ocultarse: las
# nueve siguen a la vista, que es como se pidio, pero no se puede capturar en
# una pieza que la prueba no tiene.
INACTIVE_HINT = (
    "La prueba declara menos piezas que esta.\n"
    "Sube 'No. de piezas' para capturarla."
)


class SampleBox(QGroupBox):
    """Las capturas de una pieza, agrupadas y rotuladas con su numero.

    Son cuatro en Fatiga (banco, resultado, ciclos y modo de falla) y tres en
    Rotary (revoluciones, estatus y modo de falla): la caja no sabe cuales,
    solo las coloca y las apaga en bloque.
    """

    def __init__(self, number: int, rows: list[tuple[str, QWidget]], parent=None):
        super().__init__(f"Pieza {number}", parent)
        self.number = number
        self._fields = [widget for _, widget in rows]

        form = QFormLayout(self)
        self._form = form
        form.setContentsMargins(12, 6, 12, 10)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter)

        for caption, widget in rows:
            label = QLabel(caption)
            label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-weight: normal;")
            form.addRow(label, widget)

        self._labels = [
            form.labelForField(widget) for _, widget in rows
        ]
        # Filas de apoyo (add_row): se apagan con la pieza pero no son datos.
        self._aux: list[QWidget] = []
        self._active = True
        self._extra = False

        self._normal_style = ""
        self._extra_style = (
            f"QGroupBox {{ border: 1px solid {theme.WARNING}; }}"
            f"QGroupBox::title {{ color: {theme.WARNING}; }}"
        )
        self._inactive_style = (
            f"QGroupBox {{ border: 1px dashed {theme.BORDER}; }}"
            f"QGroupBox::title {{ color: {theme.TEXT_MUTED}; }}"
        )

    # --- estado ----------------------------------------------------------
    def has_data(self) -> bool:
        """Si el usuario capturo algo en esta pieza.

        Se lee el valor, no el texto: la opcion en blanco de un combo tiene
        etiqueta visible -- ``(vacio)`` -- y contarla como texto haria que toda
        pieza pareciera capturada.
        """
        return any(field_value(field) for field in self._fields)

    def values(self) -> list[str]:
        return [field_value(field) for field in self._fields]

    def set_active(self, active: bool) -> None:
        """Habilita o apaga la pieza segun quepa en el numero declarado."""
        self._active = active
        for widget in self._fields:
            widget.setEnabled(active)
        for label in self._labels:
            if label is not None:
                label.setEnabled(active)
        for widget in self._aux:
            widget.setEnabled(active)
        self._restyle()

    def is_active(self) -> bool:
        return self._active

    def add_row(self, caption: str, widget: QWidget) -> None:
        """Una fila de apoyo que no es un dato de la pieza.

        No cuenta para has_data(): la fecha de 'Movida el' siempre tiene
        valor, y contarla haria que toda pieza detenida pareciera capturada.
        """
        label = QLabel(caption)
        label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-weight: normal;")
        self._form.addRow(label, widget)
        self._aux += [label, widget]
        label.setEnabled(self._active)
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
        if self._extra:
            style, hint, suffix = self._extra_style, EXTRA_HINT, "  (de mas)"
        elif not self._active:
            style, hint, suffix = self._inactive_style, INACTIVE_HINT, ""
        else:
            style, hint, suffix = self._normal_style, "", ""

        self.setStyleSheet(style)
        self.setToolTip(hint)
        self.setTitle(f"Pieza {self.number}{suffix}")
