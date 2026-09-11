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
- `app/db/migrations.py` — runner con `PRAGMA user_version`, 13 migraciones.
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

**Una pieza puede dejar de estar detenida sin que el mantenimiento cierre.**
Si el usuario la lleva a otro banco, `FatigueRepository.update` anota
`released_date` en su apunte, en la misma transacción. "¿Sigue detenida?" se
pregunta siempre a `MaintenanceSample.is_held`: el chip rojo, los días
descontados, las piezas que vuelven al cerrar y los recuentos de la tarjeta del
banco. Cuando cada pantalla miraba `restored` por su cuenta, una pieza que ya
corría en otro banco seguía en rojo y descontando días. `is_held` solo vale
dentro de un periodo **abierto**: el de uno cerrado lo acota su `end_date`.

`released_date` significa únicamente «se movió a otro banco». Cerrar el
mantenimiento **no** la rellena: con eso, una pieza movida el mismo día del
cierre era indistinguible de una que se quedó sin reponer.

Los bancos en mantenimiento no se ofrecen en el Test Rig: los tres sitios que
abren `FatigueDialog` le pasan `unavailable_rigs`
(`maintenance.rigs_in_maintenance`). Si agregas un cuarto, pásaselo también.
La opción se oculta pero el dato no se borra: una pieza que ya tenía ese banco
lo conserva.

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

**Guardar un formulario combina, no sobrescribe.** Varias computadoras usan la
misma base. Los `update` de Fatiga, Rotary, Genérico y Work Orders aceptan
`base=` (el registro tal como se abrió) y combinan columna por columna, dentro
de la transacción de escritura (`_values_to_save`):
- lo que el formulario no tocó queda como está guardado;
- lo que solo cambió el formulario se escribe;
- lo que cambiaron los dos a valores distintos levanta `EditConflict`, salvo
  que se pida `on_conflict=KEEP_MINE` o `KEEP_THEIRS`;
- un registro eliminado levanta `RecordDeleted`.

Sin `base` se escribe el registro entero, como antes; así siguen escribiendo
las pruebas y los scripts. Los formularios guardan con
`form_guard.update_merging`, que pregunta solo cuando hay conflicto. Antes
ganaba el último en guardar: una Work Order comenzada por otro equipo volvía a
*Pendiente* al corregirle un comentario.

**Los cinco formularios de captura heredan de `GuardedDialog`.** Llaman a
`mark_clean()` al terminar de cargar, y `reject()` —Cancelar, Esc, la X—
pregunta solo si la foto de los campos cambió. Un formulario nuevo debe hacer
lo mismo. **Una prueba que cambie campos y luego cierre el formulario** debe
sustituir `form_guard.confirm_discard`; si no, el cuadro modal la deja
colgada. Lo mismo con `ask_conflict` y `warn_deleted`, que son funciones del
módulo justamente para eso.

**Validar no abre cuadros.** Los formularios arman una lista de
`(campo, regla)` con `form_guard.gather_issues`. Para finalizar se añade
`missing_issues(general, samples, self._field_for)` y se pasa todo a
`show_issues`, que marca cada campo (propiedad `invalid`, estilo en
`theme.py`) y lo enumera en el aviso de `issue_banner()`.
- Las reglas de `validation` siguen lanzando al primer error.
- `validate_complete_for_finish` conserva su mensaje; `missing_for_finish` da
  la misma lista dato por dato.
- **Si agregas un campo a `_completeness_fields`, agrégalo también a
  `_field_for`.** Si falta, el aviso lo dice como «También falta: …», pero sin
  marcar su campo.
- Una prueba sabe qué se marcó con `invalid_widgets()` e `issue_text()`, y ya
  no necesita sustituir `QMessageBox.warning`.

**Capturar ciclos** es `CyclesDialog`. «Está corriendo» sale de
`cycles_dialog.piece_state`: tiene banco, no tiene resultado y no está
detenida. Guarda con `update_merging`, igual que los formularios. Las acciones
extra del menú del botón derecho de una tabla se agregan con
`RecordTable.add_menu_action`.

**La fecha de liberación de una pieza detenida** llega del formulario:
`FatigueDialog.moved_on()` → `update(moved_on=...)` →
`_release_moved_samples`, que agrupa por día. Sin `moved_on` se usa el día de
guardar, como antes.

