"""Catalogos en memoria.

Antes cada validacion y cada apertura de formulario hacia
``pd.read_excel("./excel_files/Auxiliar.xlsx")`` -- el archivo completo, para
leer una lista de 24 filas. Aqui se carga una vez y se refresca cuando cambia.

La capa de servicios no importa Qt a proposito: los interesados se registran
con :meth:`subscribe` y la UI conecta esa llamada a su propio refresco.
"""

from __future__ import annotations

from collections.abc import Callable

from app.db.repositories import CatalogRepository
from app.models import EMPTY_RIG, Customer, FailureMode, Requester, Rig

# Paleta de rigs. El color identifica al banco y a nadie mas: los resultados de
# pieza (Falla, S/Falla, Susp) no llevan color, se distinguen por la forma del
# chip.
#
# La anterior eran diez tonos frios "para dar familia visual", y esa idea tenia
# tres consecuencias medidas:
#
# 1. Diez colores para dieciseis rigs: cinco parejas compartian color, asi que
#    el chip no identificaba el banco. Ahora son dieciseis.
# 2. Su primer color era exactamente PRIMARY, el azul de la interfaz. Un chip
#    de ese banco se disolvia en la fila seleccionada.
# 3. Al ser todos azules y morados sobre un fondo azul oscuro, once de once
#    bajaban de 3:1 de contraste al seleccionar la fila.
#
# Estos se eligieron por muestreo del punto mas lejano en espacio Lab, con
# tres restricciones: contraste >= 3 sobre LOS TRES fondos que puede tener una
# fila (normal, franja alterna y seleccionada), dE >= 24 contra los colores de
# la interfaz (PRIMARY, INFO, el semaforo, el encabezado y los fondos) y
# dE >= 21 entre si.
#
# Lo de los tres fondos no es celo: la primera version se genero contra la
# fila normal y la seleccion, y al aclarar la franja alterna nueve de los
# dieciseis se quedaron por debajo de 3:1 justo en esa franja. Un chip tiene
# que leerse en cualquier fila donde caiga, no en la que se probo.
DEFAULT_PALETTE = (
    "#FAAA82", "#CCAD8F", "#FAE6AF", "#CCC26A",
    "#FAF173", "#E2FAA0", "#A4DB65", "#9DCC8F",
    "#73FA73", "#8FCCB8", "#73FAD6", "#6CDAEB",
    "#A0ACFA", "#DAA4EB", "#EC91FA", "#FAAFCF",
)


def color_for_index(index: int) -> str:
    return DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]


class CatalogService:
    """Cache de catalogos con notificacion de cambios."""

    def __init__(self, repository: CatalogRepository):
        self.repository = repository
        self._listeners: list[Callable[[], None]] = []

        self._customers: list[Customer] = []
        self._rigs: list[Rig] = []
        self._colors: dict[str, str] = {}
        self._codes: dict[str, list[str]] = {}
        self._statuses: list[str] = []
        self._failure_modes: list[str] = []
        self._requesters: list[str] = []
        self._loaded = False

    # --- ciclo de vida ---------------------------------------------------
    def load(self) -> None:
        self._customers = self.repository.customers()
        self._rigs = self.repository.rigs()
        self._colors = self.repository.rig_colors()
        self._codes = {
            test_type: self.repository.codes(test_type)
            for test_type in ("fatigue", "torsion", "rotary", "quasi")
        }
        self._statuses = self.repository.status_labels()
        self._failure_modes = self.repository.failure_mode_labels()
        self._requesters = self.repository.requester_names()
        self._loaded = True

    def reload(self) -> None:
        """Recarga y avisa a quien este mostrando datos derivados."""
        self.load()
        self._notify()

    def _ensure(self) -> None:
        if not self._loaded:
            self.load()

    # --- observadores ----------------------------------------------------
    def subscribe(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            callback()

    # --- consultas -------------------------------------------------------
    def customer_names(self) -> list[str]:
        self._ensure()
        return [c.name for c in self._customers]

    def rigs(self, test_type: str | None = None) -> list[Rig]:
        self._ensure()
        if test_type is None:
            return list(self._rigs)
        return [r for r in self._rigs if r.test_type == test_type]

    def rig_names(self, test_type: str) -> list[str]:
        return [r.name for r in self.rigs(test_type)]

    def codes(self, test_type: str) -> list[str]:
        self._ensure()
        return list(self._codes.get(test_type, []))

    def sample_statuses(self) -> list[str]:
        self._ensure()
        return list(self._statuses)

    def failure_modes(self) -> list[str]:
        """Modos de falla activos, en el orden en que se ofrecen al capturar."""
        self._ensure()
        return list(self._failure_modes)

    def requesters(self) -> list[str]:
        """Personas que pueden solicitar una prueba en una Work Order."""
        self._ensure()
        return list(self._requesters)

    # --- colores ---------------------------------------------------------
    def color(self, rig_name: str | None) -> str | None:
        """Color asignado a un rig, o None si no aplica pintarlo."""
        self._ensure()
        if not rig_name or rig_name == EMPTY_RIG:
            return None
        return self._colors.get(rig_name)

    def colors(self) -> dict[str, str]:
        self._ensure()
        return dict(self._colors)

    def set_color(self, rig: Rig, color: str) -> None:
        if rig.id is None:
            raise ValueError("El rig debe estar guardado antes de asignarle color")
        self.repository.set_rig_color(rig.id, color)
        self.reload()

    # --- escritura -------------------------------------------------------
    def save_rig(self, rig: Rig) -> None:
        self.repository.save_rig(rig)
        self.reload()

    def save_customer(self, customer: Customer) -> None:
        self.repository.save_customer(customer)
        self.reload()

    def add_code(self, code: str, test_type: str) -> None:
        self.repository.add_code(code, test_type)
        self.reload()

    def remove_code(self, code_id: int) -> None:
        self.repository.remove_code(code_id)
        self.reload()

    def save_failure_mode(self, mode: FailureMode) -> None:
        self.repository.save_failure_mode(mode)
        self.reload()

    def remove_failure_mode(self, mode_id: int) -> None:
        self.repository.remove_failure_mode(mode_id)
        self.reload()

    def save_requester(self, requester: Requester) -> None:
        self.repository.save_requester(requester)
        self.reload()

    def remove_requester(self, requester_id: int) -> None:
        self.repository.remove_requester(requester_id)
        self.reload()


def contrasting_text_color(background: str) -> str:
    """Negro o blanco, el que se lea mejor sobre ``background``.

    Necesario porque los colores de rig los elige el usuario y no se puede
    asumir que el fondo sea claro u oscuro.
    """
    value = background.lstrip("#")
    if len(value) != 6:
        return "#000000"

    try:
        red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#000000"

    # Luminancia relativa aproximada (ITU-R BT.601).
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return "#000000" if luminance > 0.6 else "#FFFFFF"
