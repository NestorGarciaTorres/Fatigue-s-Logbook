"""Estructura comun de los formularios de captura.

Hereda de ``GuardedDialog`` del proyecto original, y eso no es reutilizar por
economia: ahi vive lo que evita perder datos, y reescribirlo seria volver a
descubrir por que existe.

- **Cambios sin guardar.** Cancelar, Esc o la X comparan los campos contra como
  estaban al terminar de cargar, y solo preguntan si de verdad cambio algo.
  Preguntar siempre ensenia a pulsar 'Descartar' sin leer.
- **Dos equipos editando el mismo registro.** ``update_merging`` guarda contra
  el registro tal como se abrio: lo que cambio solo uno se combina, y solo se
  pregunta cuando los dos cambiaron el mismo campo. Antes ganaba el ultimo en
  guardar.
- **Validar no abre cuadros.** Se arma una lista de ``(campo, regla)``, se
  marcan todos los campos con problema a la vez y se enumeran arriba.

Lo que esta clase pone encima es la **forma**: titulo fijo, aviso bajo el
titulo, cuerpo desplazable y pie de botones fijo. Un formulario nuevo debe
heredar de aqui y exponer ``save_button``, que es lo que miden las pruebas.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

# La logica de guardado se importa entera del proyecto original.
from app.ui.dialogs.form_guard import (  # noqa: F401  (reexportadas a proposito)
    GuardedDialog,
    ask_conflict,
    confirm_discard,
    gather_issues,
    missing_issues,
    update_merging,
    warn_deleted,
)
from components import buttons, labels
from components.forms import fit_dialog_to_screen, scroll_body


class FormDialog(GuardedDialog):
    """Titulo, aviso, cuerpo desplazable y pie de botones."""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 16, 20, 16)
        self.root.setSpacing(12)

        self.root.addWidget(labels.heading(title))
        if subtitle:
            self.root.addWidget(labels.secondary(subtitle, wrap=True))

        # El aviso de lo que impide guardar va **fuera** del area que se
        # desplaza: asi se lee aunque el campo marcado este abajo del todo.
        self.root.addWidget(self.issue_banner())

        self.scroll: object | None = None
        self.body: QWidget | None = None
        self.footer = QHBoxLayout()
        self.footer.setSpacing(8)
        self.save_button = None

    # --- montaje ------------------------------------------------------------
    def set_body(self, *blocks: QWidget) -> QWidget:
        """Pone los bloques del formulario en el area desplazable."""
        self.scroll, self.body = scroll_body(*blocks)
        self.root.addWidget(self.scroll, 1)
        return self.body

    def set_footer(self, *widgets, save: str = "Guardar",
                   cancel: str = "Cancelar") -> None:
        """La fila de botones, que **no** se desplaza.

        El boton de guardar es el ultimo y va relleno: es la accion principal y
        tiene que distinguirse de las otras cinco.
        """
        for widget in widgets:
            if widget is None:
                self.footer.addStretch(1)
            else:
                self.footer.addWidget(widget)
        self.footer.addStretch(1)

        self.cancel_button = buttons.button(cancel, buttons.GHOST,
                                            on_click=self.reject)
        self.footer.addWidget(self.cancel_button)

        self.save_button = buttons.button(save, buttons.PRIMARY,
                                          on_click=self._save)
        self.footer.addWidget(self.save_button)
        self.root.addLayout(self.footer)

    def finish_setup(self, preferred_body: int | None = None,
                     available_height: int | None = None) -> None:
        """Ajusta el tamano y toma la foto de los campos.

        Va al final y en este orden: el alto se mide con lo que se va a ver, y
        ``mark_clean`` tiene que tomar los datos ya cargados -- lo que trae el
        registro no es un cambio del usuario, y cancelar un formulario recien
        abierto no tiene nada que preguntar.

        ``available_height`` existe para las pruebas, que simulan la pantalla
        de un portatil desde un monitor grande.
        """
        if self.scroll is not None and self.body is not None:
            fit_dialog_to_screen(self, self.scroll, self.body,
                                 available_height=available_height,
                                 preferred_body=preferred_body)
        self.mark_clean()

    # --- para redefinir -----------------------------------------------------
    def _save(self) -> None:                   # pragma: no cover - abstracto
        raise NotImplementedError
