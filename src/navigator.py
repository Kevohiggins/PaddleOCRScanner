import ctypes
import ctypes.wintypes
import logging
import time
import win32api
import win32con

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

LRESULT = ctypes.c_longlong
if ctypes.sizeof(ctypes.c_void_p) == 4: LRESULT = ctypes.c_long

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT))

SPECIAL_VK = {
    "enter": 0x0D, "esc": 0x1B, "space": 0x20, "tab": 0x09, "backspace": 0x08,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "page up": 0x21, "page down": 0x22,
    "insert": 0x2D, "delete": 0x2E, "capslock": 0x14,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "apps": 0x5D, "menu": 0x5D, "shift": 0x10, "ctrl": 0x11, "alt": 0x12
}

# Constantes de máscara para modificadores
MOD_SHIFT = 1 << 0
MOD_CTRL  = 1 << 1
MOD_ALT   = 1 << 2

def string_to_hotkey(s, default_s=""):
    s = s.lower().strip()
    if not s: s = default_s.lower()
    parts = [p.strip() for p in s.split('+')]
    vk = SPECIAL_VK.get(parts[-1], user32.VkKeyScanW(ord(parts[-1][0])) & 0xFF if len(parts[-1])==1 else 0)
    mask = 0
    if "shift" in parts: mask |= MOD_SHIFT
    if "ctrl" in parts or "control" in parts: mask |= MOD_CTRL
    if "alt" in parts or "menu" in parts: mask |= MOD_ALT
    return vk, mask

class ElementNavigator:
    def __init__(self, tts, config, offset_x=0, offset_y=0):
        self.tts = tts; self.config = config; self.offset_x = offset_x; self.offset_y = offset_y
        self.elements = []; self.index = -1; self._hook = None; self._running = False

    def navigate(self, elements):
        if not elements: return
        self.elements = elements; self.index = -1; self._running = True
        self._callback = HOOKPROC(self._hook_callback)
        self._hook = user32.SetWindowsHookExW(13, self._callback, kernel32.GetModuleHandleW(None), 0)
        if not self._hook: self._hook = user32.SetWindowsHookExW(13, self._callback, None, 0)
        msg = ctypes.wintypes.MSG()
        while self._running and user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg)); user32.DispatchMessageW(ctypes.byref(msg))

    def _stop(self):
        self._running = False
        if self._hook: user32.UnhookWindowsHookEx(self._hook); self._hook = None
        user32.PostQuitMessage(0)

    def _get_current_mask(self):
        mask = 0
        if (win32api.GetKeyState(win32con.VK_SHIFT) & 0x8000): mask |= MOD_SHIFT
        if (win32api.GetKeyState(win32con.VK_CONTROL) & 0x8000): mask |= MOD_CTRL
        if (win32api.GetKeyState(win32con.VK_MENU) & 0x8000): mask |= MOD_ALT
        return mask

    def _hook_callback(self, nCode, wParam, lParam):
        if nCode >= 0 and wParam == win32con.WM_KEYDOWN:
            if self._handle_key(lParam.contents.vkCode): return 1
        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def _handle_key(self, vk):
        current_mask = self._get_current_mask()
        
        # Mapa de acciones basado en configuración
        actions = {
            "key_double": ("shift+enter", self._on_double),
            "key_right":  ("apps", self._on_right),
            "key_click":  ("enter", self._on_left),
            "key_next":   ("down", self._on_next),
            "key_prev":   ("up", self._on_prev),
            "key_exit":   ("esc", self._on_exit),
            "key_copy":   ("ctrl+c", self._on_copy),
            "key_first":  ("home", self._on_first),
            "key_last":   ("end", self._on_last),
            "key_skip_next": ("right", lambda: self._on_skip(5)),
            "key_skip_prev": ("left", lambda: self._on_skip(-5)),
            "key_repeat": ("space", self._on_repeat)
        }

        for cid, (default, func) in actions.items():
            target_vk, target_mask = string_to_hotkey(self.config.get(cid, ""), default)
            if vk == target_vk and current_mask == target_mask:
                return func()
            
        return False

    def _on_next(self): self.index = (self.index+1)%len(self.elements); self._announce(); return True
    def _on_prev(self): self.index = (self.index-1)%len(self.elements); self._announce(); return True
    def _on_first(self): self.index = 0; self._announce(); return True
    def _on_last(self): self.index = len(self.elements) - 1; self._announce(); return True
    
    def _on_repeat(self):
        current_time = time.time()
        if hasattr(self, '_last_repeat_time') and (current_time - self._last_repeat_time) < 0.5:
            self._spell_current()
            self._last_repeat_time = 0
        else:
            self._last_repeat_time = current_time
            self._announce()
        return True

    def _spell_current(self):
        if hasattr(self, '_last_announced_text'):
            text = self._last_announced_text
            spelled = "; ".join([c if not c.isspace() else "espacio" for c in text])
            self.tts.speak(spelled, interrupt=True)

    def _on_skip(self, amount):
        if not self.elements: return
        self.index = (self.index + amount) % len(self.elements)
        self._announce(); return True
    def _on_left(self): self._click("left"); return True
    def _on_double(self): self._click("double"); return True
    def _on_right(self): self._click("right"); return True
    def _on_exit(self): self.tts.speak("Cerrado."); self._stop(); return True
    
    def _on_copy(self):
        if hasattr(self, '_last_announced_text'):
            import wx
            text = self._last_announced_text
            def do_copy():
                if wx.TheClipboard.Open():
                    wx.TheClipboard.SetData(wx.TextDataObject(text))
                    wx.TheClipboard.Close()
            wx.CallAfter(do_copy)
            self.tts.speak("Copiado.", interrupt=True)

    def _announce(self):
        if 0 <= self.index < len(self.elements):
            el = self.elements[self.index]
            text = el.text
            if self.config.get("translate_enabled"):
                from translator import translator_instance
                from_code = self.config.get("translate_from", "en")
                to_code = self.config.get("translate_to", "es")
                text = translator_instance.translate(text, from_code, to_code)
            
            self._last_announced_text = text
            self.tts.speak(f"{text} {self.index+1} de {len(self.elements)}", interrupt=True)

    def _click(self, mode):
        if 0 <= self.index < len(self.elements):
            el = self.elements[self.index]
            win32api.SetCursorPos((int(self.offset_x + el.center_x), int(self.offset_y + el.center_y)))
            time.sleep(0.05); m_text = "izquierdo"
            if mode == "left":
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0); win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
            elif mode == "double":
                m_text = "doble"; win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0); win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
                time.sleep(0.05); win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0); win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
            elif mode == "right":
                m_text = "derecho"; win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0); win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0)
            self.tts.speak(f"Click {m_text}"); self._stop()
