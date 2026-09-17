"""Ocupacion de rigs: que banco esta libre y que corre en cada uno.

Responder "que rig esta libre" exigia leer nueve columnas de rig en todas las
filas de la bitacora. Aqui cada banco del catalogo es una tarjeta con su color,
lo que corre en el y desde cuando.

La pantalla se lee **por estado**, y de ahi salen las tres cosas que la ordenan:

1. Cada tarjeta dice su estado en el mismo sitio y con el mismo color --libre,
   en uso o en mantenimiento-- para recorrer la rejilla sin leer.
2. Los bancos van **agrupados por bitacora**, con su encabezado y su recuento.
   Seguidos en orden de catalogo, una fila cualquiera mezclaba dos ensayos
   distintos sin nada que lo dijera.
3. Las columnas salen del ancho disponible, no de un numero fijo.

Solo hay tarjetas de Fatiga y Rotary (``OCCUPIED_TEST_TYPES``): son las
bitacoras cuyo banco se queda ocupado mientras la prueba corre. En Torsion y
Quasi el Test Rig es un dato del registro, y sus cinco bancos eran tarjetas
'Libre' permanentes sin nada que mirar en ellas.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import dates
from app.models import (
    FINISHED,
    MAINTAINED_TEST_TYPES,
    OCCUPIED_TEST_TYPES,
    ONGOING,
    TEST_TYPES,
    FatigueTest,
    RigMaintenance,
    RotaryTest,
)
from app.services import duration, maintenance, rig_usage
from app.services.identity import current_author
from components import buttons, cards, fields, labels
from components.elevation import Elevated
from pages.base import Page
from theme.color import ink_for
from theme.manager import theme

CARD_WIDTH = 248
CARD_SPACING = 12

# Cuantas pruebas se enumeran dentro de una tarjeta. En la practica un banco
# lleva una pieza, dos como mucho; el corte esta por los registros que se
# quedaron abiertos sin cerrar, que llegaron a apilar doce pruebas en el mismo
# rig de Rotary y estiraban su tarjeta a 480 px -- tres veces las demas, con
# sus tres vecinas de fila en blanco.
MAX_OCCUPANTS = 3

LIBRE = "Libre"
EN_USO = "En uso"
EN_MANTENIMIENTO = "En mantenimiento"

# (rotulo, estado que deja pasar). El estado viaja en el dato del elemento y no
# en su texto: asi el rotulo se puede acortar sin que el filtro deje de
# funcionar -- 'En mantenimiento' escrito entero le ponia 292 px de minimo al
# combo.
FILTERS = (("Todos", None), ("Libres", LIBRE), ("En uso", EN_USO),
           ("Mantenimiento", EN_MANTENIMIENTO))

POR_NOMBRE = "nombre"
POR_ANTIGUEDAD = "antiguedad"
ORDERS = (("Por nombre", POR_NOMBRE), ("Por antigüedad", POR_ANTIGUEDAD))

PILL_FOR_STATE = {LIBRE: "success", EN_USO: "info",
                  EN_MANTENIMIENTO: "maintenance"}


def _dias(cuantos: int) -> str:
    return "1 día" if cuantos == 1 else f"{cuantos} días"


def _piezas(cuantas: int) -> str:
    return "1 pieza" if cuantas == 1 else f"{cuantas} piezas"


def _days_ago(cuando: date | None, referencia: date | None = None) -> str:
    if cuando is None:
        return ""
    dias = ((referencia or date.today()) - cuando).days
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "ayer"
    return f"hace {_dias(dias)}"


class ClickableRow(QWidget):
    """Renglon que se puede pulsar. La tarjeta ensenia el Test Batch y el gesto
    natural es pulsarlo; hasta ahora no pasaba nada."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class CardsContainer(QWidget):
    """Contenedor de la rejilla, con ancho minimo cero.

    Un hijo de ancho fijo le pone suelo a la ventana entera: el ancho fijo por
    tarjeta impedia que la pantalla encogiera y recalculara columnas. Se corrige
    con ``SetNoConstraint`` **y** un ``minimumSizeHint`` de ancho 0; solo una de
    las dos no basta.
    """

    def minimumSizeHint(self):
        base = super().minimumSizeHint()
        base.setWidth(0)
        return base


