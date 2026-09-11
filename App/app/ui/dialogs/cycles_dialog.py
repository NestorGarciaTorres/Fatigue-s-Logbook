"""Capturar los ciclos de una prueba sin abrir el registro completo.

Anotar ciclos es lo que mas se repite en la bitacora de fatiga: se leen los
contadores de los bancos y se apuntan. Con el formulario completo eso era abrir
el registro, buscar la pieza entre nueve recuadros de cuatro campos, escribir y
guardar. Aqui solo estan los ciclos, y solo se capturan los de las piezas que
estan corriendo en un banco.
"""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from app.models import SUSPENDED_RESULT, FatigueTest, is_blank
from app.services.identity import current_author
from app.ui import theme
from app.ui.dialogs.form_guard import GuardedDialog, update_merging
from app.ui.widgets.common import subheading


def piece_state(number: int, sample, paused: dict) -> str | None:
    """Por que una pieza no se captura aqui, o None si esta corriendo.

    Se captura la que tiene banco y aun no tiene resultado. La terminada, la
    suspendida o la detenida por mantenimiento no avanzan: sus ciclos, si hay
    que corregirlos, se corrigen desde el registro completo.
    """
    registro = paused.get(number)
    if registro is not None:
        return f"detenida por mantenimiento de {registro.rig_name}"
    resultado = (sample.result or "").strip()
    if resultado.casefold() == SUSPENDED_RESULT.casefold() or (
        is_blank(sample.rig) and sample.cycles
    ):
        return "suspendida, fuera de banco"
    if resultado:
        return f"terminada  ·  {resultado}"
    if is_blank(sample.rig):
        return "sin banco"
    return None


def _has_data(sample) -> bool:
    return (not is_blank(sample.rig) or sample.cycles is not None
            or bool(sample.result) or bool(sample.failure_mode))


class CyclesDialog(GuardedDialog):
    """Solo los ciclos de las piezas de una prueba."""

    def __init__(self, repository, test: FatigueTest, paused: dict | None = None,
                 parent=None):
        super().__init__(parent)
        self.repository = repository
        self.test = test
        self.paused = dict(paused or {})
        self.fields: dict[int, QLineEdit] = {}
        self.notes: dict[int, QLabel] = {}
        self.states: dict[int, str | None] = {}
        # Las piezas cuyos ciclos se guardaron, para quien abrio el cuadro.
        self.changed: list[int] = []

        self.setWindowTitle(f"Capturar ciclos  -  {test.test_batch}")
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(subheading(f"Ciclos de {test.test_batch}"))

        explicacion = QLabel(
            "Solo se capturan las piezas que están corriendo en un banco. Deja "
            "un campo vacío para conservar la lectura anterior."
        )
        explicacion.setProperty("muted", "true")
        explicacion.setWordWrap(True)
        layout.addWidget(explicacion)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        for columna, titulo in enumerate(
            ("Pieza", "Banco", "Anterior", "Ciclos nuevos", "")
        ):
            encabezado = QLabel(titulo)
            encabezado.setProperty("muted", "true")
            grid.addWidget(encabezado, 0, columna)

        fila = 1
        for number, sample in enumerate(test.samples, start=1):
            # Las declaradas, y las de mas que traigan datos: las mismas que
            # enciende el formulario completo.
            if number > test.qty_samples and not _has_data(sample):
                continue
            estado = piece_state(number, sample, self.paused)
            self.states[number] = estado

            grid.addWidget(QLabel(f"Pieza {number}"), fila, 0)
            grid.addWidget(
                QLabel("" if is_blank(sample.rig) else sample.rig), fila, 1
            )
            anterior = QLabel(
                "—" if sample.cycles is None else f"{sample.cycles:,}"
            )
            anterior.setAlignment(Qt.AlignmentFlag.AlignRight
                                  | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(anterior, fila, 2)

            campo = QLineEdit()
            campo.setValidator(QIntValidator(0, 2_000_000_000, self))
            campo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            campo.setText("" if sample.cycles is None else str(sample.cycles))
            campo.setEnabled(estado is None)
            grid.addWidget(campo, fila, 3)
            self.fields[number] = campo

            nota = QLabel(estado or "")
            nota.setProperty("muted", "true")
            grid.addWidget(nota, fila, 4)
            self.notes[number] = nota
            if estado is None:
                campo.textChanged.connect(
                    lambda _texto, n=number: self._check(n)
                )
            fila += 1

        grid.setColumnStretch(4, 1)
        layout.addLayout(grid)

        if not self.editable_pieces():
            vacio = QLabel(
                "Ninguna pieza de esta prueba está corriendo en un banco: no hay "
                "ciclos que capturar aquí."
            )
            vacio.setWordWrap(True)
            vacio.setStyleSheet(f"color: {theme.TEXT_MUTED};")
            layout.addWidget(vacio)

        self.button_box = QDialogButtonBox()
        self.save_button = self.button_box.addButton(
            "Guardar ciclos", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.save_button.setProperty("accent", "success")
        # Enter guarda: se escribe la lectura y se confirma sin ir al raton.
        self.save_button.setDefault(True)
        self.button_box.addButton(
            "Cancelar", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.button_box.accepted.connect(self._save)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        editables = self.editable_pieces()
        self.save_button.setEnabled(bool(editables))
        if editables:
            primero = self.fields[editables[0]]
            primero.setFocus()
            primero.selectAll()

        self.mark_clean()

    # --- consulta ----------------------------------------------------------
    def editable_pieces(self) -> list[int]:
        return [n for n, estado in self.states.items() if estado is None]

    def value(self, number: int) -> int | None:
        texto = self.fields[number].text().strip()
        return int(texto) if texto.isdigit() else None

    # --- acciones ----------------------------------------------------------
    def _check(self, number: int) -> None:
        """Avisa de una lectura menor que la anterior, sin impedirla.

        Los contadores solo suben, asi que casi siempre es un digito de menos.
        No se bloquea: tambien puede ser la correccion de una lectura mal
        anotada antes.
        """
        anterior = self.test.samples[number - 1].cycles
        nuevo = self.value(number)
        nota = self.notes[number]
        if nuevo is not None and anterior is not None and nuevo < anterior:
            nota.setText("menor que la lectura anterior")
            nota.setStyleSheet(f"color: {theme.DANGER};")
        else:
            nota.setText("")
            nota.setStyleSheet("")

    def _save(self) -> None:
        nuevo = deepcopy(self.test)
        cambios = []
        for number in self.editable_pieces():
            valor = self.value(number)
            # Vacio conserva la lectura anterior: borrar los ciclos de una
            # pieza que corre no es algo que se haga desde aqui.
            if valor is None:
                continue
            if valor != nuevo.samples[number - 1].cycles:
                nuevo.samples[number - 1].cycles = valor
                cambios.append(number)

        if cambios:
            try:
                # Contra la prueba tal como se abrio: si otro equipo guardo algo
                # mientras tanto, se combina en vez de pisarse.
                if not update_merging(self, self.repository, nuevo,
                                      current_author(), base=self.test):
                    return
            except Exception as error:  # pragma: no cover - depende de la red
                QMessageBox.critical(self, "Error al guardar", str(error))
                return

        self.changed = cambios
        self.accept()
