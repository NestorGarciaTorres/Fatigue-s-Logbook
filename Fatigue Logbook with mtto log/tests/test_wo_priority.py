"""Orden de prioridad de las Work Orders.

La lista de ordenes pendientes es la fila de espera del laboratorio: la de
arriba es la que toca correr. Esta prueba cubre las dos mitades -- que el
repositorio mueva y renumere bien, y que la pantalla muestre y habilite lo que
corresponde.
"""

from harness import Report, make_context, offscreen, qt_app, settle

offscreen()

from app.models import WO_PENDING, WO_STARTED, WorkOrder
from app.ui.main_window import MainWindow

AUTHOR = ("verificador", "PC-PRUEBA")
report = Report("Prioridad de Work Orders")

app = qt_app()
context = make_context()
repo = context.work_orders

# --- se parte de un juego propio, sin depender de lo que haya en la base ---
lotes = ["999811STF01", "999812STF02", "999813STF03", "999814STF04"]
creadas = []
for n, lote in enumerate(lotes, start=1):
    creadas.append(repo.create(
        WorkOrder(test_type="fatigue", test_batch=lote, customer="AUDI",
                  qty_samples=n, requester="Prueba",
                  priority=repo.next_priority()),
        AUTHOR,
    ))
primera, segunda, tercera, cuarta = creadas


def fila():
    return [o.id for o in repo.pending_in_order()]


report.section("1. Una orden nueva entra al final de la fila")
report.check("las cuatro se anexaron en el orden en que se capturaron",
             fila()[-4:] == creadas, str(fila()[-4:]))
report.check("next_priority no repite el ultimo valor",
             repo.next_priority() > max(o.priority
                                        for o in repo.pending_in_order()))

report.section("2. Subir y bajar")
antes = fila()
report.check("subir mueve un lugar", repo.move(cuarta, -1, AUTHOR))
report.check("la cuarta paso delante de la tercera",
             fila()[-2:] == [cuarta, tercera], str(fila()[-2:]))
report.check("bajar la devuelve a su sitio",
             repo.move(cuarta, 1, AUTHOR) and fila() == antes,
             str(fila()[-4:]))

report.section("3. Los extremos no se mueven")
cabeza = repo.pending_in_order()[0].id
cola = repo.pending_in_order()[-1].id
report.check("la primera no puede subir", not repo.move(cabeza, -1, AUTHOR))
report.check("la ultima no puede bajar", not repo.move(cola, 1, AUTHOR))
report.check("un id que no existe no revienta",
             not repo.move(999_999, -1, AUTHOR))

report.section("4. Al frente")
report.check("move_to_top la pone de primera",
             repo.move_to_top(cuarta, AUTHOR)
             and repo.pending_in_order()[0].id == cuarta)
report.check("la que ya es primera no se mueve",
             not repo.move_to_top(cuarta, AUTHOR))
resto = [i for i in fila() if i != cuarta]
report.check("las demas conservan su orden relativo",
             resto == [i for i in antes if i != cuarta], str(resto[-4:]))

report.section("5. Las prioridades quedan sin huecos")
prioridades = [o.priority for o in repo.pending_in_order()]
report.check("son 1..N contiguas",
             prioridades == list(range(1, len(prioridades) + 1)),
             str(prioridades))

report.section("6. Una orden comenzada sale de la fila")
# Se marca comenzada con un id de prueba cualquiera: aqui solo interesa que
# deje de ocupar lugar, no de donde salio el registro.
repo.mark_started(segunda, 1, AUTHOR)
report.check("ya no aparece entre las pendientes",
             segunda not in fila(), str(fila()))
report.check("y no se deja reordenar", not repo.move(segunda, -1, AUTHOR))
# Comenzar una orden deja un hueco en el valor guardado -- se lleva su numero
# consigo -- y eso no importa: lo que ordena es que sigan creciendo, y lo que
# se ve en pantalla es la posicion, no el valor.
restantes = [o.priority for o in repo.pending_in_order()]
report.check("el hueco no rompe el orden",
             restantes == sorted(restantes) and len(set(restantes)) == len(restantes),
             str(restantes))
