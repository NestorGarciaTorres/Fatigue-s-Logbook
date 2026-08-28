# Funciones declaradas en otro archivo
from forms.edit_fatigue_form import EditFatigueForm
from logbooks.fatigue_cmplt_logbook import FatigueCMPLTLogbook

#Librerias de TKIner
import tkinter as tk
import tkinter.font as tkFont
from tkinter import messagebox

#Librerias de bootstrap
import ttkbootstrap as ttk
from ttkbootstrap.tableview import Tableview
from ttkbootstrap import Style, Button

#Librearias de SQL
import sqlite3
from contextlib import closing
import os

class FatigueLogbook:
    def __init__(self, master, main_root_ref):
    # CONFIGURACIÓN DE LA VENTANA
        self.root = master
        self.root.protocol("WM_DELETE_WINDOW", self.exit_program)
        self.main_root = main_root_ref
        self.root.title("Bitácora Fatiga")
        self.root.state("zoomed")
        
        # ----- CONFIGURACIÓN DE ESTILOS Y TIPOS DE LETRA
        # Estilo de componentes
        style = Style("superhero")
        
        # Estilo de botones
        btn_font = tkFont.Font(family="Roboto", size=12, weight="bold") 
        style.configure("primary.Outline.TButton", font=btn_font) # Color azul con outline
        style.configure("secondary.TButton", font=btn_font) # Color gris del boton
        style.configure("success.Outline.TButton", font=btn_font)
        style.configure("info.Outline.TButton", font=btn_font)
        
        # Estilo de tabla de datos
        table_font = tkFont.Font(family="Roboto",size=12)
        style.configure("Custom.Treeview", font=table_font, rowheight=32)
    
    # DETECTAR ALGUN ERROR DURANTE LA CREACIÓN DE LOS COMPONENTES
        try:
            ttk.Label(self.root, text="--- | FATIGAS | ACTUALMENTE CORRIENDO ---", font=("Roboto",24,"bold"), bootstyle="info").pack(pady=10)
            
        # ----- SECCIÓN 1 - BOTÓN NUEVO REGISTRO -----    
            # Frame
            frame_section_1 = ttk.Frame(self.root)
            frame_section_1.pack(pady=10, padx=20, fill="x")
            
            # Botón - nuevo registro
            Button(frame_section_1, text="Nuevo registro",bootstyle="primary-outline",command=self.open_fatigue_form, cursor="hand2").pack(side="left")
            # Botón - visualizar datos completos
            Button(frame_section_1, text="Ver todo", bootstyle="primary-outline",command=self.open_fatigue_cmplt_logbook, cursor="hand2").pack(side="right")
        
        # ----- SECCIÓN 2 - CREACIÓN DE TABLA -----
            # Definir campos de la tabla, el ajuste de texto y su ancho de columna
            coldata = [
                        {"text": "ID", "anchor": "center", "width": 60},
                        {"text": "Test Batch", "anchor": "center", "width": 150},
                        {"text": "Customer", "anchor": "center", "width": 150},
                        {"text": "Start Date", "anchor": "center", "width": 150},
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
            
            # Recolección de todos los registros dentro de la base de datos (Llenado de filas)
            rowdata = []
            for row in self.fetch_fatigue_data():
                row = list(row)
                if str(row[24]) == "0":
                    row[1] = "⚠️ " + str(row[1]) # Se pone el simbolo de warning a aquellos registros que no tienen WO
                rowdata.append(row)
            
            # Creación de la tabla de datos
            self.table = Tableview(
                master=self.root,
                coldata=coldata,
                rowdata=rowdata,
                paginated=True,
                searchable=True,
                autoalign=False,
                pagesize = 20,
                bootstyle="PRIMARY",
                autofit=False,
                stripecolor=("#2c3e50", "white")
            )
            
            # Configuración de la tabla
            self.table.view.configure(style="Custom.Treeview") # Definición de tipo y tamaño de letra
            style.configure("Custom.Treeview.Heading", font=("Roboto",12,"bold"), background=style.colors.primary, foreground="white")
            self.table.pack(fill="both", expand=True)
            
        # ----- SECCIÓN 3 - BOTÓN DE REGRESO -----
            frame_section_3 = ttk.Frame(self.root)
            frame_section_3.pack(pady=20, padx=20, fill="x")
            Button(frame_section_3, text="Regresar", bootstyle="secondary",command=self.back_to_main, cursor="hand2").pack(side="left")
            
        # ----- Evento en tree al dar doble click sobre un registro
            self.table.view.bind("<Double-1>", self.on_double_click)
            
            self.new_fatigue_window = None
            self.cmplt_fatigue_records = None
        except Exception as e:
            print("Ocurrio un error: ",e)
            input("Presiona enter para salir")
    
    def open_fatigue_form(self):
        if self.new_fatigue_window is None or not self.new_fatigue_window.winfo_exists():
            self.new_fatigue_window = tk.Toplevel(self.root)
            conn = sqlite3.connect("./db/test_records.db")
            EditFatigueForm(self.new_fatigue_window, self, None, self.refresh_and_show, conn, False, False)
         
    
    def open_fatigue_cmplt_logbook(self):
        # Guardar monitor en el que se está trabajando
        
        self.root.withdraw()
        if self.cmplt_fatigue_records is None or not self.cmplt_fatigue_records.winfo_exists():
            self.cmplt_fatigue_records = tk.Toplevel(self.root)
            from tools.utils import get_monitor_geometry_for_window, position_window_on_monitor
            self.original_monitor = get_monitor_geometry_for_window(self.root)
            monitor = get_monitor_geometry_for_window(self.root)
            position_window_on_monitor(self.cmplt_fatigue_records, monitor)
            FatigueCMPLTLogbook(self.cmplt_fatigue_records, self)
    
    def back_to_main(self):
        self.root.destroy()
        self.main_root.deiconify()
    
    def on_double_click(self, event):
        selected_item = self.table.view.selection()
        if selected_item:
            item_id = selected_item[0]
            values = self.table.view.item(item_id, "values")

            if values:
                self.new_fatigue_window = tk.Toplevel(self.root)
                conn = sqlite3.connect("./db/test_records.db")
                EditFatigueForm(self.new_fatigue_window, self, values, self.refresh_and_show, conn, True, False)
            else:
                messagebox.showwarning("Advertencia", "No se pudo obtener el registro seleccionado.")
    
# ---- FUNCIONES PARA MOSTRAR LOS DATOS DE LA BASE DE DATOS EN LA TABLA
    def refresh_and_show(self):
        new_data = self.fetch_fatigue_data()
        self.table.view.delete(*self.table.view.get_children())
        for row in new_data:
            row = list(row)
            if str(row[24]) == "0":
                row[1] = "⚠️ " + str(row[1])
            self.table.view.insert("","end", values=row)
        
    
    def fetch_fatigue_data(self):
        database_path = os.path.abspath("./db/test_records.db")
        
        with closing(sqlite3.connect(database_path)) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("""SELECT id,test_batch, customer, start_date, qty_samples, comments,
                                test_rig1, cycles1, test_rig2, cycles2, test_rig3, cycles3,
                                test_rig4, cycles4, test_rig5, cycles5, test_rig6, cycles6,
                                test_rig7, cycles7, test_rig8, cycles8, test_rig9, cycles9,
                                wo_status, test_status
                                FROM fatigue_tests
                                WHERE test_status='Ongoing'
                                ORDER BY id DESC
                                """)
                
                rows = cursor.fetchall()
                conn.commit()
        return rows
    
    def exit_program(self):
        import sys
        self.root.destroy()
        sys.exit()
    



