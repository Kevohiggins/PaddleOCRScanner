"""
PaddleOCR Screen Scanner — Versión Estable con Traducción Argos Estándar.
"""

import ctypes
import logging
import os
import sys
import threading
import time
import wx
import win32gui
import win32con
import win32api
import win32process
from difflib import SequenceMatcher

from config import load_config, save_config, CONFIG_FILE, get_effective_config, get_base_path
from tts_engine import TTSEngine
from ocr_engine import OCREngine
from screen_capture import capture_screen, capture_active_window
from navigator import ElementNavigator
from shadow_manager import ShadowManager
from translator import translator_instance
import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main")

MOD_MAP = {"ctrl": win32con.MOD_CONTROL, "alt": win32con.MOD_ALT, "shift": win32con.MOD_SHIFT, "win": win32con.MOD_WIN}
VK_MAP = {
    "enter": 0x0D, "esc": 0x1B, "space": 0x20, "tab": 0x09, "backspace": 0x08, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B, "apps": 0x5D, "menu": 0x5D
}

def parse_hotkey(hotkey_str):
    if not hotkey_str or hotkey_str == "Sin asignar": return 0, 0
    parts = [p.strip().lower() for p in hotkey_str.split('+')]
    mods, vk = 0, 0
    for p in parts:
        if p in MOD_MAP:
            mods |= MOD_MAP[p]
        elif p in VK_MAP:
            vk = VK_MAP[p]
        elif len(p) == 1:
            res = ctypes.windll.user32.VkKeyScanW(ord(p))
            if res != -1: vk = res & 0xFF
    return mods, vk

import wx.adv

class TrayIcon(wx.adv.TaskBarIcon):
    def __init__(self, scanner):
        super().__init__()
        self.scanner = scanner
        
        # Usamos un icono estándar de información si no hay uno específico
        icon = wx.ArtProvider.GetIcon(wx.ART_INFORMATION, wx.ART_OTHER, (16, 16))
        self.SetIcon(icon, "PaddleOCRScanner")
        
        self.Bind(wx.adv.EVT_TASKBAR_RIGHT_DOWN, self.on_click)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_click)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        help_item = menu.Append(wx.ID_ANY, "Ayuda")
        config_item = menu.Append(wx.ID_ANY, "Configuración")
        exit_item = menu.Append(wx.ID_ANY, "Salir")
        
        self.Bind(wx.EVT_MENU, self.on_help, help_item)
        self.Bind(wx.EVT_MENU, self.on_config, config_item)
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        
        return menu

    def on_click(self, event):
        self.PopupMenu(self.CreatePopupMenu())

    def on_help(self, event):
        self.scanner._on_open_manual()

    def on_config(self, event):
        self.scanner._on_open_config()

    def on_exit(self, event):
        self.scanner._on_quit_hotkey()

class HotkeyFrame(wx.Frame):
    def __init__(self, callback_map):
        super().__init__(None, style=wx.NO_BORDER)
        self.callback_map = callback_map
        self.Bind(wx.EVT_HOTKEY, self.on_hotkey)

    def register(self, hk_id, hotkey_str):
        mods, vk = parse_hotkey(hotkey_str)
        self.UnregisterHotKey(hk_id)
        if vk == 0: return False
        return self.RegisterHotKey(hk_id, mods, vk)

    def unregister_all(self):
        for hk_id in list(self.callback_map.keys()): self.UnregisterHotKey(hk_id)

    def on_hotkey(self, event):
        hk_id = event.GetId()
        if hk_id in self.callback_map: self.callback_map[hk_id]()