report.check("y el siguiente movimiento vuelve a dejarlas 1..N",
             repo.move(repo.pending_in_order()[-1].id, -1, AUTHOR)
             and [o.priority for o in repo.pending_in_order()]
             == list(range(1, repo.pending_count() + 1)),
             str([o.priority for o in repo.pending_in_order()]))

report.section("7. Queda rastro en el historial")
cambios = [e for e in context.audit.search(limit=200) if e.field == "prioridad"]
report.check("cada movimiento se auditó", len(cambios) >= 3, f"{len(cambios)}")
report.check("dice de que lugar a cual",
             all(c.old_value and c.new_value for c in cambios[:3]),
             str([(c.old_value, c.new_value) for c in cambios[:3]]))

report.section("8. La pantalla")
window = MainWindow(context)
window.show_page("work_orders")
page = window.pages["work_orders"]
settle(app)

report.check("hay una columna de prioridad",
             page.HEADERS[page.PRIORITY_COLUMN] == "#")
report.check("la columna de accion sigue al final",
             page.ACTION_COLUMN == len(page.HEADERS) - 1)

page.status_filter.setCurrentText(WO_PENDING + "s")
settle(app)
mostradas = [
    page.table.item(r, page.PRIORITY_COLUMN).text()
    for r in range(page.table.rowCount())
]
report.check("numera 1, 2, 3... por posicion, sin huecos",
             mostradas == [str(i) for i in range(1, len(mostradas) + 1)],
             str(mostradas))

report.check("el Test Batch se corrio a la columna siguiente",
             page.table.item(0, 2).text()
             == repo.pending_in_order()[0].test_batch,
             page.table.item(0, 2).text())

report.section("9. Los botones se habilitan donde tienen sentido")
page.table.selectRow(0)
settle(app)
report.check("en la primera fila no se puede subir",
             not page.up_button.isEnabled() and not page.first_button.isEnabled())
report.check("pero si bajar", page.down_button.isEnabled())

ultima_fila = page.table.rowCount() - 1
page.table.selectRow(ultima_fila)
settle(app)
report.check("en la ultima no se puede bajar", not page.down_button.isEnabled())
report.check("pero si subir y saltar al frente",
             page.up_button.isEnabled() and page.first_button.isEnabled())

report.section("10. Mover desde la pantalla conserva la seleccion")
elegida = page._orders[ultima_fila]
page.move_order(-1)
settle(app)
report.check("la orden subio una fila",
             page._orders[ultima_fila - 1].id == elegida.id,
             page._orders[ultima_fila - 1].test_batch)
report.check("y sigue seleccionada, lista para otro clic",
             page.table.currentRow() == ultima_fila - 1,
             f"fila {page.table.currentRow()}")

page.move_to_top()
settle(app)
report.check("'Primero' la lleva arriba", page._orders[0].id == elegida.id)
report.check("la seleccion la sigue hasta arriba",
             page.table.currentRow() == 0, f"fila {page.table.currentRow()}")

report.section("11. Las comenzadas se muestran sin lugar en la fila")
page.status_filter.setCurrentText("Todas")
settle(app)
comenzadas = [
    page.table.item(r, page.PRIORITY_COLUMN).text()
    for r, order in enumerate(page._orders) if order.is_started
]
report.check("hay alguna comenzada para comprobarlo", bool(comenzadas),
             str(comenzadas))
report.check("se muestran con raya, no con numero",
             all(t == "—" for t in comenzadas), str(comenzadas))

fila_comenzada = next(r for r, o in enumerate(page._orders) if o.is_started)
page.table.selectRow(fila_comenzada)
settle(app)
report.check("y con una comenzada seleccionada no hay boton activo",
             not any(b.isEnabled() for b in (page.up_button, page.down_button,
                                             page.first_button)))

raise SystemExit(report.finish())
