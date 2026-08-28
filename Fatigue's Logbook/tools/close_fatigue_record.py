import customtkinter as ctk
from tkinter import messagebox
from tools.utils import center_window
import sqlite3
from datetime import datetime

from contextlib import closing

# Librerias bootstrap
import ttkbootstrap as ttk
import tkinter.font as tkFont
from ttkbootstrap import Style
from ttkbootstrap import Button
from ttkbootstrap import DateEntry
from ttkbootstrap.constants import *

import os

class CloseFatigueWindow:
    def __init__(self, master, parent, test_batch, refresh_callback):
    # CONFIGURACIÓN DE LA VENTANA
        self.root = master
        self.parent = parent
        self.root.title = ("Cerrar prueba de fatiga")
        center_window(self.root, 400,150)
        
        self.test_batch = test_batch
        self.refresh_callback = refresh_callback
        
        style = Style()
        
        if "SRF" in self.test_batch:
            self.db_table = "rotary_tests"
        else:
            self.db_table = "fatigue_tests"
        # Label 1
        ttk.Label(self.root, text="--- Ingresa la fecha de fin de prueba ---", font=("Roboto",14,"bold"),bootstyle="info").pack(pady=10)
        self.end_date = ttk.DateEntry(self.root, dateformat='%d/%m/%Y', width=14)
        self.end_date.entry.configure(font=("Roboto",12))
        self.end_date.pack(pady=10)
        
        btn_font = tkFont.Font(family="Roboto", size=12, weight="bold")
        style.configure("success.Outline.TButton", font=btn_font)
    
        #frame_btn_actions = ctk.CTkFrame(window, fg_color="#517891")
        #frame_btn_actions.pack(pady=10, padx=20, anchor="center")
    
    
        Button(self.root, text="Guardar cambios", bootstyle="success-outline",command=self.confirm_close, cursor="hand2").pack(side="right", padx=10)

    def confirm_close(self):
        end_date = self.end_date.entry.get()
        database_path = os.path.abspath("./db/test_records.db")
        try:
            with closing(sqlite3.connect(database_path)) as conn:
                with closing(conn.cursor()) as cursor:
                    cursor.execute(f"""
                        UPDATE {self.db_table}
                        SET end_date=?, test_status=?
                        WHERE test_batch=?
                    """, (end_date, "Finished", self.test_batch))
                    conn.commit()
                    messagebox.showinfo("Prueba cerrada", "La prueba ha sido marcada como finalizada.")
           
            if self.refresh_callback():
                self.refresh_callback
            
            self.root.destroy()
            self.parent.root.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un error: {e}")
        
    
    