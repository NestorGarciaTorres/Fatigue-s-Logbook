# Bitácora de Pruebas — interfaz rediseñada

Rediseño completo de la interfaz de `fatigue-logbook`, en PySide6, con temas
claro y oscuro conmutables sin reiniciar.

Hay **cuatro paletas** y se eligen en Ajustes → Apariencia, combinadas con el
modo claro u oscuro: ocho aspectos. La de partida es **Pizarra** — neutros gris
verdoso y un azul de acción sin estridencia — y la idea que la ordena es que
*nada de la interfaz compita con los colores de los bancos*, que son lo que de
verdad hay que leer en una jornada larga.

### Por qué cada paleta necesita su propia tabla de colores de banco

No basta con repintar. Medido: los colores claros calibrados para Pizarra dejan
el acento de Acero a **ΔE 8.7** de uno de los bancos, y el de Carbón a 9.6 — ese
chip se leería como un color de interfaz en vez de como un banco. Y tampoco
existe una paleta de bancos que sirva para las cuatro: solo cabe girando el tono
40°, que convierte un banco verde en uno amarillo verdoso.

Así que las cuatro se precalculan una vez con
`python tools/generate_light_palette.py --table`, que las guarda en
`theme/rig_light_palettes.json`. Cambiar de paleta en Ajustes es entonces
reescribir dieciséis celdas, no recalcular nada: instantáneo en vez de doce
segundos.

**El proyecto original no se toca.** Esta carpeta reutiliza su lógica —
repositorios, servicios y modelos — importándola a través de `bridge.py`. Las
dos aplicaciones leen y escriben exactamente igual, así que no pueden divergir,
y la vieja sigue funcionando como siempre.

## Arranque

```powershell
cd "..\fatigue-logbook"
.\.venv\Scripts\Activate.ps1     # Python 3.13, PySide6 6.8.1.1 + openpyxl
cd "..\fatigue-logbook-ui"
python main.py                   # pythonw main.py para lanzarlo sin consola
```

Las dos carpetas tienen que estar juntas:

```
AI Projects/
├── fatigue-logbook/        <- intacto
└── fatigue-logbook-ui/     <- esto
```

## Pruebas

```powershell
python tests\run_all.py          # todas, cada una en su proceso
python tests\run_all.py theme    # solo las que lleven 'theme' en el nombre
```

Mismo formato que las del proyecto original: `OK`/`FALLO` por comprobación y
salida 1 si algo falla. **Nunca contra la base real** — `AppContext.prepare()`
migra, así que se trabaja sobre `harness.database_copy()`.

Una comprobación de color dice **la medida**: `4.61 : 1`, `dE 44.0`. Al fallar
hay que ver cuánto falta, no solo que falló.

## Las tres reglas que hacen posible el tema conmutable

El proyecto anterior no podía cambiar de tema en caliente, y el inventario dijo
por qué: 49 `setStyleSheet` inline repartidos en once archivos, y tres módulos
copiando colores a constantes propias en el momento de importar
(`DAYS_COLORS`, `SUSPENDED_COLOR`, `MAINTENANCE_COLOR`). Un color congelado así
no lo alcanza ningún cambio posterior.

1. **Ningún widget lleva `setStyleSheet`.** Todo lo visual sale de la hoja
   global (`theme/qss.py`) y lo que cambia entre widgets se expresa con
   `setProperty`. Hay **una** excepción documentada: el acento de una
   `StatCard`, que es un dato de la tarjeta y no de su tipo — y se vuelve a
   aplicar en cada cambio de tema.
2. **Ningún color se copia a una constante de módulo.** Lo que se pinta a mano
   pide `theme().palette.x` **dentro** de `paint()`.
3. **Al cambiar de tema se repolisa el árbol entero.** Qt no reaplica la hoja a
   un widget ya dibujado; sin `unpolish` + `polish` media pantalla se queda
   como estaba.

`tests/test_theme_switch.py` comprueba las tres midiendo: captura la pantalla,
cambia el tema, vuelve a capturar, y falla si queda **un solo píxel** del tema
anterior. Y revisa el código fuente para que no reaparezcan estilos inline.

## Las dos paletas de rigs

La base guarda dos colores por banco: `color` (el de siempre, tema oscuro) y
`color_light`, que añade `tools/generate_light_palette.py`.

