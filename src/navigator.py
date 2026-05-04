"""
Navegación por elementos detectados con feedback de voz.
Suprime las teclas de navegación para que no pasen a Windows.
"""

import logging
import threading
import time

import keyboard

from ocr_engine import DetectedElement
from tts_engine import TTSEngine
from clicker import click_element

logger = logging.getLogger(__name__)


class ElementNavigator:
    """
    Permite navegar por una lista de elementos detectados con el teclado.
    
    Controles:
        Flecha abajo / derecha → siguiente elemento
        Flecha arriba / izquierda → anterior
        Enter → click izquierdo en el elemento actual
        Shift+Enter → doble click izquierdo
        Menú de Aplicaciones → click derecho
        Escape → cancelar navegación
    """

    def __init__(self, tts: TTSEngine, offset_x: int = 0, offset_y: int = 0):
        self.tts = tts
        self.offset_x = offset_x
        self.offset_y = offset_y

    def navigate(self, elements: list[DetectedElement]) -> bool:
        """
        Inicia la navegación por los elementos.
        Bloquea el hilo actual hasta que el usuario seleccione o cancele.
        Suprime flechas/Enter/Escape para que no pasen a Windows.

        Returns:
            True si se hizo click en un elemento, False si se canceló.
        """
        if not elements:
            self.tts.speak("No se detectaron elementos de texto.")
            return False

        total = len(elements)
        idx = 0
        active = True
        clicked = False
        click_type = "left"
        nav_lock = threading.Lock()
        hooks = []

        def announce(index: int):
            elem = elements[index]
            # Formato: texto primero, posición al final
            msg = f"{elem.text}, {index + 1} de {total}"
            self.tts.speak(msg, interrupt=True)

        def on_next(event=None):
            nonlocal idx
            with nav_lock:
                if not active:
                    return
                idx = (idx + 1) % total
                announce(idx)

        def on_prev(event=None):
            nonlocal idx
            with nav_lock:
                if not active:
                    return
                idx = (idx - 1) % total
                announce(idx)

        def on_select_left(event=None):
            nonlocal active, clicked, click_type
            with nav_lock:
                if not active:
                    return
                clicked = True
                click_type = "left"
                active = False

        def on_select_double(event=None):
            nonlocal active, clicked, click_type
            with nav_lock:
                if not active:
                    return
                clicked = True
                click_type = "double"
                active = False

        def on_select_right(event=None):
            nonlocal active, clicked, click_type
            with nav_lock:
                if not active:
                    return
                clicked = True
                click_type = "right"
                active = False

        def on_cancel(event=None):
            nonlocal active
            with nav_lock:
                if not active:
                    return
                active = False

        # Anunciar inicio
        self.tts.speak(
            f"{total} elementos detectados. Usá las flechas.",
            interrupt=True,
        )
        time.sleep(0.3)
        announce(idx)

        # Registrar hooks
        hooks.append(('key', keyboard.on_press_key("down", on_next, suppress=True)))
        hooks.append(('key', keyboard.on_press_key("right", on_next, suppress=True)))
        hooks.append(('key', keyboard.on_press_key("up", on_prev, suppress=True)))
        hooks.append(('key', keyboard.on_press_key("left", on_prev, suppress=True)))
        
        hooks.append(('key', keyboard.on_press_key("enter", on_select_left, suppress=True)))
        
        # Para combinaciones se usa add_hotkey
        hooks.append(('hotkey', keyboard.add_hotkey("shift+enter", on_select_double, suppress=True)))
        
        # La tecla "Applications/Menu" usualmente mapea a "menu" o "apps"
        hooks.append(('key', keyboard.on_press_key("menu", on_select_right, suppress=True)))
        # Alternative for Right Click (Shift+F10)
        hooks.append(('hotkey', keyboard.add_hotkey("shift+f10", on_select_right, suppress=True)))
        
        hooks.append(('key', keyboard.on_press_key("escape", on_cancel, suppress=True)))
        
        # Bloquear Alt+Tab y tecla Windows durante la navegación para no perder el foco
        hooks.append(('hotkey', keyboard.add_hotkey("alt+tab", lambda: None, suppress=True)))
        hooks.append(('key', keyboard.on_press_key("windows", lambda e: None, suppress=True)))
        hooks.append(('key', keyboard.on_press_key("left windows", lambda e: None, suppress=True)))
        hooks.append(('key', keyboard.on_press_key("right windows", lambda e: None, suppress=True)))

        try:
            while active:
                time.sleep(0.05)
        finally:
            for type_, h in hooks:
                try:
                    if type_ == 'key':
                        keyboard.unhook(h)
                    elif type_ == 'hotkey':
                        keyboard.remove_hotkey(h)
                except Exception:
                    pass

        if clicked:
            elem = elements[idx]
            self.tts.speak(f"Click en: {elem.text}", interrupt=True)
            # Damos un pequeño respiro para que suelte las teclas modificadoras y hook antes de clickear
            time.sleep(0.15)
            click_element(elem, self.offset_x, self.offset_y, click_type)
        else:
            self.tts.speak("Cancelado.", interrupt=True)

        return clicked
