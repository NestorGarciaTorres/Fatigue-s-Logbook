# Librerias auxiliares
from tools.utils import center_window

# Libreria Bootstrap
import ttkbootstrap as ttk 
from ttkbootstrap import Style, Window, Button

# Librerias tkInter
import tkinter.font as tkFont

# Llamadas a otros archivos
from logbooks.fatigue_curr_logbook import FatigueLogbook
from logbooks.logbook_torsion import TorsionLogbook
from logbooks.logbook_rotary import RotaryLogbook
from logbooks.logbook_quasi import QuasiLogbook

class MainMenu:
    def __init__(self,master):
    # CONFIGURACIÓN DE LA VENTANA
        self.root = master
        self.root.protocol("WM_DELETE_WINDOW", self.exit_program)
        self.root.title("Main Menu")
        center_window(self.root,300,300)
        
    # CONFIGURACIÓN DE LOS BOTONES
        style = Style("superhero")
        btn_font = tkFont.Font(family="Roboto", size=12, weight="bold") 
        style.configure("primary.Outline.TButton", font=btn_font) # Color azul con outline
        style.configure("warning.Outline.TButton", font=btn_font) # Color naranja con outline
        style.configure("danger.Outline.TButton", font=btn_font) # Color rojo con outline
        style.configure("info.Outline.TButton", font=btn_font) # Color rojo con outline
    
    # FRAME PRINCIPAL
        frame = ttk.Frame(self.root, padding=15)
        frame.pack(fill="both", expand=True)
    
    # BOTONES DEL MENÚ
        ttk.Label(frame, text="Menú Principal", font=("Roboto", 24), bootstyle="primary").pack(pady=20)
        ttk.Button(frame, text="Fatiga", command=self.open_fatigue_curr_logbook, bootstyle="primary-outline", cursor="hand2").pack(pady=5, fill="x")
        ttk.Button(frame, text="Torsión", command=self.open_torsion_logbook, bootstyle="warning-outline", cursor="hand2").pack(pady=5, fill="x")
        ttk.Button(frame, text="Rotary", command=self.open_rotary_logbook, bootstyle="danger-outline", cursor="hand2").pack(pady=5, fill="x")
        ttk.Button(frame, text="Quasi", command=self.open_quasi_logbook, bootstyle="info-outline", cursor="hand2").pack(pady=5, fill="x")
        
# FUNCIONES PARA ABRIR NUEVAS VENTANAS

    def open_fatigue_curr_logbook(self):
        self.root.withdraw()
        new_window = ttk.Toplevel(self.root)
        FatigueLogbook(new_window, self.root)
        #new_root.mainloop()
    
    def open_torsion_logbook(self):
        self.root.withdraw()
        new_window = ttk.Toplevel(self.root)
        TorsionLogbook(new_window, self.root)
    
    def open_rotary_logbook(self):
        self.root.withdraw()
        new_window = ttk.Toplevel(self.root)
        RotaryLogbook(new_window, self.root)
        
    def open_quasi_logbook(self):
        self.root.withdraw()
        new_window = ttk.Toplevel(self.root)
        QuasiLogbook(new_window, self.root)
    
    def exit_program(self):
        import sys
        self.root.destroy()
        sys.exit()
