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
    backup.py                respaldos diarios y previos a migrar
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
tests/
  harness.py                 piezas comunes: copia de la base, Qt, reporte
  run_all.py                 corre cada suite en su propio proceso
  test_*.py                  una suite por área
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

### Poner las Work Orders en orden de prioridad
La lista de pendientes **es la fila de espera**: la de arriba es la que toca
correr, y la columna `#` lleva su lugar. Se acomoda seleccionando un renglón y
usando los botones de arriba:

| Botón | Qué hace | Atajo |
|---|---|---|
| **Primero** | La lleva a la cabeza de la fila | — |
| **Subir** | Un lugar hacia arriba | `Alt+↑` |
| **Bajar** | Un lugar hacia abajo | `Alt+↓` |

Una orden nueva entra **al final**: quien la captura no siempre sabe todavía si
corre antes o después que las demás. Los botones se apagan donde no aplican —en
los extremos de la lista, y en las órdenes ya comenzadas, que salen de la fila
y aparecen con `—` en vez de número—. Cada movimiento queda en el historial,
diciendo de qué lugar a cuál.

El número que se ve es la **posición**, no el valor guardado en `priority`:
comenzar o borrar una orden deja huecos en ese valor, y un hueco no significa
nada. El siguiente movimiento renumera la fila entera a 1..N.

### Agregar un solicitante (requester)
**Ajustes → Solicitantes.** La app **no trae ninguno**: son personas del
laboratorio y hay que darlas de alta. La pestaña muestra cuántas Work Orders
tiene cada una; a quien ya tiene órdenes no se le elimina, se le desactiva.

### El menú y el tamaño de las ventanas
El menú separa **Captura de pruebas** (las cuatro bitácoras, con botones más
grandes) de **Gestión y consulta** (Work Orders, Ocupación de rigs, Dashboard,
Ajustes).

Se abren **a pantalla completa** solo **Fatiga y Rotary**, que son las que
llegan a 46 columnas. Todo lo demás abre en una ventana centrada del tamaño que
necesita; los tamaños están en `COMPACT_SIZES`, en `app/ui/main_window.py`.

> Torsión y Quasi también se maximizaban, y medido eso era: **870 px de columnas
> en una ventana de 2528**, dos tercios de pantalla en blanco. Sus siete columnas
> caben en 1240.

### Qué muestra el dashboard
Cuatro tarjetas (en curso, ciclos, piezas, rigs ocupados), **tres gráficas**
—ciclos por mes, pruebas por cliente y pruebas finalizadas por tipo de ensayo—
y el panel de **piezas terminadas por banco**. Todo respeta el rango de fechas
de arriba.

Las tarjetas miden lo mismo que el resto de la app: *Pruebas en curso* suma
Fatiga y Rotary (las dos bitácoras con ciclo de vida, igual que en *Ocupación
de rigs*), *Piezas probadas* es la misma cuenta del panel de bancos, y *Rigs
ocupados* sale del mismo servicio que esa pantalla. Antes cada una contaba por
su cuenta: la pantalla de rigs decía **11** bancos ocupados y el dashboard
**10**.

La de tipo de ensayo cuenta **solo lo finalizado**: antes eran barras apiladas
de *en curso* frente a *finalizadas*, y las en curso ya están en la tarjeta
superior. La gráfica de *Uso por Test Rig* se retiró.

**Piezas terminadas por banco.** Debajo de las gráficas, un renglón por banco
del catálogo con su color, ordenados de más a menos. Cuenta **en qué banco
terminó cada pieza**, y **solo de pruebas ya cerradas**: lo que está corriendo
ahora no es trabajo hecho, y para eso está la pantalla de *Ocupación de rigs*.

- **Fatiga** anota banco por pieza, así que cada pieza va a su banco.
- **Rotary** tiene un banco por prueba: sus piezas usadas van todas ahí.
- **Torsión y Quasi** no llevan estatus —lo registrado está hecho— y sus piezas
  declaradas van al banco de la prueba.

