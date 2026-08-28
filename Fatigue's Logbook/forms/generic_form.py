# Librerias de archivos
from contextlib import closing
from tools.utils import center_window

# Libreria de lectura de archivos excel
import pandas as pd

# Libreria de Interfaces
from datetime import datetime
from tkinter import messagebox

#Libreria de SQL
import sqlite3

# Librerias del sistema
import re
import sys
import os

# Librerias TKInter y TTKBootstrap
import tkinter.font as tkFont
import ttkbootstrap as ttk
from ttkbootstrap import Style, Button, DateEntry


class GenericForm:
    def __init__(self, master, parent, edit_data, refresh_callback, db_connection, edit_mode, table_to_edit):
    # --- CONFIGURACIÓN INICIAL DE LA VENTANA
        self.root = master
        self.parent = parent
        self.root.title("Nuevo registro")
        center_window(self.root, 500,550)
        self.table_to_edit = table_to_edit
        #self.root.configure(background="#FFE5B4")
    
    # --- DEFINIR DATOS HEREDADOS
        self.conn = db_connection # Conexión de la base de datos
        #self.protocol("WM_DELETE_WINDOW", self.on_close) # Protocolo en caso de cerrar inesperadamente la ventana
        self.edit_mode = edit_mode
        self.edit_data = edit_data
        
        self.refresh_callback = refresh_callback #Función para actualizar los datos de la tabla con la nueva información
        
        # Determinar el texto del botón dependiendo de si es edición o ingreso de nuevo registro
        if self.edit_mode == True:
            self.edit_id = self.edit_data[0]
            text_btn = "Guardar Cambios"
            text_main_label = "-------- EDITAR FATIGA --------"
        else:
            text_btn = "Ingresar Registro"
    
    # --- IMPORTAR INFORMACIÓN DEL ARCHIVO DE EXCEL - AUXILIAR
        df = pd.read_excel("./excel_files/Auxiliar.xlsx", engine="openpyxl")
        self.list_customers = df["Cliente"].dropna().tolist()
        self.list_torsion_rigs = df[self.table_to_edit[5]].dropna().tolist()
        self.list_qty = ["1","2","3","4","5","6","7","8","9"]
            
    # ---- CREACION DEL FORMULARIO --------
        # Fuente para labels y entrys
        entrys_font = ("Roboto", 12)
        style = Style()
        
        text_main_label = f"---- INGRESAR NUEVA {self.table_to_edit[1]} ----"
        # Label 1
        ttk.Label(self.root, text=text_main_label, font=("Roboto",20,"bold"),bootstyle=self.table_to_edit[4]).pack(pady=10)
        
        
      # Frame: Datos generales
        # Frame test data
        frame_test_data = ttk.Frame(self.root)
        frame_test_data.pack(pady=10, padx=10, fill="x")

        center_frame1 = ttk.Frame(frame_test_data)
        center_frame1.pack(pady=10, padx=5)
        
        center_frame2 = ttk.Frame(frame_test_data)
        center_frame2.pack(pady=10, padx=5)
        
        center_frame3 = ttk.Frame(frame_test_data)
        center_frame3.pack(pady=10, padx=5)
        
        center_frame4 = ttk.Frame(frame_test_data)
        center_frame4.pack(pady=10, padx=5)
        
        center_frame5 = ttk.Frame(frame_test_data)
        center_frame5.pack(pady=10, padx=5)
        
        
        # Label - Entry -> Test Batch
        ttk.Label(center_frame1, text="*Test Batch:", font=("Arial", 12), width=13, anchor="e").pack(padx=10, side="left")
        self.test_batch = ttk.Entry(center_frame1, font=entrys_font, justify="center", bootstyle=self.table_to_edit[4], width=16)
        self.test_batch.pack(padx=10, pady=10, side="left")
        self.test_batch.bind("<KeyRelease>", lambda e: self.limit_entry(e,11))
        
        # Label - Entry -> Customer
        ttk.Label(center_frame2, text="*Cliente:", font=("Arial", 12), width=13, anchor="e").pack(padx=10, side="left")
        self.customer = ttk.Combobox(center_frame2, values=self.list_customers,font=entrys_font, justify="center", width=14, bootstyle=self.table_to_edit[4])
        self.customer.pack(padx=10, side="left")
        
        # Label - DateEntry --> Fecha de Inicio
        ttk.Label(center_frame3, text="*Fecha de prueba:", font=("Arial", 12), width=13, anchor="e").pack(padx=10, side="left")
        self.test_date = ttk.DateEntry(center_frame3, dateformat='%d/%m/%Y', width=13, bootstyle=self.table_to_edit[4])
        self.test_date.entry.configure(font=("Roboto",12))
        self.test_date.pack(padx=10, side="left")
    
        # Label - Entry -> Qty Piezas
        ttk.Label(center_frame4, text="*N° Piezas:", font=("Arial", 12), width=13, anchor="e").pack(padx=10, side="left")
        self.qty_samples = ttk.Combobox(center_frame4, values=self.list_qty,font=entrys_font,justify="center", width=14, bootstyle=self.table_to_edit[4])
        self.qty_samples.pack(padx=10, side="left")
        
        # Label - Entry -> Torsion Rig
        ttk.Label(center_frame5, text="*Test Rig:", font=("Arial", 12), width=13, anchor="e").pack(padx=10, side="left")
        self.torsion_rig = ttk.Combobox(center_frame5, values=self.list_torsion_rigs,font=entrys_font, justify="center", width=14, bootstyle=self.table_to_edit[4])
        self.torsion_rig.pack(padx=10, side="left")
        
        frame_label_comments = ttk.Frame(self.root)
        frame_label_comments.pack(pady=10, padx=5)
        ttk.Label(frame_label_comments, text="Comentarios", font=("Roboto", 12)).pack(padx=10, pady=10)
        self.comments = ttk.Entry(frame_label_comments,width=28, font=("Roboto",12), bootstyle=self.table_to_edit[4], justify="center")
        self.comments.pack(fill="x", padx=10, pady=5)
    
    # FRAME: Comentarios
        btn_font = tkFont.Font(family="Roboto", size=12, weight="bold")
        style.configure("success.Outline.TButton", font=btn_font)
        style.configure("warning.Outline.TButton", font=btn_font)
        
        # Label boton back to home
        frame_btn_actions = ttk.Frame(self.root)
        frame_btn_actions.pack(pady=10, padx=20, fill="x")
        Button(frame_btn_actions, text=text_btn, bootstyle="success-outline",command=self.save_data, cursor="hand2").pack(side="right")
        #Button(frame_btn_actions, text="Finalizar prueba", bootstyle="warning-outline",command=lambda: open_close_fatigue_window(self,self.test_batch.get(), self.refresh_callback), cursor="hand2").pack(side="left")
        #ctk.CTkButton(frame_btn_actions, text="Finalizar", command=lambda: open_close_fatigue_window(self,self.test_batch.get(), self.refresh_callback), font=("Roboto",18)).pack(side="left")
        
        
        if self.edit_mode and self.edit_data:
            self.fill_form_with_data()
        
        
        
    def save_data(self):
        try:
            test_batch = self.test_batch.get()
            test_batch = test_batch.upper()
            customer = self.customer.get()
            comments = self.comments.get() or "--"
            #start_date = self.start_date.get_date().strftime("%d-%m-%Y")
            test_date = self.test_date.entry.get()
            qty_samples = self.qty_samples.get()
            torsion_rig = self.torsion_rig.get()
            
            # VALIDACION DE DATOS
            if not self.data_validation(test_batch, customer, qty_samples):
                return
            
            qty_samples = int(qty_samples)

            data = {
                "test_batch": test_batch,
                "customer": customer,
                "test_date": test_date,
                "qty_samples": qty_samples,
                "comments": comments,
                "test_rig": torsion_rig
                }
           

            if self.edit_mode == True:
                with closing(self.conn.cursor()) as cursor:
                    cursor.execute(f"""UPDATE {self.table_to_edit[0]} SET 
                        test_batch=?, customer=?, test_date=?, qty_samples=?, comments=?, test_rig=?
                        WHERE id=?
                        """,[
                        data["test_batch"], data["customer"], data["test_date"], data["qty_samples"], 
                        data["comments"], data["test_rig"], self.edit_id])
                    
                    messagebox.showinfo(title="Actualizado", message="Registro actualizado correctamente.")
               
            else:
                with closing(self.conn.cursor()) as cursor:
                    columns = ", ".join(data.keys())
                    placeholders = ", ".join(["?"] * len(data))
                    values = list(data.values())
                    cursor.execute(f"INSERT INTO {self.table_to_edit[0]} ({columns}) VALUES ({placeholders})", values)
                    messagebox.showinfo(title="Nuevo registro", message="El nuevo registro ha sido ingresado correctamente") 
            
            self.conn.commit()
            self.conn.close()
            self.refresh_callback()
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Error:", f"Ocurrio un error: {e}")


    #def create_sample_row(frame, index, row, data):
    #    sample_id = create_labeled_entry(frame, f"Sample {index + 1}:", row, 0)
    #    test_rig = create_labeled_dropdown(frame, f"Test Rig:", data, row, 2)
    #    return sample_id, test_rig
       
    def fill_form_with_data(self):
        if not self.edit_data:
            return
        # Asignar valores a los campos generales
        self.test_batch.insert(0, self.edit_data[1])
        self.customer.set(self.edit_data[2])
        
        st_date = datetime.strptime(self.edit_data[3], "%d/%m/%Y").date()
        self.test_date.entry.delete(0, 'end')
        self.test_date.entry.insert(0, st_date.strftime("%d/%m/%Y"))
       
        self.qty_samples.set(str(self.edit_data[4]))
        self.comments.insert(0, self.edit_data[5])  # Si tienes un campo de comentarios, asígnalo también
        self.torsion_rig.set(str(self.edit_data[6]))
    
    def on_close(self):
        try:
            if hasattr(self,'conn') and self.conn:
                self.conn.close()
        except Exception as e:
            print(f"Error al cerrar la conexión: {e}")
        finally:
            self.destroy()

    def limit_entry(self,event, max_length=11):
        widget = event.widget
        if len(widget.get()) > max_length:
            widget.delete(max_length, 'end')
    
    def data_validation(self, test_batch, customer, qty_samples):
        #Importar información de clientes
        df = pd.read_excel("./excel_files/Auxiliar.xlsx", engine="openpyxl")
        self.fatigue_codes = df[self.table_to_edit[2]].dropna().tolist()
        
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
        
        try:
            with closing(self.conn.cursor()) as cursor:
                cursor.execute(f"SELECT COUNT(*) FROM {self.table_to_edit[0]} WHERE test_batch = ?", (test_batch,))
                result = cursor.fetchone()
                    
                if result and result[0] > 0:
                    messagebox.showerror("Error", f"Ya existe un registro con el Test Batch '{test_batch}', por favor ingresa uno nuevo.")
                    return False
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo validar el Test Batch: {e}")
        
        return True
