import ttkbootstrap as ttk
from menu.main_menu import MainMenu

if __name__ == "__main__":
    app = ttk.Window(themename="superhero") 
    MainMenu(app)
    app.mainloop()