Hacen falta las dos porque **ningún color contrasta 3:1 contra una fila clara y
una oscura a la vez**: contra fila clara hace falta L ≤ 0.267 y contra fila
oscura L ≥ 0.312, así que la intersección está vacía. Se comprobó barriendo el
círculo de tono entero contra tres juegos de fondos claros: cero candidatos.
Los 16 colores actuales dan 5.34:1 sobre la fila oscura y como mucho 2.15:1
sobre blanco.

La columna nueva es invisible para la app original: su
`CatalogRepository.rigs()` hace `SELECT` con las columnas nombradas una a una.
Se verificó corriendo sus 26 suites después de añadirla.

Cada banco **conserva su tono** entre temas: el que es verde en oscuro sigue
siendo verde en claro, más oscuro y más saturado. Un rig se reconoce por el
color, y cambiárselo sería pedir que se aprendan dos códigos.

**El teal quedó descartado, medido.** La paleta elegida nació con un acento
teal y no era viable: un acento teal más el verde de `success` se llevan por
delante la franja verde-menta donde caen seis de los dieciséis bancos, y la
paleta clara de rigs deja de caber. Se cambió por un azul apagado.

**Qué se cedió, medido:** los dieciséis entran con separación ΔE ≥ 18, no 20.
Seis rigs caen en la franja verde-menta (tonos 76, 88, 106, 120, 160 y 164°) y
el verde de `success` se lleva su propio radio de 24. Con un giro de tono de
40° sí se llega a ΔE 20, pero 40° convierten un banco verde en uno amarillo
verdoso. 18 es además el umbral que la migración 010 del original ya aceptó.

## Estructura

| Ruta | Qué hay |
|---|---|
| `bridge.py` | El único contacto con el original: `sys.path`, redirección de ajustes y arranque del contexto |
| `theme/tokens.py` | Las dos paletas, como datos. Campos semánticos, nunca constantes sueltas |
| `theme/qss.py` | La hoja completa, derivada de una paleta y un tamaño de letra |
| `theme/manager.py` | Tema activo, conmutación, repolish y persistencia |
| `theme/color.py` | Luminancia, contraste WCAG y distancia CIELab |
| `theme/rig_palette.py` | El color de cada banco en el tema activo, por `(nombre, tipo)` |
| `components/` | Botones, campos, tarjetas, chips, tabla, filtros, leyenda, avisos |
| `pages/` | Las pantallas |
| `excel_compact.py` | El reporte de fatigas en curso, una fila por pieza |
| `window.py` | Barra lateral, pila de pantallas y aviso de datos nuevos |

### El reporte de fatigas en curso baja la muestra a filas

El de siempre escribe **45 columnas**: 7 fijas, 2 de cola y las nueve ranuras
por sus cuatro datos —banco, resultado, ciclos y modo de falla— estén usadas o
no. Como casi ninguna prueba pasa de tres piezas, la mayor parte de la hoja va
en blanco y hay que desplazarse de lado para leer un solo registro.

`excel_compact.py` escribe **una fila por pieza**: catorce columnas, con una
pieza o con nueve. No se pierde ningún dato, los colores y las notas son los
mismos, y los ciclos siguen siendo un entero de verdad con separador de miles
—la abreviatura `8.1K` es de los chips de la pantalla y no entra en el papel—.

Qué pieza merece fila lo decide `components.models.has_content`, **la misma
función** que decide si la tabla dibuja un chip. Por eso es pública: con dos
copias del criterio, el reporte firmado y la bitácora dejan de decir lo mismo
en cuanto alguien retoca una, y `tests/test_excel_compact.py` compara las filas
de cada prueba con sus chips justamente para eso.

Las columnas de la prueba se combinan sobre las filas de sus piezas
(`MERGE_TEST_ROWS`). Es lo que la hace legible e imprimible, y cuesta que Excel
no pueda **ordenar** un rango con celdas combinadas; en `False` la hoja sale
plana y repetida, y entonces sí se ordena y se resume en una tabla dinámica.

La pestaña de finalizadas sigue con `export_fatigue(..., finished=True)`, y el
proyecto original no se toca: este módulo reutiliza sus ayudantes
(`_new_sheet`, `_append_row`, `_paint_rig`, `_totals`, `_save`) y sus colores.

### Por qué los ajustes van en archivos propios

`ui_settings.json` guarda lo que espera `AppConfig` (base, respaldos) y
`ui_theme.json` el tema y el tamaño de letra. Son dos archivos y no uno porque
`AppConfig.save()` serializa con `asdict()`: reescribiría el archivo entero y
se llevaría por delante cualquier clave que no sea suya.

