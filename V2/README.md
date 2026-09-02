# Bitácora de Pruebas (Fatigue Logbook)

Aplicación de escritorio para llevar las bitácoras de ensayos mecánicos:
**Fatiga**, **Torsión**, **Rotary** y **Quasi**.

Migrada de Tkinter/ttkbootstrap a **PySide6**, sobre una arquitectura por capas.

---

## Requisitos

- **Python 3.13** (verificado con 3.13.14; las ruedas de PySide6 son `cp39-abi3`)

```powershell
winget install --id Python.Python.3.13 --source winget
```

## Instalación

```powershell
cd "C:\Users\...\fatigue-logbook"
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Puesta en marcha (una sola vez)

```powershell
# 1. Elegir cuál de los .db es el bueno (solo lectura, no modifica nada)
python tools/pick_database.py

# 2. Archivar las copias de conflicto de OneDrive
python tools/pick_database.py --archive db/test_records.db

# 3. Migrar los catálogos de Auxiliar.xlsx a la base de datos
python tools/import_excel_catalogs.py --dry-run   # revisar
python tools/import_excel_catalogs.py             # aplicar
```

## Uso

```powershell
python main.py
```

Sin consola: `pythonw main.py`, o un acceso directo a
`.venv\Scripts\pythonw.exe main.py`.

---

## Configuración

`settings.json` en la raíz del proyecto:

```json
{
  "database_path": "db/test_records.db",
  "backup_dir": "db backups",
  "backup_keep": 30,
  "auto_backup": true
}
```

- `database_path` — ruta absoluta o relativa a la raíz del proyecto. Para el
  recurso de red usa la forma UNC: `\\\\servidor\\compartido\\test_records.db`
- `backup_keep` — cuántos respaldos diarios conservar
- También se cambia desde **Ajustes → Base de datos** dentro de la app

> **Importante:** la base **no** debe vivir en una carpeta sincronizada
> (OneDrive, SharePoint, Dropbox). Es lo que generó los archivos
> `test_records-DLCELPC303-2.db`, `-3`, `-4`: copias de conflicto que parten los
> datos en dos. Va en un recurso SMB sin sincronización.

---

## Estructura

```
main.py                      punto de entrada
settings.json                ruta de la BD (fuera del código)
app/
  config.py                  ajustes persistentes
  dates.py                   conversión dd/MM/yyyy <-> date
  models.py                  dataclasses del dominio
  context.py                 arma repositorios y servicios
  db/
    connection.py            conexión SQLite afinada para SMB
    migrations.py            migraciones por PRAGMA user_version
    repositories.py          todo el SQL del proyecto
  services/
    catalogs.py              catálogos en memoria + colores de rig
    validation.py            reglas de test batch, duplicados
    filtering.py             filtros y búsqueda
    identity.py              usuario de Windows para la auditoría
    excel_export.py          reporte de fatigas en curso
    backup.py                respaldos diarios
  ui/
    theme.py                 QSS estilo "superhero"
    main_window.py           QStackedWidget
    models/                  QAbstractTableModel por bitácora
    widgets/                 tabla, barra de filtros, tarjetas
    pages/                   menú, work orders, bitácoras, dashboard, ajustes
    dialogs/                 alta/edición, cierre, historial
tools/
  pick_database.py           elige y archiva los .db
  import_excel_catalogs.py   Auxiliar.xlsx -> tablas de catálogo
```

**Regla de la arquitectura:** nada en `ui/` ejecuta SQL. Las páginas piden
dataclasses a los repositorios; los repositorios son lo único que toca
`sqlite3`.

---

## Tareas frecuentes

### Dar de alta una Work Order y comenzar la prueba
**Menú → Work Orders.** Es el documento que autoriza una prueba, capturado
antes de que la prueba exista: tipo de ensayo, Test Batch, cliente, número de
piezas y **requester** (quien la solicita, del catálogo de Ajustes).

Quien corre la prueba pulsa **Comenzar prueba** en su renglón. Se abre el
formulario de la bitácora con esos datos ya puestos; falta la fecha de inicio
—que arranca en hoy— y los bancos, ciclos y modos de falla que se tengan. Al
guardar, el registro entra en *En curso* y la orden queda **Comenzada**,
enlazada al registro que la originó (`→ #629`). El filtro de arriba muestra
*Pendientes* por omisión.

Los datos precargados **quedan editables**: si el Test Batch de la orden trae
una errata, quien corre la prueba puede corregirla sin volver a Work Orders.

