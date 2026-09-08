"""Tema visual.

Reproduce la paleta "superhero" de ttkbootstrap que usaba la version anterior,
para que la app no se sienta distinta despues de la migracion.
"""

from __future__ import annotations

BACKGROUND = "#2B3E50"
SURFACE = "#34495E"
SURFACE_ALT = "#3D566E"
BORDER = "#4A6785"
TEXT = "#EBEBEB"
TEXT_MUTED = "#A6B5C4"
# Mas apagado que TEXT_MUTED: ese se usa para texto secundario que si se lee,
# y un campo deshabilitado tiene que distinguirse de uno capturable.
TEXT_DISABLED = "#6C7D8F"

# --- colores de la tabla ------------------------------------------------
# Cada estado de fila tiene su color, y ninguno es PRIMARY. Antes el
# encabezado y la fila seleccionada eran el mismo #5DADE2 --el mismo valor,
# no dos parecidos-- asi que la seleccion no tenia identidad propia. Peor: al
# ser un azul claro, todo lo que va pintado encima se perdia. El semaforo de
# la columna Dias caia a 1.05:1 de contraste (invisible) y los once colores
# de rig del catalogo bajaban de 3:1.
#
# La seleccion se queda OSCURA: en un tema oscuro es lo unico que deja
# legible lo que lleva encima. Que se note no lo resuelve el relleno, sino la
# barra de acento que RecordTable pinta a la izquierda de la fila.
ROW = "#34495E"          # igual que SURFACE
ROW_ALT = "#43617E"      # franja alterna: dE 10.9 contra la fila (antes 5.7)
SELECTION = "#2C3E70"    # dE 20.1 contra la fila, dE 21.0 contra la alterna
HEADER_BG = "#223343"    # dE 10.1 contra la fila; PRIMARY encima da 5.26:1

PRIMARY = "#5DADE2"
INFO = "#6EC6FF"
WARNING = "#F0AD4E"
DANGER = "#F08080"
SUCCESS = "#58D68D"
SECONDARY = "#7B8A8B"

FONT_FAMILY = '"Roboto", "Segoe UI", sans-serif'

STYLESHEET = f"""
QWidget {{
    background-color: {BACKGROUND};
    color: {TEXT};
    font-family: {FONT_FAMILY};
    font-size: 12pt;
}}

QLabel[heading="true"] {{
    font-size: 22pt;
    font-weight: bold;
    color: {INFO};
    padding: 8px 0;
}}

QLabel[subheading="true"] {{
    font-size: 15pt;
    font-weight: bold;
    color: {TEXT};
    padding: 4px 0;
}}

QLabel[muted="true"] {{
    color: {TEXT_MUTED};
    font-size: 11pt;
}}

/* --- botones --------------------------------------------------------- */
QPushButton {{
    background-color: transparent;
    border: 2px solid {PRIMARY};
    border-radius: 6px;
    color: {PRIMARY};
    font-weight: bold;
    padding: 7px 18px;
}}
QPushButton:hover {{
    background-color: {PRIMARY};
    color: {BACKGROUND};
}}
QPushButton:pressed {{
    background-color: {BORDER};
    color: {TEXT};
}}
QPushButton:disabled {{
    border-color: {SECONDARY};
    color: {SECONDARY};
}}

QPushButton[accent="success"] {{ border-color: {SUCCESS}; color: {SUCCESS}; }}
QPushButton[accent="success"]:hover {{ background-color: {SUCCESS}; color: {BACKGROUND}; }}
QPushButton[accent="warning"] {{ border-color: {WARNING}; color: {WARNING}; }}
QPushButton[accent="warning"]:hover {{ background-color: {WARNING}; color: {BACKGROUND}; }}
QPushButton[accent="danger"] {{ border-color: {DANGER}; color: {DANGER}; }}
QPushButton[accent="danger"]:hover {{ background-color: {DANGER}; color: {BACKGROUND}; }}
QPushButton[accent="secondary"] {{ border-color: {SECONDARY}; color: {TEXT_MUTED}; }}
QPushButton[accent="secondary"]:hover {{ background-color: {SECONDARY}; color: {TEXT}; }}

/* El deshabilitado va DESPUES de los acentos. Un selector de atributo gana a
   una pseudoclase, asi que la regla QPushButton:disabled de arriba no llegaba
   a aplicarse sobre un boton con acento: se veia verde y activo aunque no
   respondiera al clic. */
QPushButton:disabled,
QPushButton[accent="success"]:disabled,
QPushButton[accent="warning"]:disabled,
QPushButton[accent="danger"]:disabled,
QPushButton[accent="secondary"]:disabled {{
    background-color: transparent;
    border-color: {BORDER};
    color: {TEXT_MUTED};
}}

/* --- campos ---------------------------------------------------------- */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QPlainTextEdit {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 5px 8px;
    color: {TEXT};
    selection-background-color: {PRIMARY};
    selection-color: {BACKGROUND};
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus {{
    border-color: {PRIMARY};
}}
QLineEdit:read-only {{
    background-color: {BACKGROUND};
    color: {TEXT_MUTED};
}}
/* Un campo apagado tiene que verse apagado. Las piezas por encima de las que
   declara la prueba se deshabilitan, y sin esto se veian igual que las
   capturables: mismo fondo, mismo texto, y solo el borde del recuadro
   cambiaba. */
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled,
QSpinBox:disabled, QPlainTextEdit:disabled {{
    background-color: {BACKGROUND};
    border-color: {SURFACE_ALT};
    color: {TEXT_DISABLED};
}}
/* No se da estilo a ::drop-down. Al hacerlo, Qt deja de dibujar la flecha
   salvo que se defina tambien ::down-arrow con una imagen, y los combos y los
   selectores de fecha quedaban con aspecto de simple caja de texto. */
QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    selection-background-color: {PRIMARY};
    selection-color: {BACKGROUND};
}}

/* --- tablas ---------------------------------------------------------- */
QTableView {{
    background-color: {ROW};
    alternate-background-color: {ROW_ALT};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {SELECTION};
    selection-color: {TEXT};
}}
/* El encabezado deja de ser un bloque macizo de PRIMARY. Con el relleno
   entero competia con todo lo demas de la pantalla, y ademas era el mismo
   color que la fila seleccionada. Ahora es fondo oscuro, rotulo en PRIMARY y
   una linea inferior que lo separa del cuerpo. */
QHeaderView::section {{
    background-color: {HEADER_BG};
    color: {PRIMARY};
    font-weight: bold;
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 2px solid {PRIMARY};
    padding: 8px 6px;
}}
QHeaderView::section:hover {{
    color: {INFO};
}}
QTableView::item {{ padding: 4px; }}

/* --- pestanas -------------------------------------------------------- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {SURFACE};
    color: {TEXT_MUTED};
    padding: 9px 22px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
}}
QTabBar::tab:selected {{
    background-color: {PRIMARY};
    color: {BACKGROUND};
}}

/* --- varios ---------------------------------------------------------- */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {INFO};
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {BACKGROUND};
    border: none;
}}
QScrollBar:vertical {{ width: 12px; }}
QScrollBar:horizontal {{ height: 12px; }}
QScrollBar::handle {{
    background: {BORDER};
    border-radius: 6px;
    min-height: 30px;
    min-width: 30px;
}}
QScrollBar::handle:hover {{ background: {PRIMARY}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QToolTip {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {PRIMARY};
    padding: 4px;
}}
"""


def apply(app) -> None:
    """Aplica el tema a la QApplication."""
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