**Una pantalla no guarda repositorios, los pide al contexto.**
`reload_database` arma repositorios nuevos, y quien guardó uno al crearse
sigue en la base anterior. Le pasaba a `GenericPage`: Torsión y Quasi leían y
guardaban en la base vieja hasta reiniciar. Ahora `repository` es una
propiedad. `test_concurrent_edits` revisa todas las pantallas buscando alguna
que conserve una base distinta de la actual.

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
de que nadie respaldara. Se usa `harness.database_copy()`. Ojo con
`AppContext.reload_database`: además guarda la ruta en el **`settings.json`
real** de la raíz. Una prueba que lo llame tiene que redirigir antes
`app.config.SETTINGS_FILE` a un archivo temporal, o dejará la app apuntando a
una copia.

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
- **Con Fusion, un `QComboBox` ignora `maxVisibleItems`.** La lista se abre
  centrada sobre el campo (`SH_ComboBox_Popup = 1`) y mide todo el catálogo:
  la de clientes llegaba a 516 px. `combobox-popup: 0` en la hoja de estilos la
  abre debajo, con tope y barra (262 px). Al quitar el modo centrado, las filas
  bajan de 27 a 19 px; las devuelve `QAbstractItemView::item { min-height }`.
- **La rueda cambia un combo o una fecha que no tiene el foco** (política
  `WheelFocus`). Dentro de un `QScrollArea`, eso es cambiar el Test Rig al
  bajar por el formulario. `CenteredComboBox` y el `DateEdit` de
  `make_date_edit` usan `StrongFocus` e ignoran la rueda sin foco, y Qt la
  pasa al área.
- **Qt solo propaga al padre la rueda real.** Una enviada con `sendEvent` que
  nadie acepta no sube, así que una prueba que la mande a un combo nunca ve
  desplazarse el área, aunque con el ratón sí se desplace.
  `tests/test_form_fit.py` la sube a mano, como hace Qt.
- **`QScrollArea.sizeHint()` está topado.** Un diálogo que deja a Qt elegir su
  tamaño nace con barra aunque sobre pantalla. Por eso
  `fit_dialog_to_screen` calcula el alto (cromo + `body.sizeHint()`) y lo
  recorta al de la pantalla menos 60. El cromo se mide contra el alto que el
  **layout** reserva al área (`itemAt(...).sizeHint()`, que ya incluye su
  mínimo), no contra `area.sizeHint()`. Y el mínimo del área no es fijo en un
  formulario corto: con 220 px, la Work Order (189 px de datos) nacía con 31 px
  de hueco encima de los botones.
- **Un formulario largo desplaza su cuerpo, no la ventana entera.** Fatiga
  pedía 967 px de alto y Rotary 850: en un portátil el botón de guardar
  quedaba fuera de la pantalla. Con `scroll_body` + `fit_dialog_to_screen`, el
  título y los botones quedan fijos. Work Order (322 px) y Torsión/Quasi
  (`GenericDialog`, 426 px) siguen la misma estructura aunque quepan, para que
  con escala alta tampoco pierdan el botón. Los cinco formularios de captura la
  usan; uno nuevo debería hacer lo mismo y exponer `save_button`, que es lo que
  mide `tests/test_form_fit.py`.
- **Un widget sin padre ni variable que lo retenga se destruye en la misma
  línea.** `CyclesDialog(...).save_button.isEnabled()` falló con «Internal C++
  object already deleted»: PySide borra el objeto C++ en cuanto Python suelta
  la referencia. En las pruebas, un diálogo que se va a consultar va a una
  variable.
- **Qt no vuelve a aplicar la hoja de estilos al cambiar una propiedad.**
  `setProperty("invalid", "true")` no pinta nada hasta
  `style().unpolish()` + `style().polish()`; lo hace `form_guard._set_invalid`.

Verifica la interfaz **midiendo**, no a ojo: capturas con `grab()`, píxeles,
contrastes y ΔE. Varias de las reglas de arriba salieron de descubrir que algo
"se veía bien" y no estaba dibujándose. Los scripts de captura y las imágenes
son material de trabajo: van al scratchpad, no al repositorio.