Los bancos se cruzan por **(nombre, tipo de ensayo)**, nunca solo por el
nombre: hay un `I-25` en Torsión, otro en Quasi y otro en Rotary, y solo esos
llevan escrito de qué bitácora son.

> **Lee el subtítulo antes que las barras.** Dice cuántas piezas tienen banco
> anotado: sobre la base actual, **864 de 1,817** en lo que va de 2026. Casi
> todo lo que falta es Fatiga anterior a 2026, cuando el resultado se capturaba
> en el campo de *Test Rig*; al separarlos, la migración 008 dejó el banco
> vacío en 2,751 piezas ya cerradas. Sin ese dato, las barras se leerían como
> "estos bancos no han hecho nada", y lo que pasa es que no consta dónde
> corrieron.

Es un panel de renglones y no una gráfica de barras a propósito: con dieciséis
bancos y 1,594 piezas contra 6, las barras chicas no llegan a un píxel. Aquí
cada banco lleva su número escrito.

**El color aquí no decora.** Las cuatro tarjetas van del mismo tono: iban en
azul, verde, naranja y rojo sin que el color dijera nada, y *Rigs ocupados* en
rojo se leía como una alarma cuando es un conteo normal. En la tabla el rojo
significa *revisar* y el naranja *pieza suspendida*; gastarlos de adorno les
quita el significado que sí tienen.

Cada tipo de ensayo lleva en su barra **el color con el que aparece en el
menú**, y el pastel de clientes usa la paleta de rigs —construida justo para que
sus tonos se distingan— en vez de la rampa de azules que asignaba Qt, donde
STELLANTIS, VW, FORD y RIVIAN salían casi iguales. Muestra los cuatro primeros
clientes y suma el resto en *Otros*: se pedían ocho y en la leyenda cabían
cinco, así que las últimas porciones quedaban sin nombre.

### El idioma de la interfaz
El texto que ve el usuario lleva **tildes**: *Bitácora*, *Ocupación de rigs*,
*Días*, *Acción*, *Después*, *Regresar al menú*. En todo `app/` había **una
sola** cadena acentuada, y estaba dentro de un docstring.

El código, los comentarios y los nombres de variables **siguen en ASCII** a
propósito: son dos cosas distintas y solo una la lee el usuario.
`tests/test_ui_repaso.py` revisa los literales de `app/ui/` que llegan a la
pantalla y falla si vuelve a aparecer alguna de esas palabras sin tilde.

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
Cada pieza es un **recuadro propio** rotulado con su número, con sus cuatro
capturas dentro —**Test Rig**, **Resultado**, **Ciclos** y **Modo de falla**—,
en una rejilla de 3×3. **Las nueve se muestran siempre**, pero solo se captura
en las que la prueba declara: si *No. de piezas* dice 6, los recuadros 7, 8 y 9
quedan apagados. Subir el número los vuelve a habilitar.

Una pieza capturada **por encima** del número declarado se queda encendida y se
marca en ámbar con la etiqueta *(de mas)*, y el título del grupo dice cuántas
son. Hay registros antiguos así, y apagarlos dejaría el dato a la vista sin
manera de corregirlo. Se arregla subiendo *No. de piezas* o borrando esos datos
—al borrarlos, el recuadro se apaga solo—; nada se oculta ni se pierde.

> Antes las piezas sobrantes se "atenuaban" poniendo `color:` sobre los campos.
> Un campo vacío no tiene texto que colorear, así que lo único que cambiaba de
> color era el rótulo `Pieza N`, y el efecto era prácticamente invisible. Ahora
> se deshabilitan de verdad, y `tests/test_disabled_fields.py` lo comprueba
> midiendo píxeles, no llamadas.

### Suspender una pieza: dejar el Test Rig en blanco
Una pieza que ya está corriendo puede **suspenderse** y salir del banco, para
volver más tarde y seguir la prueba. Mientras tanto el registro tiene que poder
decir que esa pieza no está en ningún rig.

