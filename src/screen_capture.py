"""
Captura de pantalla invisible usando mss.
Soporta pantalla completa y ventana activa.
"""

import numpy as np
import mss
import win32gui
from PIL import Image


def capture_screen(monitor_index: int = 1) -> tuple[np.ndarray, int, int]:
    """
    Captura la pantalla completa del monitor indicado.
    
    Args:
        monitor_index: 1 = monitor primario, 0 = todos los monitores.
    
    Returns:
        Tupla (imagen_numpy_rgb, offset_x, offset_y).
    """
    with mss.MSS() as sct:
        monitor = sct.monitors[monitor_index]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        return np.array(img), monitor["left"], monitor["top"]


def capture_active_window() -> tuple[np.ndarray, int, int]:
    """
    Captura solo la ventana activa (foreground window).
    
    Returns:
        Tupla (imagen_numpy_rgb, offset_x, offset_y).
        Los offsets corresponden a la posición de la ventana en pantalla.
    """
    hwnd = win32gui.GetForegroundWindow()
    rect = win32gui.GetWindowRect(hwnd)
    x, y, x2, y2 = rect
    width = x2 - x
    height = y2 - y

    if width <= 0 or height <= 0:
        # Fallback a pantalla completa si la ventana tiene tamaño inválido
        return capture_screen()

    with mss.MSS() as sct:
        region = {"left": x, "top": y, "width": width, "height": height}
        screenshot = sct.grab(region)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        return np.array(img), x, y
