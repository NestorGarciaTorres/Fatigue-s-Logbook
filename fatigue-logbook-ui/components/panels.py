"""Los dos paneles del dashboard: piezas por banco y mantenimiento.

Ninguno de los dos es una grafica, y es deliberado.

- **Piezas por banco**: con dieciseis bancos y un reparto muy desigual --un
  banco de Torsion lleva 1,594 piezas y el de fatiga que mas tiene lleva 6--
  una grafica de barras deja las pequenias en menos de un pixel. Aqui cada
  banco tiene su renglon, su color y su numero escrito, asi que un 6 se lee
  igual de bien que un 1,594.
- **Mantenimiento**: los periodos son pocos y muy desiguales, y lo que se
  quiere leer de cada uno es **cuando, cuanto y por que**, que en una barra no
  cabe.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from app import dates
from components import buttons, labels
from components.cards import Card
from theme.manager import theme

# Cuantos renglones se enumeran antes de resumir. Con mas, el panel es mas
# largo que la pestania y deja de leerse de un vistazo.
MAX_ROWS = 16
BAR_HEIGHT = 10
BAR_MIN = 3


class _Bar(QWidget):
    """Barra horizontal de un renglon. Se pinta en el color de su banco."""

    def __init__(self, color: str, fraction: float, parent=None):
        super().__init__(parent)
        self._color = color
        self._fraction = max(0.0, min(1.0, fraction))
        self.setFixedHeight(BAR_HEIGHT)
        self.setMinimumWidth(40)

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QColor, QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # El carril, para que un banco con pocas piezas siga teniendo un
        # renglon visible en vez de parecer que no tiene barra.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme().palette.sunken))
        painter.drawRoundedRect(self.rect(), 5, 5)

        ancho = max(BAR_MIN, int(self.width() * self._fraction))
        painter.setBrush(QColor(self._color))
        painter.drawRoundedRect(0, 0, ancho, self.height(), 5, 5)
        painter.end()


class RigUsagePanel(Card):
    """Piezas terminadas por banco, en barras horizontales."""

    def __init__(self, rig_palette, parent=None):
        super().__init__(parent=parent)
        self.rig_palette = rig_palette
        self.body.setSpacing(10)

        self.title = labels.subheading("Piezas terminadas por banco")
        self.body.addWidget(self.title)
        self.coverage = labels.muted("")
        self.coverage.setWordWrap(True)
        self.body.addWidget(self.coverage)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(6)
        self.body.addLayout(self.grid)

    def set_usage(self, rigs, by_rig: dict, coverage: tuple[int, int]) -> None:
        self._clear()

        filas = sorted(
            ((rig, by_rig.get((rig.name, rig.test_type), 0)) for rig in rigs),
            key=lambda par: par[1], reverse=True)[:MAX_ROWS]
        mayor = max((n for _, n in filas), default=0)

        for indice, (rig, cuantas) in enumerate(filas):
            color = (self.rig_palette.color(rig.name, rig.test_type)
                     or theme().palette.border)
            self.grid.addWidget(labels.muted(rig.name), indice, 0)
            self.grid.addWidget(
                _Bar(color, cuantas / mayor if mayor else 0), indice, 1)
            numero = labels.secondary(f"{cuantas:,}")
            numero.setAlignment(Qt.AlignmentFlag.AlignRight
                                | Qt.AlignmentFlag.AlignVCenter)
            self.grid.addWidget(numero, indice, 2)
        self.grid.setColumnStretch(1, 1)

        atribuidas, total = coverage
        if total:
            # El par no sobra: casi todo lo anterior a 2026 tiene resultado
            # pero no banco, asi que sin decirlo la grafica se leeria como
            # 'estos bancos no han hecho nada'.
            self.coverage.setText(
                f"{atribuidas:,} de {total:,} piezas tienen banco anotado "
                f"({atribuidas / total:.0%}). Las demás son registros "
                f"antiguos, de cuando el banco y el resultado compartían "
                f"columna.")
        else:
            self.coverage.setText("Sin piezas terminadas en este periodo.")

    def _clear(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()


class MaintenancePanel(Card):
    """Historial de mantenimiento del periodo que se esta mirando."""

    historyRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.body.setSpacing(10)

        cabecera = QHBoxLayout()
        cabecera.addWidget(labels.subheading("Mantenimiento de bancos"))
        cabecera.addStretch(1)
        cabecera.addWidget(buttons.button(
            "Ver historial completo", buttons.GHOST,
            on_click=self.historyRequested.emit))
        self.body.addLayout(cabecera)

        self.summary = labels.muted("")
        self.summary.setWordWrap(True)
        self.body.addWidget(self.summary)

        self.rows = QVBoxLayout()
        self.rows.setSpacing(4)
        self.body.addLayout(self.rows)

    def set_history(self, records: list, rigs, downtime: dict) -> None:
        self._clear()

        if not records:
            self.summary.setText(
                "Ningún banco estuvo fuera de servicio en este periodo.")
            return

        abiertos = sum(1 for r in records if r.is_open)
        total = sum(downtime.values())
        self.summary.setText(
            f"{len(records)} periodos  ·  {total} días de paro dentro del "
            f"rango" + (f"  ·  {abiertos} sigue abierto" if abiertos == 1
                        else f"  ·  {abiertos} siguen abiertos"
                        if abiertos else ""))

        for record in records[:MAX_ROWS]:
            self.rows.addWidget(self._row(record, downtime))

        sobran = len(records) - MAX_ROWS
        if sobran > 0:
            self.rows.addWidget(labels.muted(
                f"y {sobran} periodo más" if sobran == 1
                else f"y {sobran} periodos más"))

    def _row(self, record, downtime: dict) -> QWidget:
        fila = QWidget()
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)

        caja.addWidget(labels.secondary(record.rig_name))

        periodo = dates.display(record.start_date)
        if record.end_date:
            periodo += f" a {dates.display(record.end_date)}"
        else:
            periodo += " · en curso"
        caja.addWidget(labels.muted(periodo))

        dias = downtime.get(record.key)
        if dias is not None:
            caja.addWidget(labels.pill(
                f"{dias} d", "maintenance" if record.is_open else "neutral"))

        if record.reason:
            motivo = labels.muted(record.reason)
            motivo.setToolTip(record.reason)
            caja.addWidget(motivo)

        caja.addStretch(1)
        return fila

    def _clear(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
