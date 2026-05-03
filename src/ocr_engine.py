"""
Motor OCR basado en RapidOCR (ONNX Runtime).
Usa los mismos modelos de PaddleOCR pero con ONNX Runtime como backend,
evitando los problemas de oneDNN de PaddlePaddle nativo en Windows CPU.
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


class OCREngine:
    """Wrapper de RapidOCR con ONNX Runtime."""

    def __init__(self, config: dict):
        self.config = config
        self._ocr = None

    def initialize(self):
        """
        Inicializa RapidOCR. 
        Si se especificaron modelos en la configuración, los utiliza.
        """
        from rapidocr_onnxruntime import RapidOCR

        logger.info("Inicializando RapidOCR (ONNX Runtime)")
        
        # Configuración por defecto para máxima velocidad
        ocr_kwargs = {}

        self._ocr = RapidOCR(**ocr_kwargs)
        logger.info("RapidOCR inicializado correctamente")

    def scan_image(self, image: np.ndarray) -> list[DetectedElement]:
        """
        Ejecuta OCR sobre una imagen y devuelve los elementos detectados,
        ordenados de arriba-abajo, izquierda-derecha.

        Args:
            image: Imagen como numpy array RGB.

        Returns:
            Lista de DetectedElement ordenados espacialmente.
        """
        if self._ocr is None:
            raise RuntimeError("OCREngine no inicializado. Llamá a initialize() primero.")

        import cv2
        scale_val = self.config.get("image_scale")
        scale_factor = float(scale_val) if scale_val is not None else 1.0
        original_h, original_w = image.shape[:2]
        
        # Escalar la imagen si se solicita para ganar rendimiento
        if scale_factor != 1.0 and scale_factor > 0:
            new_w = int(original_w * scale_factor)
            new_h = int(original_h * scale_factor)
            process_image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            logger.info("Imagen redimensionada a %dx%d (escala: %s) para OCR", new_w, new_h, scale_factor)
        else:
            process_image = image

        result, elapse = self._ocr(process_image)

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
                
            # Si achicamos la imagen, hay que agrandar la caja para que
            # el click del mouse caiga en el lugar correcto de la pantalla original
            if scale_factor != 1.0 and scale_factor > 0:
                bbox = [[x / scale_factor, y / scale_factor] for x, y in bbox]

            # Centro geométrico del cuadrilátero
            center_x = sum(p[0] for p in bbox) / 4.0
            center_y = sum(p[1] for p in bbox) / 4.0

            elements.append(DetectedElement(
                text=text.strip(),
                bbox=bbox,
                center_x=center_x,
                center_y=center_y,
                confidence=confidence,
            ))

        # Ordenar: agrupar por filas (tolerancia en Y), luego izq→der dentro de cada fila
        elements.sort(key=lambda e: (round(e.center_y / row_tolerance) * row_tolerance, e.center_x))

        logger.info("OCR detectó %d elementos (de %d totales, filtrados por confianza >= %.2f)",
                     len(elements), len(result), min_confidence)

        return elements
