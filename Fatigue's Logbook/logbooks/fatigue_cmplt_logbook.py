# - Llamada a otros archivos
from forms.edit_fatigue_form import EditFatigueForm

# - Librerias de base de datos
import sqlite3
from contextlib import closing

# - Librerias TKInter y TTKBootstrap
import tkinter as tk
import tkinter.font as tkFont
from tkinter import StringVar
from tkinter import messagebox

import ttkbootstrap as ttk
from ttkbootstrap import Style, Button
from ttkbootstrap.tableview import Tableview

# - Librerias del sistema
import os
import calendar

class FatigueCMPLTLogbook:
    def __init__(self, master, parent):
        self.root = master
        self.root.protocol("WM_DELETE_WINDOW", self.exit_program)
        self.parent = parent
        self.root.title("Pruebas de Fatiga finalizadas")
        self.root.state("zoomed")
        
    # ----- CONFIGURACIÓN DE ESTILOS Y TIPOS DE LETRA
        # Estilo de componentes
        style = Style("superhero")
        
        # Estilo de botones
        font_components = tkFont.Font(family="Roboto", size=12, weight="bold") 
        style.configure("primary.Outline.TButton", font=font_components) # Color azul con outline
        style.configure("secondary.TButton", font=font_components) # Color gris del boton
        style.configure("info.TButton", font=font_components)
        
        # Estilo de tabla de datos
        table_font = tkFont.Font(family="Roboto",size=12)
        style.configure("Custom.Treeview", font=table_font, rowheight=32)

        ttk.Label(self.root, text="--- PRUEBAS DE FATIGA FINALIZADAS ---", font=("Roboto",24,"bold"), bootstyle="info").pack(pady=10)

    # -VARIABLES PARA FILTROS DE MES Y AÑO
        self.selected_month = StringVar(value="Todos")
        self.selected_year = StringVar(value="Todos")
        
        months = ["Todos"] + [calendar.month_name[i] for i in range(1,13)]
        years = ["Todos"] + [str(y) for y in range(2020,2031)]
        
    # -FRAME PARA LOS COMPONENTES DE FILTROS
        frame_filters = ttk.Frame(self.root)
        frame_filters.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(frame_filters, text="Mes: ", font=font_components, width=4).pack(side="left", padx=5)
        self.month_combo = ttk.Combobox(frame_filters, textvariable=self.selected_month,values=months, width=12, font=font_components)
        self.month_combo.set("Todos")
        self.month_combo.pack(side="left", padx=10)
        
        ttk.Label(frame_filters, text="Año: ", font=font_components, width=4).pack(side="left", padx=5)
        self.year_combo = ttk.Combobox(frame_filters, textvariable=self.selected_year,values=years, width=6, font=font_components)
        self.year_combo.set("Todos")
        self.year_combo.pack(side="left", padx=10)
        
        self.label_total_cycles = ttk.Label(frame_filters, text="1", font=("Roboto",22,"bold"),bootstyle="info")
        self.label_total_cycles.pack(padx=10, side="right")
        
        self.label_total_samples = ttk.Label(frame_filters, text="2", font=("Roboto",22,"bold"),bootstyle="info")
        self.label_total_samples.pack(padx=10, side="right")
        
        self.update_totals()

    # CREACIÓN DE LA TABLA DE DATOS
        try:
            self.coldata = [
            {"text": "ID", "anchor": "center", "width": 60},
            {"text": "Test Batch", "anchor": "center", "width": 150},
            {"text": "Customer", "anchor": "center", "width": 150},
            {"text": "Start Date", "anchor": "center", "width": 150},
            {"text": "End Date", "anchor": "center", "width": 150},
            {"text": "Qty Samples", "anchor": "center", "width": 150},
            {"text": "Comments", "anchor": "center", "width": 150},
            {"text": "Test Rig 1","anchor": "center", "width": 150},
            {"text": "Cycles 1", "anchor": "center", "width": 150},
            {"text": "Test Rig 2", "anchor": "center", "width": 150},
            {"text": "Cycles 2", "anchor": "center", "width": 150},
            {"text": "Test Rig 3", "anchor": "center", "width": 150},
            {"text": "Cycles 3", "anchor": "center", "width": 150},
            {"text": "Test Rig 4", "anchor": "center", "width": 150},
            {"text": "Cycles 4", "anchor": "center", "width": 150},
            {"text": "Test Rig 5", "anchor": "center", "width": 150},
            {"text": "Cycles 5", "anchor": "center", "width": 150},
            {"text": "Test Rig 6", "anchor": "center", "width": 150},
            {"text": "Cycles 6", "anchor": "center", "width": 150},
            {"text": "Test Rig 7", "anchor": "center", "width": 150},
            {"text": "Cycles 7", "anchor": "center", "width": 150},
            {"text": "Test Rig 8", "anchor": "center", "width": 150},
            {"text": "Cycles 8", "anchor": "center", "width": 150},
            {"text": "Test Rig 9", "anchor": "center", "width": 150},
            {"text": "Cycles 9", "anchor": "center", "width": 150},
            {"text": "WO Status", "anchor": "center", "width": 150},
            {"text": "Test Status", "anchor": "center", "width": 150},
            ]
        
            rowdata = self.fetch_fatigue_data()
        
            style.configure("Custom.Treeview", font=table_font, rowheight=32)
            
            self.table = Tableview(
                master=self.root,
                coldata=self.coldata,
                rowdata=rowdata,
                paginated=True,
                searchable=True,
                autoalign=False,
                bootstyle="PRIMARY",
                pagesize = 20,
                autofit=False,
                stripecolor=("#2B3E50", "white")
            )
        
            self.table.view.configure(style="Custom.Treeview")
            style.configure("Custom.Treeview.Heading", font=("Roboto",12,"bold"), background="#6ec6ff", foreground="white")
            self.table.pack(fill="both", expand=True)
            
        # - FRAME PARA BOTON A HOME (PRUEBAS CORRIENDO)
            frame_btn_home = ttk.Frame(self.root)
            frame_btn_home.pack(pady=10, padx=10, fill="x")
            
            Button(frame_btn_home, text="Regresar", bootstyle="secondary", command=self.back_to_main, cursor="hand2").pack(side="left")
            #Button(frame_btn_home, text="Quitar de finalizados", bootstyle="info", command=self.sent_back_record, cursor="hand2").pack(side="right")
        # ----- Evento en tree al dar doble click sobre un registro
            self.table.view.bind("<Double-1>", self.on_double_click)
            self.month_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_date_filters())
            self.year_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_date_filters())
            
            self.show_fatigue_record = None
        except Exception as e:
            print("Ocurrio un error: ",e)
            input("Presiona enter para salir")
            
    
    def back_to_main(self):
        from tools.utils import get_monitor_geometry_for_window, position_window_on_monitor
        
        #monitor = get_monitor_geometry_for_window(self.root)
        self.root.destroy()
        self.parent.root.deiconify()
        position_window_on_monitor(self.parent.root, self.parent.original_monitor)
        self.parent.root.state("zoomed")
        self.parent.cmplt_fatigue_records = None
        
        if hasattr(self.parent, "refresh_and_show"):
            self.parent.refresh_and_show()
        
    def fetch_fatigue_data(self):   
        database_path = os.path.abspath("./db/test_records.db")
        
        with closing(sqlite3.connect(database_path)) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("""SELECT id,test_batch, customer, start_date, end_date, qty_samples, comments,
                                test_rig1, cycles1, test_rig2, cycles2, test_rig3, cycles3,
                                test_rig4, cycles4, test_rig5, cycles5, test_rig6, cycles6,
                                test_rig7, cycles7, test_rig8, cycles8, test_rig9, cycles9,
                                wo_status, test_status
                                FROM fatigue_tests
                                WHERE test_status='Finished'
                                ORDER BY id DESC
                                """)
                
                
                rows = cursor.fetchall()
        return rows
    
    def calculate_total_cycles(self):
        database_path = os.path.abspath("./db/test_records.db")
        total_cycles = 0
        total_samples = 0
        
        try:
            with closing(sqlite3.connect(database_path)) as conn:
                with closing(conn.cursor()) as cursor:
                    cursor.execute("""SELECT COALESCE(SUM(COALESCE(cycles1,0) + COALESCE(cycles2,0) + COALESCE(cycles3,0) +
                    COALESCE(cycles4,0) + COALESCE(cycles5,0) + COALESCE(cycles6,0) +
                    COALESCE(cycles7,0) + COALESCE(cycles8,0) + COALESCE(cycles9,0)), 0),
                    COALESCE(SUM(qty_samples), 0)
                    FROM fatigue_tests
                    WHERE test_status = 'Finished'
                    """)
            
                    result = cursor.fetchone()
                    total_cycles = result[0]
                    total_samples = result[1]

        except Exception as e:
            print("Ocurrio un error: ",e)
        return total_cycles, total_samples
     
    def update_totals(self):
        total_cycles, total_samples = self.calculate_total_cycles()
        self.label_total_cycles.configure(text=f"Total de ciclos: {total_cycles:,}")
        self.label_total_samples.configure(text=f"Total de piezas probadas: {total_samples:,}")
    
    def sent_back_record(self):
        selected_item = self.table.view.focus()
        if not selected_item:
            return
        
        item_data = self.table.view.item(selected_item)
        row_values = item_data['values']
        record_id = row_values[0]
        
        confirm = messagebox.askyesno("Confirmación", f"¿Deseas quitar el Test Batch -> {row_values[1]} de la sección de pruebas finalizadas?")
        if confirm:
            self.mark_as_ongoing(record_id)
        
        self.back_to_main()
        
    def mark_as_ongoing(self, record_id):
        database_path = os.path.abspath("./db/test_records.db")
        try:
            with closing(sqlite3.connect(database_path)) as conn:
                with closing(conn.cursor()) as cursor:
                    cursor.execute("""
                        UPDATE fatigue_tests
                        SET test_status = 'Ongoing'
                        WHERE id = ?
                    """, (record_id,))
                    conn.commit()
            messagebox.showinfo("Éxito", "El registro ha sido marcado como 'En curso'.")
            self.apply_date_filters()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo actualizar el registro: {e}")
    
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
                    query = """SELECT id, test_batch, customer, start_date, end_date, qty_samples, comments,
                                test_rig1, cycles1, test_rig2, cycles2, test_rig3, cycles3,
                                test_rig4, cycles4, test_rig5, cycles5, test_rig6, cycles6,
                                test_rig7, cycles7, test_rig8, cycles8, test_rig9, cycles9,
                                wo_status, test_status
                                FROM fatigue_tests
                                WHERE test_status='Finished'
                                """
                    
                    params = []
                    conditions = []
                    #month_num = list(calendar.month_name).index(month)
                    if month != "Todos" and year != "Todos":
                        month_num = list(calendar.month_name).index(month)
                        conditions.append("substr(end_date, 4, 2) = ?")
                        conditions.append("substr(end_date, 7, 4) = ?")
                        #query += "WHERE substr(test_date, 4, 2) = ? AND substr(test_date, 7, 4) = ?"
                        params.extend([f"{month_num:02d}", year])
                    elif year != "Todos":
                        conditions.append("substr(end_date, 7, 4) = ?")
                        #query += " AND substr(test_date, 7, 4) = ?"
                        params.append(year)
                    elif month != "Todos":
                        month_num = list(calendar.month_name).index(month)
                        conditions.append("substr(end_date, 4, 2) = ?")
                        params.extend([f"{month_num:02d}"])
                        
                    if conditions:
                        query += " AND " + " AND ".join(conditions)
                    
                    query += " ORDER BY id DESC"
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    
                    # Totales
                    total_cycles = sum(sum(row[i] if isinstance(row[i], int) else 0 for i in range(8, 26, 2)) for row in rows)
                    def safe_int(value):
                        try:
                            return int(value)
                        except (ValueError, TypeError):
                            return 0
                    total_samples = sum(safe_int(row[5]) for row in rows)
        except Exception as e:
            print("Error al aplicar filtros", e)
        
        self.table.build_table_data(self.coldata, rows)
        self.label_total_cycles.configure(text=f"Total de ciclos: {total_cycles:,}")
        self.label_total_samples.configure(text=f"Total de muestras probadas: {total_samples:,}")
    
    def exit_program(self):
        import sys
        self.root.destroy()
        sys.exit()
        
    def on_double_click(self, event):
        selected_item = self.table.view.selection()
        if selected_item:
            item_id = selected_item[0]
            values =  self.table.view.item(item_id, "values")
            
            if values:
                self.show_fatigue_record = tk.Toplevel(self.root)
                conn = sqlite3.connect("./db/test_records.db")
                EditFatigueForm(self.show_fatigue_record, self, values, self.refresh_and_show, conn, True, True)
            else:
                messagebox.showwarning("Advertencia", "No se pudo obtener el registro seleccionado.")
    
    def refresh_and_show(self):
        new_data = self.fetch_fatigue_data()
        self.table.view.delete(*self.table.view.get_children())
        for row in new_data:
            row = list(row)
            self.table.view.insert("","end", values=row)