> **Fatiga y Rotary ya no tienen botón «Nuevo registro».** Sus pruebas nacen de
> una Work Order. El formulario es el mismo de siempre, solo cambia desde dónde
> se abre. Torsión y Quasi siguen dando de alta por su cuenta: sus órdenes se
> pueden registrar, pero el renglón dice *alta en su bitácora* en vez de
> ofrecer el botón.

Una orden ya comenzada no se edita ni se elimina desde aquí: es el rastro de
quién la solicitó y cuándo se preparó, y cambiarla dejaría la orden y la prueba
diciendo cosas distintas.

### Agregar un solicitante (requester)
**Ajustes → Solicitantes.** La app **no trae ninguno**: son personas del
laboratorio y hay que darlas de alta. La pestaña muestra cuántas Work Orders
tiene cada una; a quien ya tiene órdenes no se le elimina, se le desactiva.

### El menú y el tamaño de las ventanas
El menú separa **Captura de pruebas** (las cuatro bitácoras, con botones más
grandes) de **Gestión y consulta** (Work Orders, Ocupación de rigs, Dashboard,
Ajustes).

Solo las cuatro bitácoras se abren **a pantalla completa**: son las que tienen
tablas anchas, hasta 37 columnas en vista completa. El menú, Work Orders, el
dashboard, la ocupación de rigs y los ajustes abren en una ventana centrada del
tamaño que necesitan; a pantalla completa quedaban con más vacío que contenido.
Los tamaños están en `COMPACT_SIZES`, en `app/ui/main_window.py`.

### Qué muestra el dashboard
Cuatro tarjetas (en curso, ciclos, piezas, rigs ocupados) y **tres gráficas**:
ciclos por mes, pruebas por cliente y **pruebas finalizadas por tipo de
ensayo**. Todas respetan el rango de fechas de arriba.

La de tipo de ensayo cuenta **solo lo finalizado**: antes eran barras apiladas
de *en curso* frente a *finalizadas*, y las en curso ya están en la tarjeta
superior. La gráfica de *Uso por Test Rig* se retiró.

### El texto de los formularios va centrado
Todos los campos de captura —cajas de texto, fechas y desplegables— alinean su
contenido al centro, también las opciones de la lista desplegada.

> Los desplegables cerrados necesitaron una subclase (`CenteredComboBox`). Qt
> pinta el valor de un combo no editable con `CE_ComboBoxLabel`, que alinea a la
> izquierda y no acepta cambio: ni la hoja de estilos ni el modelo llegan a esa
> alineación. La alternativa habitual —volverlo editable con un `QLineEdit` de
> solo lectura— haría que `isEditable()` respondiera `True` y cambiaría cómo se
> cargan los valores fuera de catálogo, así que solo se reemplaza el dibujado.

### Capturar las piezas de una prueba
Cada pieza es un **recuadro propio** rotulado con su número, con sus tres
capturas dentro, en una rejilla de 3×3. **Las nueve se muestran siempre**, sin
depender de *No. de piezas*: se captura sobre cualquiera sin tener que ajustar
antes el número.

Una pieza capturada **por encima** del número declarado se marca en ámbar con la
etiqueta *(de mas)*, y el título del grupo dice cuántas son. Hay registros
antiguos así. Se corrige subiendo *No. de piezas* o borrando esos datos; nada se
oculta ni se pierde por el camino.

> Antes las piezas sobrantes se "atenuaban" poniendo `color:` sobre los campos.
> Un campo vacío no tiene texto que colorear, así que lo único que cambiaba de
> color era el rótulo `Pieza N`, y el efecto era prácticamente invisible. La
> marca ámbar sobre el recuadro sí se ve.

### Los campos de "Datos generales"
Van en **tres columnas**, alineadas con la rejilla de las muestras, en tres
filas en vez de siete. Antes eran una sola lista vertical donde el campo de
*No. de piezas* medía lo mismo que el de comentarios. La fecha de fin ocupa el
final de la segunda fila, así que cuando no aplica —toda prueba en curso— el
hueco queda en el borde y no parte la rejilla.

### Agregar un Test Rig o cambiar su color
**Ajustes → Rigs y colores.** Doble clic en la columna *Color*. El cambio se
refleja de inmediato en las bitácoras, el dashboard y el reporte de Excel.

