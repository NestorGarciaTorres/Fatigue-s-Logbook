"""El solicitante, de punta a punta.

El requester vivia solo en la Work Order. Para saber quien pidio un ensayo
habia que ir a la orden, y las pruebas anteriores a las Work Orders no tienen
ninguna a la que ir. Ahora se copia al registro, que es lo que se consulta
durante anios.

Se comprueba en las cuatro capas por las que pasa el dato: la base lo guarda,
la migracion lo hereda de la orden donde se puede saber, el formulario lo trae
al comenzar la prueba, la tabla lo ensenia y lo busca, y el Excel lo lleva.
"""

from harness import Report, make_context, offscreen, qt_app

offscreen()

import sqlite3
from datetime import date
from pathlib import Path
from tempfile import mkdtemp

from openpyxl import load_workbook

from app.db import migrations
from app.models import (
    DIRECT_ENTRY_TEST_TYPES,
    ONGOING,
    QUASI,
    SAMPLE_SLOTS,
    STARTABLE_TEST_TYPES,
    TEST_TYPES,
    TORSION,
    FatigueSample,
    FatigueTest,
    GenericTest,
    RotarySample,
    RotaryTest,
    WorkOrder,
)
from app.services import filtering
from app.services.excel_export import export_fatigue_ongoing
from app.ui.dialogs.fatigue_dialog import FatigueDialog
from app.ui.dialogs.generic_dialog import GenericDialog
from app.ui.dialogs.rotary_dialog import RotaryDialog
from app.ui.models.table_models import (
    FatigueTableModel,
    GenericTableModel,
    RotaryTableModel,
)
from app.ui.pages.generic_page import GenericPage
from app.ui.widgets.common import combo_value

AUTHOR = ("verificador", "PC-PRUEBA")
report = Report("El solicitante en el registro de la prueba")

app = qt_app()
context = make_context()

QUIEN = context.catalogs.requesters()
if not QUIEN:
    # El catalogo nace vacio: son personas del laboratorio. Para la prueba se
    # da de alta una, que es lo que haria quien la usa.
    from app.models import Requester
    context.catalogs.save_requester(Requester(name="Ana Torres"))
    QUIEN = context.catalogs.requesters()
SOLICITANTE = QUIEN[0]


# ======================================================================
report.section("1. La base lo guarda en las cuatro bitacoras")

fatiga = FatigueTest(
    test_batch="999880STF01", customer="AUDI", requester=SOLICITANTE,
    start_date=date(2026, 9, 1), qty_samples=1, test_status=ONGOING,
    samples=[FatigueSample(rig=context.catalogs.rig_names("fatigue")[0],
                           cycles=100)]
            + [FatigueSample() for _ in range(SAMPLE_SLOTS - 1)],
)
fatiga_id = context.fatigue.create(fatiga, AUTHOR)
report.check("fatiga guarda y relee el solicitante",
             context.fatigue.get(fatiga_id).requester == SOLICITANTE,
             repr(context.fatigue.get(fatiga_id).requester))

rotary = RotaryTest(
    test_batch="999881SRF01", customer="AUDI", requester=SOLICITANTE,
    start_date=date(2026, 9, 1), qty_samples=1, test_status=ONGOING,
    test_rig=context.catalogs.rig_names("rotary")[0],
    samples=[RotarySample(revs=10)]
            + [RotarySample() for _ in range(SAMPLE_SLOTS - 1)],
)
rotary_id = context.rotary.create(rotary, AUTHOR)
report.check("rotary tambien",
             context.rotary.get(rotary_id).requester == SOLICITANTE)

# El Test Batch lleva la clave de tres letras de su tipo de ensayo: se toma
# del catalogo en vez de inventarla, que es lo que valida el formulario.
BATCH = {clave: f"99988{i}{context.catalogs.codes(clave)[0]}01"
         for i, clave in enumerate(TEST_TYPES, start=1)}

for config, repo in ((TORSION, context.torsion), (QUASI, context.quasi)):
    generico = GenericTest(
        test_batch=BATCH[config.key],
        customer="AUDI", requester=SOLICITANTE, test_date=date(2026, 9, 1),
        qty_samples=1, test_rig=context.catalogs.rig_names(config.key)[0],
    )
    nuevo_id = repo.create(generico, AUTHOR)
    report.check(f"{config.key} tambien",
                 repo.get(nuevo_id).requester == SOLICITANTE)

