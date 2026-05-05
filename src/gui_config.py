import wx
import os
import json
import logging
from config import CONFIG_FILE, DEFAULT_CONFIG, save_config

logger = logging.getLogger(__name__)

class HotkeyCaptureDialog(wx.Dialog):
    def __init__(self, parent, config, key_id):
        super().__init__(parent, title="Capturar Atajo", size=(300, 150))
        self.config = config; self.key_id = key_id; self.final_hotkey = ""
        panel = wx.Panel(self); sizer = wx.BoxSizer(wx.VERTICAL)
        self.label = wx.StaticText(panel, label="Presione la combinación de teclas...", style=wx.ALIGN_CENTER)
        sizer.Add(self.label, 1, wx.EXPAND | wx.ALL, 20)
        panel.SetSizer(sizer)
        self.Bind(wx.EVT_KEY_DOWN, self.on_key_down)

    def on_key_down(self, event):
        vk = event.GetKeyCode(); mods = []
        if event.ControlDown(): mods.append("ctrl")
        if event.AltDown(): mods.append("alt")
        if event.ShiftDown(): mods.append("shift")
        
        key = ""
        if 32 <= vk <= 126: key = chr(vk).lower()
        elif vk == wx.WXK_UP: key = "up"
        elif vk == wx.WXK_DOWN: key = "down"
        elif vk == wx.WXK_LEFT: key = "left"
        elif vk == wx.WXK_RIGHT: key = "right"
        elif vk == wx.WXK_RETURN: key = "enter"
        elif vk == wx.WXK_ESCAPE: key = "esc"
        elif vk == wx.WXK_SPACE: key = "space"
        elif vk == wx.WXK_TAB: key = "tab"
        elif vk == wx.WXK_BACK: key = "backspace"
        elif wx.WXK_F1 <= vk <= wx.WXK_F12: key = f"f{vk - wx.WXK_F1 + 1}"
        elif vk == wx.WXK_WINDOWS_MENU: key = "apps"

        if key:
            self.final_hotkey = "+".join(mods + [key]) if mods else key
            self.EndModal(wx.ID_OK)
        elif not mods: event.Skip()

