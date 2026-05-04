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

DEFAULT_CONFIG = {
    "ocr_language": "latin",
    "min_confidence": 0.3,
    "use_gpu": True,
    "image_scale": 0.5,
    "hotkey_screen": "ctrl+alt+s",
    "hotkey_window": "ctrl+alt+w",
    "hotkey_config": "ctrl+shift+c",
    "hotkey_quit": "ctrl+alt+q",
    "row_tolerance": 20,
    "dynamic_interval": 1.0,
    "hotkey_dynamic": "ctrl+alt+d",
    "dynamic_target": "screen",
    "crop_top": 0,
    "crop_bottom": 0,
    "crop_left": 0,
    "crop_right": 0,
    "dynamic_sensitivity": 50
}

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            return {**DEFAULT_CONFIG, **user_config}
        except (json.JSONDecodeError, IOError):
            pass
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)

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
