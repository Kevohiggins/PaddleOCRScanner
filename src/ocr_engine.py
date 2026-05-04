"""
Motor OCR basado en RapidOCR (OpenVINO).
Usa OpenVINO como backend para máximo rendimiento en hardware Intel (CPU/iGPU).
"""

import logging
import os
from dataclasses import dataclass

import numpy as np


logger = logging.getLogger(__name__)


@dataclass
class DetectedElement:
    """Elemento de texto detectado en pantalla."""
    text: str
    bbox: list  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    center_x: float
    center_y: float
    confidence: float
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0


class OCREngine:
    """Wrapper de RapidOCR con OpenVINO."""

    def __init__(self, config: dict):
        self.config = config
        self._ocr = None

    def initialize(self):
        """
        Inicializa RapidOCR con OpenVINO.
        Soporta múltiples idiomas (v5) y aceleración por hardware.
        """
        from rapidocr_openvino import RapidOCR

        use_gpu = self.config.get("use_gpu", False)
        device = "GPU" if use_gpu else "CPU"
        
        # Obtener idioma configurado (default: latin)
        lang = self.config.get("ocr_language", "latin")
        
        # Mapeo de idioma a carpeta de modelo y versión
        lang_map = {
            "latin": {"folder": "latin", "ver": 5},
            "japanese": {"folder": "chinese", "ver": 5},
            "chinese": {"folder": "chinese", "ver": 5},
            "korean": {"folder": "korean", "ver": 5},
            "cyrillic": {"folder": "cyrillic", "ver": 5},
            "thai": {"folder": "thai", "ver": 5},
            "arabic": {"folder": "arabic", "ver": 3},
            "hindi": {"folder": "hindi", "ver": 3},
        }
        
        lang_info = lang_map.get(lang, lang_map["latin"])
        target_folder = lang_info["folder"]
        is_v3 = lang_info["ver"] == 3
        
        # Determinar ruta base para modelos (soporta ejecución normal y PyInstaller)
        import sys
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        models_root = os.path.join(base_dir, "models", "v5_ov")
        
        # Rutas de modelos específicos
        rec_model_path = os.path.join(models_root, target_folder, "rec.xml")
        rec_keys_path = os.path.join(models_root, target_folder, "dict.txt")
        
        # Detectores
        det_model_path_v3 = os.path.join(models_root, "detection_v3", "det.xml")
        det_model_path_v5 = os.path.join(models_root, "detection_v5", "det.xml")
        
        ocr_kwargs = {
            "det_device": device,
            "rec_device": device,
            "cls_device": device,
            "use_cls": False,
            "use_space_char": True,
            "det_db_unclip_ratio": 2.0,
            "det_limit_side_len": 960,
        }

        # Configurar Detector
        # Si es v3 (Arabe, Hindi), forzamos su detector v3 para compatibilidad
        if is_v3 and os.path.exists(det_model_path_v3):
            ocr_kwargs["det_model_path"] = det_model_path_v3
            logger.info("OCREngine: Usando detector v3 local [%s]", lang)
        # Para v5 (Latin, Chino, etc.), NO forzamos ruta. 
        # Dejamos que RapidOCR use su detector interno optimizado para maxima velocidad.

        # Configurar Reconocedor (Usamos el nuestro para asegurar Ñ y tildes)
        if os.path.exists(rec_model_path) and os.path.exists(rec_keys_path):
            ocr_kwargs["rec_model_path"] = rec_model_path
            ocr_kwargs["rec_keys_path"] = rec_keys_path
            logger.info("OCREngine: Cargando modelo REC v%d [%s] de %s", lang_info["ver"], lang, target_folder)
        else:
            logger.warning("OCREngine: No se encontró el modelo REC local para [%s]. Se usará el del paquete.", lang)

        logger.info("Inicializando RapidOCR (OpenVINO) — Dispositivo: %s", device)
        
        try:
            self._ocr = RapidOCR(**ocr_kwargs)
            
            # Warmup invisible para evitar lag en el primer scan real
            dummy_img = np.zeros((64, 64, 3), dtype=np.uint8)
            self._ocr(dummy_img)
            
            logger.info("RapidOCR inicializado correctamente en %s", device)
        except Exception as e:
            logger.warning("Error inicializando en %s: %s. Reintentando en CPU...", device, e)
            ocr_kwargs["det_device"] = "CPU"
            ocr_kwargs["rec_device"] = "CPU"
            ocr_kwargs["cls_device"] = "CPU"
            try:
                self._ocr = RapidOCR(**ocr_kwargs)
                logger.info("RapidOCR inicializado correctamente en CPU (fallback)")
            except Exception as e2:
                logger.error("Error crítico inicializando RapidOCR: %s", e2)
                raise

    def scan_image(self, image: np.ndarray) -> list[DetectedElement]:
        """
        Ejecuta OCR sobre una imagen y devuelve los elementos detectados.
        """
        if self._ocr is None:
            raise RuntimeError("OCREngine no inicializado. Llamá a initialize() primero.")

        import cv2
        scale_val = self.config.get("image_scale")
        scale_factor = float(scale_val) if scale_val is not None else 1.0
        original_h, original_w = image.shape[:2]
        
        # Escalar la imagen si se solicita
        if scale_factor != 1.0 and scale_factor > 0:
            new_w = int(original_w * scale_factor)
            new_h = int(original_h * scale_factor)
            process_image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        else:
            process_image = image

        result, elapse = self._ocr(process_image)
        
        if elapse:
            logger.info("Tiempos OCR (OpenVINO): Det=%.3fs, Rec=%.3fs, Total=%.3fs", 
                        elapse[0] if len(elapse) > 0 else 0,
                        elapse[1] if len(elapse) > 1 else 0,
                        sum(elapse))

        if not result:
            return []

        elements = []
        conf_val = self.config.get("min_confidence")
        min_confidence = float(conf_val) if conf_val is not None else 0.5
        tol_val = self.config.get("row_tolerance")
        row_tolerance = int(tol_val) if tol_val is not None else 20

        for detection in result:
            bbox = detection[0]       # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            text = detection[1]       # texto reconocido
            confidence = float(detection[2])  # score de confianza

            if confidence < min_confidence:
                continue
                
            if scale_factor != 1.0 and scale_factor > 0:
                bbox = [[x / scale_factor, y / scale_factor] for x, y in bbox]

            center_x = sum(p[0] for p in bbox) / 4.0
            center_y = sum(p[1] for p in bbox) / 4.0
            
            # Calcular x, y, w, h para compatibilidad
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)

            elements.append(DetectedElement(
                text=text.strip(),
                bbox=bbox,
                center_x=center_x,
                center_y=center_y,
                confidence=confidence,
                x=x_min,
                y=y_min,
                w=x_max - x_min,
                h=y_max - y_min
            ))

        elements.sort(key=lambda e: (round(e.center_y / row_tolerance) * row_tolerance, e.center_x))
        return elements