class ConfigWindow(wx.Dialog):
    PRO_NAMES = {
        "hotkey_screen": "Escanear Pantalla", "hotkey_window": "Escanear Ventana", 
        "hotkey_config": "Abrir Configuración", "hotkey_quit": "Salir del Programa",
        "hotkey_dynamic": "Alternar Escaneo Dinámico", "hotkey_shadow_learn": "Modo Sombra: Aprender",
        "hotkey_shadow_clear": "Modo Sombra: Limpiar", "hotkey_shadow_toggle": "Modo Sombra: Alternar",
        "key_next": "Navegación: Siguiente", "key_prev": "Navegación: Anterior",
        "key_click": "Navegación: Click Izquierdo", "key_double": "Navegación: Doble Click",
        "key_right": "Navegación: Click Derecho", "key_exit": "Navegación: Salir"
    }

    def __init__(self, full_config):
        super().__init__(None, title="Configuración de PaddleOCR Scanner", size=(650, 600))
        self.full_config = full_config; self.current_profile = "Global"
        self.temp_config = full_config["global"].copy()
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Selector de Perfil
        p_sizer = wx.BoxSizer(wx.HORIZONTAL)
        p_sizer.Add(wx.StaticText(self, label="Perfil Activo:"), 0, wx.CENTER | wx.ALL, 5)
        profiles = ["Global"] + list(full_config.get("profiles", {}).keys())
        self.profile_choice = wx.Choice(self, choices=profiles, name="Perfil Activo")
        self.profile_choice.SetSelection(0)
        self.profile_choice.Bind(wx.EVT_CHOICE, self.on_profile_change)
        p_sizer.Add(self.profile_choice, 1, wx.EXPAND | wx.ALL, 5)
        
        self.btn_add = wx.Button(self, label="Añadir Perfil"); self.btn_add.Bind(wx.EVT_BUTTON, self.on_add_profile)
        self.btn_del = wx.Button(self, label="Eliminar Perfil"); self.btn_del.Bind(wx.EVT_BUTTON, self.on_del_profile)
        p_sizer.Add(self.btn_add, 0, wx.ALL, 5); p_sizer.Add(self.btn_del, 0, wx.ALL, 5)
        main_sizer.Add(p_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Tabs
        self.tabs = wx.Notebook(self)
        self.tab_general = wx.Panel(self.tabs); self.tab_keys = wx.ScrolledWindow(self.tabs, style=wx.VSCROLL)
        self.tab_ocr = wx.ScrolledWindow(self.tabs, style=wx.VSCROLL); self.tab_dynamic = wx.Panel(self.tabs)
        self.tab_keys.SetScrollRate(0, 20); self.tab_ocr.SetScrollRate(0, 20)
        self.tabs.AddPage(self.tab_general, "General"); self.tabs.AddPage(self.tab_keys, "Atajos de Teclado")
        self.tabs.AddPage(self.tab_ocr, "Precisión y Recortes"); self.tabs.AddPage(self.tab_dynamic, "Escaneo Dinámico")
        
        self._setup_general_tab(); self._setup_keys_tab(); self._setup_ocr_tab(); self._setup_dynamic_tab()
        main_sizer.Add(self.tabs, 1, wx.EXPAND | wx.ALL, 10)
        
        # Botones Finales
        btn_sizer = wx.StdDialogButtonSizer()
        save_btn = wx.Button(self, wx.ID_OK, label="Guardar"); save_btn.SetDefault()
        btn_sizer.AddButton(save_btn); btn_sizer.AddButton(wx.Button(self, wx.ID_CANCEL, label="Cancelar"))
        btn_sizer.Realize()
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(main_sizer); self.update_ui_from_config()
        self.Bind(wx.EVT_BUTTON, self.on_save, id=wx.ID_OK)

    def _setup_general_tab(self):
        sizer = wx.BoxSizer(wx.VERTICAL); grid = wx.FlexGridSizer(cols=2, vgap=20, hgap=10); grid.AddGrowableCol(1)
        
        # Estructura idéntica a la de escala que sí funciona
        grid.Add(wx.StaticText(self.tab_general, label="Idioma OCR:"), 0, wx.ALIGN_CENTER_VERTICAL)
        langs = ["Latino", "Chino/Japonés", "Coreano", "Cirílico", "Tailandés", "Árabe", "Hindi"]
        self.lang_choice = wx.Choice(self.tab_general, choices=langs, name="Idioma OCR")
        grid.Add(self.lang_choice, 1, wx.EXPAND)
        
        grid.Add(wx.StaticText(self.tab_general, label="Rendimiento:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.use_gpu = wx.CheckBox(self.tab_general, label="Usar Aceleración GPU (OpenVINO)")
        grid.Add(self.use_gpu, 1, wx.EXPAND)
        
        sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 20); self.tab_general.SetSizer(sizer)

    def _add_spin(self, parent, sizer, label, min_v, max_v, name=""):
        sizer.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
        spin = wx.SpinCtrl(parent, min=min_v, max=max_v, name=name or label)
        sizer.Add(spin, 1, wx.EXPAND); return spin

    def _setup_keys_tab(self):
        self.key_sizer = wx.BoxSizer(wx.VERTICAL)
        ids = ["hotkey_screen", "hotkey_window", "hotkey_config", "hotkey_quit", "hotkey_dynamic", 
               "hotkey_shadow_learn", "hotkey_shadow_clear", "hotkey_shadow_toggle",
               "key_next", "key_prev", "key_click", "key_double", "key_right", "key_exit"]
        for kid in ids:
            btn = wx.Button(self.tab_keys, label=f"{self.PRO_NAMES[kid]}: ...", name=kid)
            btn.Bind(wx.EVT_BUTTON, self.on_capture)
            setattr(self, f"btn_{kid}", btn); self.key_sizer.Add(btn, 0, wx.EXPAND | wx.ALL, 5)
        self.tab_keys.SetSizer(self.key_sizer)

    def _setup_ocr_tab(self):
        sizer = wx.BoxSizer(wx.VERTICAL); grid = wx.FlexGridSizer(cols=2, vgap=15, hgap=10); grid.AddGrowableCol(1)
        self.min_conf = self._add_spin(self.tab_ocr, grid, "Confianza mínima (1-100%):", 1, 100)
        grid.Add(wx.StaticText(self.tab_ocr, label="Escala de imagen:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.scale_choice = wx.Choice(self.tab_ocr, choices=[
            "Baja: La más rápida (35%)",
            "Media: Muy rápida (50%)",
            "Alta: Rápido y preciso (75%)",
            "Nativa: Normal (100%)",
            "Ultra: Recomendada para textos diminutos (200%)"
        ], name="Escala de imagen")
        grid.Add(self.scale_choice, 1, wx.EXPAND)
        self.crop_t = self._add_spin(self.tab_ocr, grid, "Recorte Superior (%):", 0, 100)
        self.crop_b = self._add_spin(self.tab_ocr, grid, "Recorte Inferior (%):", 0, 100)
        self.crop_l = self._add_spin(self.tab_ocr, grid, "Recorte Izquierdo (%):", 0, 100)
        self.crop_r = self._add_spin(self.tab_ocr, grid, "Recorte Derecho (%):", 0, 100)
        sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 20); self.tab_ocr.SetSizer(sizer)

    def _setup_dynamic_tab(self):
        sizer = wx.BoxSizer(wx.VERTICAL); grid = wx.FlexGridSizer(cols=2, vgap=20, hgap=10); grid.AddGrowableCol(1)
        self.dyn_target = wx.RadioBox(self.tab_dynamic, label="Objetivo del escaneo", choices=["Pantalla Completa", "Ventana Activa"], name="Objetivo")
        sizer.Add(self.dyn_target, 0, wx.EXPAND | wx.ALL, 10)
        self.dyn_interval = self._add_spin(self.tab_dynamic, grid, "Intervalo de escaneo (décimas):", 1, 100, name="Intervalo")
        self.dyn_sens = self._add_spin(self.tab_dynamic, grid, "Sensibilidad al cambio (1-100):", 1, 100, name="Sensibilidad")
        sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 20); self.tab_dynamic.SetSizer(sizer)

    def update_ui_from_config(self):
        c = self.temp_config; defs = DEFAULT_CONFIG["global"]
        l_map = {"latin":0, "chinese":1, "japanese":1, "korean":2, "cyrillic":3, "thai":4, "arabic":5, "hindi":6}
        self.lang_choice.SetSelection(l_map.get(c.get("ocr_language", "latin"), 0))
        self.use_gpu.SetValue(c.get("use_gpu", True))
        self.min_conf.SetValue(int(c.get("min_confidence", 0.5) * 100))
        s_map = {"0.35":0, "0.5":1, "0.75":2, "1.0":3, "2.0":4}
        self.scale_choice.SetSelection(s_map.get(str(c.get("image_scale", 1.0)), 3))
        for k, spin in [("crop_top", self.crop_t), ("crop_bottom", self.crop_b), ("crop_left", self.crop_l), ("crop_right", self.crop_r)]:
            spin.SetValue(int(c.get(k, 0)))
        self.dyn_interval.SetValue(int(c.get("dynamic_interval", 1.0) * 10))
        self.dyn_sens.SetValue(int(c.get("dynamic_sensitivity", 50)))
        self.dyn_target.SetSelection(0 if c.get("dynamic_target", "screen") == "screen" else 1)
        is_global = (self.current_profile == "Global")
        self.btn_del.Enable(not is_global)
        ids = ["hotkey_screen", "hotkey_window", "hotkey_config", "hotkey_quit", "hotkey_dynamic", 
               "hotkey_shadow_learn", "hotkey_shadow_clear", "hotkey_shadow_toggle",
               "key_next", "key_prev", "key_click", "key_double", "key_right", "key_exit"]
        for kid in ids:
            if hasattr(self, f"btn_{kid}"):
                val = c.get(kid, defs.get(kid, 'Sin asignar'))
                getattr(self, f"btn_{kid}").SetLabel(f"{self.PRO_NAMES[kid]}: {val}")

    def on_profile_change(self, event):
        new_p = self.profile_choice.GetStringSelection()
        if new_p == "Global": self.temp_config = self.full_config["global"].copy()
        else: self.temp_config = self.full_config["profiles"].get(new_p, self.full_config["global"]).copy()
        self.current_profile = new_p; self.update_ui_from_config()

    def on_add_profile(self, event):
        dlg = wx.TextEntryDialog(self, "Nombre del nuevo perfil (ej: vlc.exe):", "Añadir Perfil")
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetValue().strip()
            if name and name not in self.full_config["profiles"]:
                self.full_config["profiles"][name] = self.full_config["global"].copy()
                self.profile_choice.Append(name); self.profile_choice.SetStringSelection(name)
                self.on_profile_change(None)
        dlg.Destroy()

    def on_del_profile(self, event):
        p = self.profile_choice.GetStringSelection()
        if p != "Global":
            if wx.MessageBox(f"¿Borrar perfil {p}?", "Confirmar", wx.YES_NO) == wx.YES:
                del self.full_config["profiles"][p]; self.profile_choice.Delete(self.profile_choice.GetSelection())
                self.profile_choice.SetSelection(0); self.on_profile_change(None)

    def on_capture(self, event):
        btn = event.GetEventObject(); dlg = HotkeyCaptureDialog(self, self.temp_config, btn.GetName())
        if dlg.ShowModal() == wx.ID_OK: self.temp_config[btn.GetName()] = dlg.final_hotkey; self.update_ui_from_config()
        dlg.Destroy()

    def on_save(self, event):
        l_inv = {0:"latin", 1:"chinese", 2:"korean", 3:"cyrillic", 4:"thai", 5:"arabic", 6:"hindi"}
        self.temp_config["ocr_language"] = l_inv[self.lang_choice.GetSelection()]
        self.temp_config["use_gpu"] = self.use_gpu.GetValue()
        self.temp_config["min_confidence"] = self.min_conf.GetValue() / 100.0
        s_inv = {0:0.35, 1:0.5, 2:0.75, 3:1.0, 4:2.0}
        self.temp_config["image_scale"] = s_inv[self.scale_choice.GetSelection()]
        self.temp_config["dynamic_interval"] = self.dyn_interval.GetValue() / 10.0
        self.temp_config["dynamic_sensitivity"] = self.dyn_sens.GetValue()
        self.temp_config["dynamic_target"] = "screen" if self.dyn_target.GetSelection() == 0 else "window"
        self.temp_config["crop_top"] = self.crop_t.GetValue()
        self.temp_config["crop_bottom"] = self.crop_b.GetValue()
        self.temp_config["crop_left"] = self.crop_l.GetValue()
        self.temp_config["crop_right"] = self.crop_r.GetValue()
        if self.current_profile == "Global": self.full_config["global"].update(self.temp_config)
        else: self.full_config["profiles"][self.current_profile] = self.temp_config.copy()
        save_config(self.full_config); self.EndModal(wx.ID_OK)

def show_config_window(full_config):
    dlg = ConfigWindow(full_config)
    res = dlg.ShowModal()
    if res == wx.ID_OK: return dlg.full_config
    return None
