import json
import os
import sys
import wx

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # Si estamos en src/, subimos un nivel para la raíz
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILE = os.path.join(get_base_path(), "config.json")
VERSION = "1.4"

DEFAULT_CONFIG = {
    "global": {
        "ocr_language": "latin",
        "min_confidence": 0.3,
        "openvino_device": "AUTO",
        "image_scale": 0.5,
        "auto_check_updates": True,
        "hotkey_screen": "ctrl+alt+s",
        "hotkey_window": "ctrl+alt+w",
        "hotkey_config": "ctrl+alt+c",
        "hotkey_quit": "ctrl+alt+q",
        "row_tolerance": 20,
        "dynamic_interval": 1.0,
        "hotkey_dynamic": "ctrl+alt+d",
        "dynamic_target": "screen",
        "crop_top": 0,
        "crop_bottom": 0,
        "crop_left": 0,
        "crop_right": 0,
        "dynamic_sensitivity": 50,
        "dynamic_diff_mode": False,
        "key_next": "down",
        "key_prev": "up",
        "key_click": "enter",
        "key_double": "shift+enter",
        "key_right": "apps",
        "key_exit": "esc",
        "translate_enabled": False,
        "translate_to": "es",
        "translate_from": "auto",
        "hotkey_shadow_learn": "ctrl+alt+l",
        "hotkey_shadow_clear": "ctrl+alt+r",
        "hotkey_shadow_toggle": "ctrl+alt+u",
        "shadow_burst_count": 4,
        "key_copy": "ctrl+c",
        "key_first": "home",
        "key_last": "end",
        "key_skip_next": "right",
        "key_skip_prev": "left",
        "key_repeat": "space",
        "hotkey_manual": "ctrl+alt+f1",
        "auto_rescan_after_click": False,
        "auto_rescan_delay": 5,
        "hotkey_toggle_auto_rescan": "ctrl+alt+a"
    },
    "profiles": {},
    "shadow_profiles": {} # Mantenemos esto por compatibilidad o lo migramos luego
}

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            
            # Si el archivo es viejo (no tiene "global"), migramos los datos a "global"
            if "global" not in user_config:
                new_config = {"global": {}, "profiles": user_config.get("profiles", {}), "shadow_profiles": user_config.get("shadow_profiles", {})}
                for k, v in user_config.items():
                    if k not in ["profiles", "shadow_profiles"]:
                        new_config["global"][k] = v
                user_config = new_config

            # Mezclar con defaults para asegurar que no falten llaves
            final_config = DEFAULT_CONFIG.copy()
            final_config["global"].update(user_config.get("global", {}))
            final_config["profiles"].update(user_config.get("profiles", {}))
            final_config["shadow_profiles"].update(user_config.get("shadow_profiles", {}))
            return final_config
            
        except (json.JSONDecodeError, IOError):
            pass
    
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)

def get_effective_config(full_config: dict, app_name: str = None) -> dict:
    """Devuelve los ajustes resultantes para una app específica (Global + Overrides)."""
    base = full_config.get("global", {}).copy()
    if app_name and app_name in full_config.get("profiles", {}):
        base.update(full_config["profiles"][app_name])
    return base

def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def run_gui_setup(current_config=None):
    from gui_config import show_config_window
    return show_config_window(current_config)

def run_setup():
    """Por retrocompatibilidad con --setup en consola, lanza la GUI"""
    run_gui_setup()

if __name__ == "__main__":
    run_setup()
