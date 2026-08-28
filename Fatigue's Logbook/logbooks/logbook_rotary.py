# - Llamada a otros archivos
#from forms.generic_form import GenericForm
from forms.edit_rotary_form import EditRotaryForm
# - Librerias de base de datos
import sqlite3
from contextlib import closing

# - Libreria de TKInter y TTKBootstrap
import tkinter as tk
import tkinter.font as tkFont
from tkinter import StringVar
from tkinter import messagebox

import ttkbootstrap as ttk
from ttkbootstrap.tableview import Tableview
from ttkbootstrap import Style, Button

# - Librerias de sistema
import calendar
import sys
import os

class RotaryLogbook:
    def __init__(self, master, main_root_ref):
        self.root = master
        self.root.protocol("WM_DELETE_WINDOW", self.exit_program)
        self.main_root = main_root_ref
        self.root.title("Pruebas de | Rotary | finalizadas")
        self.root.state("zoomed")
        
    # ----- CONFIGURACIÓN DE ESTILOS Y TIPOS DE LETRA
        # Estilo de componentes
        style = Style("superhero")
        
        # Estilo de botones
        font_components = tkFont.Font(family="Roboto", size=12, weight="bold") 
        style.configure("primary.Outline.TButton", font=font_components) # Color azul con outline
        style.configure("secondary.TButton", font=font_components) # Color gris del boton
        style.configure("success.Outline.TButton", font=font_components) # Color gris del boton
        
        # Estilo de tabla de datos
        table_font = tkFont.Font(family="Roboto",size=12)
        style.configure("Custom.Treeview", font=table_font, rowheight=32)
        
        # Configuración del form de ingreso de nuevo registro y su modificación
        self.form_config = ["rotary_tests", "ROTARY", "Rotary Codes", "#f08080", "danger", "Rotary Tests"]

        ttk.Label(self.root, text="--- PRUEBAS DE | ROTARY | ACTUALMENTE CORRIENDO ---", font=("Roboto",24,"bold"), bootstyle="danger").pack(pady=10)
    
    # -VARIABLES PARA FILTROS DE MES Y AÑO
        self.selected_month = StringVar(value="Todos")
        self.selected_year = StringVar(value="Todos")
        
        months = ["Todos"] + [calendar.month_name[i] for i in range(1,13)]
        years = ["Todos"] + [str(y) for y in range(2020,2031)]    

    # -FRAME PARA LOS COMPONENTES DE FILTROS
        frame_filters = ttk.Frame(self.root)
        frame_filters.pack(pady=10, padx=10, fill="x")
        
        # -FRAME PARA EL BOTON DE NUEVO REGISTRO
        Button(frame_filters, text="Nuevo registro",bootstyle="danger-outline", command=self.open_rotary_form, cursor="hand2").pack(side="left", padx=(0,50))
        
        ttk.Label(frame_filters, text="Mes: ", font=font_components, width=4).pack(side="left", padx=5)
        self.month_combo = ttk.Combobox(frame_filters, textvariable=self.selected_month,values=months, width=12, font=font_components, bootstyle="danger")
        self.month_combo.set("Todos")
        self.month_combo.pack(side="left", padx=10)
        
        ttk.Label(frame_filters, text="Año: ", font=font_components, width=4).pack(side="left", padx=5)
        self.year_combo = ttk.Combobox(frame_filters, textvariable=self.selected_year,values=years, width=6, font=font_components, bootstyle="danger")
        self.year_combo.set("Todos")
        self.year_combo.pack(side="left", padx=10)
        
        self.label_total_samples = ttk.Label(frame_filters, text="2", font=("Roboto",22,"bold"),bootstyle="info")
        self.label_total_samples.pack(padx=10, side="right")
        
        self.update_totals()
        
        try:
            # ---- CREACIÓN DE TABLA DE DATOS
            # Obtener los registros de la base de datos
            rowdata = self.fetch_rotary_data()
            # Definir las columnas/encabezados de la tabla de datos 
            self.coldata = [
                                {"text": "ID", "anchor": "center", "width": 150},
                                {"text": "Test Batch", "anchor": "center", "width": 150},
                                {"text": "Customer", "anchor": "center", "width": 150},
                                {"text": "Start Date", "anchor": "center", "width": 150},
                                {"text": "End Date", "anchor": "center", "width": 150},
                                {"text": "Qty Samples", "anchor": "center", "width": 150},
                                {"text": "Comments", "anchor": "center", "width": 150},
                                {"text": "Rotary Rig","anchor": "center", "width": 150},
                                {"text": "Revs 1","anchor": "center", "width": 150},
                                {"text": "Estatus 1","anchor": "center", "width": 150},
                                {"text": "Revs 2","anchor": "center", "width": 150},
                                {"text": "Estatus 2","anchor": "center", "width": 150},
                                {"text": "Revs 3","anchor": "center", "width": 150},
                                {"text": "Estatus 3","anchor": "center", "width": 150},
                                {"text": "Revs 4","anchor": "center", "width": 150},
                                {"text": "Estatus 4","anchor": "center", "width": 150},
                                {"text": "Revs 5","anchor": "center", "width": 150},
                                {"text": "Estatus 5","anchor": "center", "width": 150},
                                {"text": "Revs 6","anchor": "center", "width": 150},
                                {"text": "Estatus 6","anchor": "center", "width": 150},
                                {"text": "Revs 7","anchor": "center", "width": 150},
                                {"text": "Estatus 7","anchor": "center", "width": 150},
                                {"text": "Revs 8","anchor": "center", "width": 150},
                                {"text": "Estatus 8","anchor": "center", "width": 150},
                                {"text": "Revs 9","anchor": "center", "width": 150},
                                {"text": "Estatus 9","anchor": "center", "width": 150},
                                {"text": "Test Status","anchor": "center", "width": 150}
                            ]
            
            # Creación de la tabla de datos
            self.table = Tableview(
                master=self.root,
                coldata=self.coldata,
                rowdata=rowdata,
                paginated=True,
                searchable=True,
                autoalign=False,
                bootstyle="dark",
                pagesize = 20,
                autofit=False,
                stripecolor=("#2B3E50", "white")
            )
            
            # Definir el estilo de la tabla
            self.table.view.configure(style="Custom.Treeview")
            # Definir el estilo de los encabezados de la tabla
            style.configure("Custom.Treeview.Heading", font=("Roboto",12,"bold"), background="#ff6347", foreground="white")
            self.table.pack(fill="both", expand=True)
            
        # ----- FRAME BOTÓN HOME -----
            frame_btn_home = ttk.Frame(self.root)
            frame_btn_home.pack(pady=10, padx=20, fill="x")
            
            Button(frame_btn_home, text="Regresar", bootstyle="secondary",command=self.back_to_main, cursor="hand2").pack(side="left")
        # ----- Evento en tree al dar doble click sobre un registro
            #self.table.view.bind("<Double-1>", self.on_double_click)
            self.month_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_date_filters())
            self.year_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_date_filters())
            self.table.view.bind("<Double-1>", self.on_double_click)
            self.new_rotary_window = None
        
        except Exception as e:
            print("Ocurrio un error: ",e)
            input("Presiona enter para salir")
        
        
    def fetch_rotary_data(self):
        database_path = os.path.abspath("./db/test_records.db")
        
        with closing(sqlite3.connect(database_path)) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("""SELECT * FROM rotary_tests
                                ORDER BY id DESC
                                """)
                                
                rows = cursor.fetchall()

        return rows
    
    def open_rotary_form(self):
        if self.new_rotary_window is None or not self.new_rotary_window.winfo_exists():
            self.new_rotary_window = tk.Toplevel(self.root)
            conn = sqlite3.connect("./db/test_records.db")
            EditRotaryForm(self.new_rotary_window, self, None, self.refresh_and_show, conn, False, False)
    
    def on_double_click(self, event):
            selected_item = self.table.view.selection()
            if selected_item:
                item_id = selected_item[0]
                values = self.table.view.item(item_id, "values")

                if values:
                    self.new_rotary_window = tk.Toplevel(self.root)
                    conn = sqlite3.connect("./db/test_records.db")
                    EditRotaryForm(self.new_rotary_window, self, values, self.refresh_and_show, conn, True, False)
                else:
                    messagebox.showwarning("Advertencia", "No se pudo obtener el registro seleccionado.")
    
    def refresh_and_show(self):
        new_data = self.fetch_rotary_data()
        self.table.view.delete(*self.table.view.get_children())
        for row in new_data:
            row = list(row)
            self.table.view.insert("","end", values=row)
    
    def calculate_total_cycles(self):
        database_path = os.path.abspath("./db/test_records.db")
        total_cycles = 0
        total_samples = 0
        
        try:
            with closing(sqlite3.connect(database_path)) as conn:
                with closing(conn.cursor()) as cursor:
                    cursor.execute("""SELECT SUM(COALESCE(qty_samples,0))
                    FROM rotary_tests              
                    """)
            
                    result = cursor.fetchone()
                    total_samples = result[0]

        except Exception as e:
            print("Ocurrio un error: ",e)
        return total_cycles, total_samples
    
    def update_totals(self):
        total_cycles, total_samples = self.calculate_total_cycles()
        self.label_total_samples.configure(text=f"Total de piezas probadas: {total_samples if total_samples is not None else 0:,}")
        
    def apply_date_filters(self, *args):
        month = self.selected_month.get()
        year = self.selected_year.get()
        database_path = os.path.abspath("./db/test_records.db")
        rows = []
        total_cycles = 0
        total_samples = 0
        try:
            with closing(sqlite3.connect(database_path)) as conn:
                with closing(conn.cursor()) as cursor:
                    query = """SELECT * FROM rotary_tests
                                """
                    
                    params = []
                    conditions = []
                    #month_num = list(calendar.month_name).index(month)
                    if month != "Todos" and year != "Todos":
                        month_num = list(calendar.month_name).index(month)
                        conditions.append("substr(test_date, 4, 2) = ?")
                        conditions.append("substr(test_date, 7, 4) = ?")
                        #query += "WHERE substr(test_date, 4, 2) = ? AND substr(test_date, 7, 4) = ?"
                        params.extend([f"{month_num:02d}", year])
                    elif year != "Todos":
                        conditions.append("substr(test_date, 7, 4) = ?")
                        #query += " AND substr(test_date, 7, 4) = ?"
                        params.append(year)
                    elif month != "Todos":
                        month_num = list(calendar.month_name).index(month)
                        conditions.append("substr(test_date, 4, 2) = ?")
                        params.extend([f"{month_num:02d}"])
                        
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                    
                    query += " ORDER BY id DESC"
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    
                    # Totales
                    #total_cycles = sum(sum(row[i] if isinstance(row[i], int) else 0 for i in range(7, 26, 2)) for row in rows)
                    total_samples = sum(row[4] if isinstance(row[4], int) else 0 for row in rows)
        except Exception as e:
            print("Error al aplicar filtros", e)
        
        self.table.build_table_data(self.coldata, rows)
        self.label_total_samples.configure(text=f"Total de muestras probadas: {total_samples:,}")
    
    def exit_program(self):
        import sys
        self.root.destroy()
        sys.exit()
    
    def back_to_main(self):
        self.root.destroy()
        self.main_root.deiconify()