class RigCard(QFrame, Elevated):
    """Un banco: su estado, lo que corre en el y desde cuando."""

    opened = Signal(object)
    # El banco entra o sale de mantenimiento desde su propia tarjeta: hacerlo
    # desde una barra de arriba obligaria a inventar una seleccion que esta
    # pantalla no tiene, y a mirar dos sitios para saber sobre cual se actua.
    maintenanceRequested = Signal(object)

    def __init__(self, rig, rig_palette, occupants: list,
                 maintenance_record: RigMaintenance | None = None,
                 downtime: int = 0, free_since: date | None = None,
                 parent=None):
        super().__init__(parent)
        self.rig = rig
        self.rig_palette = rig_palette
        self.occupants = occupants
        self.maintenance = maintenance_record
        self.downtime = downtime
        self.free_since = free_since

        if maintenance_record is not None:
            self.state = EN_MANTENIMIENTO
        elif occupants:
            self.state = EN_USO
        else:
            self.state = LIBRE

        # En un banco de Fatiga solo cabe una pieza. Si hay dos declaradas no
        # se esconde ninguna: se marcan para que alguien corrija el registro.
        # En Rotary el banco es de la prueba entera --hay bancos con varias
        # pruebas abiertas a la vez-- y ahi dos no significan un error.
        self.conflict = (len(occupants) > 1
                         and any(o.slot is not None for o, _, _ in occupants))

        self.setProperty("surface", "card")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedWidth(CARD_WIDTH)

        # El tipo de ensayo ya lo dice el encabezado de su grupo, y los dias
        # fuera de servicio acumulados son un dato de consulta, no de vistazo:
        # los dos van al tooltip, que no gasta alto de tarjeta.
        resumen = [TEST_TYPES[rig.test_type].label]
        if downtime:
            resumen.append(f"{_dias(downtime)} fuera de servicio en total")
        self.setToolTip("  ·  ".join(resumen))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        layout.addWidget(self._header())

        # El estado, siempre en el mismo sitio. Antes solo lo decia la tarjeta
        # libre y las demas habia que deducirlas de lo que llevaban dentro.
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(labels.pill(self.state, PILL_FOR_STATE[self.state]))
        fila.addStretch(1)
        layout.addLayout(fila)

        if self.state == LIBRE:
            layout.addWidget(self._free_note())
        elif self.state == EN_MANTENIMIENTO:
            layout.addWidget(self._maintenance_note(maintenance_record))

        if self.conflict:
            layout.addWidget(self._conflict_note())

        for ocupante, dias, nivel in occupants[:MAX_OCCUPANTS]:
            layout.addWidget(self._occupant(ocupante, dias, nivel))

        sobran = len(occupants) - MAX_OCCUPANTS
        if sobran > 0:
            resto = labels.muted(f"y {sobran} prueba más" if sobran == 1
                                 else f"y {sobran} pruebas más")
            resto.setAlignment(Qt.AlignmentFlag.AlignCenter)
            resto.setToolTip("\n".join(
                f"{o.test.test_batch}  ·  {o.test.customer}"
                for o, _, _ in occupants[MAX_OCCUPANTS:]))
            layout.addWidget(resto)

        layout.addStretch(1)
        # Solo los bancos de Fatiga llevan el boton: es donde el banco es de
        # cada pieza y sacarla de ahi significa algo. En Rotary el banco es de
        # la prueba entera y pararlo la suspenderia completa, que es otra
        # decision y todavia no esta tomada.
        if rig.test_type in MAINTAINED_TEST_TYPES:
            layout.addWidget(self._maintenance_button(maintenance_record))

        self.init_elevation("raised")

    # --- piezas de la tarjeta ---------------------------------------------
    def _header(self) -> QLabel:
        """El nombre del banco sobre su color.

        Es el unico sitio de la interfaz donde el color de un rig se pinta
        grande. El color es un **dato del banco**, no del tipo de widget, asi
        que no puede salir de un selector de la hoja de estilos; se pinta aqui
        y por eso hay que volver a pintarlo en cada cambio de tema. Sin esa
        reconexion la tarjeta se quedaba con el color del tema en que se
        construyo, que es justo lo que este sistema evita en todo lo demas.
        """
        self.header_label = QLabel(self.rig.name)
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._paint_header()
        theme().themeChanged.connect(self._paint_header)
        return self.header_label

    def _paint_header(self) -> None:
        color = self.rig_palette.color(
            self.rig.name, self.rig.test_type) or theme().palette.border
        self.header_label.setStyleSheet(
            f"background-color: {color}; color: {ink_for(color)};"
            f" border-radius: 6px; font-weight: 700; font-size: 12pt;"
            f" padding: 5px;")

    def _free_note(self) -> QLabel:
        """Desde cuando esta libre.

        'Libre' a secas no distingue el banco que se desocupo ayer del que
        lleva dos meses sin usarse, y no significan lo mismo.
        """
        if self.free_since is None:
            nota = labels.muted("sin pruebas anteriores")
            nota.setToolTip("Ninguna prueba cerrada registra este banco")
        else:
            nota = labels.muted(f"libre desde {_days_ago(self.free_since)}")
            nota.setToolTip(
                f"La última prueba que corrió aquí cerró el "
                f"{dates.display(self.free_since)}")
        nota.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return nota

    def _maintenance_note(self, record: RigMaintenance | None) -> QWidget:
        caja = QWidget()
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(2)

        if record is None:                     # pragma: no cover - defensivo
            return caja

        dias = record.days()
        desde = (f"desde el {dates.display(record.start_date)}"
                 if record.start_date else "")
        titulo = labels.muted(
            f"{desde}  ·  {_dias(dias)}" if dias is not None else desde)
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        columna.addWidget(titulo)

        if record.reason:
            motivo = labels.secondary(record.reason, wrap=True)
            motivo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            columna.addWidget(motivo)

        detenidas = [s for s in record.samples if s.is_held]
        if detenidas:
            nota = labels.muted(f"{_piezas(len(detenidas))} detenidas")
            nota.setAlignment(Qt.AlignmentFlag.AlignCenter)
            nota.setToolTip("\n".join(
                f"{s.test_batch or f'registro #{s.record_id}'}  ·  "
                f"pieza {s.slot}" for s in detenidas))
            columna.addWidget(nota)
        return caja

    def _conflict_note(self) -> QLabel:
        """Dos piezas declaradas en el mismo banco: un dato que corregir."""
        nota = labels.pill(f"{len(self.occupants)} piezas aquí", "warning")
        nota.setToolTip(
            "En un banco solo puede correr una pieza a la vez. Abre los "
            "registros y corrige el Test Rig de la que ya no esté aquí.")
        return nota

    def _occupant(self, ocupante, dias: int | None, nivel: str) -> QWidget:
        """La pieza que corre en el banco. Se pulsa para abrir su prueba."""
        record = ocupante.test

        fila = ClickableRow()
        fila.setToolTip(f"Abrir el registro de {record.test_batch}")
        fila.clicked.connect(lambda r=record: self.opened.emit(r))

        caja = QVBoxLayout(fila)
        caja.setContentsMargins(0, 2, 0, 2)
        caja.setSpacing(1)

        titulo = record.test_batch
        if ocupante.slot is not None:
            titulo += f"  ·  pieza {ocupante.slot}"
        caja.addWidget(labels.label(titulo, labels.SECONDARY))

        detalle = (f"{record.customer}  ·  {_dias(dias)}" if dias is not None
                   else record.customer)
        # El semaforo va como pastilla y no tiniendo el texto: el color de
        # texto es lo primero que se pierde cuando cambia el fondo.
        pastilla = {duration.OK: "neutral", duration.WARNING: "warning",
                    duration.CRITICAL: "danger"}[nivel]
        if nivel == duration.OK:
            caja.addWidget(labels.muted(detalle))
        else:
            interior = QHBoxLayout()
            interior.setContentsMargins(0, 0, 0, 0)
            interior.setSpacing(6)
            interior.addWidget(labels.pill(_dias(dias or 0), pastilla))
            interior.addWidget(labels.muted(record.customer))
            interior.addStretch(1)
            caja.addLayout(interior)
        return fila

    def _maintenance_button(self, record: RigMaintenance | None):
        boton = buttons.button(
            "Terminar mantenimiento" if record else "Poner en mantenimiento",
            buttons.SUCCESS if record else buttons.MAINTENANCE,
            on_click=lambda: self.maintenanceRequested.emit(self.rig))
        return boton

    # --- para ordenar ------------------------------------------------------
    def urgency(self) -> int:
        """Dias que hacen interesante a este banco, para ordenar por ellos.

        Del que mas tiempo lleva en el mismo estado al que menos: la prueba mas
        antigua, el mantenimiento mas largo, el banco que lleva mas sin usarse.
        """
        if self.state == EN_MANTENIMIENTO and self.maintenance is not None:
            return self.maintenance.days() or 0
        if self.state == EN_USO:
            return max((d or 0 for _, d, _ in self.occupants), default=0)
        if self.free_since is not None:
            return (date.today() - self.free_since).days
        # Un banco sin historial lleva libre desde siempre: va al final de los
        # libres, no al principio, porque no se sabe nada de el.
        return 0


