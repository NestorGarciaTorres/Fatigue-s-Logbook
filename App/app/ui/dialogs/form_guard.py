"""Lo que evita que un formulario pierda datos sin que nadie lo note.

Dos cosas distintas con el mismo fin:

1. **Cambios sin guardar.** Cancelar, pulsar Esc o cerrar la ventana tiraba lo
   capturado sin preguntar. :class:`GuardedDialog` compara los campos contra
   como estaban al terminar de cargar y solo pregunta si de verdad cambio
   algo: preguntar siempre ensenia a pulsar 'Descartar' sin leer.
2. **Dos equipos editando el mismo registro.** Guardar escribia el registro
   entero, asi que lo que otro equipo hubiera guardado mientras el formulario
   estaba abierto se perdia. :func:`update_merging` guarda contra el registro
   tal como se abrio: lo que cambio solo uno de los dos se combina solo, y
   solo se pregunta cuando los dos cambiaron el mismo campo.

Las preguntas son funciones de este modulo y no metodos: las pruebas las
sustituyen para contestar sin abrir un cuadro modal que las dejaria colgadas.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from app.db.repositories import (
    KEEP_MINE,
    KEEP_THEIRS,
    EditConflict,
    RecordDeleted,
)
from app.services import validation
from app.ui.dialogs.history_dialog import field_label, value_label
from app.ui.widgets.common import combo_value

# Cuantos problemas se enumeran en el aviso antes de resumir. Con mas, el aviso
# empuja el formulario fuera de la vista; los campos siguen marcados igual.
ISSUES_LISTED = 6


# --- cambios sin guardar -------------------------------------------------
def form_snapshot(root: QWidget) -> tuple:
    """Lo que dice cada campo del formulario, en orden de creacion.

    Se leen valores y no textos: un combo con opcion en blanco ensenia
    '(sin banco)' pero vale ''. Los QLineEdit internos de combos y fechas se
    saltan, porque su valor ya lo da el control al que pertenecen. Y solo
    cuenta lo de esta ventana: el cuadro de 'Finalizar prueba' es hijo del
    formulario y su fecha no es un cambio del registro.
    """
    valores = []
    for widget in root.findChildren(QWidget):
        if widget.window() is not root:
            continue
        if isinstance(widget, QComboBox):
            valores.append(combo_value(widget))
        elif isinstance(widget, QDateEdit):
            valores.append(widget.date().toString("yyyy-MM-dd"))
        elif isinstance(widget, QLineEdit) and not isinstance(
            widget.parentWidget(), (QComboBox, QAbstractSpinBox)
        ):
            valores.append(widget.text())
    return tuple(valores)


def confirm_discard(parent: QWidget) -> bool:
    """Pregunta antes de tirar lo capturado. True si se descarta."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Cambios sin guardar")
    box.setText("Este formulario tiene cambios sin guardar.")
    box.setInformativeText("Si lo cierras ahora, lo que capturaste se pierde.")
    descartar = box.addButton("Descartar cambios",
                              QMessageBox.ButtonRole.DestructiveRole)
    seguir = box.addButton("Seguir editando",
                           QMessageBox.ButtonRole.RejectRole)
    # Lo seguro es lo que pasa con Enter o Esc: seguir editando.
    box.setDefaultButton(seguir)
    box.setEscapeButton(seguir)
    box.exec()
    return box.clickedButton() is descartar


def gather_issues(checks) -> list[tuple[QWidget, str]]:
    """Corre cada regla y junta sus mensajes, cada uno con su campo.

    ``checks`` es una lista de ``(campo, funcion)``. Las reglas de
    ``validation`` lanzan al primer error; aqui se corren todas para ensenar
    de una vez todo lo que impide guardar.
    """
    issues: list[tuple[QWidget, str]] = []
    for widget, check in checks:
        try:
            check()
        except validation.ValidationError as error:
            issues.append((widget, str(error)))
    return issues


def missing_issues(general, samples, widget_for) -> list[tuple[QWidget, str]]:
    """Lo que falta para finalizar, cada dato sobre el campo donde se captura.

    ``widget_for(numero_de_pieza_o_None, etiqueta)`` devuelve ese campo. Si
    alguno no tuviera campo se marca el aviso igual, sobre el primero que si
    lo tenga: un faltante que no se ensenia es peor que uno mal ubicado.
    """
    issues: list[tuple[QWidget, str]] = []
    sin_campo: list[str] = []
    for number, caption in validation.missing_for_finish(general, samples):
        lugar = f"Pieza {number}  ·  {caption}" if number else caption
        widget = widget_for(number, caption)
        if widget is None:
            sin_campo.append(lugar)
            continue
        issues.append((widget, f"{lugar}: falta capturarlo"))
    if sin_campo and issues:
        issues.append((issues[0][0], "También falta: " + ", ".join(sin_campo)))
    return issues