Los desplegables de pieza traen una primera opción —`(sin banco)`,
`(sin resultado)`, `(sin modo)`— que **vacía el campo**. Esa etiqueta se ve al
desplegar la lista, que es donde hace falta; con el campo cerrado se dibuja
**vacío**. Mostrarla como valor seleccionado convertía el formulario en 27
campos anunciando lo que no tienen, y un campo vacío ya se lee vacío. Sin ella no había
vuelta atrás: un desplegable cerrado de Qt no ofrece forma de regresar a "sin
selección" una vez que se elige algo, así que un Test Rig puesto por error, o
una pieza suspendida, se quedaban con banco para siempre.

El Rotary Rig de la prueba Rotary funciona igual.

Cada uno de esos cambios queda en el historial: `Pieza 1 · Test Rig`, de
`I-02-1` a `(vacio)` y de vuelta cuando la pieza regresa al banco.

**La pieza suspendida se ve naranja.** En la base, un Test Rig vaciado vuelve
como `--`, exactamente igual que una ranura que nadie usó: sin marca, una
pieza retirada a medio correr se pierde entre las vacías. Se reconoce por lo
que falta y lo que sobra —**hay ciclos y no hay banco**— y el chip pasa a
**naranja con contorno punteado**:

| Lo que se ve | Qué significa |
|---|---|
| Cuadrado con el color del rig | Corriendo en ese banco |
| **Cuadrado naranja punteado** | **Corrió y hoy no está en ningún banco** |
| Pastilla sin relleno | Ya terminó; solo consta el resultado |
| Sin chip | Ranura sin usar |

Un resultado la descarta, **salvo `Susp`**: una pieza que falló o que aguantó
terminó y no espera volver al banco, mientras que una marcada como suspendida,
por definición, no está corriendo en ninguno. Y así es como se captura en la
práctica: se vacía el Test Rig y se anota `Susp`.

El naranja es `WARNING`, que la migración 010 tiene entre los colores
reservados: ningún rig puede acercársele (el más próximo queda a ΔE 26.2), así
que un chip naranja nunca se lee como "corriendo en el banco naranja", que es
justo lo contrario de lo que dice. El contorno punteado está por si el color no
basta —el rig más cercano es un salmón— y por eso la leyenda ejemplifica
"banco" con un tono lejano y no con ese salmón.

Solo aplica a pruebas **en curso**: en una finalizada, una pieza sin banco no
espera volver, es dato histórico que nunca se capturó. En Rotary el banco es de
la prueba entera, así que vaciarlo marca de golpe todas las piezas que seguían
corriendo —y solo esas—. La misma marca sale en la vista de columnas completas
(la celda de *Test Rig* se pinta) y en el Excel, donde la celda dice
`Suspendida` y la hoja lleva la nota al pie que lo explica.

### Finalizar una prueba: se exige lo declarado
**Finalizar prueba** ya no cierra el registro con lo que haya. Antes de pedir la
fecha de fin comprueba que esté completo:

- **Datos generales**: Test Batch, Cliente, Inicio de prueba, No. de piezas y
  Tiene Work Order. *Comentarios* sigue siendo opcional.
- **Datos de las muestras**, solo **hasta la cantidad declarada**: Test Rig,
  Resultado y Ciclos de cada pieza. Si se probaron 6, de la 7 a la 9 pueden ir
  vacías.
- **Modo de falla** solo se pide a la pieza cuyo resultado es `Falla`. El
  catálogo describe *cómo* falló, no *si* falló, y exigirlo en una `S/Falla`
  sería pedir un dato inventado.

Lo que falte se lista de una vez, por pieza, en un solo aviso: pedirlo campo a
campo obliga a cerrar el mensaje, llenar uno y chocar con el siguiente.

> Al finalizar, el formulario ahora **guarda lo capturado antes de cerrar**.
> Antes `close()` solo tocaba el estatus y la fecha, así que lo que el usuario
> acabara de escribir se perdía al pulsar *Finalizar prueba*.