Y viven aquí, no en el original: sin esa redirección, cambiar el tamaño de
letra desde esta interfaz reescribiría el `settings.json` del proyecto que debe
quedar intacto.

## Lo que se reutiliza en vez de reescribirse

Hay módulos dentro de `app/ui/` del original que son reglas de negocio con ropa
de interfaz. Se importan:

- `form_guard` — combinación de ediciones entre equipos, guardia de cambios sin
  guardar, marcado de campos inválidos.
- `report_export` — el recorrido completo de guardar un reporte.
- `main_window.WATCHED_TABLES` y `CHANGES_POLL_MS` — qué tablas vigila cada
  pantalla.

Y los criterios de dominio se le piden a los servicios, nunca se copian:
`validation.requires_failure_mode`, `duration`, `maintenance`, `filtering`,
`rig_usage`.

## Los formularios

Los cinco de captura heredan de `FormDialog`, que a su vez hereda de
`GuardedDialog` del proyecto original. Ahí vive lo que evita perder datos y no
se reescribe: la guardia de cambios sin guardar, la combinación de ediciones
entre dos equipos y el marcado de campos inválidos.

Lo que `FormDialog` pone encima es la **forma**, y cada pieza existe por un
fallo concreto:

- **Título y botones fijos, cuerpo desplazable.** Fatiga pedía 967 px de alto y
  Rotary 850; en un portátil de 768 el botón de guardar quedaba debajo del
  borde de la pantalla, sin forma de llegar a él.
- **Fatiga se abre por filas.** Las nueve piezas siguen ahí, pero la ventana
  nace mostrando dos filas. Lo normal en un test batch son seis.
- **El aviso de lo que falta va fuera del área que se desplaza**, para que se
  lea aunque el campo marcado esté abajo del todo.
- **Las piezas que sobran del número declarado se apagan, no se ocultan** — y
  si ya traen datos se quedan encendidas y en ámbar, porque hay registros
  antiguos así y apagarlas dejaría el dato sin manera de corregirlo.

`tests/test_forms.py` lo mide simulando una pantalla de 768 px: el botón de
guardar dentro de la ventana, fuera de la zona desplazable, y el formulario
recién abierto sin cambios pendientes.

## Estado

**Las tres fases están hechas.** Sistema de tema, componentes, las ocho
pantallas y los formularios de captura, todo funcionando con datos reales en
los dos temas.

Del proyecto original se sigue importando **solo lo deliberado**: `form_guard`
(la lógica de guardado), `report_export`, las tablas de traducción de columnas
del historial y el mapeo de tablas vigiladas. Nada de presentación.

Medido en la última corrida: ancho mínimo de la ventana **1,081 px** (el tope
de un portátil de 1366 es 1326), y **415 comprobaciones** en 4 suites, todas
pasando — las cuatro paletas se miden enteras, en sus dos modos.

### Una trampa que cuesta dos horas

Una prueba que cambia campos y después cierra el formulario **tiene** que
sustituir `form_guard.confirm_discard`: si no, `reject()` abre el cuadro de
"cambios sin guardar" y la suite se queda esperando a que alguien lo conteste.
Los síntomas engañan — la suite imprime sus comprobaciones, todas en verde, y el
proceso no termina nunca, colgando de paso a `run_all.py`. Lo mismo con
`ask_conflict` y `warn_deleted`; son funciones de módulo justo para poder
sustituirlas.

### Lo que las gráficas obligan a hacer distinto

`QtCharts` no toma el color de la hoja de estilos: hay que dárselo widget a
widget. Por eso el Dashboard es el **único** sitio de la app donde cambiar de
tema reconstruye algo en vez de solo repintarlo — se conecta a `themeChanged` y
rehace las tres gráficas.

### Las dos excepciones a "ningún widget lleva setStyleSheet"

Las dos pintan un color que es **dato**, no tipo de widget, así que no puede
salir de un selector: el acento de una `StatCard` y el color del banco en la
cabecera de su tarjeta de ocupación. Lo que las hace legítimas es que las dos
se vuelven a aplicar en cada cambio de tema. `tests/test_theme_switch.py` las
lleva en una lista explícita y falla ante una tercera — de hecho cazó la de la
tarjeta de rig cuando todavía no tenía esa reconexión.
