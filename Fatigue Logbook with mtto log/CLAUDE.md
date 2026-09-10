# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Bitácora de ensayos mecánicos (Fatiga, Torsión, Rotary, Quasi) en PySide6 sobre
SQLite. **Está en uso diario**: la base de `db/` tiene datos reales de
producción. El README documenta el producto; esto documenta cómo trabajar en él.

## Comandos

```powershell
.\.venv\Scripts\Activate.ps1        # Python 3.13, PySide6 6.8.1.1 + openpyxl
python main.py                      # arranca la app (pythonw main.py sin consola)

python tests\run_all.py             # todas las suites, cada una en su proceso
python tests\run_all.py priority    # solo las que lleven 'priority' en el nombre
python tests\test_chip_colors.py    # una sola suite, directa
```

No hay pytest ni linter: cada `tests/test_*.py` es un script que imprime
`OK`/`FALLO` por comprobación y sale con código 1 si algo falla. Se lanzan en
procesos separados porque varias crean una `QApplication` y dos no conviven en
el mismo intérprete. Al agregar una suite basta con nombrarla `test_*.py`; las
nuevas usan `harness.Report` y terminan con `raise SystemExit(report.finish())`.

Una comprobación dice **qué se esperaba y por qué**, no solo que algo es cierto:
el detalle lleva la medida (`3.01 : 1`, `dE 20.7`, `sobran 0 px`) para que al
fallar se vea cuánto falta.

Scripts de una sola vez, ya ejecutados: `tools/pick_database.py` (compara los
`.db` y archiva las copias de conflicto de OneDrive) y
`tools/import_excel_catalogs.py` (`Auxiliar.xlsx` → tablas de catálogo).

## Arquitectura

**La regla que ordena todo: nada en `app/ui/` ejecuta SQL.** Las páginas piden
dataclasses a los repositorios; `app/db/repositories.py` es lo único que toca
`sqlite3`. Lo que no es ni SQL ni pantalla vive en `app/services/`.

- `app/context.py` — `AppContext` arma conexión, repositorios y servicios una
  sola vez y se pasa a las páginas. `prepare()` migra y carga catálogos.
- `app/db/connection.py` — la base vive en un recurso de red SMB: **nunca WAL**
  (`journal_mode=DELETE`, `busy_timeout=15000`, `BEGIN IMMEDIATE` para escribir,
  reintentos ante bloqueo). Todo pasa por aquí.
- `app/db/migrations.py` — runner con `PRAGMA user_version`, 12 migraciones.
- `app/models.py` — dataclasses del dominio, no tuplas por posición.
- `app/services/` — catálogos en memoria, validación, filtros, duración
  (semáforo de antigüedad), uso de rigs, mantenimiento, respaldo, export a
  Excel.
- `app/ui/models/table_models.py` — un `QAbstractTableModel` por bitácora; los
  delegados leen roles propios (`SORT_ROLE`, `DAYS_LEVEL_ROLE`, `CHIPS_ROLE`,
  `RIG_COLOR_ROLE`) en vez de colores de texto.

**La alineación es de la columna, no de la celda** (`column_alignment`): números
a la derecha, todo lo demás a la izquierda, y el encabezado como su columna.
Decidirla mirando el valor de cada celda es lo que había antes, y hacía que una
celda vacía se alineara distinto que sus vecinas — `None` no es ni fecha ni
número.

Cálculos que dos pantallas comparten van a un servicio, no se copian. Cuando la
ocupación de rigs se calculaba en dos sitios, una pantalla decía 11 bancos
ocupados y la otra 10; ahora las dos llaman a `app/services/rig_usage.py`.

**El mantenimiento de un banco toca dos tablas a la vez.** `MaintenanceRepository`
es el único repositorio que escribe en la tabla de otra bitácora: abrir un
periodo vacía el `test_rigN` de las piezas que corrían ahí, y cerrarlo se lo
devuelve. Va en una sola transacción porque las dos mitades por separado
mienten — un banco parado con sus piezas asignadas seguiría contando como
ocupado, y unas piezas sin banco sin nada que lo explique se leen como
suspensiones sueltas. Solo salen del banco las piezas **sin resultado**: la que
ya falló terminó ahí, y su banco es el dato de dónde corrió.

De ahí sale también que la columna *Días* sea **tiempo de ensayo** y no de
calendario. Los periodos se unen antes de restar (`app/services/maintenance.py`)
y los umbrales del semáforo se calibran con el mismo descuento: calibrar con
calendario y medir en días efectivos daría un semáforo optimista siempre.

**Todo lo que se mide tiene que poder consultarse.** El tiempo de mantenimiento
se descontaba de los días de cada prueba antes de que hubiera ninguna pantalla
que enseñara de dónde salía; el historial está ahora en
`MaintenanceHistoryDialog` y en el panel del dashboard. Al filtrar por rango,
`overlapping()` incluye los periodos **abiertos que empezaron antes** —son los
que tienen el banco parado hoy— y `downtime_by_rig(window=...)` recorta los días
al rango en vez de sumarlos enteros.

