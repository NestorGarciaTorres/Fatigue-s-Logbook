"""Dashboard con graficas.

Usa ``PySide6.QtCharts``, que viene incluido con PySide6: no agrega
dependencias. Todas las graficas respetan el rango de fechas seleccionado.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from app.context import AppContext
from app.models import FINISHED, ONGOING
from app.services import filtering
from app.services.filtering import TestFilters
from app.ui import theme
from app.ui.pages.base_page import BasePage
from app.ui.widgets.common import StatCard
from app.ui.widgets.filter_bar import make_date_edit, to_date

MONTH_NAMES = [
    "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
]


def _style_chart(chart: QChart, title: str) -> QChart:
    chart.setTitle(title)
    chart.setBackgroundBrush(QColor(theme.SURFACE))
    chart.setTitleBrush(QColor(theme.TEXT))
    chart.legend().setLabelColor(QColor(theme.TEXT))
    chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
    return chart


def _style_axis(axis) -> None:
    axis.setLabelsColor(QColor(theme.TEXT))
    axis.setTitleBrush(QColor(theme.TEXT))
    axis.setGridLineColor(QColor(theme.BORDER))
    axis.setLinePenColor(QColor(theme.BORDER))


def _chart_view(chart: QChart) -> QChartView:
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    # 230 y no 260: con dos filas de graficas, 260 le ponia a la
    # ventana un suelo de 803 px y no bajaba al tamano pedido.
    view.setMinimumHeight(230)
    return view


class DashboardPage(BasePage):
    def __init__(self, context: AppContext, parent=None):
        super().__init__("Dashboard", parent)
        self.context = context

        # --- rango de fechas ---------------------------------------------
        controls = QHBoxLayout()
        self.date_from = make_date_edit(date(date.today().year, 1, 1))
        self.date_to = make_date_edit()

        controls.addWidget(QLabel("Desde:"))
        controls.addWidget(self.date_from)
        controls.addWidget(QLabel("Hasta:"))
        controls.addWidget(self.date_to)

        update = QPushButton("Actualizar")
        update.clicked.connect(self.refresh)
        controls.addWidget(update)
        controls.addStretch(1)
        self.content.addLayout(controls)

        # --- tarjetas ----------------------------------------------------
        cards = QHBoxLayout()
        self.card_ongoing = StatCard("Pruebas en curso", "0", theme.INFO)
        self.card_cycles = StatCard("Ciclos acumulados", "0", theme.SUCCESS)
        self.card_samples = StatCard("Piezas probadas", "0", theme.WARNING)
        self.card_rigs = StatCard("Rigs ocupados", "0", theme.DANGER)
        for card in (
            self.card_ongoing, self.card_cycles, self.card_samples, self.card_rigs
        ):
            cards.addWidget(card)
        self.content.addLayout(cards)

        # --- graficas ----------------------------------------------------
        self.charts = QWidget()
        self.grid = QGridLayout(self.charts)
        self.grid.setSpacing(10)
        self.content.addWidget(self.charts, 1)

    # --- datos -----------------------------------------------------------
    def _range_filter(self) -> TestFilters:
        return TestFilters(
            date_from=to_date(self.date_from),
            date_to=to_date(self.date_to),
        )

    def refresh(self) -> None:
        window = self._range_filter()

        fatigue_all = self.context.fatigue.list()
        fatigue = filtering.apply(fatigue_all, window)
        finished = [t for t in fatigue if t.test_status == FINISHED]
        ongoing_all = [t for t in fatigue_all if t.test_status == ONGOING]

        self.card_ongoing.set_value(len(ongoing_all))
        self.card_cycles.set_value(sum(t.total_cycles for t in finished))
        self.card_samples.set_value(sum(t.qty_samples for t in finished))

        # Solo rigs del catalogo: las columnas de rig traen tambien resultados
        # de muestra, y contarlos inflaba el numero de bancos ocupados.
        catalog = {rig.name for rig in self.context.catalogs.rigs()}
        busy_rigs = {
            sample.rig
            for test in ongoing_all
            for sample in test.samples
            if sample.rig in catalog
        }
        self.card_rigs.set_value(len(busy_rigs))

        self._clear_charts()
        # Tres graficas: la de ciclos por mes ocupa la fila de arriba entera.
        self.grid.addWidget(_chart_view(self._cycles_by_month(finished)), 0, 0, 1, 2)
        self.grid.addWidget(_chart_view(self._by_customer(fatigue)), 1, 0)
        self.grid.addWidget(_chart_view(self._by_test_type(window)), 1, 1)

    def _clear_charts(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    # --- graficas --------------------------------------------------------
    def _cycles_by_month(self, tests) -> QChart:
        """Ciclos por mes de cierre, ultimos 12 meses del rango."""
        totals: dict[tuple[int, int], int] = defaultdict(int)
        for test in tests:
            when = test.end_date or test.start_date
            if when:
                totals[(when.year, when.month)] += test.total_cycles

        keys = sorted(totals)[-12:]
        categories = [f"{MONTH_NAMES[m - 1]} {str(y)[2:]}" for y, m in keys]

        bar_set = QBarSet("Ciclos")
        bar_set.setColor(QColor(theme.PRIMARY))
        for key in keys:
            bar_set.append(totals[key])

        series = QBarSeries()
        series.append(bar_set)

        chart = _style_chart(QChart(), "Ciclos por mes")
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories or ["Sin datos"])
        _style_axis(axis_x)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%d")
        _style_axis(axis_y)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setVisible(False)
        return chart

    def _by_customer(self, tests) -> QChart:
        counts = Counter(test.customer for test in tests if test.customer)
        series = QPieSeries()
        for customer, count in counts.most_common(8):
            slice_ = series.append(f"{customer} ({count})", count)
            slice_.setLabelColor(QColor(theme.TEXT))

        chart = _style_chart(QChart(), "Pruebas por cliente")
        chart.addSeries(series)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        return chart

    def _by_test_type(self, window: TestFilters) -> QChart:
        """Pruebas finalizadas por tipo de ensayo.

        Antes eran barras apiladas de 'en curso' frente a 'finalizadas'. Las en
        curso ya estan en la tarjeta de arriba y son un numero que cambia cada
        semana; aqui interesa el trabajo cerrado.
        """
        fatigue = filtering.apply(self.context.fatigue.list(), window)
        rotary = filtering.apply(self.context.rotary.list(), window)
        torsion = filtering.apply(self.context.torsion.list(), window)
        quasi = filtering.apply(self.context.quasi.list(), window)

        finished_set = QBarSet("Finalizadas")
        finished_set.setColor(QColor(theme.SUCCESS))

        for records in (fatigue, rotary):
            finished_set.append(
                sum(1 for t in records if t.test_status == FINISHED)
            )

        # Torsion y Quasi no llevan estatus: toda prueba registrada esta hecha.
        for records in (torsion, quasi):
            finished_set.append(len(records))

        series = QBarSeries()
        series.append(finished_set)

        chart = _style_chart(QChart(), "Pruebas finalizadas por tipo de ensayo")
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(["Fatiga", "Rotary", "Torsion", "Quasi"])
        _style_axis(axis_x)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%d")
        _style_axis(axis_y)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        return chart
