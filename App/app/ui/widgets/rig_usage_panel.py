"""Piezas terminadas por banco, en barras horizontales.

No es una QChart y es a proposito. Con dieciseis bancos y un reparto muy
desigual --T-7243 lleva 1,594 piezas de Torsion y el banco de fatiga que mas
tiene lleva 6-- una grafica de barras deja las pequenias en menos de un pixel,
que es justo lo que se le critico a la de tipos de ensayo. Aqui cada banco
tiene su renglon, su color y su numero escrito, asi que un 6 se lee igual de
bien que un 1,594.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.models import TEST_TYPES
from app.ui import theme

ROW_HEIGHT = 17
BAR_HEIGHT = 10
NAME_WIDTH = 150


def _label(text: str, color: str, size: int = 10, bold: bool = False) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {color}; font-size: {size}pt; border: none;"
        + (" font-weight: bold;" if bold else "")
    )
    return label


class RigUsagePanel(QFrame):
    """Un renglon por banco: nombre, barra de su color y piezas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"QFrame {{ background-color: {theme.SURFACE};"
            f" border-radius: 6px; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(6)

        titulo = QHBoxLayout()
        titulo.addWidget(_label("Piezas terminadas por banco", theme.TEXT, 11))
        titulo.addStretch(1)
        self.subtitle = _label("", theme.TEXT_MUTED, 9)
        titulo.addWidget(self.subtitle)
        outer.addLayout(titulo)

        self.rows = QGridLayout()
        self.rows.setHorizontalSpacing(10)
        self.rows.setVerticalSpacing(2)
        self.rows.setColumnStretch(1, 1)
        outer.addLayout(self.rows)

        self.note = _label("", theme.TEXT_MUTED, 9)
        self.note.setWordWrap(True)
        outer.addWidget(self.note)
        outer.addStretch(1)

    # --- datos -----------------------------------------------------------
    def set_usage(self, rigs, counts: dict, coverage: tuple[int, int]) -> None:
        """``counts`` va por (nombre, tipo); ``coverage`` es (atribuidas, total)."""
        self._clear()

        # Los nombres se repiten entre tipos de ensayo --hay tres I-25-- asi
        # que solo esos llevan de que bitacora son.
        repetidos = {r.name for r in rigs
                     if sum(1 for o in rigs if o.name == r.name) > 1}

        ordenados = sorted(
            rigs, key=lambda r: (-counts.get((r.name, r.test_type), 0), r.name)
        )
        mayor = max(counts.values(), default=0)

        for fila, rig in enumerate(ordenados):
            piezas = counts.get((rig.name, rig.test_type), 0)
            nombre = rig.name
            if rig.name in repetidos:
                nombre = f"{rig.name}  ·  {TEST_TYPES[rig.test_type].label}"

            etiqueta = _label(nombre, theme.TEXT if piezas else theme.TEXT_MUTED)
            etiqueta.setFixedWidth(NAME_WIDTH)
            etiqueta.setAlignment(Qt.AlignmentFlag.AlignRight
                                  | Qt.AlignmentFlag.AlignVCenter)
            self.rows.addWidget(etiqueta, fila, 0)

            self.rows.addWidget(self._bar(rig, piezas, mayor), fila, 1)

            total = _label(f"{piezas:,}" if piezas else "—",
                           theme.TEXT if piezas else theme.TEXT_MUTED)
            total.setFixedWidth(70)
            total.setAlignment(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter)
            self.rows.addWidget(total, fila, 2)

        atribuidas, todas = coverage
        self.subtitle.setText(f"{atribuidas:,} de {todas:,} piezas con banco anotado")
        if atribuidas < todas:
            faltan = todas - atribuidas
            self.note.setText(
                f"Faltan {faltan:,} piezas por atribuir: se cerraron sin dejar "
                f"anotado el banco. Casi todas son de Fatiga anterior a 2026, "
                f"cuando el resultado se capturaba en el campo de Test Rig y la "
                f"migración 008 lo separó dejando el banco vacío."
            )
            self.note.setVisible(True)
        else:
            self.note.setVisible(False)

    def _bar(self, rig, piezas: int, mayor: int) -> QWidget:
        """Barra proporcional al banco que mas piezas terminó."""
        contenedor = QWidget()
        contenedor.setFixedHeight(ROW_HEIGHT)
        contenedor.setStyleSheet("border: none;")
        caja = QHBoxLayout(contenedor)
        caja.setContentsMargins(0, (ROW_HEIGHT - BAR_HEIGHT) // 2, 0,
                                (ROW_HEIGHT - BAR_HEIGHT) // 2)
        caja.setSpacing(0)

        barra = QWidget()
        barra.setFixedHeight(BAR_HEIGHT)
        barra.setStyleSheet(
            f"background-color: {rig.color}; border-radius: 2px;"
        )
        barra.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Fixed)

        # El reparto es muy desigual, asi que una barra con datos nunca baja de
        # un minimo: sin eso, seis piezas contra mil quinientas no se veian.
        peso = max(int(1000 * piezas / mayor), 12) if piezas and mayor else 0
        caja.addWidget(barra, peso)
        caja.addStretch(max(1000 - peso, 0))
        return contenedor

    def _clear(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
