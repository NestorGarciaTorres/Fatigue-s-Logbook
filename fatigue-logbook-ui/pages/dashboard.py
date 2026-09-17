"""Dashboard: lo que se hizo en un rango de fechas.

Va en **dos pestanias** y no en una columna: todo junto pedia 1,300 px de alto
y en una pantalla de 1080 nacia cortado. Los filtros y las tarjetas se quedan
arriba, a la vista en las dos.

Las graficas son ``QtCharts`` y no toman el color de la hoja de estilos: hay
que dárselo widget a widget. Por eso se **reconstruyen enteras** en cada
refresco y tambien al cambiar de tema -- es el unico sitio de la app donde el
cambio de tema obliga a rehacer algo en vez de solo repintarlo.
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
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.models import FATIGUE, FINISHED, ONGOING, QUASI, ROTARY, TORSION
from app.services import filtering, maintenance, rig_usage
from app.services.filtering import TestFilters
from components import buttons, cards, fields, labels
from components.panels import MaintenancePanel, RigUsagePanel
from pages.base import Page
from theme.manager import theme

MONTH_NAMES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

# Cuantos clientes se enumeran antes de agrupar el resto en 'Otros'. Son seis
# y no ocho porque la leyenda va al lado del pastel y con mas entradas se
# cortaba por abajo: dos porciones quedaban sin nombre, que es peor que
# agruparlas a proposito en 'Otros'.
SLICES = 6


def _style_chart(chart: QChart, title: str) -> QChart:
    paleta = theme().palette
    chart.setTitle(title)
    chart.setBackgroundBrush(QColor(paleta.surface))
    chart.setBackgroundPen(QColor(paleta.surface))
    chart.setTitleBrush(QColor(paleta.text))
    chart.legend().setLabelColor(QColor(paleta.text_secondary))
    chart.setMargins(chart.margins())
    return chart


def _style_axis(axis) -> None:
    paleta = theme().palette
    axis.setLabelsColor(QColor(paleta.text_secondary))
    axis.setGridLineColor(QColor(paleta.divider))
    axis.setLinePenColor(QColor(paleta.border))


def _chart_view(chart: QChart) -> QChartView:
    vista = QChartView(chart)
    vista.setRenderHint(QPainter.RenderHint.Antialiasing)
    vista.setFrameShape(QFrame.Shape.NoFrame)
    vista.setMinimumHeight(300)
    vista.setBackgroundBrush(QColor(theme().palette.surface))
    return vista


class DashboardPage(Page):
    def __init__(self, context, rig_palette, parent=None):
        super().__init__("Dashboard",
                         "Lo que se hizo en el periodo seleccionado", parent)
        self.context = context
        self.rig_palette = rig_palette
        self._maintenance: list = []

        # --- rango de fechas ---------------------------------------------
        controles = QHBoxLayout()
        controles.setSpacing(8)
        self.date_from = fields.date_edit(date(date.today().year, 1, 1))
        self.date_to = fields.date_edit()
        controles.addWidget(labels.muted("Desde"))
        controles.addWidget(self.date_from)
        controles.addWidget(labels.muted("Hasta"))
        controles.addWidget(self.date_to)
        controles.addWidget(buttons.button("Actualizar", buttons.PRIMARY,
                                           on_click=self.refresh))
        controles.addStretch(1)
        self.content.addLayout(controles)

        # --- tarjetas ----------------------------------------------------
        # Todas del mismo color salvo la de paro. El color aqui no es adorno:
        # en la tabla el rojo significa 'revisar' y el naranja 'suspendida', y
        # gastarlos de decoracion les quita el significado que si tienen.
        self.card_ongoing = cards.StatCard("Pruebas en curso", "0", "accent")
        self.card_cycles = cards.StatCard("Ciclos acumulados", "0", "accent")
        self.card_samples = cards.StatCard("Piezas probadas", "0", "accent")
        self.card_rigs = cards.StatCard("Rigs ocupados", "0", "accent")
        self.card_downtime = cards.StatCard(
            "Días de paro", "0", "maintenance",
            hint="Días que algún banco estuvo fuera de servicio dentro del "
                 "rango de fechas seleccionado")
        self.content.addLayout(cards.stat_row(
            self.card_ongoing, self.card_cycles, self.card_samples,
            self.card_rigs, self.card_downtime))

        # --- dos pestanias ------------------------------------------------
        self.tabs = QTabWidget()

        self.charts = QWidget()
        self.grid = QGridLayout(self.charts)
        self.grid.setSpacing(12)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.tabs.addTab(self._scrollable(self.charts), "Resumen")

        # Los paneles no se recrean en cada refresco como las graficas: son
        # dieciseis renglones de widgets y volver a construirlos hace
        # parpadear la pantalla.
        self.rig_usage = RigUsagePanel(rig_palette)
        self.maintenance_panel = MaintenancePanel()
        self.maintenance_panel.historyRequested.connect(self.show_history)

        self.rigs_tab = QWidget()
        columna = QVBoxLayout(self.rigs_tab)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(12)
        columna.addWidget(self.rig_usage)
        columna.addWidget(self.maintenance_panel)
        columna.addStretch(1)
        self.tabs.addTab(self._scrollable(self.rigs_tab),
                         "Bancos y mantenimiento")

        self.content.addWidget(self.tabs, 1)

        # Las graficas llevan sus colores dentro, no en la hoja de estilos:
        # hay que rehacerlas al cambiar de tema.
        theme().themeChanged.connect(self._repaint_charts)

    @staticmethod
    def _scrollable(contenido: QWidget) -> QScrollArea:
        """Cada pestania se desplaza por su cuenta si la pantalla es muy baja."""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(contenido)
        return area

    # --- datos -------------------------------------------------------------
    def _range_filter(self) -> TestFilters:
        return TestFilters(date_from=fields.to_date(self.date_from),
                           date_to=fields.to_date(self.date_to))

    def refresh(self) -> None:
        ventana = self._range_filter()

        fatigue_all = self.context.fatigue.list()
        fatigue = filtering.apply(fatigue_all, ventana)
        cerradas = [t for t in fatigue if t.test_status == FINISHED]
        abiertas = [t for t in fatigue_all if t.test_status == ONGOING]
        rotary_all = self.context.rotary.list()
        rotary_abiertas = [t for t in rotary_all if not t.is_finished]

        # Las pruebas abiertas son las de Fatiga *y* Rotary, que son las dos
        # bitacoras con ciclo de vida, igual que en la pantalla de rigs.
        self.card_ongoing.set_value(len(abiertas) + len(rotary_abiertas))
        self.card_cycles.set_value(sum(t.total_cycles for t in cerradas))

        # La ocupacion la calcula el mismo servicio que la pantalla de rigs:
        # cuando cada una lo hacia por su cuenta, una decia 10 bancos ocupados
        # y la otra 11.
        rigs = self.context.catalogs.rigs()
        ocupados, _ = rig_usage.occupancy(
            abiertas, rotary_abiertas, rig_usage.catalog_keys(rigs))
        self.card_rigs.set_value(len(ocupados))

        self._rebuild_charts(fatigue, cerradas, ventana)

        piezas = rig_usage.finished_pieces(
            fatigue, filtering.apply(rotary_all, ventana),
            {"torsion": filtering.apply(self.context.torsion.list(), ventana),
             "quasi": filtering.apply(self.context.quasi.list(), ventana)})
        # La misma cuenta que el panel: la tarjeta decia las piezas declaradas
        # de Fatiga y el panel las de las cuatro bitacoras, asi que los dos
        # numeros de la misma pantalla no cuadraban.
        self.card_samples.set_value(piezas.total)
        self.rig_usage.set_usage(rigs, piezas.by_rig,
                                 (piezas.attributed, piezas.total))

        registros = self.context.maintenance.list()
        desde, hasta = ventana.date_from, ventana.date_to
        self._maintenance = maintenance.overlapping(registros, desde, hasta)
        # Recortado al rango, no sumado entero: lo que se mide aqui no es lo
        # que el banco estuvo parado en total, sino dentro del periodo.
        parado = maintenance.downtime_by_rig(self._maintenance,
                                             window=(desde, hasta))
        self.card_downtime.set_value(sum(parado.values()))
        self.maintenance_panel.set_history(self._maintenance, rigs, parado)

    def _repaint_charts(self) -> None:
        """Al cambiar de tema. Solo si la pantalla ya tiene datos cargados."""
        if self.grid.count():
            self.refresh()

    # --- graficas ----------------------------------------------------------
    def _rebuild_charts(self, fatigue, cerradas, ventana) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        # La de ciclos por mes ocupa la fila de arriba entera.
        self.grid.addWidget(_chart_view(self._cycles_by_month(cerradas)),
                            0, 0, 1, 2)
        self.grid.addWidget(_chart_view(self._by_customer(fatigue)), 1, 0)
        self.grid.addWidget(_chart_view(self._by_test_type(ventana)), 1, 1)

    def _cycles_by_month(self, tests) -> QChart:
        """Ciclos por mes de cierre, ultimos doce meses del rango."""
        totales: dict[tuple[int, int], int] = defaultdict(int)
        for test in tests:
            cuando = test.end_date or test.start_date
            if cuando:
                totales[(cuando.year, cuando.month)] += test.total_cycles

        claves = sorted(totales)[-12:]
        categorias = [f"{MONTH_NAMES[m - 1]} {str(y)[2:]}" for y, m in claves]

        # En millones: el eje llegaba a 42669745 y esa cifra hay que contarla
        # con el dedo para saber de que orden es.
        barra = QBarSet("Ciclos")
        barra.setColor(QColor(theme().palette.accent))
        barra.setBorderColor(QColor(theme().palette.accent))
        for clave in claves:
            barra.append(totales[clave] / 1_000_000)

        series = QBarSeries()
        series.append(barra)

        chart = _style_chart(QChart(), "Ciclos por mes (millones)")
        chart.addSeries(series)

        eje_x = QBarCategoryAxis()
        eje_x.append(categorias or ["Sin datos"])
        _style_axis(eje_x)
        chart.addAxis(eje_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(eje_x)

        eje_y = QValueAxis()
        eje_y.setLabelFormat("%.0f")
        _style_axis(eje_y)
        chart.addAxis(eje_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(eje_y)
        eje_y.setTickCount(4)
        eje_y.applyNiceNumbers()

        chart.legend().setVisible(False)
        return chart

    def _by_customer(self, tests) -> QChart:
        """Reparto por cliente. Los que no caben van juntos en 'Otros'.

        Los colores salen de la paleta de bancos del tema activo, que esta
        construida justo para que se distingan entre si; dejandoselo a Qt,
        STELLANTIS, VW, FORD y RIVIAN salian casi del mismo azul.
        """
        cuentas = Counter(t.customer for t in tests if t.customer)
        principales = cuentas.most_common(SLICES)
        resto = sum(cuentas.values()) - sum(n for _, n in principales)

        entradas = list(principales)
        if resto:
            entradas.append(
                (f"Otros: {len(cuentas) - len(principales)} clientes", resto))

        paleta_bancos = list(self.rig_palette.colors().values())
        paleta = theme().palette
        series = QPieSeries()
        for posicion, (cliente, cuantas) in enumerate(entradas):
            porcion = series.append(f"{cliente} ({cuantas})", cuantas)
            color = (paleta_bancos[(posicion * 3) % len(paleta_bancos)]
                     if paleta_bancos else paleta.accent)
            porcion.setColor(QColor(color))
            porcion.setBorderColor(QColor(paleta.surface))
            porcion.setLabelColor(QColor(paleta.text))

        chart = _style_chart(QChart(), "Pruebas por cliente")
        chart.addSeries(series)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        return chart

    def _by_test_type(self, ventana) -> QChart:
        """Pruebas finalizadas por tipo de ensayo.

        Las en curso ya estan en la tarjeta de arriba y cambian cada semana;
        aqui interesa el trabajo cerrado.
        """
        fatigue = filtering.apply(self.context.fatigue.list(), ventana)
        rotary = filtering.apply(self.context.rotary.list(), ventana)
        torsion = filtering.apply(self.context.torsion.list(), ventana)
        quasi = filtering.apply(self.context.quasi.list(), ventana)

        cerradas = [
            sum(1 for t in fatigue if t.test_status == FINISHED),
            sum(1 for t in rotary if t.test_status == FINISHED),
            # Torsion y Quasi no llevan estatus: lo registrado esta hecho.
            len(torsion),
            len(quasi),
        ]

        # Una serie por tipo, cada una con el color de su bitacora. Con una
        # sola serie, Rotary (13 contra 215) quedaba reducido a una linea de
        # un pixel.
        paleta = theme().palette
        acentos = [paleta.accent, paleta.danger, paleta.warning, paleta.info]
        series = QBarSeries()
        for config, total, color in zip(
                (FATIGUE, ROTARY, TORSION, QUASI), cerradas, acentos):
            barra = QBarSet(config.label)
            barra.setColor(QColor(color))
            barra.setBorderColor(QColor(color))
            barra.append(total)
            series.append(barra)

        chart = _style_chart(QChart(),
                             "Pruebas finalizadas por tipo de ensayo")
        chart.addSeries(series)

        eje_x = QBarCategoryAxis()
        eje_x.append([""])
        _style_axis(eje_x)
        chart.addAxis(eje_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(eje_x)

        eje_y = QValueAxis()
        eje_y.setLabelFormat("%d")
        _style_axis(eje_y)
        chart.addAxis(eje_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(eje_y)
        eje_y.setTickCount(4)
        eje_y.applyNiceNumbers()

        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        return chart

    # --- historial ---------------------------------------------------------
    def show_history(self) -> None:
        """Todos los periodos, sin recortar por el rango.

        El panel ensenia lo que cae dentro del periodo que se esta mirando; la
        ventana ensenia el historial completo, que es a lo que se viene cuando
        se pulsa 'Ver historial completo'.
        """
        from dialogs.history import MaintenanceHistoryDialog

        MaintenanceHistoryDialog(
            maintenance.overlapping(self.context.maintenance.list()),
            title="Historial de mantenimiento de bancos", parent=self).exec()
