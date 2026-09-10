"""Ocupacion de rigs: que banco esta libre y que corre en cada uno.

Responder "que rig esta libre" exigia leer nueve columnas de rig en todas las
filas de la bitacora. Aqui cada banco del catalogo es una tarjeta con su color,
lo que corre en el y desde cuando.

La pantalla se lee **por estado**, y por eso las tres cosas que la ordenan son:

1. Cada tarjeta dice su estado en el mismo sitio y con el mismo color -- libre,
   en uso o en mantenimiento -- para que se recorra la rejilla sin leer.
2. Los bancos van **agrupados por bitacora**, con su encabezado y su recuento.
   Antes venian seguidos en orden de catalogo y una fila cualquiera mezclaba
   dos ensayos distintos sin nada que lo dijera: la tercera fila llevaba dos
   rigs de Fatiga y dos de Quasi.
3. Las columnas salen del ancho disponible, no de un numero fijo.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import dates
from app.context import AppContext
from app.models import (
    FINISHED,
    MAINTAINED_TEST_TYPES,
    ONGOING,
    TEST_TYPES,
    FatigueTest,
    RigMaintenance,
    RotaryTest,
)
from app.services import duration, maintenance, rig_usage
from app.services.catalogs import contrasting_text_color
from app.services.identity import current_author
from app.ui import theme
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.dialogs.maintenance_history_dialog import (
    MaintenanceHistoryDialog,
)
from app.ui.dialogs.maintenance_dialog import (
    FinishMaintenanceDialog,
    StartMaintenanceDialog,
)
from app.ui.dialogs.rotary_dialog import RotaryDialog
from app.ui.pages.base_page import BasePage
from app.ui.widgets.common import StatCard

CARD_WIDTH = 240
CARD_SPACING = 10

# Cuantas pruebas se enumeran dentro de una tarjeta. En la practica un banco
# lleva una pieza, dos como mucho; el corte esta por los registros que se
# quedaron abiertos sin cerrar, que llegaron a apilar doce pruebas en el mismo
# rig de Rotary y estiraban su tarjeta a 480 px -- tres veces las demas, con
# sus tres vecinas de fila en blanco.
MAX_OCCUPANTS = 3

# --- estados de un banco --------------------------------------------------
LIBRE = "Libre"
EN_USO = "En uso"
EN_MANTENIMIENTO = "En mantenimiento"

STATE_COLORS = {
    LIBRE: theme.SUCCESS,
    EN_USO: theme.TEXT,
    EN_MANTENIMIENTO: theme.MAINTENANCE,
}

# (rotulo, estado que deja pasar). El estado viaja en el dato del elemento y no
# en su texto: asi el rotulo se puede acortar sin que el filtro deje de
# funcionar, que es justo lo que hizo falta -- 'En mantenimiento' escrito entero
# le ponia 292 px de minimo al combo.
FILTERS = (
    ("Todos", None),
    ("Libres", LIBRE),
    ("En uso", EN_USO),
    ("Mantenimiento", EN_MANTENIMIENTO),
)

POR_NOMBRE = "nombre"
POR_ANTIGUEDAD = "antiguedad"
ORDERS = (
    ("Por nombre", POR_NOMBRE),
    ("Por antigüedad", POR_ANTIGUEDAD),
)


def _muted(text: str, size: int = 9) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(
        f"color: {theme.TEXT_MUTED}; font-size: {size}pt; border: none;"
    )
    return label


def _plural_estado(estado: str, cuantos: int) -> str:
    """'3 libres', pero '3 en uso'. Solo el adjetivo concuerda."""
    if estado == LIBRE:
        return "libre" + ("s" if cuantos != 1 else "")
    return estado.lower()


def _dias(cuantos: int) -> str:
    """'1 dia' / 'N dias'. Lo escribe el usuario, asi que concuerda."""
    return "1 día" if cuantos == 1 else f"{cuantos} días"


def _piezas(cuantas: int) -> str:
    return f"{cuantas} pieza detenida" if cuantas == 1 \
        else f"{cuantas} piezas detenidas"


def _days_ago(when: date | None, reference: date | None = None) -> str:
    """'hoy' / 'ayer' / 'hace N dias'. Un numero suelto no dice de que es."""
    if when is None:
        return ""
    dias = ((reference or date.today()) - when).days
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "ayer"
    return f"hace {_dias(dias)}"


class CardsContainer(QWidget):
    """Lienzo de las tarjetas, que no le pone suelo de ancho a la ventana.

    Las tarjetas llevan ancho fijo --es lo que las mantiene iguales-- y el
    layout convierte la suma de ese ancho en el minimo del contenedor: la
    pantalla ya no podia encoger por debajo de una fila entera, y al estrechar
    la ventana el reparto de columnas no bajaba nunca. Es el mismo tropiezo que
    la franja de la leyenda, y se corrige igual: ``SetNoConstraint`` **y**
    ``minimumSizeHint`` con ancho cero; con una sola de las dos no basta.
    """

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(0)
        return hint


class ClickableRow(QWidget):
    """Fila que responde al clic. Para abrir la prueba que ocupa el banco."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class RigCard(QFrame):
    """Un banco de pruebas: su estado, lo que corre en el y desde cuando."""

    # La prueba que ocupa el banco, al pulsar su renglon.
    opened = Signal(object)
    # El banco entra o sale de mantenimiento desde su propia tarjeta: hacerlo
    # desde una barra de arriba obligaria a inventar una seleccion que esta
    # pantalla no tiene, y a mirar dos sitios para saber sobre cual se actua.
    maintenanceRequested = Signal(object)

    def __init__(self, rig, occupants: list,
                 maintenance: RigMaintenance | None = None,
                 downtime: int = 0, free_since: date | None = None,
                 parent=None):
        super().__init__(parent)
        self.rig = rig
        self.occupants = occupants
        self.maintenance = maintenance
        self.downtime = downtime
        self.free_since = free_since

        if maintenance is not None:
            self.state = EN_MANTENIMIENTO
        elif occupants:
            self.state = EN_USO
        else:
            self.state = LIBRE

        self.setFixedWidth(CARD_WIDTH)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        # Un banco parado se marca en rojo aunque tenga piezas anotadas: lo
        # primero que hay que saber de el es que no esta trabajando. Manda
        # sobre el color del propio rig, que solo dice cual es.
        borde = {
            EN_MANTENIMIENTO: theme.MAINTENANCE,
            EN_USO: rig.color,
            LIBRE: theme.BORDER,
        }[self.state]
        self.setStyleSheet(
            f"QFrame {{ background-color: {theme.SURFACE};"
            f" border: 2px solid {borde}; border-radius: 8px; }}"
        )

        # El tipo de ensayo ya lo dice el encabezado de su grupo, y los dias
        # fuera de servicio acumulados son un dato de consulta, no de vistazo:
        # los dos van al tooltip, que no gasta alto de tarjeta.
        resumen = [TEST_TYPES[rig.test_type].label]
        if downtime:
            resumen.append(f"{_dias(downtime)} fuera de servicio en total")
        self.setToolTip("  ·  ".join(resumen))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # --- encabezado con el color del rig ------------------------------
        header = QLabel(rig.name)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(
            f"background-color: {rig.color};"
            f" color: {contrasting_text_color(rig.color)};"
            f" border: none; border-radius: 4px;"
            f" font-weight: bold; font-size: 12pt; padding: 4px;"
        )
        layout.addWidget(header)

        # --- el estado, siempre en el mismo sitio -------------------------
        # Antes solo lo decia la tarjeta libre ('Libre' en verde) y las demas
        # habia que deducirlas de lo que llevaban dentro. Con la palabra en el
        # mismo renglon de todas las tarjetas, la rejilla se recorre de un
        # vistazo sin leer ninguna.
        estado = QLabel(self.state)
        estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        estado.setStyleSheet(
            f"color: {STATE_COLORS[self.state]}; font-size: 11pt;"
            f" font-weight: bold; border: none;"
        )
        layout.addWidget(estado)

        if self.state == LIBRE:
            layout.addWidget(self._free_note())
        elif self.state == EN_MANTENIMIENTO:
            layout.addWidget(self._maintenance_note(maintenance))

        for record, days, level in occupants[:MAX_OCCUPANTS]:
            layout.addWidget(self._occupant(record, days, level))

        sobran = len(occupants) - MAX_OCCUPANTS
        if sobran > 0:
            resto = _muted(f"y {sobran} prueba más" if sobran == 1
                           else f"y {sobran} pruebas más")
            resto.setToolTip("\n".join(
                f"{r.test_batch}  ·  {r.customer}"
                for r, _, _ in occupants[MAX_OCCUPANTS:]
            ))
            layout.addWidget(resto)

        layout.addStretch(1)
        # Solo los bancos de Fatiga llevan el boton: es donde el banco es de
        # cada pieza y sacarla de ahi significa algo. En Rotary el banco es de
        # la prueba entera y pararlo la suspenderia completa, que es otra
        # decision y todavia no esta tomada.
        if rig.test_type in MAINTAINED_TEST_TYPES:
            layout.addWidget(self._maintenance_button(maintenance))

    # --- piezas de la tarjeta --------------------------------------------
    def _free_note(self) -> QLabel:
        """Desde cuando esta libre. 'Libre' a secas no distingue el banco que
        se desocupo ayer del que lleva dos meses sin usarse."""
        if self.free_since is None:
            nota = _muted("sin pruebas anteriores")
            nota.setToolTip("Ninguna prueba cerrada registra este banco")
            return nota
        nota = _muted(f"desde {_days_ago(self.free_since)}")
        nota.setToolTip(
            f"La última prueba en este banco terminó el "
            f"{dates.display(self.free_since)}"
        )
        return nota

    def _maintenance_note(self, record: RigMaintenance) -> QWidget:
        """Desde cuando esta parado el banco y por que."""
        note = QWidget()
        note.setStyleSheet("border: none;")
        box = QVBoxLayout(note)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(1)

        dias = record.days()
        detalle = f"desde el {dates.display(record.start_date)}"
        if dias:
            detalle += f"  ·  {_dias(dias)}"
        box.addWidget(_muted(detalle))

        if record.reason:
            motivo = QLabel(record.reason)
            motivo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            motivo.setWordWrap(True)
            motivo.setStyleSheet(
                f"color: {theme.TEXT}; font-size: 9pt; border: none;"
            )
            box.addWidget(motivo)

        paradas = [s for s in record.samples if not s.restored]
        if paradas:
            piezas = _muted(_piezas(len(paradas)))
            piezas.setToolTip("\n".join(
                f"{s.test_batch or f'#{s.record_id}'}  ·  pieza {s.slot}"
                for s in paradas
            ))
            box.addWidget(piezas)

        return note

    def _occupant(self, record, days: int | None, level: str) -> QWidget:
        """La prueba que corre en el banco. Se pulsa para abrirla."""
        colors = {
            duration.OK: theme.TEXT,
            duration.WARNING: theme.WARNING,
            duration.CRITICAL: theme.DANGER,
        }

        row = ClickableRow()
        row.setStyleSheet("border: none;")
        row.setToolTip(f"Abrir el registro de {record.test_batch}")
        row.clicked.connect(lambda r=record: self.opened.emit(r))

        box = QVBoxLayout(row)
        box.setContentsMargins(0, 2, 0, 2)
        box.setSpacing(1)

        batch = QLabel(record.test_batch)
        batch.setStyleSheet(
            f"color: {theme.PRIMARY}; font-size: 11pt; border: none;"
        )
        box.addWidget(batch)

        detail = QLabel(
            f"{record.customer}  ·  {_dias(days)}" if days is not None
            else record.customer
        )
        detail.setStyleSheet(
            f"color: {colors[level]}; font-size: 9pt; border: none;"
        )
        box.addWidget(detail)
        return row

    def _maintenance_button(self, record: RigMaintenance | None) -> QPushButton:
        button = QPushButton(
            "Terminar mantenimiento" if record else "Poner en mantenimiento"
        )
        button.setProperty("accent", "success" if record else "maintenance")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        # A los 12 pt de la app el rotulo no cabe en los 240 px de la tarjeta y
        # Qt lo recorta por los dos lados en vez de acortarlo: se leia "'oner
        # en mantenimient". Con 10 pt entra entero, que es lo que importa en un
        # boton que cambia de texto segun el estado del banco.
        button.setStyleSheet("font-size: 10pt; padding: 6px 8px;")
        button.clicked.connect(
            lambda _=False, rig=self.rig: self.maintenanceRequested.emit(rig)
        )
        return button

    # --- para ordenar -----------------------------------------------------
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


