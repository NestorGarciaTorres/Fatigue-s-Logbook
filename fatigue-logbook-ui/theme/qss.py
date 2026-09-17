"""La hoja de estilos, construida a partir de una paleta y un tamano de letra.

Todo lo visual de la app sale de aqui. **Ningun widget lleva su propio
``setStyleSheet``**, y no es una preferencia de estilo: un estilo inline se
ejecuta una sola vez, al construir el widget, asi que el color queda congelado
ahi y un cambio de tema no lo alcanza nunca. El proyecto anterior tenia 49 de
esos repartidos en once archivos, y es la razon por la que su tema no se podia
conmutar. Lo que cambia entre widgets se expresa con propiedades
(``setProperty``), que se declaran abajo como selectores de atributo.

Los tamanos se derivan del base, nunca se escriben fijos: subir la letra en
Ajustes tiene que mover toda la jerarquia en proporcion, no dejar el titulo
donde estaba.

Qt no soporta ``box-shadow`` en QSS. La elevacion de tarjetas y dialogos se
dibuja con ``QGraphicsDropShadowEffect`` desde ``components/elevation.py``; lo
que se hace aqui es el resto (fondo, radio y borde sutil).
"""

from __future__ import annotations

from theme.tokens import Palette

BASE_FONT_PT = 12
MIN_FONT_PT = 10
MAX_FONT_PT = 15

# Radios. Uno chico para controles y uno grande para superficies: mezclar
# radios al azar es lo que hace que una interfaz parezca ensamblada y no
# disenada.
RADIUS_CONTROL = 8
RADIUS_SURFACE = 12


def clamp_font(size) -> int:
    """El tamano pedido, dentro de lo que la app puede dibujar."""
    try:
        valor = int(size)
    except (TypeError, ValueError):
        return BASE_FONT_PT
    return max(MIN_FONT_PT, min(MAX_FONT_PT, valor))


def scale(base: int) -> dict[str, int]:
    """Los tamanos de letra derivados del base, en puntos."""
    factor = base / BASE_FONT_PT
    return {
        "base": base,
        "display": round(30 * factor),
        "heading": round(21 * factor),
        "subheading": round(15 * factor),
        "small": round(11 * factor),
        "tiny": round(10 * factor),
        "metric": round(26 * factor),
    }


