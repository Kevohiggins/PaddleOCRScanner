import wx
import os
from config import save_config, load_config


class NativeConfigDialog(wx.Dialog):
    """Diálogo nativo de configuración, 100% compatible con lectores de pantalla."""

    def __init__(self, parent, title, config):
        super().__init__(parent, title=title, size=(550, 800),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.config = dict(config)
        self.result_config = None

        main_container = wx.BoxSizer(wx.VERTICAL)

        # ScrolledWindow para que funcione en cualquier resolución
        scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        scroll.SetScrollRate(0, 20)
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Cabecera ---
        header = wx.Panel(scroll)
        header.SetBackgroundColour(wx.Colour(0, 120, 215))
        h_sizer = wx.BoxSizer(wx.VERTICAL)

        t = wx.StaticText(header, label="Configuración de PaddleOCR Scanner")
        t.SetForegroundColour(wx.WHITE)
        f = t.GetFont()
        f.SetPointSize(16)
        f.SetWeight(wx.FONTWEIGHT_BOLD)
        t.SetFont(f)

        sub = wx.StaticText(header, label="Personalizá atajos, precisión y rendimiento")
        sub.SetForegroundColour(wx.WHITE)

        h_sizer.Add(t, 0, wx.ALL, 10)
        h_sizer.Add(sub, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        header.SetSizer(h_sizer)
        scroll_sizer.Add(header, 0, wx.EXPAND)

        content = wx.BoxSizer(wx.VERTICAL)

        # =====================================================================
        # Helpers
        # =====================================================================
        def section(label):
            box = wx.StaticBox(scroll, label=label)
            fnt = box.GetFont()
            fnt.SetWeight(wx.FONTWEIGHT_BOLD)
            box.SetFont(fnt)
            return wx.StaticBoxSizer(box, wx.VERTICAL)

        def add_text_field(parent, grid, label_text, value, tooltip):
            """Agrega un campo de texto con su etiqueta accesible."""
            lbl = wx.StaticText(parent, label=label_text)
            ctrl = wx.TextCtrl(parent, value=str(value), name=label_text)
            ctrl.SetName(label_text)
            ctrl.SetToolTip(tooltip)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        def add_spin_double(parent, grid, label_text, value, lo, hi, inc, digits, tooltip):
            """Agrega un SpinCtrlDouble con su etiqueta accesible."""
            lbl = wx.StaticText(parent, label=label_text)
            ctrl = wx.SpinCtrlDouble(parent, min=lo, max=hi, initial=float(value), inc=inc, name=label_text)
            ctrl.SetDigits(digits)
            ctrl.SetName(label_text)
            ctrl.SetToolTip(tooltip)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        def add_spin_int(parent, grid, label_text, value, lo, hi, tooltip):
            """Agrega un SpinCtrl entero con su etiqueta accesible."""
            lbl = wx.StaticText(parent, label=label_text)
            ctrl = wx.SpinCtrl(parent, value=str(value), min=lo, max=hi, name=label_text)
            ctrl.SetName(label_text)
            ctrl.SetToolTip(tooltip)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        def add_choice(parent, grid, label_text, choices, selection, tooltip):
            """Agrega un Choice (desplegable) con su etiqueta accesible."""
            lbl = wx.StaticText(parent, label=label_text)
            ctrl = wx.Choice(parent, choices=choices, name=label_text)
            ctrl.SetSelection(selection)
            ctrl.SetName(label_text)
            ctrl.SetToolTip(tooltip)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        # =====================================================================
        # 1. ATAJOS DE TECLADO
        # =====================================================================
        s1 = section("Atajos de Teclado")
        g1 = wx.FlexGridSizer(cols=2, vgap=15, hgap=10)
        g1.AddGrowableCol(1)

        self.hk_screen = add_text_field(scroll, g1,
            "Escanear Pantalla Completa",
            self.config.get("hotkey_screen", "ctrl+alt+s"),
            "Combinación de teclas para escanear toda la pantalla. Ejemplo: ctrl+alt+s")

        self.hk_window = add_text_field(scroll, g1,
            "Escanear Ventana Activa",
            self.config.get("hotkey_window", "ctrl+alt+w"),
            "Combinación de teclas para escanear solo la ventana activa. Ejemplo: ctrl+alt+w")

        self.hk_config = add_text_field(scroll, g1,
            "Abrir este Menú",
            self.config.get("hotkey_config", "ctrl+shift+c"),
            "Combinación de teclas para abrir esta ventana de configuración. Ejemplo: ctrl+shift+c")

        self.hk_quit = add_text_field(scroll, g1,
            "Cerrar Aplicación",
            self.config.get("hotkey_quit", "ctrl+alt+q"),
            "Combinación de teclas para cerrar el programa. Ejemplo: ctrl+alt+q")

        s1.Add(g1, 1, wx.EXPAND | wx.ALL, 10)
        content.Add(s1, 0, wx.EXPAND | wx.TOP, 15)

        # =====================================================================
        # 2. MOTOR DE RECONOCIMIENTO
        # =====================================================================
        s2 = section("Motor de Reconocimiento")
        g2 = wx.FlexGridSizer(cols=2, vgap=15, hgap=10)
        g2.AddGrowableCol(1)

        self.min_conf = add_spin_double(scroll, g2,
            "Confianza Mínima",
            self.config.get("min_confidence", 0.5),
            0.1, 1.0, 0.1, 1,
            "Valores altos ignoran texto dudoso. 0.5 es el balance ideal.")

        self.row_tol = add_spin_int(scroll, g2,
            "Tolerancia de Filas (píxeles)",
            self.config.get("row_tolerance", 20),
            1, 100,
            "Margen vertical para agrupar palabras en la misma línea.")

        scale_choices = [
            "Nativa (100% - Preciso)",
            "Alta (75%)",
            "Media (50%)",
            "Baja (35% - Rápido)",
        ]
        scale_val = str(self.config.get("image_scale", 1.0))
        scale_idx = {"1.0": 0, "0.75": 1, "0.5": 2, "0.35": 3}.get(scale_val, 0)

        self.scale = add_choice(scroll, g2,
            "Resolución de Análisis",
            scale_choices, scale_idx,
            "Reducir la resolución acelera el proceso pero puede perder letras muy chicas.")

        lang_choices = [
            "Latino (Español, Inglés, etc.)",
            "Japonés / Chino",
            "Coreano",
            "Cirílico (Ruso, Ucraniano, etc.)",
            "Tailandés",
            "Árabe (Árabe, Urdu, Persa)",
            "Hindi (Hindi, Marathi, Nepalí)"
        ]
        lang_val = self.config.get("ocr_language", "latin")
        lang_map = {
            "latin": 0, "japanese": 1, "chinese": 1, "korean": 2, 
            "cyrillic": 3, "thai": 4, "arabic": 5, "hindi": 6
        }
        lang_idx = lang_map.get(lang_val, 0)
        
        self.lang_choice = add_choice(scroll, g2,
            "Idioma del OCR",
            lang_choices, lang_idx,
            "Seleccioná el modelo optimizado para el idioma que quieras leer.")

        s2.Add(g2, 1, wx.EXPAND | wx.ALL, 10)
        content.Add(s2, 0, wx.EXPAND | wx.TOP, 15)

        # =====================================================================
        # 3. ESCANEO DINÁMICO
        # =====================================================================
        s3 = section("Escaneo Dinámico (Lectura Continua)")
        g3 = wx.FlexGridSizer(cols=2, vgap=12, hgap=10)
        g3.AddGrowableCol(1)

        self.hk_dynamic = add_text_field(scroll, g3,
            "Atajo de Activación",
            self.config.get("hotkey_dynamic", "ctrl+alt+d"),
            "Combinación de teclas para activar o desactivar la lectura en tiempo real.")

        self.dyn_interval = add_spin_double(scroll, g3,
            "Intervalo de Escaneo (segundos)",
            self.config.get("dynamic_interval", 1.0),
            0.2, 10.0, 0.2, 1,
            "Cada cuánto tiempo se escanea la pantalla en segundo plano.")

        # --- Sensibilidad (justo después del intervalo) ---
        sens_lbl = wx.StaticText(scroll, label="Sensibilidad al Cambio")
        g3.Add(sens_lbl, 0, wx.ALIGN_CENTER_VERTICAL)

        sens_row = wx.BoxSizer(wx.HORIZONTAL)
        self.sensitivity = wx.Slider(
            scroll,
            value=int(self.config.get("dynamic_sensitivity", 50)),
            minValue=0, maxValue=100,
            style=wx.SL_HORIZONTAL,
            name="Sensibilidad al Cambio"
        )
        self.sensitivity.SetName("Sensibilidad al Cambio")
        self.sensitivity.SetToolTip("0: No verbaliza cambios automáticamente. 100: Verbaliza ante cualquier cambio mínimo.")

        self.sens_val = wx.StaticText(scroll, label=str(self.sensitivity.GetValue()) + "%")
        self.sensitivity.Bind(wx.EVT_SLIDER,
            lambda e: self.sens_val.SetLabel(str(self.sensitivity.GetValue()) + "%"))

        sens_row.Add(self.sensitivity, 1, wx.EXPAND)
        sens_row.Add(self.sens_val, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 8)
        g3.Add(sens_row, 1, wx.EXPAND)

        target_idx = 0 if self.config.get("dynamic_target") == "screen" else 1
        self.dyn_target = add_choice(scroll, g3,
            "Área de Lectura",
            ["Toda la Pantalla", "Solo Ventana Activa"],
            target_idx,
            "Elegí si querés escanear toda la pantalla o solo la ventana activa.")

        self.crop_t = add_spin_int(scroll, g3,
            "Recorte Superior (%)",
            self.config.get("crop_top", 0), 0, 100,
            "Porcentaje de la pantalla a descartar desde arriba.")

        self.crop_b = add_spin_int(scroll, g3,
            "Recorte Inferior (%)",
            self.config.get("crop_bottom", 0), 0, 100,
            "Porcentaje de la pantalla a descartar desde abajo.")

        self.crop_l = add_spin_int(scroll, g3,
            "Recorte Izquierdo (%)",
            self.config.get("crop_left", 0), 0, 100,
            "Porcentaje de la pantalla a descartar desde la izquierda.")

        self.crop_r = add_spin_int(scroll, g3,
            "Recorte Derecho (%)",
            self.config.get("crop_right", 0), 0, 100,
            "Porcentaje de la pantalla a descartar desde la derecha.")

        s3.Add(g3, 1, wx.EXPAND | wx.ALL, 10)
        content.Add(s3, 0, wx.EXPAND | wx.TOP, 15)

        # =====================================================================
        # Ensamblar
        # =====================================================================
        scroll_sizer.Add(content, 1, wx.EXPAND | wx.ALL, 15)
        scroll.SetSizer(scroll_sizer)
        main_container.Add(scroll, 1, wx.EXPAND)

        # --- Botones ---
        main_container.Add(wx.StaticLine(self), 0, wx.EXPAND)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        save_btn = wx.Button(self, label="Guardar Configuración", size=(180, 40))
        save_btn.SetDefault()
        save_btn.SetBackgroundColour(wx.Colour(0, 120, 215))
        save_btn.SetForegroundColour(wx.WHITE)
        save_btn.Bind(wx.EVT_BUTTON, self.on_save)

        cancel_btn = wx.Button(self, label="Cancelar", size=(100, 40))
        cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)

        btn_sizer.Add(save_btn, 0, wx.RIGHT, 10)
        btn_sizer.Add(cancel_btn, 0)

        main_container.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 20)

        self.SetSizer(main_container)
        self.Center()

    # -----------------------------------------------------------------
    # Eventos
    # -----------------------------------------------------------------
    def on_save(self, event):
        scale_map = {0: "1.0", 1: "0.75", 2: "0.5", 3: "0.35"}

        self.config["hotkey_screen"] = self.hk_screen.GetValue()
        self.config["hotkey_window"] = self.hk_window.GetValue()
        self.config["hotkey_config"] = self.hk_config.GetValue()
        self.config["hotkey_quit"] = self.hk_quit.GetValue()
        self.config["min_confidence"] = self.min_conf.GetValue()
        self.config["row_tolerance"] = self.row_tol.GetValue()
        self.config["image_scale"] = float(scale_map[self.scale.GetSelection()])
        
        lang_map_inv = {0: "latin", 1: "japanese", 2: "korean", 3: "cyrillic", 4: "thai", 5: "arabic", 6: "hindi"}
        self.config["ocr_language"] = lang_map_inv[self.lang_choice.GetSelection()]

        self.config["hotkey_dynamic"] = self.hk_dynamic.GetValue()
        self.config["dynamic_interval"] = self.dyn_interval.GetValue()
        self.config["dynamic_target"] = "screen" if self.dyn_target.GetSelection() == 0 else "window"
        self.config["crop_top"] = self.crop_t.GetValue()
        self.config["crop_bottom"] = self.crop_b.GetValue()
        self.config["crop_left"] = self.crop_l.GetValue()
        self.config["crop_right"] = self.crop_r.GetValue()
        self.config["dynamic_sensitivity"] = self.sensitivity.GetValue()

        save_config(self.config)
        self.result_config = self.config
        self.EndModal(wx.ID_OK)

    def on_cancel(self, event):
        self.EndModal(wx.ID_CANCEL)


def show_config_window(current_config=None):
    """Abre el diálogo de configuración y devuelve la config resultante o None."""
    app = wx.App.Get()
    if not app:
        app = wx.App(False)

    config_to_edit = current_config if current_config else load_config()
    dlg = NativeConfigDialog(None, "Configuración PaddleOCR Scanner", config_to_edit)

    result = None
    if dlg.ShowModal() == wx.ID_OK:
        result = dlg.result_config

    dlg.Destroy()
    return result


if __name__ == "__main__":
    show_config_window()
