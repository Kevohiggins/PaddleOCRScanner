import logging
import sys
import numpy as np
import mss
import win32gui
import threading
import cv2  # ¡Añadimos OpenCV acá!

logger = logging.getLogger(__name__)
_thread_local = threading.local()


def get_sct():
    if not hasattr(_thread_local, 'sct'):
        _thread_local.sct = mss.mss()
    return _thread_local.sct


def is_black_frame(img: np.ndarray) -> bool:
    """Detecta rápidamente si una captura está completamente negra (ej. cortina de pantalla)."""
    if img is None or img.size == 0:
        return True
    return float(np.mean(img[::16, ::16])) < 0.1


def _wgc_draw_border():
    """En Windows 10 (build < 20348) WGC no soporta draw_border=False; solo usarlo en Win11+."""
    try:
        return False if sys.getwindowsversion().build >= 20348 else None
    except Exception:
        return None


def _capture_monitor_wgc(monitor_index: int = 1) -> np.ndarray | None:
    """
    Captura un monitor usando Windows Graphics Capture (WGC), que obtiene el
    contenido del compositor antes de la transformación de color de la cortina
    de pantalla de NVDA (MagSetFullscreenColorEffect).
    """
    try:
        from windows_capture import WindowsCapture
    except ImportError:
        logger.warning("windows-capture no está instalado; no se puede usar WGC.")
        return None

    result = [None]

    def _run():
        try:
            capture = WindowsCapture(
                cursor_capture=False,
                draw_border=_wgc_draw_border(),
                monitor_index=monitor_index,
            )

            @capture.event
            def on_frame_arrived(frame, capture_control):
                try:
                    bgr = frame.convert_to_bgr()
                    result[0] = bgr.frame_buffer.copy()
                except Exception:
                    buf = frame.frame_buffer
                    if buf is not None and buf.ndim == 3 and buf.shape[2] >= 3:
                        result[0] = np.ascontiguousarray(buf[:, :, :3])
                finally:
                    capture_control.stop()

            @capture.event
            def on_closed():
                pass

            capture.start()
        except Exception as e:
            logger.warning("Error en captura WGC (monitor %s): %s", monitor_index, e)

    # Ejecutar en hilo dedicado para evitar conflicto COM STA del hilo principal de wx
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=3.0)
    return result[0]


class PersistentWGCCapture:
    """Sesión WGC persistente para evitar abrir/cerrar Direct3D en escaneo dinámico."""

    def __init__(self, monitor_index: int = 1):
        self.monitor_index = monitor_index
        self._lock = threading.Lock()
        self._latest_frame = None
        self._frame_event = threading.Event()
        self._control = None
        self._started = False

    def start(self) -> bool:
        try:
            from windows_capture import WindowsCapture
        except ImportError:
            return False

        ok = [False]

        def _start():
            try:
                capture = WindowsCapture(
                    cursor_capture=False,
                    draw_border=_wgc_draw_border(),
                    monitor_index=self.monitor_index,
                )

                @capture.event
                def on_frame_arrived(frame, capture_control):
                    try:
                        bgr = frame.convert_to_bgr()
                        buf = bgr.frame_buffer.copy()
                    except Exception:
                        raw = frame.frame_buffer
                        if raw is not None and raw.ndim == 3 and raw.shape[2] >= 3:
                            buf = np.ascontiguousarray(raw[:, :, :3])
                        else:
                            return
                    with self._lock:
                        self._latest_frame = buf
                    self._frame_event.set()

                @capture.event
                def on_closed():
                    self._started = False

                self._control = capture.start_free_threaded()
                self._started = True
                ok[0] = True
            except Exception as e:
                logger.warning("No se pudo iniciar PersistentWGCCapture: %s", e)
                self._started = False

        t = threading.Thread(target=_start, daemon=True)
        t.start()
        t.join(timeout=3.0)
        return ok[0]

    def get_frame(self, timeout: float = 0.5) -> np.ndarray | None:
        if not self._started:
            return None
        if not self._frame_event.wait(timeout=timeout):
            return None
        with self._lock:
            return self._latest_frame

    def stop(self):
        self._started = False
        if self._control is not None:
            try:
                self._control.stop()
            except Exception:
                pass
            self._control = None
        with self._lock:
            self._latest_frame = None
        self._frame_event.clear()


def capture_screen(monitor_index: int = 1) -> tuple[np.ndarray, int, int]:
    sct = get_sct()
    monitor = sct.monitors[monitor_index]

    wgc_img = _capture_monitor_wgc(monitor_index)
    if wgc_img is not None and not is_black_frame(wgc_img):
        return wgc_img, monitor["left"], monitor["top"]

    screenshot = sct.grab(monitor)

    # 1. CERO COPIAS: Leemos la memoria RAM cruda (instantáneo)
    img_bgra = np.frombuffer(screenshot.bgra, dtype=np.uint8).reshape((screenshot.height, screenshot.width, 4))

    # 2. Extraemos los 3 colores (BGR) usando C++ ultra optimizado
    # ¡No lo pasamos a RGB! A OpenCV y RapidOCR les gusta el BGR.
    img = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)

    return img, monitor["left"], monitor["top"]


def capture_active_window() -> tuple[np.ndarray, int, int]:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return capture_screen()
    try:
        rect = win32gui.GetWindowRect(hwnd)
        x, y, x2, y2 = rect
        width = x2 - x
        height = y2 - y
    except Exception:
        return capture_screen()

    if width <= 0 or height <= 0:
        return capture_screen()

    sct = get_sct()
    cx, cy = x + width // 2, y + height // 2
    mon_idx = 1
    for idx in range(1, len(sct.monitors)):
        m = sct.monitors[idx]
        if m["left"] <= cx < m["left"] + m["width"] and m["top"] <= cy < m["top"] + m["height"]:
            mon_idx = idx
            break

    wgc_img = _capture_monitor_wgc(mon_idx)
    if wgc_img is not None and not is_black_frame(wgc_img):
        m = sct.monitors[mon_idx]
        rx1 = max(0, x - m["left"])
        ry1 = max(0, y - m["top"])
        rx2 = min(wgc_img.shape[1], x2 - m["left"])
        ry2 = min(wgc_img.shape[0], y2 - m["top"])
        if rx2 > rx1 and ry2 > ry1:
            return wgc_img[ry1:ry2, rx1:rx2], m["left"] + rx1, m["top"] + ry1
        return wgc_img, m["left"], m["top"]

    region = {"left": x, "top": y, "width": width, "height": height}
    screenshot = sct.grab(region)

    # 1. CERO COPIAS
    img_bgra = np.frombuffer(screenshot.bgra, dtype=np.uint8).reshape((screenshot.height, screenshot.width, 4))

    # 2. Extracción a BGR
    img = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)

    return img, x, y