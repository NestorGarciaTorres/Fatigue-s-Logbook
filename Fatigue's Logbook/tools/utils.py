from screeninfo import get_monitors

def center_window(window, width, height):
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = int((screen_width / 2) - (width / 2))
    y = int((screen_height / 2) - (height / 2))
    window.geometry(f"{width}x{height}+{x}+{y}")

def get_monitor_geometry_for_window(window):
    window.update_idletasks()
    x = window.winfo_rootx()
    y = window.winfo_rooty()
    for monitor in get_monitors():
        if monitor.x <= monitor.x + monitor.width and monitor.y <= monitor.y + monitor.height:
            return monitor
    
    return get_monitors()[0]

def position_window_on_monitor(window, monitor):
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    x = monitor.x + (monitor.width - width) // 2
    y  = monitor.y + (monitor.height - height) // 2
    window.geometry(f"+{x}+{y}")