Mientras la prueba está *En curso* no se exige nada de esto: se guarda con lo
que se tenga, que es justo lo que permite anotar los ciclos conforme se leen y
dejar una pieza sin banco mientras está suspendida.

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
`S/Falla`, `Susp`) no llevan ninguno: lo que los separa es la **forma** del
chip — el banco va **cuadrado y relleno**, el resultado en **pastilla sin
relleno**. La única excepción es el naranja de una
[pieza suspendida](#suspender-una-pieza-dejar-el-test-rig-en-blanco), que dice
lo contrario que los demás colores: no *está corriendo aquí* sino *corrió y no
está en ningún banco*.

La paleta tiene **16 colores para 16 rigs**, elegidos por muestreo del punto
más lejano en espacio Lab con tres restricciones medibles:

| Restricción | Umbral | Real |
|---|---:|---:|
| Contraste sobre los tres fondos de fila | ≥ 3 : 1 | 3.01 : 1 |
| Distancia a los colores de la interfaz | ΔE ≥ 24 | 24.3 |
| Distancia entre dos rigs | ΔE ≥ 18 | 20.7 |

Si agregas un rig nuevo, revisa que su color cumpla lo mismo;
`tests/test_table_colors.py` lo comprueba sobre el catálogo real.

> **De dónde viene esto.** La paleta anterior eran diez tonos fríos "para dar
> familia visual". Medido, eso significaba: diez colores para dieciséis rigs
> (**cinco parejas compartían color**, así que el chip no identificaba el
> banco), su primer color era exactamente `PRIMARY` —el azul de la interfaz— y
> al ser todos azules y morados sobre un fondo azul oscuro, **los once
> distintos bajaban de 3 : 1** contra la fila seleccionada. La migración 010
> los repartió de nuevo, conservando el color de un rig cuando seguía siendo
> válido: de dieciséis, quince cambiaron y uno se quedó como estaba.

> Las migraciones 005 y 010 se conservan las dos, cada una con su copia
> **congelada** de la paleta y del criterio de su momento. Reescribir una
> migración ya aplicada cambiaría una historia que las bases existentes
> reprodujeron; y depender del código vivo haría que una base nueva no quedara
> igual que la real.

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
chips en una sola columna (10 columnas en total, en vez de 46). El botón
**Ver columnas completas** despliega una columna por banco, por resultado, por
ciclos y por modo de falla cuando necesitas leer o copiar un valor exacto. Pasa el cursor sobre
los chips para ver el detalle de cada pieza, modo de falla incluido.

En la vista completa, **las tres primeras columnas se quedan fijas** —ID, Test
Batch y Cliente— y no se van con el desplazamiento horizontal. Sin eso, al
llegar a *Test Rig 7* ya no se veía de qué prueba era la fila. Es la misma idea
que el `freeze_panes` que esta app aplica al Excel que exporta.

La columna *Muestras* **reserva siempre el ancho de las nueve piezas** (413 px
con la fuente actual), no el de la fila más ancha del momento. Así la pieza 7
cae en la misma posición en todas las filas, y una prueba de nueve piezas
capturada después no queda cortada: los anchos se miden una sola vez por juego
de columnas —para que no salten mientras se teclea en el buscador— así que
medir por contenido dejaba la columna con el tamaño de los datos que hubiera
al abrir.

### Cómo se reparte el ancho de la tabla
Las columnas se miden **una sola vez por juego de columnas** —para que no salten
mientras se teclea en el buscador— y ninguna pasa de 240 px. Lo que sobra se
reparte **en proporción a lo que mide cada una**, con dos límites: ninguna crece
a más del doble (una columna de tres dígitos a 90 px es tan absurda como el
hueco que se quiere quitar) y la de *Muestras* no se toca, porque su ancho es el
de nueve chips. El resto se lo lleva **Comentarios**.

Antes sobraba mucho y no lo usaba nadie:

| Bitácora | Antes | Ahora |
|---|---:|---:|
| Torsión | 870 px de 2528 (66% vacío) | 100% |
| Quasi | 865 px de 2528 (66% vacío) | 100% |
| Fatiga · En curso | 1491 px de 2520 (41% vacío) | 100% |
| Rotary | 1655 px de 2540 (35% vacío) | 100% |
| Fatiga · Finalizadas | 1672 px de 2508 (33% vacío) | 100% |

Y **se fueron dos columnas que no informaban de nada**: *Estatus* era constante
por construcción —`Ongoing` en las 11 filas de *En curso*, `Finished` en las 618
de *Finalizadas*— así que gastaba ancho en repetir el nombre de la pestaña, y
encima en inglés; *WO* decía lo mismo que el triángulo que ya lleva el Test
Batch. Rotary sí conserva *Estatus*, porque es la única bitácora que mezcla
pruebas abiertas y cerradas en la misma tabla; ahí dice *En curso* o
*Finalizada*, no el valor crudo que guarda la base.

En Torsión, Quasi y Rotary el banco va como **chip** y no pintando la celda
entera: son 400 filas con el mismo `T-7243`, y el relleno completo era un bloque
de color de arriba abajo que no distinguía nada. En Fatiga el color se sigue
aplicando a la celda en la vista de 46 columnas, donde la rejilla densa se lee
como un mapa.

### Abrir un registro, y los atajos de teclado
Un registro se abre con **doble clic**, con **Enter** sobre la fila, con el botón
**Abrir registro** o con el **menú del botón derecho**. Los tres últimos son
nuevos: antes solo estaba el doble clic y eso no lo decía nadie —sin botón, sin
menú y sin barra de estado no hay forma de descubrirlo—.

| Atajo | Qué hace |
|---|---|
| `Ctrl+F` | Cursor al buscador |
| `F5` | Recargar la pantalla |
| `Esc` | Regresar al menú |
| `Ctrl+N` | Nuevo registro / Nueva Work Order |
| `Ctrl+E` | Exportar a Excel (Fatiga en curso) |
| `Alt+↑` `Alt+↓` | Subir o bajar una Work Order |
| `Enter` | Abrir el registro seleccionado |

Antes había **dos atajos en toda la app**, y los dos eran para reordenar Work
Orders.

### Los colores de la tabla
Cada estado de fila tiene su color, y **ninguno es `PRIMARY`**:

| Estado | Color | |
|---|---|---|
| Fila | `#34495E` | |
| Franja alterna | `#43617E` | ΔE 10.9 contra la fila (antes 5.7) |
| Seleccionada | `#2C3E70` | ΔE 20.1, más una barra de 3 px en `PRIMARY` a la izquierda |
| Encabezado | `#223343` | rótulo en `PRIMARY`, 5.26 : 1 |

**La selección se queda oscura a propósito.** Antes era `#5DADE2`, *el mismo
valor* que el encabezado, y al ser un azul claro mataba todo lo que llevaba
encima: el semáforo de *Días* caía a **1.05 : 1** —invisible— y los once
colores de rig del catálogo bajaban de 3 : 1, dos de ellos idénticos al fondo
de la selección. En un tema oscuro, un relleno claro obliga a rediseñar todo lo
que va encima; lo que hace inconfundible la fila no es el relleno, es la barra.

El encabezado dejó de ser un bloque macizo de `PRIMARY`, que competía con el
resto de la pantalla; ahora `PRIMARY` significa una sola cosa: **activo o con
foco**.

> Cuidado al tocar estos valores: los colores de rig se eligieron para
> contrastar sobre **los tres** fondos de fila. La primera versión se generó
> solo contra la fila normal y la selección, y al aclarar la franja alterna
> nueve de dieciséis se quedaron por debajo del mínimo justo en esa franja.
> `tests/test_table_colors.py` lo comprueba.

### Saber qué prueba lleva demasiado tiempo
La columna **Días** de la pestaña *En curso* lleva semáforo. Los umbrales no
están escritos en el código: salen del percentil 75 y 95 de las pruebas ya
cerradas de esa misma bitácora, así que se ajustan solos si cambia el ritmo del
laboratorio. Con los datos actuales de Fatiga: hasta 12 días normal, 13–28
atención, 29 o más revisar. En la pestaña *Finalizadas* la misma columna
muestra cuánto duró la prueba, **sin semáforo** —antes salía toda en verde, que
es como decir "todas bien" cuando no se está midiendo nada.

El nivel se dibuja como un **punto de color** junto al número, no tiñendo el
número. El color del texto es lo primero que se pierde cuando la fila cambia de
fondo; un punto es una forma sólida y aguanta cualquier fila. El nivel viaja en
su propio rol del modelo (`DAYS_LEVEL_ROLE`) y lo pinta `DaysBadgeDelegate`.

### Saber qué rig está libre
Menú → **Ocupación de rigs**. Una tarjeta por banco del catálogo, con lo que
corre en él y desde cuándo. Los bancos se distinguen por nombre *y* tipo de
ensayo: el `I-25` de Torsión, el de Quasi y el de Rotary son tres bancos
distintos.

Cada tarjeta lleva, junto al tipo de ensayo, **cuántas piezas ha terminado**
ese banco en toda la historia —el mismo dato que el panel del dashboard, que
sí respeta el rango de fechas—. Responde de un vistazo "este banco está
libre, y ha sacado esto".

### Ver quién cambió un registro
Las columnas son **Fecha, Usuario, Acción, Campo, Antes y Después**. El
nombre del equipo va en el tooltip del usuario: era una columna entera para
un dato que casi nunca se busca.

Abre el registro y pulsa **Ver historial**. El historial completo está en
**Ajustes → Base de datos → Historial completo**.

Se guarda el nombre de la columna, que es lo correcto para la base pero
ilegible en pantalla, así que la ventana lo traduce:

| En la base | En el historial |
|---|---|
| `test_rig3` | Pieza 3 · Test Rig |
| `failure_mode1` | Pieza 1 · Modo de falla |
| `cycles7` | Pieza 7 · Ciclos |
| `wo_status` = `1` / `0` | Tiene Work Order = Sí / No |
| `test_status` = `Ongoing` | Estatus = En curso |
| `--`, `NULL` o vacío | `(vacio)` |

Ese último importa: una pieza que sale del banco se guarda como `--`, y
mostrarlo tal cual hacía pensar que el valor nuevo eran literalmente dos
guiones.

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
- Las columnas `failure_mode1..9` y `result1..9` se agregaron con `ALTER TABLE`
  (migraciones 006 y 008) y guardan **NULL** cuando no se capturan. Las viejas
  usan `"--"` y `0` para lo mismo, que es lo que obliga a `_has_content()` a
  existir. Al no tener historia detrás, no había motivo para heredar esa
  convención.
- **Una migración no debe depender de código vivo.** La 005 importaba la paleta
  y el criterio de choque de `app.services.catalogs`, y eso hacía que una
  migración ya aplicada cambiara de comportamiento cada vez que se tocaba la
  paleta: una base nueva no habría quedado igual que la real. Ahora lleva una
  copia congelada de ambos. La 008 hace lo mismo con los tres resultados de
  muestra.
- `work_orders.priority` (migración 009) es un entero donde el número más bajo
  va primero. A las órdenes que ya existían se les repartió por antigüedad, que
  es el orden en que se venían mostrando: nadie vio un cambio al abrir la app.

## Estado

Migración aplicada sobre la base real el **29/08/2026**:

- `db/test_records.db` migrada, con 1104 registros intactos
  (628 fatiga, 13 rotary, 400 torsión, 63 quasi)
- 16 copias de conflicto movidas a `db/_conflictos/2026-08-29/`
- La app anterior en Tkinter fue eliminada tras validar la nueva
- Respaldo previo completo en
  `../_respaldo_fatigue-logbook_2026-08-29_203131`

Esquema actual: **`user_version = 10`** (02/09/2026).

Contraste con la app anterior: 647,487,325 ciclos y 2,843 piezas en pruebas
finalizadas — idénticos en ambas versiones, y verificados de nuevo tras cada
migración posterior (006, 008 y 009).

### Respaldo antes de migrar

El respaldo diario se hacía **después** de aplicar las migraciones, así que la
copia de un día con migración guardaba la base ya migrada: si algo salía mal no
había a dónde volver. Ahora, cuando `migrations.pending()` devuelve algo,
`main.py` copia la base a `db backups/pre-migracion/` **antes** de tocarla. Es
una copia con marca de tiempo aparte de la diaria, porque la diaria no se
repite si la app ya se abrió ese día.

## Pruebas

```powershell
python tests\run_all.py            # las 18 suites
python tests\run_all.py priority   # solo las que lleven 'priority' en el nombre
```

Cada archivo corre en su propio proceso: varias necesitan una `QApplication` y
dos no conviven en el mismo intérprete. `tests/harness.py` tiene lo común, y
sus dos reglas salieron de tropezar con ellas:

1. **Nunca contra la base real.** `AppContext.prepare()` aplica migraciones,
   así que una prueba que abriera `db/test_records.db` la dejaba migrada antes
   de que nadie hubiera sacado un respaldo. `database_copy()` trabaja sobre una
   copia temporal.
2. **Nada de contar filas fijas.** La app está en uso y la base crece. Una
   prueba que espere "10 registros en curso" falla la semana que viene sin que
   nada esté mal: se comprueba contra lo que diga la base.

`tests/test_rig_usage.py` cubre las piezas por banco y la ocupación: primero
con datos armados a mano, donde se sabe la respuesta —una prueba cerrada, una
abierta que no debe contar, una pieza sin banco, y los tres `I-25` que no se
deben mezclar—, y luego contra la base real, comprobando que la pantalla de
rigs y el dashboard dicen el mismo número.

`tests/test_ui_repaso.py` es la que cuida el repaso de interfaz: mide que las
columnas llenen la ventana, que ninguna repita el mismo valor en todas las
filas, que las congeladas sigan en su sitio tras desplazar, que no vuelva a
aparecer texto sin tildes, que el dashboard no gaste el rojo ni el naranja de
adorno, que cada pantalla tenga sus atajos y que un desplegable en blanco se
dibuje en blanco —eso último contando píxeles, no llamadas—.

## Resuelto: el banco y el resultado ya no comparten columna

Hasta la migración 008, las columnas `test_rig1..9` de `fatigue_tests`
guardaban dos cosas distintas: **2,777 resultados de muestra contra 45 nombres
de banco**. El formulario anterior ofrecía `Falla`/`Susp`/`S/Falla` en el
desplegable de Test Rig — por el bug de lectura del Excel — y el equipo usó esa
columna para anotar si la pieza había fallado.

La migración 008 agregó `result1..9` y movió ahí esos valores, dejando
`test_rigN` solo para bancos. Ahora cada pieza puede decir a la vez **dónde
corrió y cómo acabó**, que antes era imposible:

| Columna | Qué guarda |
|---|---|
| `test_rigN` | El banco de pruebas, del catálogo de Rigs |
| `resultN` | `Falla`, `S/Falla` o `Susp` |
| `cyclesN` | Los ciclos que aguantó |
| `failure_modeN` | El modo de falla, del diccionario de Ajustes |

En el formulario son cuatro campos por pieza; en la vista completa, cuatro
columnas; en el Excel, cuatro también. En la vista compacta el chip toma el
**color del banco** y su **forma** dice de qué se tiene constancia: cuadrado si
se sabe dónde corrió, pastilla si solo se anotó el resultado — que es el caso de
casi todo lo anterior a 2026 — y cuadrado naranja punteado si la pieza está
suspendida, fuera de banco.

El aviso de **Ocupación de rigs** ("valores fuera del catálogo") ya no se llena
de resultados: lo que aparezca ahí ahora es un banco de verdad que falta del
catálogo.

## Pendientes

- **Definir el recurso de red** donde vivirá la base. Mientras tanto corre en
  local. Al moverla, actualiza `database_path` en `settings.json` o usa
  **Ajustes → Base de datos**.
- **Probar concurrencia** una vez esté el recurso: abrir la app en dos equipos
  y guardar a la vez unas diez veces. Ninguno debe fallar y no deben aparecer
  archivos `-2`, `-3`.
- La carpeta `Extras/` se conserva como referencia histórica; ya no la usa nada.