**Una prueba nace de una Work Order**, no de un botón de alta: las cuatro
bitácoras se abren desde *Work Orders → Comenzar prueba*
(`STARTABLE_TEST_TYPES`, hoy los cuatro tipos). La excepción es **Torsión**, la
única que conserva además su "Nuevo registro" (`DIRECT_ENTRY_TEST_TYPES`),
porque ahí llega la pieza y se corre sin orden previa. Si buscas el alta de una
bitácora y no aparece, es esto.

El **requester** viaja de la orden al registro y se queda ahí: es lo que se
consulta años después, y las pruebas anteriores a las Work Orders no tienen
orden a la que ir a preguntar. Es opcional en el formulario -- exigirlo
impediría cerrar los cientos de registros que no lo tienen.

Dónde están los datos: `settings.json` en la raíz apunta a `db/test_records.db`
y a `db backups/`; también se cambia desde *Ajustes → Base de datos*. La base
**no puede vivir en carpeta sincronizada** (OneDrive/SharePoint): eso generó los
`test_records-...-2.db`, `-3`, `-4` que hubo que archivar.

## Reglas que cuestan caro si se rompen

**Migraciones autocontenidas.** Una migración no importa código vivo: congela
su propia copia de paletas, criterios y listas (ver `_M010_PALETTE`). Si
importara `app.services`, cambiar ese servicio reescribiría el pasado. Deben
ser idempotentes: correr el runner dos veces no cambia nada la segunda.
`main.py` respalda **antes** de migrar (`migrations.pending()` +
`backup.pre_migration_backup()`), no después.

Para agregar una: una función `_migration_0NN_...(conn)` y una entrada más en la
tupla `MIGRATIONS`; `LATEST_VERSION` sale de ahí sola. Pruébala primero sobre
una copia (`harness.database_copy()`), dos veces seguidas, y comprueba los
totales por tabla antes y después.

**Las pruebas nunca contra la base real** — `AppContext.prepare()` migra, y una
prueba que abriera `db/test_records.db` dejaría migrada la de producción antes
de que nadie respaldara. Se usa `harness.database_copy()`.

**Nada de contar filas fijas.** La app está en uso y la base crece: una prueba
que espere "10 registros en curso" falla la semana que viene sin que nada esté
mal. Se compara contra lo que diga la base. Tampoco se afirma nada sobre "la
primera fila": lo que haya ahí depende de lo que capturó el laboratorio.

**Antes de culpar al código, mira el `audit_log`.** Cada alta, edición, cierre y
reapertura queda registrada con usuario y equipo. Dos veces un cambio inesperado
en los datos resultó ser una edición del propio usuario en la app abierta —que
suele estarlo mientras trabajas—, y una de ellas enseñó cómo se captura de
verdad una suspensión: vaciar el Test Rig y anotar `Susp`.

## Convenciones

- **Código y comentarios en ASCII; el texto que ve el usuario, con tildes.**
  Son dos cosas distintas y solo una la lee el usuario.
  `tests/test_ui_repaso.py` falla si vuelve a colarse una etiqueta sin tilde.
- Los comentarios explican **por qué**, y suelen decir qué pasaba antes. Se
  conservan: son el registro de los tropiezos.
- Fechas: en la base son texto `dd/MM/yyyy` (formato heredado); los repositorios
  reciben y devuelven `datetime.date` y traducen en el borde.
- Estatus (`Ongoing`/`Finished`) se guardan en inglés porque así nació la base;
  en pantalla se traducen (`STATUS_LABELS`).
- Una ranura de muestra vacía puede ser `None`, `""` o `"--"` (las columnas
  viejas no guardaban nulos): usar `models.is_blank()`.
- Los saltos de línea están mezclados: unos archivos son LF y otros CRLF. Un
  `read_text()`/`write_text()` sobre un archivo LF lo convierte entero a CRLF y
  el diff sale con el archivo completo cambiado. Para editar, la herramienta de
  edición; si hace falta un script, respeta el salto original y evita heredocs
  cuando el texto lleve `\n` dentro de una cadena.

## El color significa cosas

No es decoración y hay pruebas que lo fijan:

- Cada rig tiene su color, con tres restricciones medibles sobre el catálogo
  real: contraste ≥ 3:1 sobre los **tres** fondos de fila, ΔE ≥ 24 contra los
  colores de la interfaz y ΔE ≥ 18 entre rigs (`tests/test_table_colors.py`).
- `WARNING` naranja = pieza suspendida, fuera de banco. `DANGER` rojo =
  revisar (antigüedad). `PRIMARY` = activo o con foco. Gastarlos de adorno les
  quita el significado.
- **El color de un banco significa «está corriendo aquí ahora», no «corrió
  aquí».** Por eso una pieza declarada por completo lo pierde y se queda en un
  cuadrado sin relleno (`DONE`). Lo que decide el color es el presente; el
  pasado va en el tooltip y en la vista de columnas completas.
- Cuando algo se declara "completo", el criterio sale de
  `validation.requires_failure_mode` y no se reescribe: el modo de falla solo
  se le exige a la pieza que falló. Duplicar ese criterio dejaría a las
  `S/Falla` eternamente incompletas en una pantalla y completas en otra.
