"""Capturar los ciclos de una prueba sin abrir el registro completo.

Anotar ciclos es lo que mas se repite en la bitacora de fatiga: se leen los
contadores de los bancos y se apuntan. Con el formulario completo eso era abrir
el registro, buscar la pieza entre nueve recuadros de cuatro campos, escribir y
guardar. Aqui solo estan los ciclos, y solo de las piezas que **estan
corriendo** en un banco.

Guarda con ``update_merging``, igual que los formularios: si otro equipo anoto
algo mientras tanto, se combina en vez de pisarse.
"""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QMessageBox, QVBoxLayout

from app.models import SUSPENDED_RESULT, FatigueTest, is_blank
from app.services.identity import current_author
from components import fields, labels
from dialogs.base import FormDialog, update_merging


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
    if (resultado.casefold() == SUSPENDED_RESULT.casefold()
            or (is_blank(sample.rig) and sample.cycles)):
        return "suspendida, fuera de banco"
    if resultado:
        return f"terminada  ·  {resultado}"
    if is_blank(sample.rig):
        return "sin banco"
    return None


def _has_data(sample) -> bool:
    return (not is_blank(sample.rig) or sample.cycles is not None
            or bool(sample.result) or bool(sample.failure_mode))


class CyclesDialog(FormDialog):
    """Solo los ciclos de las piezas de una prueba."""

    def __init__(self, repository, test: FatigueTest,
                 paused: dict | None = None, parent=None):
        self.repository = repository
        self.test = test
        self.paused = dict(paused or {})
        self.fields: dict[int, object] = {}
        self.notes: dict[int, object] = {}
        self.states: dict[int, str | None] = {}
        # Las piezas cuyos ciclos se guardaron, para quien abrio el cuadro.
        self.changed: list[int] = []

        super().__init__(
            f"Capturar ciclos  ·  {test.test_batch}",
            "Solo se capturan las piezas que están corriendo en un banco. "
            "Deja un campo vacío para conservar la lectura anterior.",
            parent)
        self.setMinimumWidth(660)

        cuerpo = self._grid_block()
        self.set_body(cuerpo)
        self.set_footer(save="Guardar ciclos")

        editables = self.editable_pieces()
        self.save_button.setEnabled(bool(editables))
        # Enter guarda: se escribe la lectura y se confirma sin ir al raton.
        self.save_button.setDefault(True)
        if editables:
            primero = self.fields[editables[0]]
            primero.setFocus()
            primero.selectAll()

        self.finish_setup()

    def _grid_block(self):
        from PySide6.QtWidgets import QWidget

        caja = QWidget()
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(10)

        rejilla = QGridLayout()
        rejilla.setHorizontalSpacing(16)
        rejilla.setVerticalSpacing(8)
        for columna_n, titulo in enumerate(
                ("Pieza", "Banco", "Anterior", "Ciclos nuevos", "")):
            rejilla.addWidget(labels.muted(titulo), 0, columna_n)

        fila = 1
        for numero, sample in enumerate(self.test.samples, start=1):
            # Las declaradas, y las de mas que traigan datos: las mismas que
            # enciende el formulario completo.
            if numero > self.test.qty_samples and not _has_data(sample):
                continue
            estado = piece_state(numero, sample, self.paused)
            self.states[numero] = estado

            rejilla.addWidget(labels.label(f"Pieza {numero}"), fila, 0)
            rejilla.addWidget(
                labels.secondary("" if is_blank(sample.rig) else sample.rig),
                fila, 1)

            anterior = labels.muted(
                "—" if sample.cycles is None else f"{sample.cycles:,}")
            anterior.setAlignment(Qt.AlignmentFlag.AlignRight
                                  | Qt.AlignmentFlag.AlignVCenter)
            rejilla.addWidget(anterior, fila, 2)

            campo = fields.number_edit()
            campo.setText("" if sample.cycles is None else str(sample.cycles))
            campo.setEnabled(estado is None)
            rejilla.addWidget(campo, fila, 3)
            self.fields[numero] = campo

            nota = labels.muted(estado or "")
            rejilla.addWidget(nota, fila, 4)
            self.notes[numero] = nota
            if estado is None:
                campo.textChanged.connect(
                    lambda _t, n=numero: self._check(n))
            fila += 1

        rejilla.setColumnStretch(4, 1)
        columna.addLayout(rejilla)

        if not self.editable_pieces():
            columna.addWidget(labels.secondary(
                "Ninguna pieza de esta prueba está corriendo en un banco: no "
                "hay ciclos que capturar aquí.", wrap=True))
        return caja

    # --- consulta -----------------------------------------------------------
    def editable_pieces(self) -> list[int]:
        return [n for n, estado in self.states.items() if estado is None]

    def value(self, number: int) -> int | None:
        texto = self.fields[number].text().strip()
        return int(texto) if texto.isdigit() else None

    # --- acciones -----------------------------------------------------------
    def _check(self, number: int) -> None:
        """Avisa de una lectura menor que la anterior, **sin impedirla**.

        Los contadores solo suben, asi que casi siempre es un digito de menos.
        No se bloquea: tambien puede ser la correccion de una lectura mal
        anotada antes.
        """
        anterior = self.test.samples[number - 1].cycles
        nuevo = self.value(number)
        nota = self.notes[number]
        baja = (nuevo is not None and anterior is not None
                and nuevo < anterior)
        labels.set_pill(nota, "menor que la lectura anterior" if baja else "",
                        "warning" if baja else "neutral")
        nota.setVisible(baja)

    def _save(self) -> None:
        nuevo = deepcopy(self.test)
        cambios = []
        for numero in self.editable_pieces():
            valor = self.value(numero)
            # Vacio conserva la lectura anterior: borrar los ciclos de una
            # pieza que corre no es algo que se haga desde aqui.
            if valor is None:
                continue
            if valor != nuevo.samples[numero - 1].cycles:
                nuevo.samples[numero - 1].cycles = valor
                cambios.append(numero)

        if cambios:
            try:
                if not update_merging(self, self.repository, nuevo,
                                      current_author(), base=self.test):
                    return
            except Exception as error:         # pragma: no cover - depende de red
                QMessageBox.critical(self, "Error al guardar", str(error))
                return

        self.changed = cambios
        self.accept()