# Vaciarlo tiene que poder deshacerse: se guarda NULL, no la cadena vacia, para
# que la columna diga "no se capturo" y no "se capturo un vacio".
sin_nadie = context.fatigue.get(fatiga_id)
sin_nadie.requester = ""
context.fatigue.update(sin_nadie, AUTHOR)
report.check("se puede dejar sin solicitante",
             context.fatigue.get(fatiga_id).requester == "",
             repr(context.fatigue.get(fatiga_id).requester))
crudo = sqlite3.connect(str(context.database.path)).execute(
    "SELECT requester FROM fatigue_tests WHERE id = ?", (fatiga_id,)
).fetchone()[0]
report.check("y en la base queda NULL, no una cadena vacia", crudo is None,
             repr(crudo))


# ======================================================================
report.section("2. La migracion lo hereda de la Work Order")

# Se llama a la migracion directamente y no via migrate(): la copia ya viene
# migrada, y lo que se quiere comprobar es la regla, no el runner. Es
# idempotente, asi que correrla otra vez no estropea nada.
orden = WorkOrder(test_type="fatigue", test_batch="999882STF01",
                  customer="AUDI", qty_samples=1, requester=SOLICITANTE)
orden_id = context.work_orders.create(orden, AUTHOR)
nacida = FatigueTest(test_batch="999882STF01", customer="AUDI",
                     start_date=date(2026, 9, 1), qty_samples=1)
nacida_id = context.fatigue.create(nacida, AUTHOR)
context.work_orders.mark_started(orden_id, nacida_id, AUTHOR)

# Una prueba de torsion con el mismo id que la de fatiga: si el cruce no
# filtrara por tipo de ensayo, heredaria el solicitante que no le toca.
gemela = GenericTest(test_batch=f"999883{context.catalogs.codes('torsion')[0]}01",
                     customer="AUDI",
                     test_date=date(2026, 9, 1), qty_samples=1)
gemela_id = context.torsion.create(gemela, AUTHOR)
sqlite3.connect(str(context.database.path)).execute(
    "UPDATE torsion_tests SET id = ? WHERE id = ?", (nacida_id, gemela_id)
).connection.commit()

with context.database.connect() as conn:
    migrations._migration_012_requester(conn)

report.check("la prueba nacida de una orden hereda su solicitante",
             context.fatigue.get(nacida_id).requester == SOLICITANTE,
             repr(context.fatigue.get(nacida_id).requester))
report.check("y la prueba de otro tipo con el mismo id no lo hereda",
             not context.torsion.get(nacida_id).requester,
             repr(context.torsion.get(nacida_id).requester))

# Segunda pasada: no debe pisar lo que alguien haya corregido a mano.
corregida = context.fatigue.get(nacida_id)
corregida.requester = "Otra persona"
context.fatigue.update(corregida, AUTHOR)
with context.database.connect() as conn:
    migrations._migration_012_requester(conn)
report.check("y no pisa una correccion hecha a mano",
             context.fatigue.get(nacida_id).requester == "Otra persona",
             context.fatigue.get(nacida_id).requester)


# ======================================================================
report.section("3. El formulario lo trae de la Work Order")

for tipo in sorted(STARTABLE_TEST_TYPES):
    report.check(f"una WO de {tipo} se puede comenzar",
                 WorkOrder(test_type=tipo).can_start)

pedido = WorkOrder(test_type="fatigue", test_batch="999884STF01",
                   customer="AUDI", qty_samples=2, requester=SOLICITANTE)
dialogo = FatigueDialog(context.fatigue, context.catalogs, context.audit,
                        work_order=pedido)
report.check("fatiga precarga el solicitante de la orden",
             combo_value(dialogo.requester) == SOLICITANTE,
             combo_value(dialogo.requester))
report.check("y lo recoge al guardar",
             dialogo._collect().requester == SOLICITANTE)

pedido_rotary = WorkOrder(test_type="rotary", test_batch="999885SRF01",
                          customer="AUDI", qty_samples=1,
                          requester=SOLICITANTE)
