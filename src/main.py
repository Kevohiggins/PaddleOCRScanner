"""
PaddleOCR Screen Scanner — Punto de entrada principal.

Herramienta de accesibilidad que escanea la pantalla con OCR,
permite navegar los elementos detectados con teclado, y hace click
en el elemento seleccionado.

Uso:
    python main.py            → Inicia el scanner
    python main.py --setup    → Abre menú de configuración (consola)
"""

import argparse
import ctypes
import logging
import os
import sys
import threading
import time
import wx
from difflib import SequenceMatcher

from pynput import keyboard as pynput_keyboard

from config import load_config, run_setup, run_gui_setup
from tts_engine import TTSEngine
from ocr_engine import OCREngine
from screen_capture import capture_screen, capture_active_window
from navigator import ElementNavigator

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def is_admin() -> bool:
    """Verifica si el proceso actual tiene privilegios de administrador."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def elevate_to_admin():
    """Re-lanza el script como administrador para que los hooks funcionen en ventanas elevadas."""
    params = " ".join(sys.argv[1:])
    python_exe = sys.executable

    if getattr(sys, 'frozen', False):
        # Si está compilado (PyInstaller), python_exe ya es el ejecutable.
        # No pasamos el script como argumento extra porque eso causaría un error en argparse.
        logger.info("Re-lanzando ejecutable como administrador: %s %s", python_exe, params)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", python_exe, params, None, 1,
        )
    else:
        script = os.path.abspath(sys.argv[0])
        logger.info("Re-lanzando script como administrador: %s %s %s", python_exe, script, params)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", python_exe, f'"{script}" {params}', None, 1,
        )

    if ret > 32:
        sys.exit(0)
    else:
        logger.error("No se pudo elevar a administrador (código: %s)", ret)
        print("Error: No se pudo obtener permisos de administrador.")
        sys.exit(1)


class PaddleOCRScanner:
    """Aplicación principal del scanner."""

    def __init__(self):
        self.config = load_config()
        self.tts = TTSEngine()
        self.ocr = OCREngine(self.config)
        self._scan_lock = threading.Lock()
        self._quit_event = threading.Event()
        self._last_offset_x = 0
        self._last_offset_y = 0
        
        self.is_dynamic_running = False
        self.dynamic_thread = None
        self.hotkey_listener = None
        self.app = None

    def start(self):
        """Inicializa todo y arranca el listener de hotkeys."""
        self.tts.speak("Iniciando PaddleOCR Scanner...")

        try:
            self.tts.speak("Cargando motor OCR.")
            self.ocr.initialize()
            self.tts.speak("Motor OCR listo.")
        except Exception as e:
            self.tts.speak(f"Error al inicializar el motor OCR: {e}")
            logger.error("Error inicializando OCR: %s", e, exc_info=True)
            sys.exit(1)

        # Hotkeys al estilo SpectrOCR usando pynput
        hk_map = {
            self._to_pynput_str(self.config.get("hotkey_screen") or "ctrl+alt+s"): self._on_scan_screen,
            self._to_pynput_str(self.config.get("hotkey_window") or "ctrl+alt+w"): self._on_scan_window,
            self._to_pynput_str(self.config.get("hotkey_config") or "ctrl+shift+c"): self._on_open_config,
            self._to_pynput_str(self.config.get("hotkey_quit") or "ctrl+alt+q"): self._on_quit_hotkey,
            self._to_pynput_str(self.config.get("hotkey_dynamic") or "ctrl+alt+d"): self._toggle_dynamic_mode
        }
        
        self.hotkey_listener = pynput_keyboard.GlobalHotKeys(hk_map)
        self.hotkey_listener.start()

        hotkey_screen = self.config.get("hotkey_screen") or "ctrl+alt+s"
        hotkey_window = self.config.get("hotkey_window") or "ctrl+alt+w"
        hotkey_config = self.config.get("hotkey_config") or "ctrl+shift+c"
        hotkey_quit = self.config.get("hotkey_quit") or "ctrl+alt+q"
        hotkey_dynamic = self.config.get("hotkey_dynamic") or "ctrl+alt+d"

        tts_screen = hotkey_screen.replace('ctrl', 'control').replace('+', ' ')
        tts_window = hotkey_window.replace('ctrl', 'control').replace('+', ' ')
        tts_config = hotkey_config.replace('ctrl', 'control').replace('+', ' ')
        tts_quit = hotkey_quit.replace('ctrl', 'control').replace('+', ' ')
        tts_dynamic = hotkey_dynamic.replace('ctrl', 'control').replace('+', ' ')

        self.tts.speak(
            f"Scanner activo. "
            f"{tts_screen} para pantalla completa. "
            f"{tts_window} para ventana activa. "
            f"{tts_dynamic} para escaneo dinámico. "
            f"{tts_config} para configuración. "
            f"{tts_quit} para salir."
        )

        logger.info("Scanner activo. Hotkeys: screen=%s, window=%s, config=%s, quit=%s",
                     hotkey_screen, hotkey_window, hotkey_config, hotkey_quit)
        print("PaddleOCR Scanner activo (administrador).")
        print(f"  Pantalla completa: {hotkey_screen}")
        print(f"  Ventana activa:    {hotkey_window}")
        print(f"  Configuración:     {hotkey_config}")
        print(f"  Salir:             {hotkey_quit}")
        print()

        self.app = wx.App(False)
        self.dummy_frame = wx.Frame(None, title="Dummy")
        self.app.MainLoop()

        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self.tts.speak("PaddleOCR Scanner cerrado.")
        logger.info("Scanner cerrado.")

    def _to_pynput_str(self, hk_str):
        """Convierte 'ctrl+alt+s' a '<ctrl>+<alt>+s' para pynput."""
        parts = hk_str.lower().split('+')
        new_parts = []
        for p in parts:
            p = p.strip()
            if len(p) > 1:
                new_parts.append(f"<{p}>")
            else:
                new_parts.append(p)
        return "+".join(new_parts)

    def _release_modifiers(self):
        """Fuerza la liberación de teclas modificadoras a nivel de sistema (Windows API)."""
        # Códigos Virtual-Key para: LCtrl, RCtrl, LShift, RShift, LAlt, RAlt, LWin, RWin
        # 0x0002 es el flag KEYEVENTF_KEYUP
        for vk in [0xA2, 0xA3, 0xA0, 0xA1, 0xA4, 0xA5, 0x5B, 0x5C]:
            ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)

    def _on_scan_screen(self):
        """Escanea pantalla completa."""
        self._release_modifiers()
        self._start_scan(mode="screen")

    def _on_scan_window(self):
        """Escanea solo la ventana activa."""
        self._release_modifiers()
        self._start_scan(mode="window")
        
    def _toggle_dynamic_mode(self):
        """Alterna el estado del escaneo dinámico."""
        self._release_modifiers()
        if self.is_dynamic_running:
            self.is_dynamic_running = False
            self.tts.speak("Escaneo dinámico desactivado.", interrupt=True)
        else:
            self.is_dynamic_running = True
            self.tts.speak("Escaneo dinámico activado.", interrupt=True)
            self.dynamic_thread = threading.Thread(target=self._dynamic_ocr_loop, daemon=True)
            self.dynamic_thread.start()

    def _dynamic_ocr_loop(self):
        """Bucle que escanea la pantalla continuamente usando lógica similar a LION."""
        prev_string = ""
        
        while self.is_dynamic_running:
            start_time = time.time()
            
            # Leer configuración en cada ciclo para permitir cambios en tiempo real
            interval = float(self.config.get("dynamic_interval", 1.0))
            target = self.config.get("dynamic_target", "screen")
            sensitivity = float(self.config.get("dynamic_sensitivity", 50))
            threshold = sensitivity / 100.0
            
            crop_top = float(self.config.get("crop_top", 0)) / 100.0
            crop_bottom = float(self.config.get("crop_bottom", 0)) / 100.0
            crop_left = float(self.config.get("crop_left", 0)) / 100.0
            crop_right = float(self.config.get("crop_right", 0)) / 100.0

            try:
                # 1. Captura
                if target == "window":
                    image, off_x, off_y = capture_active_window()
                else:
                    image, off_x, off_y = capture_screen()
                
                h, w = image.shape[:2]
                
                # 2. Calcular márgenes de recorte
                y1 = int(h * crop_top)
                y2 = int(h * (1.0 - crop_bottom))
                x1 = int(w * crop_left)
                x2 = int(w * (1.0 - crop_right))
                
                # Validar recorte
                if y1 < y2 and x1 < x2:
                    cropped_image = image[y1:y2, x1:x2]
                    
                    # 3. OCR
                    elements = self.ocr.scan_image(cropped_image)
                    current_texts = [e.text for e in elements]
                    
                    # 4. Diferencias estilo LION (usando SequenceMatcher)
                    all_text = " ".join(current_texts).strip()
                    
                    if all_text:
                        similarity = SequenceMatcher(None, prev_string, all_text).ratio()
                        # Si el texto cambió lo suficiente, verbalizar
                        if similarity < threshold:
                            self.tts.speak(all_text, interrupt=True)
                            prev_string = all_text
                    
            except Exception as e:
                logger.error("Error en bucle dinámico: %s", e)
                
            # Calcular tiempo restante para dormir
            elapsed = time.time() - start_time
            sleep_time = max(0.1, interval - elapsed)
            time.sleep(sleep_time)

    def _on_open_config(self):
        """Abre la GUI de configuración en el hilo principal."""
        self._release_modifiers()
        wx.CallAfter(self._open_config_native)

    def _open_config_native(self):
        """Abre la ventana de configuración wxPython de manera nativa."""
        try:
            from gui_config import show_config_window
            old_config = dict(self.config)
            
            new_config = show_config_window(self.config)
            
            if new_config:
                self.config.update(new_config)
                self.tts.speak("Configuración actualizada.", interrupt=True)
                # Re-inicializar OCR si cambió algún parámetro relevante
                if (old_config.get("det_model") != self.config.get("det_model") or
                    old_config.get("rec_model") != self.config.get("rec_model")):
                    self.tts.speak("Re-cargando motor OCR con los nuevos modelos...")
                    self.ocr = OCREngine(self.config)
                    self.ocr.initialize()
                    self.tts.speak("Motor OCR actualizado.")
        except Exception as e:
            self.tts.speak(f"Error en configuración: {e}", interrupt=True)
            logger.error("Error en configuración: %s", e, exc_info=True)

    def _on_quit_hotkey(self):
        self._quit_event.set()
        if self.app:
            wx.CallAfter(self.app.ExitMainLoop)

    def _start_scan(self, mode: str):
        """Inicia un escaneo en thread aparte."""
        if not self._scan_lock.acquire(blocking=False):
            self.tts.speak("Escaneo en curso, esperá.", interrupt=True)
            return
        threading.Thread(target=self._do_scan, args=(mode,), daemon=True).start()

    def _do_scan(self, mode: str):
        """Ejecuta el flujo: captura → OCR → navegación."""
        try:
            if mode == "window":
                self.tts.speak("Escaneando ventana activa...", interrupt=True)
            else:
                self.tts.speak("Escaneando pantalla...", interrupt=True)
            logger.info("Escaneo modo=%s", mode)

            # 1. Captura
            if mode == "window":
                image, offset_x, offset_y = capture_active_window()
            else:
                image, offset_x, offset_y = capture_screen()

            self._last_offset_x = offset_x
            self._last_offset_y = offset_y
            logger.info("Captura: %dx%d, offset=(%d,%d)",
                        image.shape[1], image.shape[0], offset_x, offset_y)

            # 2. OCR
            elements = self.ocr.scan_image(image)

            if not elements:
                self.tts.speak("No se detectó texto.", interrupt=True)
                return

            logger.info("Detectados %d elementos", len(elements))

            # 3. Navegación
            navigator = ElementNavigator(self.tts, offset_x, offset_y)
            navigator.navigate(elements)

        except Exception as e:
            self.tts.speak(f"Error: {e}", interrupt=True)
            logger.error("Error en escaneo: %s", e, exc_info=True)
        finally:
            self._scan_lock.release()


def main():
    parser = argparse.ArgumentParser(description="PaddleOCR Screen Scanner")
    parser.add_argument("--setup", action="store_true", help="Configuración por consola")
    parser.add_argument("--no-admin", action="store_true", help="No pedir admin")
    args = parser.parse_args()

    if args.setup:
        run_setup()
        return

    if not args.no_admin and not is_admin():
        print("Solicitando privilegios de administrador...")
        elevate_to_admin()
        return

    scanner = PaddleOCRScanner()
    scanner.start()


if __name__ == "__main__":
    main()
