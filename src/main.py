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

from config import load_config, run_setup, run_gui_setup, CONFIG_FILE
from tts_engine import TTSEngine
from ocr_engine import OCREngine
from screen_capture import capture_screen, capture_active_window
from navigator import ElementNavigator
from shadow_manager import ShadowManager
import keyboard
import win32gui
import win32process

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
        
        # Modo Sombra
        self.shadow = ShadowManager(CONFIG_FILE)
        self._is_learning = False
        
        self.is_dynamic_running = False
        self.dynamic_thread = None
        self.app = None
        self._last_reset_time = 0

    def start(self):
        """Inicializa todo y arranca el listener de hotkeys."""
        self.tts.play_startup()
        self.tts.speak("Iniciando PaddleOCR Scanner...")

        try:
            self.tts.speak("Cargando motor OCR.")
            self.ocr.initialize()
            self.tts.speak("Motor OCR listo.")
        except Exception as e:
            self.tts.speak(f"Error al inicializar el motor OCR: {e}")
            logger.error("Error inicializando OCR: %s", e, exc_info=True)
            sys.exit(1)

        # Hotkeys usando la librería 'keyboard' para soporte total de supresión (secuestro de teclas)
        try:
            keyboard.add_hotkey(self.config.get("hotkey_screen") or "ctrl+alt+s", self._on_scan_screen, suppress=True)
            keyboard.add_hotkey(self.config.get("hotkey_window") or "ctrl+alt+w", self._on_scan_window, suppress=True)
            keyboard.add_hotkey(self.config.get("hotkey_config") or "ctrl+shift+c", self._on_open_config, suppress=True)
            keyboard.add_hotkey(self.config.get("hotkey_quit") or "ctrl+alt+q", self._on_quit_hotkey, suppress=True)
            keyboard.add_hotkey(self.config.get("hotkey_dynamic") or "ctrl+alt+d", self._toggle_dynamic_mode, suppress=True)
            
            keyboard.add_hotkey("ctrl+alt+l", self._on_start_learning, suppress=True)
            keyboard.add_hotkey("ctrl+alt+r", self._on_reset_shadow, suppress=True)
            keyboard.add_hotkey("ctrl+alt+u", self._on_toggle_shadow, suppress=True)
            logger.info("Hotkeys registrados con supresión activa.")
        except Exception as e:
            logger.error("Error registrando hotkeys: %s", e)

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
        self.tts.play_shutdown()
        self.tts.speak("PaddleOCR Scanner cerrado.")
        logger.info("Scanner cerrado.")

    def _release_modifiers(self):
        """Fuerza la liberación de teclas modificadoras (Keyboard & WinAPI)."""
        # 1. Liberar vía librería keyboard para limpiar su estado interno
        for key in ['ctrl', 'alt', 'shift', 'windows']:
            try:
                keyboard.release(key)
            except Exception:
                pass
        
        # 2. Pequeño respiro para que Windows procese el estado físico
        time.sleep(0.05)

        # 3. Liberación forzosa vía Windows API (KeyUp)
        # LCtrl, RCtrl, LShift, RShift, LAlt, RAlt, LWin, RWin
        vks = [0xA2, 0xA3, 0xA0, 0xA1, 0xA4, 0xA5, 0x5B, 0x5C]
        for vk in vks:
            # 0x0002 es el flag KEYEVENTF_KEYUP
            ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)

    def _get_active_app_name(self):
        """Obtiene el título de la ventana activa para usar como nombre de perfil."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return "Global"
            # Limpiar un poco el título para que no sea excesivamente largo o variable
            return title[:50].strip()
        except Exception:
            return "Global"

    def _update_current_app(self):
        """Actualiza el perfil de sombra basado en la ventana actual."""
        app_name = self._get_active_app_name()
        self.shadow.set_app(app_name)

    def _on_scan_screen(self):
        """Escanea pantalla completa."""
        self._release_modifiers()
        self._update_current_app()
        self._start_scan(mode="screen")

    def _on_scan_window(self):
        """Escanea solo la ventana activa."""
        self._release_modifiers()
        self._update_current_app()
        self._start_scan(mode="window")
        
    def _toggle_dynamic_mode(self):
        """Alterna el estado del escaneo dinámico."""
        self._release_modifiers()
        self._update_current_app()
        if self.is_dynamic_running:
            self.is_dynamic_running = False
            self.tts.play_error() # Tono bajo para indicar que se apagó
            self.tts.speak("Escaneo dinámico desactivado.", interrupt=True)
        else:
            self.is_dynamic_running = True
            self.tts.play_scan_start() # Tono ascendente para indicar que arrancó
            self.tts.speak("Escaneando dinámicamente.", interrupt=True)
            self.dynamic_thread = threading.Thread(target=self._dynamic_ocr_loop, daemon=True)
            self.dynamic_thread.start()

    def _dynamic_ocr_loop(self):
        """Bucle que escanea la pantalla continuamente usando lógica similar a LION."""
        prev_string = ""
        
        while self.is_dynamic_running:
            start_time = time.time()
            
            # Actualizar perfil por si cambió de ventana
            self._update_current_app()
            
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
                    
                    # 3. OCR (con lock para evitar conflictos con otros hilos)
                    with self._scan_lock:
                        elements = self.ocr.scan_image(cropped_image)
                    
                    # 3.5 Filtrar por Modo Sombra
                    elements = self.shadow.filter_elements(elements)
                    
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
            if (old_config.get("ocr_language") != self.config.get("ocr_language") or
                old_config.get("use_gpu") != self.config.get("use_gpu") or
                old_config.get("image_scale") != self.config.get("image_scale")):
                self.tts.speak("Re-cargando motor OCR...")
                self.ocr = OCREngine(self.config)
                self.ocr.initialize()
                self.tts.speak("Motor OCR actualizado.")
        except Exception as e:
            self.tts.speak(f"Error en configuración: {e}", interrupt=True)
            logger.error("Error en configuración: %s", e, exc_info=True)

    def _on_quit_hotkey(self):
        """Cierra el programa liberando las teclas para evitar que queden 'pegadas'."""
        self._release_modifiers()
        time.sleep(0.2) # Breve espera para que Windows procese la liberación
        self._quit_event.set()
        if self.app:
            wx.CallAfter(self.app.ExitMainLoop)

    def _on_start_learning(self):
        """Inicia el proceso de aprendizaje del Modo Sombra."""
        if self._is_learning:
            self.tts.speak("Ya estoy aprendiendo la interfaz.", interrupt=True)
            return
        self._release_modifiers()
        self._update_current_app()
        threading.Thread(target=self._do_learning, daemon=True).start()

    def _do_learning(self):
        """Fase de aprendizaje: identifica elementos persistentes durante unos segundos."""
        self._is_learning = True
        try:
            app_name = self.shadow.current_app
            self.tts.play_scan_start()
            self.tts.speak(f"Modo Sombra: Aprendiendo perfil [{app_name}]. Mantené la pantalla quieta 5 segundos.", interrupt=True)
            
            samples = []
            start_time = time.time()
            duration = 5.0
            
            # 1. Recolectar muestras
            while time.time() - start_time < duration:
                try:
                    # Usar captura de pantalla completa para el aprendizaje
                    image, off_x, off_y = capture_screen()
                    
                    with self._scan_lock:
                        elements = self.ocr.scan_image(image)
                        
                    if elements:
                        samples.append(elements)
                    time.sleep(0.6) # Un poco más rápido que antes para tener más muestras
                except Exception as e:
                    logger.error("Error en muestreo de aprendizaje: %s", e)

            if len(samples) < 2:
                self.tts.play_error()
                self.tts.speak("No se obtuvieron suficientes muestras para aprender.")
                return

            # 2. Agrupar elementos similares entre muestras por proximidad
            # Cada entrada en 'groups' será: {'element': DetectedElement, 'count': int}
            groups = []
            
            for sample in samples:
                for el in sample:
                    found_group = False
                    # Buscar un grupo existente donde este elemento encaje
                    for group in groups:
                        target = group['element']
                        # Distancia euclidiana entre centros
                        dist_sq = ((el.x + el.w/2) - (target.x + target.w/2))**2 + \
                                  ((el.y + el.h/2) - (target.y + target.h/2))**2
                        
                        # Si están cerca (radio de 20px)
                        if dist_sq < 400: 
                            text_sim = SequenceMatcher(None, el.text, target.text).ratio()
                            
                            # Criterio de coincidencia:
                            # 1. El texto es muy parecido (>70%)
                            # 2. O la posición Y el tamaño son muy estables (típico de un reloj o HUD)
                            #    Un subtítulo cambia mucho de ancho, un reloj no.
                            size_stable = abs(el.w - target.w) < 15 and abs(el.h - target.h) < 10
                            
                            if text_sim > 0.7 or (dist_sq < 225 and size_stable):
                                group['count'] += 1
                                found_group = True
                                break
                    
                    if not found_group:
                        groups.append({'element': el, 'count': 1})

            # 3. Identificar regiones estables (que aparecen en > 80% de las muestras)
            # Esto evita que subtítulos o avisos temporales sean capturados.
            threshold = len(samples) * 0.8
            stable_regions = []
            stable_texts = []
            
            for group in groups:
                if group['count'] >= threshold:
                    el = group['element']
                    # Si el texto es corto y siempre igual, lo marcamos como sombra de texto también
                    if len(el.text) > 2 and len(el.text) < 30:
                        stable_texts.append(el.text)

                    # Añadir margen generoso para absorber jitter de OCR
                    margin = 8
                    stable_regions.append([
                        el.x - margin, 
                        el.y - margin, 
                        el.w + margin*2, 
                        el.h + margin*2
                    ])

            # 4. Guardar nuevas regiones y textos
            added_count = 0
            for reg in stable_regions:
                if self.shadow.add_region(*reg):
                    added_count += 1
            
            for txt in stable_texts:
                self.shadow.add_text_shadow(txt)
            
            self.shadow.save()
            self.tts.play_scan_success()
            if added_count > 0:
                self.tts.speak(f"Aprendizaje completado en [{app_name}]. Se agregaron {added_count} sombras.", interrupt=True)
            else:
                self.tts.speak(f"No se encontraron elementos nuevos en [{app_name}].", interrupt=True)

        except Exception as e:
            logger.error("Error crítico en _do_learning: %s", e, exc_info=True)
            self.tts.speak(f"Ocurrió un error durante el aprendizaje: {e}")
        finally:
            self._is_learning = False

    def _on_reset_shadow(self):
        """Limpia las sombras del perfil actual o de todos (si se pulsa 2 veces)."""
        self._release_modifiers()
        now = time.time()
        
        # Si la diferencia es menor a 0.6 segundos, es una pulsación doble
        if now - self._last_reset_time < 0.6:
            self.shadow.clear_all()
            self.tts.play_error()
            self.tts.speak("Todas las sombras de todos los perfiles han sido eliminadas.", interrupt=True)
            self._last_reset_time = 0 # Resetear tiempo para evitar triple pulsación
        else:
            self._last_reset_time = now
            # Usar un pequeño delay para el mensaje de la app actual por si viene la segunda pulsación
            threading.Timer(0.6, self._do_single_reset, args=(now,)).start()

    def _do_single_reset(self, press_time):
        """Ejecuta el reset individual si no hubo una segunda pulsación."""
        # Si el tiempo sigue siendo el mismo, no hubo otra pulsación en el medio
        if self._last_reset_time == press_time:
            self._update_current_app()
            app_name = self.shadow.current_app
            self.shadow.clear()
            self.shadow.is_enabled = True
            self.tts.play_error()
            self.tts.speak(f"Sombras de [{app_name}] reseteadas. Pulsá dos veces rápido para borrar todo.", interrupt=True)

    def _on_toggle_shadow(self):
        """Activa o desactiva el filtrado de sombras."""
        self._release_modifiers()
        is_enabled = self.shadow.toggle()
        if is_enabled:
            self.tts.play_scan_success()
            self.tts.speak("Modo Sombra activado.")
        else:
            self.tts.play_error()
            self.tts.speak("Modo Sombra desactivado.")

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
            
            self.tts.play_scan_start()
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
            
            # 2.5 Filtrar por Modo Sombra
            elements = self.shadow.filter_elements(elements)

            if not elements:
                self.tts.play_error()
                self.tts.speak("No se detectó texto.", interrupt=True)
                return

            self.tts.play_scan_success()
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