rdialogo = RotaryDialog(context.rotary, context.catalogs, context.audit,
                        work_order=pedido_rotary)
report.check("rotary igual",
             rdialogo._collect().requester == SOLICITANTE)

torsion_batch = f"999886{context.catalogs.codes('torsion')[0]}01"
pedido_torsion = WorkOrder(test_type="torsion", test_batch=torsion_batch,
                           customer="AUDI", qty_samples=1,
                           requester=SOLICITANTE)
gdialogo = GenericDialog(context.torsion, context.catalogs, context.audit,
                         TORSION, work_order=pedido_torsion)
report.check("torsion tambien, con el mismo formulario de siempre",
             gdialogo._collect().requester == SOLICITANTE)
report.check("y el titulo dice que viene de una orden",
             "WO" in gdialogo.windowTitle(), gdialogo.windowTitle())
report.check("el batch de la orden se precarga",
             gdialogo._collect().test_batch == torsion_batch,
             gdialogo._collect().test_batch)

# Guardar desde ahi tiene que dejar el id a la vista: es lo que la pantalla de
# Work Orders necesita para enlazar la orden con el registro.
gdialogo._save()
report.check("al guardar publica el id del registro creado",
             gdialogo.created_id is not None, str(gdialogo.created_id))
if gdialogo.created_id:
    report.check("y el registro guardado lleva el solicitante",
                 context.torsion.get(gdialogo.created_id).requester
                 == SOLICITANTE)


# ======================================================================
report.section("4. El alta directa la conserva solo Torsion")

report.check("torsion mantiene su boton de alta",
             "torsion" in DIRECT_ENTRY_TEST_TYPES)
pagina_torsion = GenericPage(context, TORSION)
report.check("y la pagina lo construye",
             pagina_torsion.new_button is not None)

pagina_quasi = GenericPage(context, QUASI)
report.check("quasi ya no: su prueba nace de una Work Order",
             pagina_quasi.new_button is None)
report.check("y no se deja un boton apagado en su lugar",
             not any(w.text() == "Nuevo registro"
                     for w in pagina_quasi.findChildren(type(
                         pagina_torsion.new_button))))


# ======================================================================
report.section("5. La tabla lo ensenia y la busqueda lo encuentra")

modelos = {
    "fatigue": FatigueTableModel(context.catalogs, show_end_date=False),
    "rotary": RotaryTableModel(context.catalogs),
    "generico": GenericTableModel(context.catalogs),
}
for nombre, modelo in modelos.items():
    report.check(f"{nombre}: la tabla tiene columna Requester",
                 "Requester" in modelo.headers, str(modelo.headers))

conmigo = context.fatigue.get(fatiga_id)
conmigo.requester = SOLICITANTE
context.fatigue.update(conmigo, AUTHOR)
modelo = modelos["fatigue"]
modelo.set_records([context.fatigue.get(fatiga_id)])
columna = modelo.headers.index("Requester")
report.check("y ensenia el valor en su celda",
             modelo.data(modelo.index(0, columna)) == SOLICITANTE,
             repr(modelo.data(modelo.index(0, columna))))

encontrados = filtering.apply(
    context.fatigue.list(ONGOING),
    filtering.TestFilters(search=SOLICITANTE.split()[0]),
)
report.check("la busqueda encuentra por solicitante",
             any(t.id == fatiga_id for t in encontrados),
             f"{len(encontrados)} registros")


# ======================================================================
report.section("6. El Excel lo lleva")

destino = Path(mkdtemp(prefix="bitacora_xlsx_")) / "reporte.xlsx"
export_fatigue_ongoing(context.fatigue.list(ONGOING),
                       context.catalogs.colors(), destino)
hoja = load_workbook(destino).active
cabeceras = [c.value for c in hoja[2]]
report.check("el reporte trae la columna Requester",
             "Requester" in cabeceras, str(cabeceras[:8]))

columna_excel = cabeceras.index("Requester") + 1
fila = next(f for f in range(3, hoja.max_row + 1)
            if hoja.cell(row=f, column=1).value == fatiga_id)
report.check("con el solicitante de la prueba",
             hoja.cell(row=fila, column=columna_excel).value == SOLICITANTE,
             repr(hoja.cell(row=fila, column=columna_excel).value))

raise SystemExit(report.finish())
