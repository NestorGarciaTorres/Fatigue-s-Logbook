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
    QScrollArea,
    QWidget,
)

from app.context import AppContext
from app.models import FATIGUE, FINISHED, ONGOING, QUASI, ROTARY, TORSION
from app.services import filtering, maintenance, rig_usage
from app.services.catalogs import DEFAULT_PALETTE
from app.services.filtering import TestFilters
from app.ui import theme
from app.ui.dialogs.maintenance_history_dialog import (
    MaintenanceHistoryDialog,
)
from app.ui.pages.base_page import BasePage
from app.ui.widgets.common import StatCard
from app.ui.widgets.filter_bar import make_date_edit, to_date
from app.ui.widgets.maintenance_panel import MaintenancePanel
from app.ui.widgets.rig_usage_panel import RigUsagePanel

# Porciones con nombre en el pastel de clientes; el resto se suma en
# 'Otros'. Se pedian ocho y en la leyenda cabian cinco renglones, asi
# que las ultimas porciones quedaban sin nombre.
SLICES = 4

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
    # 230 medido: por debajo de eso Qt pone puntos suspensivos en las
    # etiquetas del eje y recorta la ultima linea de la leyenda. La
    # ventana crecio para que quepan las dos filas y el panel de bancos;
    # en una pantalla mas baja, el area de desplazamiento se encarga.
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
        # Las cuatro en el mismo color. Iban en azul, verde, naranja y rojo
        # sin que el color dijera nada, y 'Rigs ocupados' en rojo se leia como
        # una alarma cuando es un conteo normal. En la tabla el rojo significa
        # 'revisar' y el naranja 'pieza suspendida'; gastarlos aqui de adorno
        # les quita el significado que si tienen.
        cards = QHBoxLayout()
        self.card_ongoing = StatCard("Pruebas en curso", "0", theme.INFO)
        self.card_cycles = StatCard("Ciclos acumulados", "0", theme.INFO)
        self.card_samples = StatCard("Piezas probadas", "0", theme.INFO)
        self.card_rigs = StatCard("Rigs ocupados", "0", theme.INFO)
        # El unico color distinto de la fila, y no es adorno: los dias que el
        # laboratorio no pudo ensayar porque el banco estaba parado.
        # 'Días de paro' y no 'Días de mantenimiento': el rotulo largo pedia
        # 303 px de tarjeta y dejaba la fila de cinco por encima del ancho de
        # la ventana. Lo que significa va en el tooltip, que no cuesta ancho.
        self.card_downtime = StatCard("Días de paro", "0", theme.MAINTENANCE)
        self.card_downtime.setToolTip(
            "Días que algún banco estuvo fuera de servicio dentro del rango "
            "de fechas seleccionado"
        )
        for card in (
            self.card_ongoing, self.card_cycles, self.card_samples,
            self.card_rigs, self.card_downtime,
        ):
            cards.addWidget(card)
        self.content.addLayout(cards)

        # --- graficas ----------------------------------------------------
        # Dentro de un area con desplazamiento: entre dos filas de
        # graficas y los dieciseis bancos, el contenido pide 1,135 px de
        # alto. En una pantalla de portatil eso deja la ventana mas alta
        # que el escritorio, y una ventana no se puede encoger por debajo
        # del minimo de lo que lleva dentro.
        self.charts = QWidget()
        self.grid = QGridLayout(self.charts)
        self.grid.setSpacing(10)
        self.grid.setContentsMargins(0, 0, 0, 0)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setWidget(self.charts)
        self.content.addWidget(area, 1)

        # El panel de bancos no se recrea en cada refresco como las
        # graficas: son dieciseis renglones de widgets y volver a
        # construirlos hace parpadear la pantalla.
        self.rig_usage = RigUsagePanel()

        # El historial de mantenimiento, con el mismo rango que todo lo demas.
        # Tampoco se recrea en cada refresco, por lo mismo que el de bancos.
        self.maintenance_panel = MaintenancePanel()
        self.maintenance_panel.historyRequested.connect(self.show_history)
        self._maintenance: list = []

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
        rotary_all = self.context.rotary.list()
        rotary_ongoing = [t for t in rotary_all if not t.is_finished]

        # Las cuatro tarjetas miden lo mismo que el resto de la app:
        # las pruebas abiertas son las de Fatiga *y* Rotary, que son las
        # dos bitacoras con ciclo de vida, igual que en la pantalla de
        # rigs. Antes esta contaba solo Fatiga.
        self.card_ongoing.set_value(len(ongoing_all) + len(rotary_ongoing))
        self.card_cycles.set_value(sum(t.total_cycles for t in finished))

        # La ocupacion la calcula el mismo servicio que la pantalla de
        # rigs. Aqui se contaba solo Fatiga y cruzando por nombre: decia
        # 10 bancos ocupados donde la otra pantalla decia 11.
        rigs = self.context.catalogs.rigs()
        ocupados, _ = rig_usage.occupancy(
            ongoing_all, rotary_ongoing, rig_usage.catalog_keys(rigs),
        )
        self.card_rigs.set_value(len(ocupados))

        self._clear_charts()
        # Tres graficas: la de ciclos por mes ocupa la fila de arriba entera.
        self.grid.addWidget(_chart_view(self._cycles_by_month(finished)), 0, 0, 1, 2)
        self.grid.addWidget(_chart_view(self._by_customer(fatigue)), 1, 0)
        self.grid.addWidget(_chart_view(self._by_test_type(window)), 1, 1)

        # Y abajo, lo que ha sacado cada banco.
        piezas = rig_usage.finished_pieces(
            fatigue,
            filtering.apply(rotary_all, window),
            {
                "torsion": filtering.apply(self.context.torsion.list(), window),
                "quasi": filtering.apply(self.context.quasi.list(), window),
            },
        )
        # La misma cuenta que el panel: la tarjeta decia las piezas
        # declaradas de Fatiga y el panel las de las cuatro bitacoras,
        # asi que los dos numeros de la misma pantalla no cuadraban.
        self.card_samples.set_value(piezas.total)
        self.rig_usage.set_usage(rigs, piezas.by_rig,
                                 (piezas.attributed, piezas.total))
        self.grid.addWidget(self.rig_usage, 2, 0, 1, 2)

        # Y el mantenimiento: que bancos estuvieron parados en el rango, cuanto
        # y por que. Se recorta al rango igual que las graficas -- lo que se
        # mide aqui no es lo que el banco estuvo parado en total, sino lo que
        # estuvo parado dentro del periodo que se esta mirando.
        registros = self.context.maintenance.list()
        desde, hasta = window.date_from, window.date_to
        self._maintenance = maintenance.overlapping(registros, desde, hasta)
        parado = maintenance.downtime_by_rig(
            self._maintenance, window=(desde, hasta)
        )
        self.card_downtime.set_value(sum(parado.values()))
        self.maintenance_panel.set_history(self._maintenance, rigs, parado)
        self.grid.addWidget(self.maintenance_panel, 3, 0, 1, 2)

    def _clear_charts(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None and widget not in (self.rig_usage,
                                                     self.maintenance_panel):
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

        # En millones: el eje llegaba a 42669745 y esa cifra hay que
        # contarla con el dedo para saber de que orden es.
        bar_set = QBarSet("Ciclos")
        bar_set.setColor(QColor(theme.PRIMARY))
        for key in keys:
            bar_set.append(totals[key] / 1_000_000)

        series = QBarSeries()
        series.append(bar_set)

        chart = _style_chart(QChart(), "Ciclos por mes (millones)")
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories or ["Sin datos"])
        _style_axis(axis_x)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%.0f")
        _style_axis(axis_y)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        axis_y.setTickCount(4)
        axis_y.applyNiceNumbers()

        chart.legend().setVisible(False)
        return chart

    def _by_customer(self, tests) -> QChart:
        """Reparto por cliente. Los que no caben van juntos en 'Otros'.

        Antes se pedian los ocho primeros y la leyenda se cortaba en el sexto,
        asi que dos porciones quedaban sin nombre; y el tono lo elegia Qt, que
        reparte una rampa de azules donde STELLANTIS, VW, FORD y RIVIAN salian
        casi del mismo color. Ahora los colores son los de la paleta de rigs,
        que esta construida justo para que se distingan entre si.
        """
        counts = Counter(test.customer for test in tests if test.customer)
        principales = counts.most_common(SLICES)
        resto = sum(counts.values()) - sum(n for _, n in principales)

        series = QPieSeries()
        entradas = list(principales)
        if resto:
            entradas.append(
                (f"Otros: {len(counts) - len(principales)} clientes", resto)
            )

        for posicion, (customer, count) in enumerate(entradas):
            slice_ = series.append(f"{customer} ({count})", count)
            color = DEFAULT_PALETTE[(posicion * 3) % len(DEFAULT_PALETTE)]
            slice_.setColor(QColor(color))
            slice_.setBorderColor(QColor(theme.SURFACE))
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

        cerradas = [
            sum(1 for t in fatigue if t.test_status == FINISHED),
            sum(1 for t in rotary if t.test_status == FINISHED),
            # Torsion y Quasi no llevan estatus: lo registrado esta hecho.
            len(torsion),
            len(quasi),
        ]

        # Una serie por tipo, cada una con el color con el que ese ensayo
        # aparece en el menu. Antes era una sola serie verde con una leyenda
        # que decia 'Finalizadas' -- el titulo otra vez -- y con Rotary (13
        # contra 215) reducido a una linea de un pixel.
        series = QBarSeries()
        for config, total in zip((FATIGUE, ROTARY, TORSION, QUASI), cerradas):
            barra = QBarSet(config.label)
            barra.setColor(QColor(config.accent))
            barra.setBorderColor(QColor(config.accent))
            barra.append(total)
            series.append(barra)

        chart = _style_chart(QChart(), "Pruebas finalizadas por tipo de ensayo")
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append([""])
        _style_axis(axis_x)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%d")
        _style_axis(axis_y)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        axis_y.setTickCount(4)
        axis_y.applyNiceNumbers()

        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        return chart

    # --- historial -------------------------------------------------------
    def show_history(self) -> None:
        """Todos los periodos de mantenimiento, sin recortar por el rango.

        El panel ensenia lo que cae dentro del periodo que se esta mirando;
        la ventana ensenia el historial completo, que es a lo que se viene
        cuando se pulsa 'Ver historial completo'.
        """
        MaintenanceHistoryDialog(
            maintenance.overlapping(self.context.maintenance.list()),
            title="Historial de mantenimiento de bancos", parent=self,
        ).exec()
