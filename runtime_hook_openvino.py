"""
Runtime hook para OpenVINO y CTranslate2 en PyInstaller.

PROBLEMA RAÍZ:
- OpenVINO usa os.path.dirname(__file__) para buscar libs/ → no siempre funciona en EXE
- Si falla, OpenVINO llama sys.exit() → mata el proceso
- CTranslate2 usa importlib.resources.files() → no funciona en EXE

SOLUCIÓN:
1. Setear OPENVINO_LIB_PATHS para que OpenVINO nunca llegue a sys.exit()
2. Forzar os.add_dll_directory() para ambas librerías
3. Pre-cargar DLLs de CTranslate2 con ctypes.CDLL()
"""
import os
import sys
import ctypes
import glob

if sys.platform == "win32":
    # Evitar el conflicto fatal de OpenMP al cargar múltiples copias de libiomp5md.dll (Torch y CTranslate2)
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["OMP_NUM_THREADS"] = "1" # Opcional: reducir la cantidad de hilos que CTranslate2 o Torch intentan acaparar para evitar quemar la CPU
    
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    
    # =====================================================================
    # 1. OpenVINO: la solución nuclear
    # =====================================================================
    ov_libs = os.path.join(base, "openvino", "libs")
    if os.path.isdir(ov_libs):
        # A) Registrar en el buscador de DLLs de Python 3.8+
        os.add_dll_directory(ov_libs)
        
        # B) Agregar al PATH clásico
        os.environ["PATH"] = ov_libs + os.pathsep + os.environ.get("PATH", "")
        
        # C) Setear OPENVINO_LIB_PATHS para que openvino/utils.py NO llame sys.exit()
        #    Esta variable de entorno es la última opción que OpenVINO revisa.
        #    Si está seteada, la usa directamente sin buscar en __file__.
        os.environ["OPENVINO_LIB_PATHS"] = ov_libs
    
    # =====================================================================
    # 2. CTranslate2: pre-cargar DLLs antes de que __init__.py falle
    # =====================================================================
    ct2_dir = os.path.join(base, "ctranslate2")
    if os.path.isdir(ct2_dir):
        os.add_dll_directory(ct2_dir)
        os.environ["PATH"] = ct2_dir + os.pathsep + os.environ.get("PATH", "")
        for dll_path in glob.glob(os.path.join(ct2_dir, "*.dll")):
            try:
                ctypes.CDLL(dll_path)
            except OSError:
                pass
    
    # =====================================================================
    # 3. Torch: registrar su carpeta de DLLs
    # =====================================================================
    torch_lib = os.path.join(base, "torch", "lib")
    if os.path.isdir(torch_lib):
        os.add_dll_directory(torch_lib)
        os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")
