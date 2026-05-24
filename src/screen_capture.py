"""
Captura de pantalla invisible usando mss.
Soporta pantalla completa y ventana activa.
Optimizado para rendimiento y seguridad de hilos mediante threading.local.
"""

import numpy as np
import mss
import win32gui
import threading

# Almacén local de hilos para mantener instancias de mss persistentes por hilo
# Esto ahorra batería en el hilo dinámico (reutiliza instancia)
# y da estabilidad en hilos de escaneo estático (instancias aisladas).
_thread_local = threading.local()

def get_sct():
    if not hasattr(_thread_local, 'sct'):
        _thread_local.sct = mss.mss()
    return _thread_local.sct

def capture_screen(monitor_index: int = 1) -> tuple[np.ndarray, int, int]:
    """
    Captura la pantalla completa del monitor indicado de forma eficiente y segura.
    """
    sct = get_sct()
    monitor = sct.monitors[monitor_index]
    screenshot = sct.grab(monitor)
    
    # Conversión eficiente de BGRA a RGB
    img = np.array(screenshot, dtype=np.uint8)[:, :, :3]
    img = img[:, :, ::-1] # BGR to RGB
    
    return img, monitor["left"], monitor["top"]


def capture_active_window() -> tuple[np.ndarray, int, int]:
    """
    Captura solo la ventana activa (foreground window) de forma segura.
    """
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return capture_screen()
    try:
        rect = win32gui.GetWindowRect(hwnd)
        x, y, x2, y2 = rect
        width = x2 - x
        height = y2 - y
    except Exception:
        return capture_screen()

    if width <= 0 or height <= 0:
        return capture_screen()

    sct = get_sct()
    region = {"left": x, "top": y, "width": width, "height": height}
    screenshot = sct.grab(region)
    
    # Convertir a RGB eficiente
    img = np.array(screenshot, dtype=np.uint8)[:, :, :3]
    img = img[:, :, ::-1] # BGR to RGB
    
    return img, x, y
