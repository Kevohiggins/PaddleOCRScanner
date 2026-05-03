"""
Ejecutor de clicks automáticos usando pyautogui.
Calcula el centro geométrico del bounding box y clickea ahí.
"""

import logging
import pyautogui

from ocr_engine import DetectedElement

logger = logging.getLogger(__name__)

# Desactivar el failsafe de pyautogui (mover mouse a esquina para abortar)
# Lo dejamos activado por seguridad — si algo sale mal, mové el mouse a la esquina sup-izq
pyautogui.FAILSAFE = True
# Sin pausa entre acciones
pyautogui.PAUSE = 0.05


def click_element(element: DetectedElement, offset_x: int = 0, offset_y: int = 0, click_type: str = "left"):
    """
    Clickea en el centro del bounding box del elemento.

    Args:
        element: Elemento detectado con coordenadas.
        offset_x: Offset X del monitor (para multi-monitor).
        offset_y: Offset Y del monitor.
        click_type: "left", "right", o "double".
    """
    abs_x = int(element.center_x + offset_x)
    abs_y = int(element.center_y + offset_y)

    logger.info("Click (%s) en (%d, %d) — texto: '%s'", click_type, abs_x, abs_y, element.text)
    
    if click_type == "double":
        pyautogui.doubleClick(abs_x, abs_y)
    elif click_type == "right":
        pyautogui.click(abs_x, abs_y, button="right")
    else:
        pyautogui.click(abs_x, abs_y, button="left")