class PaddleOCRScanner:
    def __init__(self):
        self.full_config = load_config()
        self.config = get_effective_config(self.full_config)
        self.tts = TTSEngine()
        self.ocr = OCREngine(self.config)
        self._scan_lock = threading.Lock()
        self.is_dynamic_running = False
        self.shadow = ShadowManager(CONFIG_FILE)
        self.app = wx.App(False)
        self.tray = TrayIcon(self)
        self.hotkey_frame = None
        self._last_profile = "Global"
        self._last_elements = []

    def start(self):
        self.tts.play_startup()
        self.tts.speak("Cargando scanner.")
        try:
            self.ocr.initialize()
            translator_instance.set_on_ready_callback(lambda: self.tts.speak("Motor de traducción listo.") if self.config.get("translate_enabled") else None)
            
            if self.config.get("translate_type", "local") == "local" and self.config.get("translate_enabled"):
                self.tts.speak("Iniciando motor de traducción.")
                translator_instance.ensure_initialized()
        except Exception as e:
            logger.error(f"Error inicializando OCR: {e}")
            self.tts.speak("Error al cargar el motor de lectura.")
        
        hk_map = { 
            101: self._on_scan_screen, 102: self._on_scan_window, 103: self._on_open_config, 
            104: self._on_quit_hotkey, 105: self._toggle_dynamic_scan, 106: self._on_learn_shadow, 
            107: self._on_clear_shadow, 108: self._on_toggle_shadow, 109: self._on_open_manual,
            110: self._on_toggle_auto_rescan
        }
        self.hotkey_frame = HotkeyFrame(hk_map); self._refresh_hotkeys()
        self.tts.speak("Scanner listo.")
        self.app.MainLoop()
        if hasattr(self, 'tray'): self.tray.Destroy()
        self.tts.speak("Cerrando programa.")
        self.tts.play_shutdown(); time.sleep(1.0); sys.exit(0)

    def _get_current_app_name(self):
        hwnd = win32gui.GetForegroundWindow(); _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try: import psutil; return psutil.Process(pid).name()
        except: return "Global"

    def _update_profile(self):
        app_name = self._get_current_app_name(); self.shadow.set_app(app_name)
        new_config = get_effective_config(self.full_config, app_name)
        
        needs_reinit = (
            new_config.get("ocr_language") != self.config.get("ocr_language") or 
            new_config.get("use_gpu") != self.config.get("use_gpu") or
            str(new_config.get("image_scale")) != str(self.config.get("image_scale"))
        )
        
        if needs_reinit:
            self.config = new_config; self.ocr = OCREngine(self.config); self.ocr.initialize()
        else: 
            self.config = new_config
            self.ocr.config = new_config
        
        self._last_profile = app_name if app_name in self.full_config["profiles"] else "Global"

    def _refresh_hotkeys(self):
        c = self.full_config["global"]
        self.hotkey_frame.register(101, c.get("hotkey_screen", "ctrl+alt+s"))
        self.hotkey_frame.register(102, c.get("hotkey_window", "ctrl+alt+w"))
        self.hotkey_frame.register(103, c.get("hotkey_config", "ctrl+alt+c"))
        self.hotkey_frame.register(104, c.get("hotkey_quit", "ctrl+alt+q"))
        self.hotkey_frame.register(105, c.get("hotkey_dynamic", "ctrl+alt+d"))
        self.hotkey_frame.register(106, c.get("hotkey_shadow_learn", "ctrl+alt+l"))
        self.hotkey_frame.register(107, c.get("hotkey_shadow_clear", "ctrl+alt+r"))
        self.hotkey_frame.register(108, c.get("hotkey_shadow_toggle", "ctrl+alt+u"))
        self.hotkey_frame.register(109, c.get("hotkey_manual", "ctrl+alt+f1"))
        self.hotkey_frame.register(110, c.get("hotkey_toggle_auto_rescan", "ctrl+alt+a"))

    def _on_open_manual(self):
        self._release_modifiers()
        import webbrowser
        manual_path = os.path.join(get_base_path(), "manual.html")
        if os.path.exists(manual_path):
            webbrowser.open(f"file:///{manual_path}")
            self.tts.speak("Abriendo manual.")
        else:
            self.tts.speak("No se encontró el manual.")

    def _on_toggle_auto_rescan(self):
        self._release_modifiers()
        current = self.config.get("auto_rescan_after_click", False)
        self.config["auto_rescan_after_click"] = not current
        self.full_config["global"]["auto_rescan_after_click"] = not current
        state = "activado" if not current else "desactivado"
        self.tts.speak(f"Reescaneo automático {state}.")

    def _release_modifiers(self):
        for vk in [0x11, 0x12, 0x10, 0x5B, 0x5C]: ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)
        time.sleep(0.1)

    def _on_learn_shadow(self): self._release_modifiers(); threading.Thread(target=self._do_burst_learning, daemon=True).start()

    def _do_burst_learning(self):
        app_name = self._get_current_app_name(); self.shadow.set_app(app_name)
        self.tts.speak("Aprendizaje iniciado.")
        burst_results = []
        burst_count = int(self.config.get("shadow_burst_count", 4))
        for i in range(burst_count):
            try:
                img, ox, oy = capture_screen(); elements = self.ocr.scan_image(img)
                burst_results.append(elements); self.tts.play_scan_start()
            except Exception as e: logger.error(f"Error en aprendizaje: {e}")
            time.sleep(1.0)
        count = self.shadow.learn_from_burst(burst_results)
        if count > 0:
            self.full_config = load_config(); self.tts.play_scan_success(); self.tts.speak(f"Completado. {count} sombras fijadas.")
        else: self.tts.play_error(); self.tts.speak("Sin sombras nuevas.")

    def _on_clear_shadow(self): self._release_modifiers(); self.shadow.clear(); self.tts.speak("Sombras borradas.")
    def _on_toggle_shadow(self): self._release_modifiers(); state = self.shadow.toggle(); self.tts.speak("Sombra activa." if state else "Sombra inactiva.")

    def _on_scan_screen(self): 
        self._release_modifiers(); self._update_profile()
        self.tts.speak("Escaneando pantalla."); self._start_scan("screen")

    def _on_scan_window(self): 
        self._release_modifiers(); self._update_profile()
        self.tts.speak("Escaneando ventana."); self._start_scan("window")

    def _apply_crops(self, img, ox, oy):
        h, w = img.shape[:2]
        ct, cb, cl, cr = [float(self.config.get(k, 0))/100.0 for k in ["crop_top", "crop_bottom", "crop_left", "crop_right"]]
        y1, y2 = int(h * ct), int(h * (1.0 - cb)); x1, x2 = int(w * cl), int(w * (1.0 - cr))
        if y2 <= y1 + 50: y1, y2 = 0, h
        if x2 <= x1 + 50: x1, x2 = 0, w
        return img[y1:y2, x1:x2], ox + x1, oy + y1

    def _toggle_dynamic_scan(self):
        self._release_modifiers()
        if self.is_dynamic_running:
            self.is_dynamic_running = False; self.tts.play_error(); self.tts.speak("Escaneo dinámico detenido.")
        else:
            self._update_profile(); self.is_dynamic_running = True
            self.tts.play_scan_start(); self.tts.speak("Escaneo dinámico activado.")
            threading.Thread(target=self._dynamic_scan_loop, daemon=True).start()

    def _dynamic_scan_loop(self):
        prev_text = ""
        prev_elements_texts = set()
        prev_img_hash = None
        while self.is_dynamic_running:
            loop_start = time.time()
            try:
                self._update_profile()
                img, ox, oy = capture_active_window() if self.config.get("dynamic_target") == "window" else capture_screen()
                img, ox, oy = self._apply_crops(img, ox, oy)

                # Atajo rápido: si la imagen no cambió, no gastar CPU en OCR
                import hashlib
                img_hash = hashlib.md5(img.tobytes()).digest()
                if img_hash == prev_img_hash:
                    # El usuario sugirió poner el sleep aquí. Esperamos el intervalo configurado.
                    elapsed = time.time() - loop_start
                    remaining = max(0.1, float(self.config.get("dynamic_interval", 1.0)) - elapsed)
                    time.sleep(remaining)
                    continue
                prev_img_hash = img_hash

                with self._scan_lock: elements = self.ocr.scan_image(img)
                self._last_elements = elements
                elements = self.shadow.filter_elements(elements)

                sens_val = int(self.config.get("dynamic_sensitivity", 50))
                if sens_val >= 100: # Alta
                    min_len = 1; threshold = 0.9
                elif sens_val >= 80: # Media Alta
                    min_len = 1; threshold = 0.7
                elif sens_val >= 60: # Normal
                    min_len = 2; threshold = 0.5
                elif sens_val >= 40: # Media Baja
                    min_len = 3; threshold = 0.3
                else: # Baja
                    min_len = 4; threshold = 0.1

                if self.config.get("dynamic_diff_mode", False):
                    # Modo Diferencial: solo leer lo nuevo
                    current_texts = [e.text.strip() for e in elements if len(e.text.strip()) >= min_len]
                    new_texts = []
                    for txt in current_texts:
                        is_old = False
                        for prev in prev_elements_texts:
                            if SequenceMatcher(None, txt.lower(), prev.lower()).ratio() >= threshold:
                                is_old = True; break
                        if not is_old:
                            new_texts.append(txt)
                    prev_elements_texts = set(current_texts)
                    if new_texts:
                        new_text = " ".join(new_texts)
                        if self.config.get("translate_enabled"):
                            from_code = self.config.get("translate_from", "en")
                            to_code = self.config.get("translate_to", "es")
                            new_text = translator_instance.translate(
                                new_text, from_code, to_code, 
                                translate_type=self.config.get("translate_type", "local"),
                                service=self.config.get("translate_service", "google"),
                                swap=self.config.get("translate_swap", False)
                            )
                        self.tts.speak(new_text, interrupt=self.config.get("dynamic_interrupt", False))
                else:
                    # Modo clásico: leer todo si cambió
                    filtered_elements = [e for e in elements if len(e.text.strip()) >= min_len]
                    full_text = " ".join([e.text for e in filtered_elements]).strip()
                    if full_text and SequenceMatcher(None, prev_text, full_text).ratio() < threshold:
                        prev_text = full_text
                        if self.config.get("translate_enabled"):
                            from_code = self.config.get("translate_from", "en")
                            to_code = self.config.get("translate_to", "es")
                            full_text = translator_instance.translate(
                                full_text, from_code, to_code, 
                                translate_type=self.config.get("translate_type", "local"),
                                service=self.config.get("translate_service", "google"),
                                swap=self.config.get("translate_swap", False)
                            )
                        self.tts.speak(full_text, interrupt=self.config.get("dynamic_interrupt", False))
            except Exception as e: logger.error(f"Error dinámico: {e}")
            
            # Sleep compensado: descuenta el tiempo que tardó el procesamiento
            elapsed = time.time() - loop_start
            remaining = max(0, float(self.config.get("dynamic_interval", 1.0)) - elapsed)
            time.sleep(remaining)

    def _start_scan(self, mode):
        if self._scan_lock.locked(): return
        threading.Thread(target=self._do_scan, args=(mode,), daemon=True).start()

    def _do_scan(self, mode):
        with self._scan_lock:
            try:
                self.tts.play_scan_start()
                img, ox, oy = capture_active_window() if mode == "window" else capture_screen()
                img, ox, oy = self._apply_crops(img, ox, oy)
                raw = self.ocr.scan_image(img); self._last_elements = raw
                elements = self.shadow.filter_elements(raw)
            except Exception as e:
                logger.error(f"Error en escaneo: {e}")
                self.tts.speak("Error en el escaneo.")
                return

        # La traducción se hace dinámicamente en ElementNavigator._announce()
        # al navegar, para no retrasar el reporte inicial de resultados.

        if elements:
            self.tts.play_scan_success()
            self.tts.speak(f"{len(elements)} resultados.", interrupt=True)
            nav = ElementNavigator(self.tts, self.config, ox, oy, rescan_callback=lambda: self._start_scan(mode))
            nav.navigate(elements)
        else: 
            self.tts.play_error(); self.tts.speak("No se detectó nada.", interrupt=True)

    def _on_open_config(self): self._release_modifiers(); wx.CallAfter(self._open_config_native)

    def _open_config_native(self):
        from gui_config import show_config_window
        res = show_config_window(self.full_config, self._last_profile, restart_callback=self.restart_app)
        if res:
            old_trans = self.config.get("translate_enabled", False)
            self.full_config = res
            self._update_profile()
            new_trans = self.config.get("translate_enabled", False)
            
            msg = "Guardado."
            if old_trans != new_trans:
                msg += " Traducción " + ("activada." if new_trans else "desactivada.")
                if new_trans:
                    translator_instance.ensure_initialized()
            
            translator_instance.refresh_languages()
            self.tts.speak(msg)
        self._refresh_hotkeys()

    def _on_quit_hotkey(self):
        self._release_modifiers()
        if self.app: wx.CallAfter(self.app.ExitMainLoop)

    def restart_app(self):
        import sys
        import subprocess
        self.is_dynamic_running = False
        executable = sys.executable
        args = sys.argv
        subprocess.Popen([executable] + args)
        os._exit(0)

def main():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{os.path.abspath(sys.argv[0])}"', None, 1)
    else: PaddleOCRScanner().start()

if __name__ == "__main__": main()