def build(palette: Palette, font_pt: int = BASE_FONT_PT) -> str:
    """La hoja completa para esa paleta y ese tamano de letra."""
    p = palette
    pt = scale(clamp_font(font_pt))

    return f"""
/* ==================================================================
   Base
   ================================================================== */
QWidget {{
    background-color: {p.bg};
    color: {p.text};
    font-family: "Inter", "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: {pt['base']}pt;
}}

QMainWindow, QDialog {{
    background-color: {p.bg};
}}

/* Un QLabel hereda el fondo del padre y sobre una tarjeta eso se ve como un
   recuadro de otro color detras del texto. Se pintan transparentes y quien
   necesite fondo lo pide por propiedad. */
QLabel {{
    background: transparent;
}}

/* ==================================================================
   Tipografia
   ================================================================== */
QLabel[role="display"] {{
    font-size: {pt['display']}pt;
    font-weight: 700;
    color: {p.text};
}}
QLabel[role="heading"] {{
    font-size: {pt['heading']}pt;
    font-weight: 700;
    color: {p.text};
}}
QLabel[role="subheading"] {{
    font-size: {pt['subheading']}pt;
    font-weight: 600;
    color: {p.text};
}}
QLabel[role="secondary"] {{
    color: {p.text_secondary};
}}
QLabel[role="muted"] {{
    color: {p.text_muted};
    font-size: {pt['small']}pt;
}}
QLabel[role="eyebrow"] {{
    color: {p.text_muted};
    font-size: {pt['tiny']}pt;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel[role="metric"] {{
    font-size: {pt['metric']}pt;
    font-weight: 700;
    color: {p.text};
}}
QLabel:disabled {{
    color: {p.text_disabled};
}}

/* ==================================================================
   Superficies
   ================================================================== */
QFrame[surface="card"] {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: {RADIUS_SURFACE}px;
}}
QFrame[surface="sunken"] {{
    background-color: {p.sunken};
    border: 1px solid {p.border};
    border-radius: {RADIUS_SURFACE}px;
}}
QFrame[surface="plain"] {{
    background-color: {p.surface};
    border: none;
    border-radius: {RADIUS_SURFACE}px;
}}
QFrame[role="divider"] {{
    background-color: {p.divider};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

/* ==================================================================
   Botones
   ================================================================== */
/* El de accion va relleno, no contorneado. En el tema anterior TODOS los
   botones eran contorneados, asi que ninguno destacaba sobre otro y la accion
   principal de una pantalla se perdia entre cinco iguales. */
QPushButton {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: {RADIUS_CONTROL}px;
    color: {p.text};
    font-weight: 600;
    padding: 8px 16px;
    min-height: 18px;
}}
QPushButton:hover {{
    background-color: {p.sunken};
    border-color: {p.text_muted};
}}
QPushButton:pressed {{
    background-color: {p.divider};
}}
QPushButton:focus {{
    border: 2px solid {p.accent};
    padding: 7px 15px;
}}

QPushButton[variant="primary"] {{
    background-color: {p.accent};
    border: 1px solid {p.accent};
    color: {p.text_on_accent};
}}
QPushButton[variant="primary"]:hover {{
    background-color: {p.accent_hover};
    border-color: {p.accent_hover};
}}
QPushButton[variant="primary"]:pressed {{
    background-color: {p.accent_pressed};
    border-color: {p.accent_pressed};
}}

QPushButton[variant="ghost"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {p.text_secondary};
    font-weight: 500;
}}
QPushButton[variant="ghost"]:hover {{
    background-color: {p.sunken};
    color: {p.text};
}}

QPushButton[variant="success"] {{
    background-color: {p.success};
    border-color: {p.success};
    color: {p.text_on_accent if not p.is_dark else '#14121F'};
}}
QPushButton[variant="danger"] {{
    background-color: {p.danger};
    border-color: {p.danger};
    color: {p.text_on_accent if not p.is_dark else '#14121F'};
}}
QPushButton[variant="warning"] {{
    background-color: transparent;
    border-color: {p.warning};
    color: {p.warning};
}}
QPushButton[variant="warning"]:hover {{
    background-color: {p.warning};
    color: {'#14121F' if p.is_dark else '#FFFFFF'};
}}
QPushButton[variant="maintenance"] {{
    background-color: transparent;
    border-color: {p.maintenance};
    color: {p.maintenance};
}}
QPushButton[variant="maintenance"]:hover {{
    background-color: {p.maintenance};
    color: {'#14121F' if p.is_dark else '#FFFFFF'};
}}

/* El deshabilitado va DESPUES de las variantes. Un selector de atributo le
   gana a una pseudoclase, asi que una regla :disabled escrita antes no llega a
   aplicarse sobre un boton con variante: se veia relleno y activo aunque no
   respondiera al clic. */
QPushButton:disabled,
QPushButton[variant="primary"]:disabled,
QPushButton[variant="ghost"]:disabled,
QPushButton[variant="success"]:disabled,
QPushButton[variant="danger"]:disabled,
QPushButton[variant="warning"]:disabled,
QPushButton[variant="maintenance"]:disabled {{
    background-color: transparent;
    border: 1px solid {p.divider};
    color: {p.text_disabled};
}}

/* ==================================================================
   Navegacion lateral
   ================================================================== */
QFrame[role="sidebar"] {{
    background-color: {p.surface};
    border: none;
    border-right: 1px solid {p.border};
}}
QPushButton[nav="item"] {{
    background-color: transparent;
    border: none;
    border-radius: {RADIUS_CONTROL}px;
    color: {p.text_secondary};
    font-weight: 600;
    padding: 10px 14px;
    text-align: left;
}}
QPushButton[nav="item"]:hover {{
    background-color: {p.sunken};
    color: {p.text};
}}
QPushButton[nav="item"][active="true"] {{
    background-color: {p.accent_soft};
    color: {p.accent if not p.is_dark else p.accent_hover};
}}

/* ==================================================================
   Campos
   ================================================================== */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: {RADIUS_CONTROL}px;
    padding: 7px 10px;
    color: {p.text};
    selection-background-color: {p.accent};
    selection-color: {p.text_on_accent};
    min-height: 18px;
}}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QSpinBox:hover {{
    border-color: {p.text_muted};
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border: 2px solid {p.accent};
    padding: 6px 9px;
}}

/* Campo que impide guardar (form_guard.show_issues del proyecto original, que
   esta interfaz reutiliza tal cual). Va despues del foco para ganarle: el
   campo marcado recibe el foco y tiene que seguir viendose en rojo. */
QLineEdit[invalid="true"], QComboBox[invalid="true"],
QDateEdit[invalid="true"], QSpinBox[invalid="true"] {{
    border: 2px solid {p.danger};
    padding: 6px 9px;
}}

QLineEdit:read-only {{
    background-color: {p.sunken};
    color: {p.text_secondary};
}}
/* Un campo apagado tiene que verse apagado. Las piezas por encima de las que
   declara la prueba se deshabilitan, y sin esto se veian igual que las
   capturables: mismo fondo, mismo texto, y solo cambiaba el borde. */
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled,
QSpinBox:disabled, QPlainTextEdit:disabled {{
    background-color: {p.sunken};
    border-color: {p.divider};
    color: {p.text_disabled};
}}

/* No se da estilo a ::drop-down. Al hacerlo, Qt deja de dibujar la flecha
   salvo que se defina tambien ::down-arrow con una imagen, y los combos y los
   selectores de fecha quedan con aspecto de simple caja de texto. */
/* Con Fusion la lista se abre centrada sobre el campo e ignora
   maxVisibleItems: la de clientes llegaba a 516 px y crecia con el catalogo.
   'combobox-popup: 0' la abre debajo, con tope de filas y barra. */
QComboBox {{
    combobox-popup: 0;
}}
QComboBox QAbstractItemView {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: {RADIUS_CONTROL}px;
    padding: 4px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
    outline: none;
}}
/* Sin esto, al quitar el modo centrado las filas bajan de 27 a 19 px. */
QComboBox QAbstractItemView::item {{
    min-height: 26px;
    padding: 0 8px;
    border-radius: 6px;
}}

/* ==================================================================
   Tablas
   ================================================================== */
QTableView {{
    background-color: {p.row};
    alternate-background-color: {p.row_alt};
    gridline-color: {p.grid};
    border: 1px solid {p.border};
    border-radius: {RADIUS_SURFACE}px;
    selection-background-color: {p.selection};
    selection-color: {p.text};
    outline: none;
}}
QTableView::item {{
    padding: 5px;
    border: none;
}}
QHeaderView {{
    background-color: {p.header_bg};
}}
QHeaderView::section {{
    background-color: {p.header_bg};
    color: {p.header_text};
    font-weight: 700;
    border: none;
    border-right: 1px solid {p.grid};
    border-bottom: 1px solid {p.border};
    padding: 9px 7px;
}}
QHeaderView::section:hover {{
    color: {p.text};
}}
QTableCornerButton::section {{
    background-color: {p.header_bg};
    border: none;
}}

/* ==================================================================
   Pestanas
   ================================================================== */
QTabWidget::pane {{
    border: 1px solid {p.border};
    border-radius: {RADIUS_SURFACE}px;
    top: -1px;
    background-color: {p.surface};
}}
QTabBar::tab {{
    background-color: transparent;
    color: {p.text_muted};
    padding: 9px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
    margin-right: 4px;
}}
QTabBar::tab:hover {{
    color: {p.text};
}}
QTabBar::tab:selected {{
    color: {p.accent if not p.is_dark else p.accent_hover};
    border-bottom: 2px solid {p.accent};
}}

/* ==================================================================
   Avisos
   ================================================================== */
/* Datos nuevos de otro equipo. Informa, no alarma: nada esta mal, solo hay
   algo mas reciente que lo que se ve en pantalla. */
QFrame[banner="info"] {{
    background-color: {p.accent_soft};
    border: 1px solid {p.accent};
    border-radius: {RADIUS_CONTROL}px;
}}
QFrame[banner="info"] QLabel {{
    color: {p.text};
    font-size: {pt['small']}pt;
}}
/* El aviso que enumera lo que falta, bajo el titulo del formulario. */
QLabel[issues="true"] {{
    background-color: {p.surface};
    border: 1px solid {p.danger};
    border-left: 4px solid {p.danger};
    border-radius: {RADIUS_CONTROL}px;
    padding: 10px 14px;
    color: {p.text};
    font-size: {pt['small']}pt;
}}

/* Etiquetas de estado. El color dice que estado es; la forma la da el radio. */
QLabel[pill="neutral"], QLabel[pill="success"], QLabel[pill="warning"],
QLabel[pill="danger"], QLabel[pill="info"], QLabel[pill="maintenance"] {{
    border-radius: 10px;
    padding: 3px 10px;
    font-size: {pt['tiny']}pt;
    font-weight: 700;
}}
QLabel[pill="neutral"] {{ background-color: {p.sunken}; color: {p.text_secondary}; }}
QLabel[pill="success"] {{ background-color: {p.sunken}; color: {p.success}; }}
QLabel[pill="warning"] {{ background-color: {p.sunken}; color: {p.warning}; }}
QLabel[pill="danger"] {{ background-color: {p.sunken}; color: {p.danger}; }}
QLabel[pill="info"] {{ background-color: {p.accent_soft}; color: {p.info}; }}
QLabel[pill="maintenance"] {{ background-color: {p.sunken}; color: {p.maintenance}; }}

/* ==================================================================
   Varios
   ================================================================== */
QGroupBox {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: {RADIUS_SURFACE}px;
    margin-top: 16px;
    padding: 14px 12px 12px 12px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: {p.text_secondary};
}}
QGroupBox[slot="dimmed"] {{
    background-color: {p.sunken};
    border: 1px dashed {p.divider};
}}
QGroupBox[slot="extra"] {{
    border: 1px solid {p.warning};
}}
QGroupBox[slot="extra"]::title {{
    color: {p.warning};
}}

QScrollArea {{
    background-color: transparent;
    border: none;
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    border: none;
    margin: 0;
}}
QScrollBar:vertical {{ width: 12px; }}
QScrollBar:horizontal {{ height: 12px; }}
QScrollBar::handle {{
    background: {p.border};
    border-radius: 6px;
    min-height: 32px;
    min-width: 32px;
}}
QScrollBar::handle:hover {{ background: {p.text_muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QToolTip {{
    background-color: {p.overlay};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 6px 8px;
}}

QMenu {{
    background-color: {p.overlay};
    border: 1px solid {p.border};
    border-radius: {RADIUS_CONTROL}px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 24px 7px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {p.accent_soft};
    color: {p.text};
}}

QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {p.border};
    border-radius: 4px;
    background-color: {p.surface};
}}
QCheckBox::indicator:checked {{
    background-color: {p.accent};
    border-color: {p.accent};
}}

QMessageBox {{
    background-color: {p.surface};
}}
QDialogButtonBox {{
    button-layout: 2;
}}
"""