**El color es solo de los bancos.** Los resultados de pieza (`Falla`,
`S/Falla`, `Susp`) no llevan ninguno: banco y resultado comparten el mismo
campo y lo que los separa es la **forma** del chip — el banco va **cuadrado y
relleno**, el resultado en **pastilla sin relleno**. Como no hay tonos
reservados, cualquier color vale para un banco; la paleta se mantiene en tonos
fríos solo por coherencia visual entre bancos.

> La migración 005 recoloreó en su día los rigs cuyo tono chocaba con el rojo,
> el verde o el ámbar de los resultados. Esa migración se conserva tal cual
> —reescribirla cambiaría una historia que las bases existentes ya
> aplicaron— pero ahora usa su propia copia congelada de la paleta y del
> criterio, en vez de importarlos del código vivo.

### Editar el diccionario de modos de falla
**Ajustes → Modos de falla.** Al capturar una pieza de Fatiga o de Rotary,
además del banco/resultado y los ciclos se elige su **modo de falla** de esta
lista. Describe *cómo* falló la pieza; para decir *si* falló están los estatus
`Falla` / `S/Falla` / `Susp`. Si la pieza no falló, el campo se deja vacío.

Los siete modos que trae la app al instalarse (`Fractura`, `Fisura`,
`Deformacion permanente`, `Desgaste`, `Aflojamiento`, `Fuga`,
`Falla de soldadura`) son **genéricos, para que el desplegable no nazca vacío**:
la idea es reemplazarlos por la nomenclatura del laboratorio.

La pestaña muestra cuántas muestras usan cada modo. Un modo en uso no se puede
eliminar — dejaría esos registros con un valor que ya no está en la lista —
pero sí se puede **desactivar** para retirarlo del desplegable sin perder lo ya
capturado. Renombrarlo cambia solo la lista: el modo se guarda como texto en
cada muestra, así que las ya capturadas conservan el nombre anterior, y la app
lo advierte antes de hacerlo.

### Agregar un cliente o una clave de prueba
**Ajustes → Clientes** / **Ajustes → Claves.** Las claves son las tres letras
del Test Batch (`STF`, `SRF`, ...); solo se aceptan las de esa lista.

### Exportar las fatigas en curso
Bitácora de Fatiga, pestaña **En curso**, botón **Exportar a Excel**. Respeta
los filtros activos y aplica el color de cada rig a sus celdas. Cada muestra
ocupa tres columnas: `Test Rig N`, `Ciclos N` y `Modo falla N`.

### Cambiar entre vista compacta y completa
Fatiga y Rotary abren en **vista compacta**: las 9 muestras se dibujan como
chips en una sola columna (10 columnas en total, en vez de 37). El botón
**Ver columnas completas** despliega una columna por rig, por ciclos y por modo
de falla cuando necesitas leer o copiar un valor exacto. Pasa el cursor sobre
los chips para ver el detalle de cada pieza, modo de falla incluido.

La columna *Muestras* **reserva siempre el ancho de las nueve piezas** (413 px
con la fuente actual), no el de la fila más ancha del momento. Así la pieza 7
cae en la misma posición en todas las filas, y una prueba de nueve piezas
capturada después no queda cortada: los anchos se miden una sola vez por juego
de columnas —para que no salten mientras se teclea en el buscador— así que
medir por contenido dejaba la columna con el tamaño de los datos que hubiera
al abrir.

### Saber qué prueba lleva demasiado tiempo
La columna **Días** de la pestaña *En curso* lleva semáforo. Los umbrales no
están escritos en el código: salen del percentil 75 y 95 de las pruebas ya
cerradas de esa misma bitácora, así que se ajustan solos si cambia el ritmo del
laboratorio. Con los datos actuales de Fatiga: hasta 12 días normal, 13–28
atención, 29 o más revisar. En la pestaña *Finalizadas* la misma columna
muestra cuánto duró la prueba, sin semáforo.

### Saber qué rig está libre
Menú → **Ocupación de rigs**. Una tarjeta por banco del catálogo, con lo que
corre en él y desde cuándo. Los bancos se distinguen por nombre *y* tipo de
ensayo: el `I-25` de Torsión, el de Quasi y el de Rotary son tres bancos
distintos.

### Ver quién cambió un registro
Abre el registro y pulsa **Ver historial**. El historial completo está en
**Ajustes → Base de datos → Historial completo**.

---

## Formato del Test Batch

6 dígitos + clave de 3 letras + 2 dígitos. Ejemplo: `242314STF09`.

---

## Notas de la migración

