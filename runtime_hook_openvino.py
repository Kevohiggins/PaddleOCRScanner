"""
Runtime hook para OpenVINO y CTranslate2 en PyInstaller.

Optimizado para la versión 1.5 Lite (sin Torch/Stanza).
"""
import os
import sys
import ctypes
import glob

if sys.platform == "win32":
    # Evitar conflictos de librerías de hilos (OpenMP)
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["OMP_NUM_THREADS"] = "1"
    
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    
    # 1. OpenVINO: Asegurar que encuentre sus librerías dinámicas
    ov_libs = os.path.join(base, "openvino", "libs")
    if os.path.isdir(ov_libs):
        os.add_dll_directory(ov_libs)
        os.environ["PATH"] = ov_libs + os.pathsep + os.environ.get("PATH", "")
        os.environ["OPENVINO_LIB_PATHS"] = ov_libs
    
    # 2. CTranslate2: Pre-cargar DLLs para evitar errores de importación
    ct2_dir = os.path.join(base, "ctranslate2")
    if os.path.isdir(ct2_dir):
        os.add_dll_directory(ct2_dir)
        os.environ["PATH"] = ct2_dir + os.pathsep + os.environ.get("PATH", "")
        # Forzar la carga de DLLs para que Python las reconozca antes del import
        for dll_path in glob.glob(os.path.join(ct2_dir, "*.dll")):
            try:
                ctypes.CDLL(dll_path)
            except OSError:
                pass