class RigsPage(BasePage):
    def __init__(self, context: AppContext, parent=None):
        super().__init__("Ocupación de rigs", parent)
        self.context = context
        self._cards: list[RigCard] = []
        self._columns = 0

        header = QHBoxLayout()
        # Los tres estados de un banco comparten familia y cada uno lleva su
        # color; 'Pruebas en curso' es otra cosa --cuenta pruebas, no bancos--
        # y va en el color del texto para que no parezca un cuarto estado.
        self.card_busy = StatCard("Rigs en uso", "0", theme.INFO)
        self.card_free = StatCard("Rigs libres", "0", theme.SUCCESS)
        self.card_maintenance = StatCard("En mantenimiento", "0",
                                         theme.MAINTENANCE)
        self.card_tests = StatCard("Pruebas en curso", "0", theme.TEXT)
        for card in (self.card_busy, self.card_free, self.card_maintenance,
                     self.card_tests):
            header.addWidget(card)
        header.addStretch(1)
        self.content.addLayout(header)

        # Los controles van en su propia fila y no junto a las tarjetas de
        # arriba: los dos combos pedian 552 px entre los dos, y sumados a las
        # cuatro tarjetas le ponian a la pantalla un minimo de 1,846 px de
        # ancho. Una pantalla no puede exigir mas ancho del que tiene el
        # escritorio de un portatil.
        controles = QHBoxLayout()
        controles.addStretch(1)

        controles.addWidget(QLabel("Mostrar"))
        self.state_filter = QComboBox()
        for rotulo, estado in FILTERS:
            self.state_filter.addItem(rotulo, estado)
        self.state_filter.currentIndexChanged.connect(self._apply_filter)
        controles.addWidget(self.state_filter)

        controles.addSpacing(12)
        controles.addWidget(QLabel("Orden"))
        self.order = QComboBox()
        for rotulo, criterio in ORDERS:
            self.order.addItem(rotulo, criterio)
        self.order.currentIndexChanged.connect(self._apply_filter)
        controles.addWidget(self.order)

        controles.addSpacing(12)
        # El historial de mantenimiento tambien se consulta desde aqui, que es
        # donde se captura. Sin esto solo se veia el periodo abierto, en la
        # tarjeta de su banco: los cerrados no aparecian en ninguna pantalla.
        historial = QPushButton("Historial")
        historial.setProperty("accent", "secondary")
        historial.setToolTip(
            "Periodos de mantenimiento de todos los bancos: cuándo, "
            "cuánto duraron y por qué"
        )
        historial.clicked.connect(self.show_history)
        controles.addWidget(historial)

        controles.addSpacing(12)
        refresh = QPushButton("Actualizar")
        refresh.clicked.connect(self.refresh)
        controles.addWidget(refresh)
        self.content.addLayout(controles)

        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet(f"color: {theme.WARNING}; font-size: 10pt;")
        self.notice.setVisible(False)
        self.content.addWidget(self.notice)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.Shape.NoFrame)
        self.container = CardsContainer()
        self.groups = QVBoxLayout(self.container)
        self.groups.setSpacing(14)
        self.groups.setContentsMargins(0, 0, 0, 0)
        self.groups.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.groups.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.area.setWidget(self.container)
        self.content.addWidget(self.area, 1)

        # Cuando el filtro no deja ningun banco. Sin esto la pantalla se queda
        # en blanco, que se confunde con que la app fallo.
        self.empty = QLabel("Ningún banco coincide con el filtro")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 13pt; padding: 30px;"
        )
        self.empty.setVisible(False)
        self.content.addWidget(self.empty)

    # --- datos -----------------------------------------------------------
    def refresh(self) -> None:
        # Mantenimiento primero: los dias que se ensenian en cada tarjeta van
        # sin el tiempo que la prueba estuvo detenida, igual que en la
        # bitacora, y eso lo necesita ya el cruce de ocupacion.
        registros = self.context.maintenance.list()
        occupancy, unknown, ongoing_count = self._collect(registros)

        parados = maintenance.open_by_rig(registros)
        fuera = maintenance.downtime_by_rig(registros)
        # Historico completo, sin rango de fechas: la pregunta es desde cuando
        # esta libre este banco, no que hizo en un periodo.
        desocupados = rig_usage.last_used(
            self.context.fatigue.list(),
            self.context.rotary.list(),
            {"torsion": self.context.torsion.list(),
             "quasi": self.context.quasi.list()},
        )

        self._clear()
        for rig in self.context.catalogs.rigs():
            key = (rig.name, rig.test_type)
            card = RigCard(
                rig, occupancy.get(key, []),
                maintenance=parados.get(key),
                downtime=fuera.get(key, 0),
                free_since=desocupados.get(key),
            )
            card.maintenanceRequested.connect(self.toggle_maintenance)
            card.opened.connect(self.open_record)
            self._cards.append(card)

        self.card_busy.set_value(self._count(EN_USO))
        self.card_free.set_value(self._count(LIBRE))
        self.card_maintenance.set_value(self._count(EN_MANTENIMIENTO))
        self.card_tests.set_value(ongoing_count)

        if unknown:
            listed = ", ".join(
                f"{name} ({count})" for name, count in sorted(unknown.items())
            )
            # Hasta la migracion 008 esto se llenaba de 'Falla' y 'S/Falla':
            # eran resultados capturados en el campo de banco. Ya no. Lo que
            # aparezca aqui ahora es un banco de verdad que falta del catalogo.
            self.notice.setText(
                f"Valores en columnas de rig que no están en el catálogo: "
                f"{listed}. Agrégalos en Ajustes -> Rigs y colores, o "
                f"corrígelos en el registro: esas piezas no aparecen "
                f"asignadas a ningún banco."
            )
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

        El cruce lo hace ``app.services.rig_usage``, que es el mismo que usa la
        tarjeta del dashboard: cuando cada pantalla lo calculaba por su cuenta,
        una decia 11 bancos ocupados y la otra 10.
        """
        fatigue = self.context.fatigue.list(ONGOING)
        rotary = self.context.rotary.list(ONGOING)
        ocupados, fuera = rig_usage.occupancy(
            fatigue, rotary,
            rig_usage.catalog_keys(self.context.catalogs.rigs()),
        )

        # Los dias son de ensayo, no de calendario: se descuenta lo que la
        # prueba estuvo parada por mantenimiento del banco. Es el mismo numero
        # que ensenia la bitacora, y tiene que serlo -- dos pantallas dando
        # dias distintos de la misma prueba ya paso una vez con la ocupacion.
        historial = self.context.fatigue.list()
        detenidas = maintenance.stopped_by_test(historial, registros or [])

        # La antiguedad se calcula aparte porque cada bitacora tiene sus
        # propios umbrales: los de Fatiga salen del historial de Fatiga.
        umbrales = {
            "fatigue": duration.DurationThresholds.from_history(
                duration.history_durations(historial, detenidas)
            ),
            "rotary": duration.DurationThresholds.from_history(
                duration.history_durations(self.context.rotary.list())
            ),
        }

        occupancy: dict[tuple[str, str], list] = {}
        for (nombre, tipo), pruebas in ocupados.items():
            filas = []
            for test in pruebas:
                days = duration.days_running(
                    test.start_date, stopped=detenidas.get(test.id, 0)
                )
                filas.append((test, days, umbrales[tipo].level(days)))
            # La prueba mas antigua primero: si la tarjeta corta la lista, lo
            # que se queda a la vista es lo que lleva mas tiempo ahi.
            filas.sort(key=lambda fila: fila[1] or 0, reverse=True)
            occupancy[(nombre, tipo)] = filas

        return occupancy, fuera, len(fatigue) + len(rotary)

    # --- presentacion ----------------------------------------------------
    def _visible_cards(self) -> list[RigCard]:
        estado = self.state_filter.currentData()
        visibles = [c for c in self._cards
                    if estado is None or c.state == estado]

        if self.order.currentData() == POR_ANTIGUEDAD:
            visibles.sort(key=lambda c: c.urgency(), reverse=True)
        return visibles

    def _apply_filter(self) -> None:
        self._columns = 0          # fuerza el reparto con el ancho de ahora
        self._relayout()

    def _relayout(self) -> None:
        """Coloca las tarjetas por bitacora, con las columnas que quepan."""
        columnas = self._fit_columns()
        ancho = self._card_width(columnas)
        visibles = self._visible_cards()

        self._clear_groups()
        self.empty.setVisible(not visibles)
        self.area.setVisible(bool(visibles))
        if not visibles:
            return

        for clave, config in TEST_TYPES.items():
            grupo = [c for c in visibles if c.rig.test_type == clave]
            if not grupo:
                continue
            self.groups.addWidget(self._group_header(config, grupo))

            rejilla = QGridLayout()
            rejilla.setSpacing(CARD_SPACING)
            rejilla.setContentsMargins(0, 0, 0, 0)
            rejilla.setAlignment(Qt.AlignmentFlag.AlignLeft)
            for indice, card in enumerate(grupo):
                card.setParent(None)
                card.setFixedWidth(ancho)
                rejilla.addWidget(card, indice // columnas, indice % columnas)
            self.groups.addLayout(rejilla)

        self._columns = columnas

    def _group_header(self, config, grupo: list[RigCard]) -> QWidget:
        """Titulo de la bitacora con el reparto de sus bancos."""
        fila = QWidget()
        caja = QHBoxLayout(fila)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(10)

        titulo = QLabel(config.label)
        titulo.setStyleSheet(
            f"color: {config.accent}; font-size: 13pt; font-weight: bold;"
        )
        caja.addWidget(titulo)

        partes = [f"{len(grupo)} banco" + ("s" if len(grupo) != 1 else "")]
        for estado in (EN_USO, LIBRE, EN_MANTENIMIENTO):
            cuantos = sum(1 for c in grupo if c.state == estado)
            if cuantos:
                partes.append(f"{cuantos} {_plural_estado(estado, cuantos)}")
        resumen = QLabel("  ·  ".join(partes))
        resumen.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 10pt;"
        )
        caja.addWidget(resumen)
        caja.addStretch(1)
        return fila

    def _available_width(self) -> int:
        """Ancho util de la rejilla, reservando siempre la barra de scroll.

        Se descuenta este o no visible a proposito. Si se midiera el hueco real,
        el reparto se perseguiria la cola: tarjetas mas anchas -> mas alto ->
        aparece la barra -> el hueco encoge -> las tarjetas ya no caben.
        """
        barra = self.area.verticalScrollBar().sizeHint().width()
        visible = self.area.verticalScrollBar().isVisible()
        return self.area.viewport().width() - (0 if visible else barra)

    def _fit_columns(self) -> int:
        """Cuantas tarjetas caben a lo ancho.

        Eran cuatro fijas, midieran lo que midieran la ventana y la tarjeta:
        en una ventana ancha sobraba sitio sin usar y en una estrecha se salian.
        """
        ancho = self._available_width()
        return max(1, (ancho + CARD_SPACING) // (CARD_WIDTH + CARD_SPACING))

    def _card_width(self, columnas: int) -> int:
        """Lo que sobra se reparte entre las tarjetas, no se deja en blanco.

        Con 240 px fijos y cinco columnas quedaban 230 px muertos a la derecha
        de la rejilla, y dentro de la tarjeta el boton de mantenimiento iba tan
        justo que hubo que bajarle la letra a 10 pt para que no se recortara.
        """
        libre = self._available_width() - CARD_SPACING * (columnas - 1)
        return max(CARD_WIDTH, libre // columnas)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Solo se reordena si cambia el numero de columnas: mover dieciseis
        # tarjetas en cada pixel de arrastre hace parpadear la pantalla.
        if self._cards and self._fit_columns() != self._columns:
            self._relayout()

    def _clear(self) -> None:
        self._clear_groups()
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []

    def _clear_groups(self) -> None:
        """Vacia la pila de grupos sin destruir las tarjetas.

        Las tarjetas se reutilizan al filtrar y al cambiar de columnas: se
        sacan del layout, no se borran. Solo ``_clear`` las destruye.
        """
        while self.groups.count():
            item = self.groups.takeAt(0)
            widget = item.widget()
            if isinstance(widget, RigCard):
                widget.setParent(None)
                continue
            if widget is not None:
                widget.deleteLater()
                continue
            rejilla = item.layout()
            if rejilla is None:
                continue
            while rejilla.count():
                hijo = rejilla.takeAt(0).widget()
                if hijo is not None:
                    hijo.setParent(None)
            rejilla.deleteLater()

    # --- acciones --------------------------------------------------------
    def open_record(self, record) -> None:
        """Abre la prueba que ocupa el banco, en el formulario de su bitacora.

        La tarjeta ensenia el Test Batch y el gesto natural es pulsarlo; hasta
        ahora no pasaba nada y habia que ir a la bitacora a buscarlo.
        """
        if isinstance(record, FatigueTest):
            dialog = FatigueDialog(
                self.context.fatigue, self.context.catalogs,
                self.context.audit, test=record,
                read_only=record.is_finished, parent=self,
            )
        elif isinstance(record, RotaryTest):
            dialog = RotaryDialog(
                self.context.rotary, self.context.catalogs, self.context.audit,
                test=record, read_only=record.test_status == FINISHED,
                parent=self,
            )
        else:                                  # pragma: no cover - solo esas dos
            return

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def show_history(self) -> None:
        """Todos los periodos, del mas reciente al mas antiguo."""
        MaintenanceHistoryDialog(
            maintenance.overlapping(self.context.maintenance.list()),
            title="Historial de mantenimiento de bancos", parent=self,
        ).exec()

    def toggle_maintenance(self, rig) -> None:
        """Pone el banco en mantenimiento, o lo devuelve al servicio."""
        abierto = maintenance.open_by_rig(
            self.context.maintenance.list(
                rig_name=rig.name, test_type=rig.test_type, open_only=True
            )
        ).get((rig.name, rig.test_type))

        if abierto is None:
            self._start_maintenance(rig)
        else:
            self._finish_maintenance(abierto)

    def _start_maintenance(self, rig) -> None:
        afectadas = maintenance.affected_samples(
            rig.name, rig.test_type, self.context.fatigue.list(ONGOING)
        )
        dialog = StartMaintenanceDialog(rig, afectadas, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self.context.maintenance.start(
                dialog.maintenance(created_by=current_author()[0]),
                afectadas,
                current_author(),
            )
        except Exception as error:             # pragma: no cover - depende de red
            QMessageBox.critical(
                self, "No se pudo registrar el mantenimiento", str(error)
            )
            return

        self.refresh()

    def _finish_maintenance(self, record: RigMaintenance) -> None:
        dialog = FinishMaintenanceDialog(record, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            repuestas = self.context.maintenance.finish(
                record.id, dialog.end_date(), current_author(),
                restore=dialog.restore(),
            )
        except Exception as error:             # pragma: no cover - depende de red
            QMessageBox.critical(
                self, "No se pudo cerrar el mantenimiento", str(error)
            )
            return

        self.refresh()

        # Solo se avisa de lo que el usuario no puede ver en la tarjeta: que
        # piezas volvieron a su banco esta en la bitacora, no aqui.
        pendientes = len([s for s in record.samples if not s.restored])
        if pendientes and repuestas < pendientes:
            QMessageBox.information(
                self, "Mantenimiento cerrado",
                f"Se repusieron {repuestas} de {pendientes} piezas. Las demás "
                f"ya tenían otro banco asignado y se dejaron como estaban.",
            )
