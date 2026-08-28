# - Librerias de archivos
from tools.utils import center_window
from tools.close_fatigue_record import CloseFatigueWindow

# - Libreria de lectura de archivos excel
import pandas as pd

# - Libreria de Interfaces
from datetime import datetime
from tkinter import messagebox

# - Libreria de SQL
import sqlite3
from contextlib import closing

# - Librerias bootstrap
import tkinter as tk
import ttkbootstrap as ttk
import tkinter.font as tkFont
from ttkbootstrap import Style, Button, DateEntry

# - Librerias del sistema
import re
import os

class EditFatigueForm:
    def __init__(self, master, parent, edit_data, refresh_callback, db_conn, edit_mode, show_info_mode):
    # CONFIGURACIÓN DE LA VENTANA TOP LEVEL
        self.root = master
        self.parent = parent
        self.root.title("Nuevo registro - Fatiga")
        #self.root.configure(fg_color="517891")
        center_window(self.root, 1100, 820)
        
    # ASIGNACIÓN DE VARIABLES HEREDADAS
        self.db_conn = db_conn
        self.refresh_callback = refresh_callback
        self.edit_data = edit_data
        self.edit_mode = edit_mode
        
        self.show_info_mode = show_info_mode
        # Cambiar texto de labels dependiendo de si está activo el modo edición o no
        if self.edit_mode == True:
            self.edit_id = self.edit_data[0]
            text_btn_save = "Guardar Cambios"
            if self.show_info_mode:
                text_top_label = "-------- | PRUEBA FINALIZADA | --------"
            else:
                text_top_label = "-------- EDITAR FATIGA --------"
        else:
            text_btn_save = "Ingresar Registro"
            text_top_label = "-------- INGRESAR NUEVO REGISTRO --------"
        
        # Importar información de clientes y rigs de archivo excel
        df = pd.read_excel("./excel_files/Auxiliar.xlsx", engine="openpyxl")
        self.list_customers = df["Cliente"].dropna().tolist()
        self.list_fatigue_rigs = df["Fatigue Rigs"].dropna().tolist()
        self.list_qty = ["1","2","3","4","5","6","7","8","9"]
        
    # CREACIÓN DEL FORMULARIO    
        # Definir fuente general para labels y entrys
        font_components = ("Roboto", 12)
        style = Style()
        # Top Label
        ttk.Label(self.root, text=text_top_label, font=("Roboto",22,"bold"), bootstyle="info" if not self.show_info_mode else "danger").pack(pady=10)
        
        # Top Label 2
        ttk.Label(self.root, text="Datos generales", font=("Roboto",22,"bold"),bootstyle="info").pack(pady=10)
        
      # Frame - Datos generales de la prueba
        frame_test_data = ttk.Frame(self.root)
        frame_test_data.pack(anchor="center", pady=10)
        
        # Test Batch
        ttk.Label(frame_test_data, text="*Test Batch", font=font_components).pack(padx=10, side="left")
        self.test_batch = ttk.Entry(frame_test_data, font=font_components, justify="center", width=14)
        self.test_batch.pack(padx=10,pady=10, side="left")
        self.test_batch.bind("<KeyRelease>", lambda e: self.limit_entry(e, max_length=11))
        
        # Customer
        ttk.Label(frame_test_data, text="*Cliente", font=font_components).pack(padx=10, side="left")
        self.customer = ttk.Combobox(frame_test_data, values=self.list_customers, font=font_components, justify="center", width=14)
        self.customer.pack(padx=10, side="left")
        
        # Start Date
        ttk.Label(frame_test_data, text="*Inicio de prueba", font=font_components).pack(padx=10, side="left")
        self.start_date = ttk.DateEntry(frame_test_data, dateformat='%d/%m/%Y', width=14)
        self.start_date.entry.configure(font=("Roboto",12))
        self.start_date.pack(padx=10, side="left")
        
        # Samples quantity
        ttk.Label(frame_test_data, text="*No. Piezas", font=font_components).pack(padx=10, side="left")
        self.qty_samples = ttk.Combobox(frame_test_data, values=self.list_qty, font=font_components, justify="center", width=14)
        self.qty_samples.pack(padx=10, side="left")
        
        # Work Order
        frame_test_data_r2 = ttk.Frame(self.root)
        frame_test_data_r2.pack(anchor="center", pady=10)
        
        ttk.Label(frame_test_data_r2, text="¿Se tiene WO?", font=font_components).pack(padx=10, side="left")
        self.WO = ttk.Combobox(frame_test_data_r2, values=["Si","No"],font=font_components, justify="center", width=4)
        self.WO.set("Si")
        self.WO.pack(padx=10, side="left")
        
        self.label_end_date = ttk.Label(frame_test_data_r2, text="Fin de prueba", font=font_components)
        self.label_end_date.pack(padx=10, side="left")
        self.end_date = ttk.DateEntry(frame_test_data_r2, dateformat='%d/%m/%Y', width=14)
        self.end_date.entry.configure(font=("Roboto",12))
        self.end_date.pack(padx=10, side="left")
        
        # Label encabezado de la sección
        ttk.Label(self.root, text="Datos de las muestras", font=("Roboto",22,"bold"),bootstyle="info").pack(pady=10)
        
      # Frame datos de las muestras
        frame_samples_data = ttk.Frame(self.root)
        frame_samples_data.pack(anchor="center", pady=10)
        
        #Varibles que almacenarán los componentes de test rig y ciclake
        self.test_rigs = []
        self.cycles_samples = []
        
        # Espacios para la correcta organización de los componentes
        ttk.Label(frame_samples_data, text="        ",font=font_components).grid(row=0, column=2, padx=10, pady=2)
        ttk.Label(frame_samples_data, text="        ",font=font_components).grid(row=0, column=5, padx=10, pady=2)
        ttk.Label(frame_samples_data, text="        ",font=font_components).grid(row=2, column=0, padx=10, pady=2)
        ttk.Label(frame_samples_data, text="        ",font=font_components).grid(row=5, column=0, padx=10, pady=2)
        
        # Ciclo para la creación de los entrys y combobox
        for i in range(9):
            row = (i // 3) * 3
            col = (i % 3) * 3
            
            # Entrys
            ttk.Label(frame_samples_data, text=f"Pieza {i+1}", font=font_components).grid(row=row, column=col, padx=10, pady=2)
            entry = ttk.Entry(frame_samples_data, font=font_components, justify="center", width=16)
            entry.grid(row=row, column=col+1, padx=10, pady=5)
            self.cycles_samples.append(entry)
            
            # Combobox
            ttk.Label(frame_samples_data, text=f"Test Rig", font=font_components).grid(row=row+1, column=col, padx=10, pady=2)
            combo = ttk.Combobox(frame_samples_data, values=self.list_fatigue_rigs, font=font_components, justify="center", width=14)
            combo.grid(row=row+1, column=col+1, padx=10, pady=5)
            self.test_rigs.append(combo)
        
        
        
        ttk.Label(self.root, text="Comentarios", font=font_components).pack(padx=10,pady=10)
        self.comments = ttk.Entry(self.root, width=28, font=font_components)
        self.comments.pack(padx=10, pady=5)
        
        # Botones de finalizar y guardar datos
        frame_btns_footer = ttk.Frame(self.root)
        frame_btns_footer.pack(fill="x", pady=10, padx=20)
        self.btn_save_data = Button(frame_btns_footer, text=text_btn_save, bootstyle="success-outline", command=self.save_data, cursor="hand2")
        self.btn_save_data.pack(side="right")
        self.btn_finish_record = Button(frame_btns_footer, text="Finalizar prueba", bootstyle="warning-outline", command=self.close_fatigue_record, cursor="hand2")
        self.btn_finish_record.pack(side="left")
        
        self.btn_sent_back_record = Button(frame_btns_footer, text="Quitar de finalizados", bootstyle="info", command=self.sent_back_record, cursor="hand2")
        self.btn_sent_back_record.pack(side="right")
        
        if show_info_mode:
            self.btn_save_data.pack_forget()
            self.btn_finish_record.pack_forget()
        else:
            self.end_date.pack_forget()
            self.label_end_date.pack_forget()
            self.btn_sent_back_record.pack_forget()
        
        if self.edit_mode and self.edit_data:
            self.fill_form_with_data()
        
        self.window_close_fatigue = None
           
    def save_data(self):
        try:
            test_batch = self.test_batch.get()
            test_batch = test_batch.upper()
            customer = self.customer.get()
            comments = self.comments.get() or "--"
            #start_date = self.start_date.get_date().strftime("%d-%m-%Y")
            start_date = self.start_date.entry.get()
            qty_samples = self.qty_samples.get()
            
            # VALIDACION DE DATOS
            if not self.data_validation(test_batch, customer, qty_samples):
                return
            
            qty_samples = int(qty_samples)
            test_rig_values = [rig.get() if rig.get() else "--" for rig in self.test_rigs]
            cycles_values = [entry.get() if entry.get() else "0" for entry in self.cycles_samples]
            data = {
                "test_batch": test_batch,
                "customer": customer,
                "start_date": start_date,
                "qty_samples": qty_samples,
                "comments": comments,
                "wo_status": self.WO.get() == "Si",
                "test_status": "Ongoing"
                }
           
            for i in range(9):
                data[f"test_rig{i+1}"] = test_rig_values[i]
                data[f"cycles{i+1}"] = int(cycles_values[i]) if cycles_values[i].isdigit() else None
            if self.edit_mode == True:
                with closing(self.db_conn.cursor()) as cursor:
                    cursor.execute("""UPDATE fatigue_tests SET 
                        test_batch=?, customer=?, start_date=?, qty_samples=?, comments=?, 
                        test_rig1=?, cycles1=?, test_rig2=?, cycles2=?, test_rig3=?, cycles3=?, 
                        test_rig4=?, cycles4=?, test_rig5=?, cycles5=?, test_rig6=?, cycles6=?, 
                        test_rig7=?, cycles7=?, test_rig8=?, cycles8=?, test_rig9=?, cycles9=?, 
                        wo_status=?, test_status=?
                        WHERE id=?
                        """, [data["test_batch"], data["customer"], data["start_date"], data["qty_samples"], data["comments"],
                        data["test_rig1"], data["cycles1"], data["test_rig2"], data["cycles2"],
                        data["test_rig3"], data["cycles3"], data["test_rig4"], data["cycles4"],
                        data["test_rig5"], data["cycles5"], data["test_rig6"], data["cycles6"],
                        data["test_rig7"], data["cycles7"], data["test_rig8"], data["cycles8"],
                        data["test_rig9"], data["cycles9"], data["wo_status"], data["test_status"],
                        self.edit_id])
                    messagebox.showinfo(title="Actualizado", message="Registro actualizado correctamente.")    
            else:
                with closing(self.db_conn.cursor()) as cursor:
                    columns = ", ".join(data.keys())
                    placeholders = ", ".join(["?"] * len(data))
                    values = list(data.values())
                    cursor.execute(f"INSERT INTO fatigue_tests ({columns}) VALUES ({placeholders})", values)
                    messagebox.showinfo(title="Nuevo registro", message="El nuevo registro ha sido ingresado correctamente") 
            
            self.db_conn.commit()
            self.db_conn.close()
            self.refresh_callback()
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Error:", f"Ocurrio un error: {e}")    
        
    def fill_form_with_data(self):
        if not self.edit_data:
            return
        # Asignar valores a los campos generales
        cleaned_test_batch = self.edit_data[1].replace("⚠️ ", "")
        self.test_batch.insert(0, cleaned_test_batch)
        self.customer.set(self.edit_data[2])
        
        st_date = datetime.strptime(self.edit_data[3], "%d/%m/%Y").date()
        self.start_date.entry.delete(0, 'end')
        self.start_date.entry.insert(0, st_date.strftime("%d/%m/%Y"))
       
        if self.show_info_mode:
            self.qty_samples.set(str(self.edit_data[5]))
            self.comments.insert(0, self.edit_data[6]) 
            self.WO.set("No" if int(self.edit_data[25]) == 0 else "Si")
        else:
            self.qty_samples.set(str(self.edit_data[4]))
            self.comments.insert(0, self.edit_data[5]) 
            self.WO.set("No" if int(self.edit_data[24]) == 0 else "Si")
        
        #print(self.edit_data)#23
        # Asignar valores a los test rigs y ciclos
        if self.show_info_mode:
            self.initial_rig_position = 7
            self.initial_cycles_position = 8
        else:
            self.initial_rig_position = 6
            self.initial_cycles_position = 7
            
        for i in range(9):
            rig_index = self.initial_rig_position + i * 2
            cycle_index = self.initial_cycles_position + i * 2
            if rig_index < len(self.edit_data):
                self.test_rigs[i].set(self.edit_data[rig_index])
            if cycle_index < len(self.edit_data):
                self.cycles_samples[i].insert(0, str(self.edit_data[cycle_index]))
        
        if self.show_info_mode:
            with closing(self.db_conn.cursor()) as cursor:
                cursor.execute("""
                    SELECT end_date FROM fatigue_tests
                    WHERE id=?
                """,(self.edit_data[0],))
                
                end_date = cursor.fetchall()
                self.db_conn.commit()
                print(f"End date: {end_date[0][0]}")
            
            nd_date = datetime.strptime(end_date[0][0], "%d/%m/%Y").date()
            self.end_date.entry.delete(0, 'end')
            self.end_date.entry.insert(0, nd_date.strftime("%d/%m/%Y"))
            
    def on_close(self):
        try:
            if hasattr(self,'db_conn') and self.db_conn:
                self.db_conn.close()
        except Exception as e:
            print(f"Error al cerrar la conexión: {e}")
        finally:
            self.root.destroy()
    
    def close_fatigue_record(self):
        if self.window_close_fatigue is None or not self.window_close_fatigue.winfo_exists():
            self.window_close_fatigue = tk.Toplevel(self.root)
            CloseFatigueWindow(self.window_close_fatigue, self, self.test_batch.get(), self.refresh_callback)
            self.root.withdraw()
    
    def limit_entry(self,event, max_length=11):
        widget = event.widget
        if len(widget.get()) > max_length:
            widget.delete(max_length, 'end')
    
    def data_validation(self, test_batch, customer, qty_samples):
        #Importar información de clientes
        df = pd.read_excel("./excel_files/Auxiliar.xlsx", engine="openpyxl")
        self.fatigue_codes = df["Fatigue Codes"].dropna().tolist()
        
        print(customer)
        if not test_batch or not customer.strip() or not qty_samples:
            messagebox.showerror("Error", "Los campos Test Batch, Cliente y N° Piezas son obligatorios")
            return False
        
        match = re.fullmatch(r"(\d{6})([A-Z]{3})(\d{2})", test_batch.upper())
        if not match:
            messagebox.showerror("Error", "El campo Test Batch no cumple con el formato requerido (7 dígitos + clave + 2 dígitos)")
            return False
        
        key = match.group(2).upper()
        if key not in self.fatigue_codes:
            messagebox.showerror("Error", f"La clave '{key}' no es válida. Usa alguna de las siguientes: {', '.join(self.fatigue_codes)}.")
            return False
        
        if not self.edit_mode:
            try:
                with closing(self.db_conn.cursor()) as cursor:
                    cursor.execute("SELECT COUNT(*) FROM fatigue_tests WHERE test_batch = ?", (test_batch,))
                    result = cursor.fetchone()
                        
                    if result and result[0] > 0:
                        messagebox.showerror("Error", f"Ya existe un registro con el Test Batch '{test_batch}', por favor ingresa uno nuevo.")
                        return False
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo validar el Test Batch: {e}")
        
        return True        
    
    def sent_back_record(self):
        confirm = messagebox.askyesno("Confirmación", f"¿Deseas quitar el Test Batch -> {self.edit_data[1]} de la sección de pruebas finalizadas?")
        
        if confirm:
            database_path = os.path.abspath("./db/test_records.db")
            try:
                with closing(sqlite3.connect(database_path)) as conn:
                    with closing(conn.cursor()) as cursor:
                        cursor.execute("""
                            UPDATE fatigue_tests
                            SET test_status = 'Ongoing'
                            WHERE id = ?
                        """, (self.edit_data[0],))
                        conn.commit()
                messagebox.showinfo("Éxito", "El registro ha sido marcado como 'En curso'.")
                #self.apply_date_filters()
                self.root.destroy()
                if hasattr(self.parent, "refresh_and_show"):
                    self.parent.refresh_and_show()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo actualizar el registro: {e}")
        
        
    
    