class RigsPage(Page):
    def __init__(self, context, rig_palette, parent=None):
        super().__init__("Ocupación de rigs",
                         "Qué banco está libre y qué corre en cada uno",
                         parent)
        self.context = context
        self.rig_palette = rig_palette
        self._cards: list[RigCard] = []
        self._columns = 0

        self.card_busy = cards.StatCard("Rigs en uso", "0", "accent")
        self.card_free = cards.StatCard("Rigs libres", "0", "success")
        self.card_maintenance = cards.StatCard("En mantenimiento", "0",
                                               "maintenance")
        self.card_tests = cards.StatCard("Pruebas en curso", "0")
        self.content.addLayout(cards.stat_row(
            self.card_busy, self.card_free, self.card_maintenance,
            self.card_tests))

        # Los controles en su propia fila: los dos combos pedian 552 px entre
        # los dos y, sumados a las cuatro tarjetas, le ponian a la pantalla un
        # minimo de 1,846 px de ancho.
        controles = QHBoxLayout()
        controles.setSpacing(10)
        controles.addWidget(labels.muted("Mostrar"))
        self.state_filter = fields.SearchableComboBox(centered=False)
        for rotulo, estado in FILTERS:
            self.state_filter.addItem(rotulo, estado)
        self.state_filter.currentIndexChanged.connect(self._apply_filter)
        controles.addWidget(self.state_filter)

        controles.addSpacing(10)
        controles.addWidget(labels.muted("Orden"))
        self.order = fields.SearchableComboBox(centered=False)
        for rotulo, criterio in ORDERS:
            self.order.addItem(rotulo, criterio)
        self.order.currentIndexChanged.connect(self._apply_filter)
        controles.addWidget(self.order)

        controles.addStretch(1)
        controles.addWidget(buttons.button(
            "Historial", buttons.GHOST,
            tooltip="Periodos de mantenimiento de todos los bancos: cuándo, "
                    "cuánto duraron y por qué",
            on_click=self.show_history))
        controles.addWidget(buttons.button(
            "Actualizar", on_click=self.refresh))
        self.content.addLayout(controles)

        self.notice = labels.secondary("", wrap=True)
        self.notice.setVisible(False)
        self.content.addWidget(self.notice)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.Shape.NoFrame)
        self.container = CardsContainer()
        self.groups = QVBoxLayout(self.container)
        self.groups.setSpacing(16)
        self.groups.setContentsMargins(0, 0, 0, 0)
        self.groups.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.groups.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.area.setWidget(self.container)
        self.area.viewport().installEventFilter(self)
        self.content.addWidget(self.area, 1)

        # Cuando el filtro no deja ningun banco. Sin esto la pantalla se queda
        # en blanco, que se confunde con que la app fallo.
        self.empty = labels.subheading("Ningún banco coincide con el filtro")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setVisible(False)
        self.content.addWidget(self.empty)

    # --- datos -------------------------------------------------------------
    def refresh(self) -> None:
        # Mantenimiento primero: los dias de cada tarjeta van sin el tiempo que
        # la prueba estuvo detenida, igual que en la bitacora, y eso lo
        # necesita ya el cruce de ocupacion.
        registros = self.context.maintenance.list()
        ocupacion, desconocidos, en_curso = self._collect(registros)

        parados = maintenance.open_by_rig(registros)
        fuera = maintenance.downtime_by_rig(registros)
        # Historico completo, sin rango: la pregunta es desde cuando esta libre
        # este banco, no que hizo en un periodo.
        desocupados = rig_usage.last_used(
            self.context.fatigue.list(), self.context.rotary.list(),
            {"torsion": self.context.torsion.list(),
             "quasi": self.context.quasi.list()})

        self._clear()
        for rig in self.context.catalogs.rigs():
            if rig.test_type not in OCCUPIED_TEST_TYPES:
                continue
            clave = (rig.name, rig.test_type)
            tarjeta = RigCard(
                rig, self.rig_palette, ocupacion.get(clave, []),
                maintenance_record=parados.get(clave),
                downtime=fuera.get(clave, 0),
                free_since=desocupados.get(clave))
            tarjeta.maintenanceRequested.connect(self.toggle_maintenance)
            tarjeta.opened.connect(self.open_record)
            self._cards.append(tarjeta)

        self.card_busy.set_value(self._count(EN_USO))
        self.card_free.set_value(self._count(LIBRE))
        self.card_maintenance.set_value(self._count(EN_MANTENIMIENTO))
        self.card_tests.set_value(en_curso)

        if desconocidos:
            listados = ", ".join(f"{nombre} ({cuantos})" for nombre, cuantos
                                 in sorted(desconocidos.items()))
            self.notice.setText(
                f"Valores en columnas de rig que no están en el catálogo: "
                f"{listados}. Agrégalos en Ajustes → Rigs y colores, o "
                f"corrígelos en el registro: esas piezas no aparecen "
                f"asignadas a ningún banco.")
            self.notice.setVisible(True)
        else:
            self.notice.setVisible(False)

        self._apply_filter()

    def cards(self, test_type: str | None = None) -> list[RigCard]:
        """Las tarjetas construidas, para consultarlas desde fuera."""
        if test_type is None:
            return list(self._cards)
        return [c for c in self._cards if c.rig.test_type == test_type]

    def _count(self, state: str) -> int:
        return sum(1 for c in self._cards if c.state == state)

    def _collect(self, registros: list[RigMaintenance] | None = None):
        """Que corre en cada rig, segun las pruebas en curso.

        El cruce lo hace ``app.services.rig_usage``, el mismo que usa el
        dashboard: cuando cada pantalla lo calculaba por su cuenta, una decia
        11 bancos ocupados y la otra 10.
        """
        fatigue = self.context.fatigue.list(ONGOING)
        rotary = self.context.rotary.list(ONGOING)
        ocupados, fuera = rig_usage.occupancy(
            fatigue, rotary, rig_usage.catalog_keys(self.context.catalogs.rigs()))

        # Los dias son de ensayo, no de calendario: se descuenta lo que la
        # prueba estuvo parada por mantenimiento. Es el mismo numero que
        # ensenia la bitacora, y tiene que serlo.
        historial = self.context.fatigue.list()
        detenidas = maintenance.stopped_by_test(historial, registros or [])

        # La antiguedad se calcula aparte porque cada bitacora tiene sus
        # propios umbrales: los de Fatiga salen del historial de Fatiga.
        umbrales = {
            "fatigue": duration.DurationThresholds.from_history(
                duration.history_durations(historial, detenidas)),
            "rotary": duration.DurationThresholds.from_history(
                duration.history_durations(self.context.rotary.list())),
        }

        ocupacion: dict[tuple[str, str], list] = {}
        for clave, ocupantes in ocupados.items():
            filas = []
            for ocupante in ocupantes:
                test = ocupante.test
                dias = duration.days_running(
                    test.start_date, stopped=detenidas.get(test.id, 0))
                filas.append((ocupante, dias, umbrales[clave[1]].level(dias)))
            # La prueba mas antigua primero: si la tarjeta corta la lista, lo
            # que se queda a la vista es lo que lleva mas tiempo ahi.
            filas.sort(key=lambda fila: fila[1] or 0, reverse=True)
            ocupacion[clave] = filas

        return ocupacion, fuera, len(fatigue) + len(rotary)

    # --- presentacion ------------------------------------------------------
    def _visible_cards(self) -> list[RigCard]:
        estado = self.state_filter.currentData()
        visibles = [c for c in self._cards
                    if estado is None or c.state == estado]
        if self.order.currentData() == POR_ANTIGUEDAD:
            visibles.sort(key=lambda c: c.urgency(), reverse=True)
        return visibles

    def _apply_filter(self) -> None:
        self._relayout(self._visible_cards())

    def _relayout(self, visibles: list[RigCard]) -> None:
        self._clear_groups()
        self.empty.setVisible(not visibles)
        self.area.setVisible(bool(visibles))
        if not visibles:
            return

        columnas = self._fit_columns()
        self._columns = columnas
        por_bitacora = self.order.currentData() != POR_ANTIGUEDAD

        if por_bitacora:
            grupos = [(TEST_TYPES[tipo], [c for c in visibles
                                          if c.rig.test_type == tipo])
                      for tipo in sorted(OCCUPIED_TEST_TYPES)]
        else:
            grupos = [(None, visibles)]

        for config, grupo in grupos:
            if not grupo:
                continue
            if config is not None:
                self.groups.addWidget(self._group_header(config, grupo))
            rejilla = QGridLayout()
            rejilla.setSpacing(CARD_SPACING)
            rejilla.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            for indice, tarjeta in enumerate(grupo):
                tarjeta.setParent(self.container)
                tarjeta.setVisible(True)
                rejilla.addWidget(tarjeta, indice // columnas,
                                  indice % columnas)
            rejilla.setColumnStretch(columnas, 1)
            self.groups.addLayout(rejilla)

    def _group_header(self, config, grupo: list[RigCard]) -> QWidget:
        caja = QWidget()
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(0, 4, 0, 0)
        fila.setSpacing(10)
        fila.addWidget(labels.eyebrow(config.label))
        en_uso = sum(1 for c in grupo if c.state == EN_USO)
        fila.addWidget(labels.muted(
            f"{en_uso} de {len(grupo)} en uso"))
        fila.addStretch(1)
        return caja

    def _fit_columns(self) -> int:
        ancho = max(self.area.viewport().width(), CARD_WIDTH)
        return max(1, (ancho + CARD_SPACING) // (CARD_WIDTH + CARD_SPACING))

    def eventFilter(self, obj, event) -> bool:
        """Recolocar las tarjetas cuando el area cambia de ancho.

        Se vigila el viewport del area y no la pagina: cuando la pagina recibe
        su resizeEvent, el area todavia no tiene su tamano final, asi que
        ``_fit_columns`` medía sobre un ancho provisional y la rejilla nacia con
        dos columnas teniendo sitio para cuatro.
        """
        from PySide6.QtCore import QEvent

        if (obj is self.area.viewport()
                and event.type() == QEvent.Type.Resize
                and self._cards
                and self._fit_columns() != self._columns):
            self._apply_filter()
        return super().eventFilter(obj, event)

    def _clear(self) -> None:
        self._clear_groups()
        for tarjeta in self._cards:
            tarjeta.setParent(None)
            tarjeta.deleteLater()
        self._cards = []

    def _clear_groups(self) -> None:
        while self.groups.count():
            item = self.groups.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
                continue
            rejilla = item.layout()
            if rejilla is None:
                continue
            while rejilla.count():
                hijo = rejilla.takeAt(0).widget()
                if hijo is not None:
                    # Las tarjetas no se destruyen: se reusan al refiltrar.
                    hijo.setParent(None)
            rejilla.deleteLater()

    # --- acciones ----------------------------------------------------------
    def open_record(self, record) -> None:
        """Abre la prueba que ocupa el banco, en el formulario de su bitacora."""
        from dialogs.fatigue import FatigueDialog
        from dialogs.rotary import RotaryDialog

        if isinstance(record, FatigueTest):
            abiertos = self.context.maintenance.open_records()
            detenidas = {
                slot: registro
                for (test_id, slot), registro
                in maintenance.paused_slots(abiertos).items()
                if test_id == record.id
            }
            dialogo = FatigueDialog(
                self.context.fatigue, self.context.catalogs,
                self.context.audit, test=record,
                read_only=record.is_finished, paused=detenidas,
                unavailable_rigs=maintenance.rigs_in_maintenance(abiertos),
                parent=self)
        elif isinstance(record, RotaryTest):
            dialogo = RotaryDialog(
                self.context.rotary, self.context.catalogs,
                self.context.audit, test=record,
                read_only=record.test_status == FINISHED, parent=self)
        else:                                  # pragma: no cover - solo esas dos
            return

        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def show_history(self) -> None:
        """Todos los periodos, del mas reciente al mas antiguo."""
        from dialogs.history import MaintenanceHistoryDialog

        MaintenanceHistoryDialog(
            maintenance.overlapping(self.context.maintenance.list()),
            title="Historial de mantenimiento de bancos", parent=self).exec()

    def toggle_maintenance(self, rig) -> None:
        """Pone el banco en mantenimiento, o lo devuelve al servicio."""
        abierto = maintenance.open_by_rig(
            self.context.maintenance.list(rig_name=rig.name,
                                          test_type=rig.test_type,
                                          open_only=True)
        ).get((rig.name, rig.test_type))

        if abierto is None:
            self._start_maintenance(rig)
        else:
            self._finish_maintenance(abierto)

    def _start_maintenance(self, rig) -> None:
        from dialogs.maintenance import StartMaintenanceDialog

        afectadas = maintenance.affected_samples(
            rig.name, rig.test_type, self.context.fatigue.list(ONGOING))
        dialogo = StartMaintenanceDialog(rig, afectadas, parent=self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self.context.maintenance.start(
                dialogo.maintenance(created_by=current_author()[0]),
                afectadas, current_author())
        except Exception as error:             # pragma: no cover - depende de red
            QMessageBox.critical(self, "No se pudo registrar el mantenimiento",
                                 str(error))
            return
        self.refresh()

    def _finish_maintenance(self, record: RigMaintenance) -> None:
        from dialogs.maintenance import FinishMaintenanceDialog

        dialogo = FinishMaintenanceDialog(record, parent=self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            repuestas = self.context.maintenance.finish(
                record.id, dialogo.end_date(), current_author(),
                restore=dialogo.restore())
        except Exception as error:             # pragma: no cover - depende de red
            QMessageBox.critical(self, "No se pudo cerrar el mantenimiento",
                                 str(error))
            return

        self.refresh()

        # Solo se avisa de lo que el usuario no puede ver en la tarjeta: que
        # piezas volvieron a su banco esta en la bitacora, no aqui.
        pendientes = len([s for s in record.samples if s.is_held])
        if pendientes and repuestas < pendientes:
            QMessageBox.information(
                self, "Mantenimiento cerrado",
                f"Se repusieron {repuestas} de {pendientes} piezas. Las demás "
                f"ya tenían otro banco asignado y se dejaron como estaban.")