def _set_invalid(widget: QWidget, invalid: bool) -> None:
    """La marca roja es una propiedad que lee la hoja de estilos (theme.py)."""
    widget.setProperty("invalid", "true" if invalid else "false")
    # Qt no vuelve a aplicar la hoja de estilos al cambiar una propiedad.
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class GuardedDialog(QDialog):
    """Formulario que no tira lo capturado ni esconde lo que impide guardar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clean: tuple | None = None
        self._banner: QLabel | None = None
        self._issues: list[tuple[QWidget, str]] = []
        self._issue_title = ""
        self._watched: set[int] = set()
        self._tooltips: dict[int, str] = {}

    # --- lo que impide guardar -------------------------------------------
    def issue_banner(self) -> QLabel:
        """El aviso de lo que impide guardar.

        Cada formulario lo pone bajo su titulo, fuera del area que se
        desplaza: asi se lee aunque el campo marcado este abajo.
        """
        self._banner = QLabel()
        self._banner.setProperty("issues", "true")
        self._banner.setWordWrap(True)
        self._banner.hide()
        return self._banner

    def show_issues(self, title: str, issues: list[tuple[QWidget, str]]) -> None:
        """Marca en rojo cada campo con problema y los enumera arriba.

        Antes era un cuadro modal con el primer error: se cerraba, se
        corregia ese campo y al volver a guardar aparecia el siguiente. Ahora
        se ven todos a la vez, cada uno sobre su campo, y la vista baja sola
        hasta el primero.
        """
        self.clear_issues()
        self._issue_title = title
        self._issues = list(issues)
        for widget, message in self._issues:
            self._tooltips.setdefault(id(widget), widget.toolTip())
            widget.setToolTip(message)
            _set_invalid(widget, True)
            self._watch(widget)
        self._render_issues()

        if self._issues:
            primero = self._issues[0][0]
            area = getattr(self, "scroll", None)
            if area is not None and area.isAncestorOf(primero):
                area.ensureWidgetVisible(primero)
            primero.setFocus()

    def clear_issues(self) -> None:
        for widget, _ in self._issues:
            self._unmark(widget)
        self._issues = []
        self._render_issues()

    def invalid_widgets(self) -> list[QWidget]:
        """Los campos marcados ahora mismo, en el orden en que se avisan."""
        return [widget for widget, _ in self._issues]

    def issue_text(self) -> str:
        return self._banner.text() if self._banner is not None else ""

    def _unmark(self, widget: QWidget) -> None:
        _set_invalid(widget, False)
        widget.setToolTip(self._tooltips.pop(id(widget), widget.toolTip()))

    def _watch(self, widget: QWidget) -> None:
        """Al tocar un campo marcado se le quita la marca, sin esperar a guardar."""
        if id(widget) in self._watched:
            return
        self._watched.add(id(widget))

        def editado(*_args, campo=widget):
            self._field_edited(campo)

        if isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(editado)
        elif isinstance(widget, QDateEdit):
            widget.dateChanged.connect(editado)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(editado)

    def _field_edited(self, widget: QWidget) -> None:
        if not any(marcado is widget for marcado, _ in self._issues):
            return
        self._unmark(widget)
        self._issues = [(w, m) for w, m in self._issues if w is not widget]
        self._render_issues()

    def _render_issues(self) -> None:
        if self._banner is None:
            return
        if not self._issues:
            self._banner.hide()
            return
        cuantos = len(self._issues)
        cabecera = (f"{self._issue_title}: "
                    + ("hay 1 campo por corregir" if cuantos == 1
                       else f"hay {cuantos} campos por corregir")
                    + ", marcados en rojo.")
        lineas = [f"•  {mensaje}" for _, mensaje in self._issues[:ISSUES_LISTED]]
        if cuantos > ISSUES_LISTED:
            lineas.append(f"…  y {cuantos - ISSUES_LISTED} más")
        self._banner.setText("\n".join([cabecera, *lineas]))
        self._banner.show()

    # --- cambios sin guardar ---------------------------------------------
    def mark_clean(self) -> None:
        """Toma como punto de partida lo que hay en pantalla ahora.

        Se llama al terminar de cargar: lo que trae el registro o la Work
        Order no es un cambio del usuario, y cancelar un formulario recien
        abierto no tiene nada que preguntar.
        """
        self._clean = form_snapshot(self)

    def has_unsaved_changes(self) -> bool:
        if self._clean is None or getattr(self, "read_only", False):
            return False
        return form_snapshot(self) != self._clean

    def reject(self) -> None:
        # Cancelar, Esc y la X de la ventana pasan todos por aqui.
        if self.has_unsaved_changes() and not confirm_discard(self):
            return
        super().reject()


# --- dos equipos, un registro --------------------------------------------
def describe_conflict(conflict: EditConflict, audit) -> list[str]:
    """Una linea por campo en disputa: lo tuyo, lo guardado y quien lo guardo.

    Quien lo guardo sale del historial: la ultima entrada de ese campo en ese
    registro es la que dejo el valor que hay ahora.
    """
    historial = audit.for_record(conflict.table, conflict.record_id)
    lineas = []
    for column, (_, mine, theirs) in conflict.fields.items():
        # Dos renglones por campo: todo en uno no cabia en el cuadro y Qt lo
        # partia a media frase, justo dentro del parentesis de quien lo guardo.
        guardado = f"guardado: {value_label(column, theirs)}"
        ultimo = next((e for e in historial if e.field == column), None)
        if ultimo is not None:
            guardado += (f", por {ultimo.changed_by} el "
                         f"{ultimo.changed_at:%d/%m/%Y %H:%M}")
        lineas.append(f"{field_label(column)}\n"
                      f"    tuyo: {value_label(column, mine)}   ·   {guardado}")
    return lineas


def ask_conflict(parent: QWidget, conflict: EditConflict, audit) -> str | None:
    """Que valor queda en los campos que cambiaron los dos.

    Devuelve ``KEEP_MINE``, ``KEEP_THEIRS`` o None para volver al formulario
    sin guardar nada.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Otro equipo cambió este registro")
    registro = conflict.test_batch or "este registro"
    box.setText(
        f"Mientras tenías abierto {registro}, alguien más guardó otros "
        f"valores en los mismos campos que tú cambiaste."
    )
    box.setInformativeText(
        "\n\n".join(describe_conflict(conflict, audit))
        + "\n\nEl resto de tus cambios se guarda igual; solo falta decidir "
          "qué valor queda en estos campos."
    )
    mios = box.addButton("Guardar los míos", QMessageBox.ButtonRole.AcceptRole)
    suyos = box.addButton("Dejar los guardados",
                          QMessageBox.ButtonRole.ActionRole)
    volver = box.addButton("Volver al formulario",
                           QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(volver)
    box.setEscapeButton(volver)
    box.exec()

    elegido = box.clickedButton()
    if elegido is mios:
        return KEEP_MINE
    if elegido is suyos:
        return KEEP_THEIRS
    return None


def warn_deleted(parent: QWidget, error: RecordDeleted) -> None:
    QMessageBox.warning(
        parent, "El registro ya no existe",
        f"Otro equipo eliminó {error.test_batch or 'este registro'} mientras "
        f"lo tenías abierto. Tus cambios no se guardaron.",
    )


def update_merging(parent: QWidget, repository, record, author, base,
                   **extra) -> bool:
    """Guarda ``record`` combinandolo con lo que otro equipo guardo desde ``base``.

    Devuelve False si no se guardo nada: el usuario eligio volver al
    formulario, o el registro ya no existe. Cualquier otro error sube a quien
    llama, que ya sabe ensenarlo. ``extra`` pasa tal cual al ``update`` del
    repositorio (Fatiga recibe ahi el dia en que se movio cada pieza).
    """
    try:
        repository.update(record, author, base=base, **extra)
        return True
    except RecordDeleted as error:
        warn_deleted(parent, error)
        return False
    except EditConflict as conflict:
        eleccion = ask_conflict(parent, conflict, repository.audit)
        if eleccion is None:
            return False

    # Se combina otra vez desde el mismo punto de partida, no desde lo que se
    # leyo al detectar el conflicto: asi, si alguien mas guardo mientras la
    # pregunta estaba abierta, su cambio en otros campos tampoco se pisa.
    repository.update(record, author, base=base, on_conflict=eleccion, **extra)
    return True