- `logbook_torsion.py` y `logbook_quasi.py` eran copias idénticas salvo seis
  cadenas: ahora son una sola `GenericPage` parametrizada.
- `fatigue_curr_logbook.py` y `fatigue_cmplt_logbook.py` eran dos ventanas con
  la misma consulta: ahora son dos pestañas de `FatiguePage`.
- La marca `⚠️` de pruebas sin Work Order era texto pegado al Test Batch, que
  había que quitar con `.replace()` antes de editar. Ahora es un ícono de
  columna y el dato queda limpio.
- El combo de rig de Rotary se construía con `values="I-25"` (una cadena, no una
  lista), así que ofrecía `I`, `-`, `2`, `5` como cuatro opciones. Ahora sale
  del catálogo.
- En `Auxiliar.xlsx`, las celdas B11:B13 de la columna *Fatigue Rigs* no son
  rigs: son los resultados de muestra `Falla`, `Susp` y `S/Falla`. Como el
  código hacía `df["Fatigue Rigs"].dropna().tolist()`, aparecían en el
  desplegable de bancos de prueba. Ahora van a `sample_statuses` y el catálogo
  de fatiga tiene los 10 rigs reales.
- Las fechas siguen guardándose como texto `dd/MM/yyyy` para no romper los
  registros existentes; la app las convierte a `date` en el borde.
- `work_orders.started_test_id` apunta a la fila de la bitácora que salió de
  esa orden, pero **no es una clave foránea**: la tabla destino depende de
  `test_type`, y SQLite no admite una referencia condicional.
- Las columnas `failure_mode1..9` se agregaron con `ALTER TABLE` (migración
  006) y son las únicas columnas de muestra que guardan **NULL** cuando no se
  capturan. Las viejas usan `"--"` y `0` para lo mismo, que es lo que obliga a
  `_has_content()` a existir. Al no tener historia detrás, no había motivo para
  heredar esa convención.

## Estado

Migración aplicada sobre la base real el **29/08/2026**:

- `db/test_records.db` migrada a `user_version = 7`, con 1104 registros intactos
  (628 fatiga, 13 rotary, 400 torsión, 63 quasi)
- 16 copias de conflicto movidas a `db/_conflictos/2026-08-29/`
- La app anterior en Tkinter fue eliminada tras validar la nueva
- Respaldo previo completo en
  `../_respaldo_fatigue-logbook_2026-08-29_203131`

Contraste con la app anterior: 647,487,325 ciclos y 2,843 piezas en pruebas
finalizadas — idénticos en ambas versiones, y verificados de nuevo tras la
migración 006 (01/09/2026).

## Hallazgo abierto: las columnas `test_rigN` de Fatiga

En `fatigue_tests`, las columnas `test_rig1..9` contienen:

| Valor | Veces |
|---|---:|
| `--` (vacío) | 2,831 |
| `Falla` | 1,818 |
| `S/Falla` | 945 |
| `Susp` | 14 |
| Nombres de rig reales | **44** |

Es decir, **2,777 resultados de muestra contra 44 rigs**. Como el formulario
anterior ofrecía `Falla`/`Susp`/`S/Falla` en el desplegable de Test Rig (por el
bug del Excel), el equipo ha usado esa columna para registrar si cada pieza
falló, no en qué banco corrió.

Mientras se decide qué hacer, los chips y las celdas colorean lo que haya:
color de rig si el valor está en el catálogo, y si no, color de resultado
(`Falla` rojo, `S/Falla` verde, `Susp` ámbar).

Opciones, de menor a mayor alcance:

1. **Dejarlo así.** Aceptar que en Fatiga esa columna significa "resultado" y
   renombrarla en la interfaz.
2. **Separar el dato:** agregar `result1..9` al esquema y migrar los 2,777
   valores, dejando `test_rigN` solo para bancos. Es lo correcto, y permitiría
   por fin saber qué rig corrió cada pieza.
3. **Ambos:** migrar y además capturar el rig de aquí en adelante.

## Pendientes

- **Definir el recurso de red** donde vivirá la base. Mientras tanto corre en
  local. Al moverla, actualiza `database_path` en `settings.json` o usa
  **Ajustes → Base de datos**.
- **Probar concurrencia** una vez esté el recurso: abrir la app en dos equipos
  y guardar a la vez unas diez veces. Ninguno debe fallar y no deben aparecer
  archivos `-2`, `-3`.
- La carpeta `Extras/` se conserva como referencia histórica; ya no la usa nada.