- `MAINTENANCE` (`#FE9296`) rojo = el banco de esa pieza está en mantenimiento.
  **No es `DANGER`**: sobre la franja alterna `DANGER` se queda en 2.49:1 y el
  número del chip deja de leerse en una fila de cada dos. Un color nuevo para
  la tabla se elige midiendo contra **los tres fondos de fila**, no contra uno.
- **Un color nuevo ya no cabe sin ceder algo.** Con dieciséis rigs y el
  semáforo, el espacio está lleno: el rojo del mantenimiento quedó a ΔE 23.5
  del salmón de `I-02-1`, medio punto por debajo de la regla. Se aceptó porque
  la **forma** cubre esa distancia —ningún chip de banco lleva trama— y porque
  lo otro era perder legibilidad, que no tiene respaldo. Al agregar un estado,
  primero mira si se distingue por forma o textura; si necesitas color, mide y
  di qué cediste. Las formas las dibuja `sample_chips.paint_chip_shape`, que
  usan la tabla y la leyenda: si la leyenda dibujara su propia versión,
  enseñaría una forma que la tabla ya no usa.
- La selección de fila es **oscura** a propósito: es lo único que deja legibles
  los chips y el semáforo que van encima. Lo que la marca es la barra de acento
  de 3 px, no el relleno.

## Qt: cosas verificadas a golpes

- `QTableView.drawRow` **no se despacha a Python** en PySide6: se puede definir
  y Qt nunca la llama. Lo que se pinta por fila va en `paintEvent`.
- Un `QComboBox` no editable alinea su texto a la izquierda pase lo que pase
  (`CE_ComboBoxLabel`); `CenteredComboBox` lo dibuja aparte, y por eso tiene que
  elegir el `QPalette.ColorGroup` a mano o los campos deshabilitados se pintan
  como activos.
- El primer `grab()`/`render()` de un proceso sale en blanco; con plataforma
  offscreen el texto sale como cuadros.
- Maximizar no es instantáneo: medir la ventana justo después da el tamaño del
  `sizeHint`, no el de la pantalla.
- El dashboard anima las series (`SeriesAnimations`): una captura inmediata sale
  con las gráficas vacías. No es un fallo; hay que esperar ~1.5 s de reloj.
- **Un hijo de ancho fijo le pone suelo a la ventana entera.** Pasó dos veces:
  la franja de la `Legend` (1,561 px, y 1,900 con el mantenimiento) y la
  rejilla de tarjetas de *Ocupación de rigs*, cuyo ancho fijo por tarjeta
  impedía que la pantalla encogiera y recalculara columnas. Se corrige con
  `SetNoConstraint` **y** `minimumSizeHint` devolviendo ancho 0; solo una de
  las dos no basta. Vale la pena medir el `minimumSizeHint().width()` de una
  pantalla nueva: si pasa de ~1,300 no cabe en un portátil.
- Dos `QComboBox` con etiquetas largas costaban 552 px de mínimo. El rótulo
  visible y el valor son cosas distintas: el estado va en `itemData` y el
  rótulo se acorta sin tocar la lógica.
- **Un `QComboBox` mide por su elemento más largo.** El de clientes pedía 292 px
  por `MERCEDES-BENZ`. Se corrige con `setMinimumContentsLength` +
  `AdjustToMinimumContentsLengthWithIcon`: mide por caracteres y el nombre
  completo sigue entero al desplegar.
- **Una fila horizontal no encoge.** Botones y `StatCard` en la misma fila
  sumaban 1,650 px en Fatiga y 1,862 en Work Orders. El arreglo es partir la
  fila —acciones arriba, métricas debajo—, no acortar todo a la fuerza.
- Un `QLabel` con `wordWrap` y un texto **sin espacios** (una ruta) no puede
  partirse: su mínimo es el texto entero, y así pedía 1,136 px él solo. Se
  acorta por el centro y el valor completo va al tooltip.

`tests/test_ui_repaso.py` mide el `minimumSizeHint().width()` de las ocho
pantallas y falla si alguna pasa de 1,326 px (un portátil de 1366 menos el
margen que deja `_fit_window`). Las seis que lo pasaban ya están corregidas.
- Un `QPushButton` no acorta su texto: si no cabe, Qt lo **recorta por los dos
  lados** ("'oner en mantenimient") sin avisar. En una tarjeta de ancho fijo
  hay que bajarle el tamaño de letra o acortar el rótulo.
- Un `QDialog` de las páginas se abre con `exec()`: si una prueba dispara
  `recordActivated` sin desconectar antes la ranura de la página, se queda
  colgada esperando a que alguien cierre el diálogo.

Verifica la interfaz **midiendo**, no a ojo: capturas con `grab()`, píxeles,
contrastes y ΔE. Varias de las reglas de arriba salieron de descubrir que algo
"se veía bien" y no estaba dibujándose. Los scripts de captura y las imágenes
son material de trabajo: van al scratchpad, no al repositorio.
