import logging
import threading
import os
import urllib.request
import tempfile
import json
import sys
import traceback

# Logger estándar
logger = logging.getLogger("TranslatorDebug")
logger.setLevel(logging.INFO)
# Ya no creamos translation_debug.log

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        # Aseguramos _MEIPASS en mayúsculas
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative_path)

argos_dir = get_resource_path(os.path.join("models", "argos"))
os.makedirs(argos_dir, exist_ok=True)
os.environ["ARGOS_PACKAGES_DIR"] = argos_dir

if getattr(sys, 'frozen', False):
    try:
        import certifi
        os.environ['SSL_CERT_FILE'] = certifi.where()
    except: pass

    # =========================================================================
    # PRE-CARGA DE DLLs DE CTRANSLATE2 PARA PYINSTALLER
    # ctranslate2/__init__.py usa importlib.resources.files() para encontrar
    # su carpeta y cargar DLLs. En PyInstaller esto falla silenciosamente.
    # La solución: cargar las DLLs manualmente ANTES de importar argostranslate.
    # =========================================================================
    import ctypes
    import glob
    _base = sys._MEIPASS
    _ct2_dir = os.path.join(_base, "ctranslate2")
    if os.path.isdir(_ct2_dir):
        try:
            os.add_dll_directory(_ct2_dir)
        except OSError:
            pass
        os.environ["PATH"] = _ct2_dir + os.pathsep + os.environ.get("PATH", "")
        for _dll in glob.glob(os.path.join(_ct2_dir, "*.dll")):
            try:
                ctypes.CDLL(_dll)
                logger.info(f"Pre-cargada DLL: {os.path.basename(_dll)}")
            except OSError as _e:
                logger.warning(f"No se pudo pre-cargar {_dll}: {_e}")

