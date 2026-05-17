import urllib.request
import json
import os
import sys
import threading
import wx
import subprocess
from config import VERSION

REPO = "kevohiggins/PaddleOCRScanner"

def check_updates_async(parent, silent=False):
    def run():
        url = f"https://api.github.com/repos/{REPO}/releases/latest"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'PaddleOCRScanner-Updater'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                # Nos quedamos solo con los números y los puntos, ignorando cualquier letra
                latest_tag = "".join([c for c in data.get("tag_name", "") if c.isdigit() or c == '.'])
                
                def parse_version(v):
                    parts = [int(x) for x in v.split('.') if x.isdigit()]
                    while len(parts) < 3:
                        parts.append(0)
                    return parts
                
                if parse_version(latest_tag) > parse_version(VERSION):
                    wx.CallAfter(show_update_dialog, parent, data)
                elif not silent:
                    wx.CallAfter(wx.MessageBox, f"Estás en la versión más reciente ({VERSION}).", "Actualizador")
        except Exception as e:
            if not silent:
                wx.CallAfter(wx.MessageBox, f"Error al buscar actualizaciones: {e}", "Error")
            
    threading.Thread(target=run, daemon=True).start()

def show_update_dialog(parent, data):
    tag = data.get("tag_name")
    body = data.get("body", "No hay descripción.")
    msg = f"¡Hay una nueva versión disponible: {tag}!\n\nCambios:\n{body}\n\n¿Deseas actualizar ahora?"
    
    if wx.MessageBox(msg, "Actualización Disponible", wx.YES_NO | wx.ICON_QUESTION) == wx.YES:
        download_update(parent, data)

def download_update(parent, data):
    assets = data.get("assets", [])
    url = None
    for asset in assets:
        if asset.get("name", "").endswith("_Update.zip"):
            url = asset.get("browser_download_url")
            break
            
    if not url:
        wx.MessageBox("No se encontró el archivo de actualización (_Update.zip) en el lanzamiento.", "Error")
        return
        
    prog = wx.ProgressDialog("Descargando", "Descargando actualización...", parent=parent, style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE)
    
    def run():
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'PaddleOCRScanner-Updater'})
            with urllib.request.urlopen(req) as response:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 8192
                
                from config import get_base_path
                base_path = get_base_path()
                zip_path = os.path.join(base_path, "update.zip")
                
                with open(zip_path, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int(downloaded * 100 / total_size)
                            wx.CallAfter(prog.Update, percent, f"Descargando: {percent}%")
                            
                wx.CallAfter(prog.Destroy)
                wx.CallAfter(apply_update, base_path, zip_path)
        except Exception as e:
            wx.CallAfter(prog.Destroy)
            wx.CallAfter(wx.MessageBox, f"Error al descargar: {e}", "Error")
            
    threading.Thread(target=run, daemon=True).start()

def apply_update(base_path, zip_path):
    import zipfile
    tmp_dir = os.path.join(base_path, "update_tmp")
    
    try:
        # Extraer en python
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(tmp_dir)
            
        # Detectar si hay una carpeta raíz en el zip
        items = os.listdir(tmp_dir)
        source_dir = tmp_dir
        if len(items) == 1 and os.path.isdir(os.path.join(tmp_dir, items[0])):
            source_dir = os.path.join(tmp_dir, items[0])
            
        bat_path = os.path.join(base_path, "apply_update.bat")
        exe_name = "PaddleOCR Scanner.exe"
        
        # El archivo BAT espera pacientemente a que se cierre el ejecutable y aplica la actualización.
        # Es inteligente: si detecta vestigios de la versión 1.4 (como la carpeta torch), hace limpieza total.
        # Si ya está en la 1.5 Lite, hace una actualización liviana (robocopy directo), permitiendo zips futuros diminutos.
        bat_content = f"""@echo off
set "EXE_NAME={exe_name}"

:: 1. Esperar de forma segura a que el proceso principal se haya cerrado por completo
:wait_loop
tasklist /FI "IMAGENAME eq %EXE_NAME%" 2>NUL | find /I "%EXE_NAME%" >nul
if %errorlevel% equ 0 (
    timeout /t 1 /nobreak > nul
    goto :wait_loop
)
timeout /t 2 /nobreak > nul

:: 2. Detectar si venimos de la v1.4 (si existe la carpeta de torch en _internal)
if exist "{base_path}\_internal\torch" (
    :: --- MODO MIGRACIÓN 1.4 -> 1.5 (Destrucción y limpieza total) ---
    
    :: Crear directorio temporal para el salvavidas
    mkdir "{base_path}\_update_backup" > nul 2>&1
    mkdir "{base_path}\_update_backup\models" > nul 2>&1
    
    :: Mover config.json y modelos de OCR (v5_ov) a la zona segura
    if exist "{base_path}\config.json" move /y "{base_path}\config.json" "{base_path}\_update_backup\" > nul 2>&1
    if exist "{base_path}\_internal\models\v5_ov" move "{base_path}\_internal\models\v5_ov" "{base_path}\_update_backup\models\" > nul 2>&1
    
    :: Volar la carpeta _internal vieja entera con su giga de basura
    rmdir /s /q "{base_path}\_internal" > nul 2>&1
    
    :: Borrar archivos viejos sueltos de la raíz excepto temporales
    for %%i in ("{base_path}\*") do (
        if not "%%~nxi"=="apply_update.bat" if not "%%~nxi"=="update.zip" del /q "%%i" > nul 2>&1
    )
    
    :: Extraer los nuevos archivos de la v1.5 Lite
    robocopy "{source_dir}" "{base_path}" /E /MOVE /IS /IT /R:5 /W:1 > nul
    
    :: Restaurar config.json a la raíz
    if exist "{base_path}\_update_backup\config.json" move /y "{base_path}\_update_backup\config.json" "{base_path}\" > nul 2>&1
    
    :: Restaurar los modelos de OCR (v5_ov) a la nueva carpeta _internal\models\
    if exist "{base_path}\_update_backup\models\v5_ov" (
        rmdir /s /q "{base_path}\_internal\models\v5_ov" > nul 2>&1
        mkdir "{base_path}\_internal\models" > nul 2>&1
        move "{base_path}\_update_backup\models\v5_ov" "{base_path}\_internal\models\" > nul 2>&1
    )
    
    :: Borrar backup temporal
    rmdir /s /q "{base_path}\_update_backup" > nul 2>&1
) else (
    :: --- MODO ACTUALIZACIÓN LIVIANA 1.5+ -> 1.6+ (Sobre-escritura incremental) ---
    :: Permite que los futuros Update.zip pesen solo unos pocos megas.
    robocopy "{source_dir}" "{base_path}" /E /MOVE /IS /IT /R:5 /W:1 > nul
)

:: 3. Limpiar archivos temporales de la descarga
rmdir /s /q "{tmp_dir}" > nul 2>&1
del "{zip_path}" > nul 2>&1

:: 4. Arrancar la nueva versión limpia
start "" "{os.path.join(base_path, exe_name)}"
del "%~f0"
"""
        
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)
            
        subprocess.Popen([bat_path], shell=True)
        wx.CallAfter(wx.GetApp().ExitMainLoop)
    except Exception as e:
        wx.MessageBox(f"Error al aplicar la actualización: {e}", "Error")
