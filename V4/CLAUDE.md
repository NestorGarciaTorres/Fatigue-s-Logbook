# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Bitácora de ensayos mecánicos (Fatiga, Torsión, Rotary, Quasi) en PySide6 sobre
SQLite. **Está en uso diario**: la base de `db/` tiene datos reales de
producción. El README documenta el producto; esto documenta cómo trabajar en él.

## Comandos

```powershell
.\.venv\Scripts\Activate.ps1        # Python 3.13, PySide6 6.8.1.1 + openpyxl
python main.py                      # arranca la app (pythonw main.py sin consola)

python tests\run_all.py             # las 18 suites, cada una en su proceso
python tests\run_all.py priority    # solo las que lleven 'priority' en el nombre
python tests\test_chip_colors.py    # una sola suite, directa
```

No hay pytest ni linter: cada `tests/test_*.py` es un script que imprime
`OK`/`FALLO` por comprobación y sale con código 1 si algo falla. Se lanzan en
procesos separados porque varias crean una `QApplication` y dos no conviven en
el mismo intérprete. Al agregar una suite basta con nombrarla `test_*.py`.

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
- `app/db/migrations.py` — runner con `PRAGMA user_version`, 10 migraciones.
- `app/models.py` — dataclasses del dominio, no tuplas por posición.
- `app/services/` — catálogos en memoria, validación, filtros, duración
  (semáforo de antigüedad), uso de rigs, respaldo, export a Excel.
- `app/ui/models/table_models.py` — un `QAbstractTableModel` por bitácora; los
  delegados leen roles propios (`SORT_ROLE`, `DAYS_LEVEL_ROLE`, `CHIPS_ROLE`,
  `RIG_COLOR_ROLE`) en vez de colores de texto.

Cálculos que dos pantallas comparten van a un servicio, no se copian. Cuando la
ocupación de rigs se calculaba en dos sitios, una pantalla decía 11 bancos
ocupados y la otra 10; ahora las dos llaman a `app/services/rig_usage.py`.

## Reglas que cuestan caro si se rompen

**Migraciones autocontenidas.** Una migración no importa código vivo: congela
su propia copia de paletas, criterios y listas (ver `_M010_PALETTE`). Si
importara `app.services`, cambiar ese servicio reescribiría el pasado. Deben
ser idempotentes: correr el runner dos veces no cambia nada la segunda.
`main.py` respalda **antes** de migrar (`migrations.pending()` +
`backup.pre_migration_backup()`), no después.

**Las pruebas nunca contra la base real** — `AppContext.prepare()` migra, y una
prueba que abriera `db/test_records.db` dejaría migrada la de producción antes
de que nadie respaldara. Se usa `harness.database_copy()`.

**Nada de contar filas fijas.** La app está en uso y la base crece: una prueba
que espere "10 registros en curso" falla la semana que viene sin que nada esté
mal. Se compara contra lo que diga la base. Tampoco se afirma nada sobre "la
primera fila": lo que haya ahí depende de lo que capturó el laboratorio.

**Antes de culpar al código, mira el `audit_log`.** Cada alta, edición, cierre y
reapertura queda registrada con usuario y equipo. Dos veces un cambio inesperado
en los datos resultó ser una edición del propio usuario en la app abierta.

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

## El color significa cosas

No es decoración y hay pruebas que lo fijan:

- Cada rig tiene su color, con tres restricciones medibles sobre el catálogo
  real: contraste ≥ 3:1 sobre los **tres** fondos de fila, ΔE ≥ 24 contra los
  colores de la interfaz y ΔE ≥ 18 entre rigs (`tests/test_table_colors.py`).
- `WARNING` naranja = pieza suspendida, fuera de banco. `DANGER` rojo =
  revisar (antigüedad). `PRIMARY` = activo o con foco. Gastarlos de adorno les
  quita el significado.
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

Verifica la interfaz **midiendo**, no a ojo: capturas con `grab()`, píxeles,
contrastes y ΔE. Varias de las reglas de arriba salieron de descubrir que algo
"se veía bien" y no estaba dibujándose.