class Translator:
    def __init__(self):
        self._initialized = False
        self._initializing = False
        self._argos_installed = False
        self._installed_languages = []
        self._available_languages = {}
        self._on_ready_callback = None
        self._lock = threading.Lock()
        self._master_catalog_path = get_resource_path(os.path.join("src", "assets", "languages_catalog.json"))
        self._load_catalogs()

    def _load_catalogs(self):
        if os.path.exists(self._master_catalog_path):
            try:
                with open(self._master_catalog_path, "r", encoding="utf-8") as f:
                    self._available_languages.update(json.load(f))
            except: pass

    def ensure_initialized(self):
        if self._initialized or self._initializing: return
        self._initializing = True
        threading.Thread(target=self._initialize, daemon=True).start()

    def _initialize(self):
        try:
            logger.info("--- INICIANDO MOTOR DE TRADUCCIÓN ARGOS ---")
            import argostranslate.translate
            import argostranslate.package
            self._argos_installed = True
            self.refresh_languages()
            self._initialized = True
            self._initializing = False
            logger.info(f"Motor Argos listo. Modelos instalados: {len(self._installed_languages)}")
            if self._on_ready_callback: self._on_ready_callback()
            threading.Thread(target=self._load_catalog_online, daemon=True).start()
        except Exception as e:
            self._initializing = False
            logger.error(f"Error init: {traceback.format_exc()}")

    def _load_catalog_online(self):
        try:
            import argostranslate.package
            argostranslate.package.update_package_index()
            pkgs = argostranslate.package.get_available_packages()
            cat = {p.from_code: p.from_name for p in pkgs}
            for p in pkgs: cat[p.to_code] = p.to_name
            if cat:
                self._available_languages.update(cat)
        except: pass

    def get_available_languages_dict(self):
        return self._available_languages if self._available_languages else {"en": "English", "es": "Spanish", "ja": "Japanese"}

    def refresh_languages(self):
        if not self._argos_installed: return
        try:
            import argostranslate.translate
            if hasattr(argostranslate.translate, 'installed_languages'):
                argostranslate.translate.installed_languages = None
            argostranslate.translate.load_installed_languages()
            self._installed_languages = argostranslate.translate.get_installed_languages()
        except: pass

    def is_model_installed(self, from_code, to_code):
        if not self._argos_installed or not self._initialized: return False
        try:
            lang_from = next((l for l in self._installed_languages if l.code == from_code), None)
            lang_to = next((l for l in self._installed_languages if l.code == to_code), None)
            if not lang_from or not lang_to: return False
            return lang_from.get_translation(lang_to) is not None
        except: return False

    def translate(self, text, from_code, to_code, translate_type="local", service="google", swap=False):
        if not text: return text
        
        if translate_type == "online":
            try:
                import translators as ts
                print(f"DEBUG: Enviando a {service} [{from_code}->{to_code}]: {text}")
                
                if swap:
                    # Intercambio Inteligente: probamos traducir al destino
                    result = ts.translate_text(text, translator=service, from_language='auto', to_language=to_code)
                    if result.strip().lower() == text.strip().lower():
                        # Si devuelve lo mismo, asumimos que ya estaba en el idioma destino!
                        # Traducimos al origen!
                        print(f"DEBUG: Texto ya estaba en destino. Invirtiendo traducción a {from_code}...")
                        result = ts.translate_text(text, translator=service, from_language='auto', to_language=from_code)
                else:
                    result = ts.translate_text(text, translator=service, from_language='auto', to_language=to_code)
                    
                print(f"DEBUG: Resultado {service}: {result}")
                return result
            except Exception as e:
                print(f"Error en traducción Online ({service}): {e}")
                return text
                
        # Modo Local (Argos)
        if not self._argos_installed or not self._initialized: return text
        with self._lock:
            try:
                import argostranslate.translate
                logger.info(f"Traduciendo Local [{from_code}->{to_code}]: {text[:50]}...")
                result = argostranslate.translate.translate(text, from_code, to_code)
                logger.info(f"Resultado Local: {result[:50]}...")
                return result
            except Exception as e:
                logger.error(f"Error en traducción Local:\n{traceback.format_exc()}")
                return text

    def download_model(self, from_code, to_code, progress_callback=None):
        if not self._argos_installed: return False
        try:
            import argostranslate.package
            logger.info(f"Iniciando descarga: {from_code} -> {to_code}")
            if progress_callback: progress_callback("Conectando...", 5)
            
            argostranslate.package.update_package_index()
            available = argostranslate.package.get_available_packages()
            
            needed = []
            direct = next((p for p in available if p.from_code == from_code and p.to_code == to_code), None)
            if direct:
                needed = [direct]
            else:
                p1 = next((p for p in available if p.from_code == from_code and p.to_code == "en"), None)
                p2 = next((p for p in available if p.from_code == "en" and p.to_code == to_code), None)
                if p1 and p2: needed = [p1, p2]
            
            if not needed:
                logger.error(f"No se encontró ruta de paquetes para {from_code} -> {to_code}")
                return False

            for i, pkg in enumerate(needed):
                def reporthook(b, bs, ts):
                    if ts > 0 and progress_callback:
                        p = (b * bs / ts); overall = int(((i + p) / len(needed)) * 100)
                        progress_callback(f"Bajando {i+1}/{len(needed)}...", min(99, overall))
                
                url = pkg.links[0] if hasattr(pkg, 'links') and pkg.links else pkg.download_url
                logger.info(f"Descargando parte {i+1}/{len(needed)} desde: {url}")
                
                temp_path = os.path.join(tempfile.gettempdir(), f"pkg_{from_code}_{to_code}_{i}.argosmodel")
                
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')]
                urllib.request.install_opener(opener)
                
                try:
                    urllib.request.urlretrieve(url, temp_path, reporthook)
                    logger.info(f"Parte {i+1} descargada en temporal: {temp_path}")
                except Exception as e_dl:
                    logger.error(f"Error en la descarga física del archivo: {e_dl}")
                    raise e_dl
                
                logger.info(f"Instalando paquete desde {temp_path}...")
                argostranslate.package.install_from_path(temp_path)
                logger.info(f"Paquete {i+1} instalado correctamente.")
                
                if os.path.exists(temp_path): os.remove(temp_path)

            self.refresh_languages()
            if progress_callback: progress_callback("¡Hecho!", 100)
            return True
        except Exception as e:
            logger.error(f"Fallo crítico en download_model: {traceback.format_exc()}")
            if progress_callback: progress_callback("Error de red o archivo", 0)
            return False

    def delete_model(self, from_code, to_code):
        try:
            import argostranslate.package
            for p in argostranslate.package.get_installed_packages():
                if p.from_code == from_code and p.to_code == to_code:
                    argostranslate.package.uninstall(p)
            self.refresh_languages()
            return True
        except: return False

    def set_on_ready_callback(self, cb):
        self._on_ready_callback = cb
        if self._initialized: cb()

translator_instance = Translator()
