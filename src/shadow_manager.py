import json
import os
import logging

logger = logging.getLogger(__name__)

class ShadowManager:
    """
    Gestiona las 'sombras' (regiones de la pantalla ignoradas) con perfiles por aplicación.
    Permite el filtrado basado en la ubicación persistente y contenido de los elementos.
    """

    def __init__(self, config_path=None):
        self.config_path = config_path
        self.is_enabled = True
        self.current_app = "Global"
        
        # Estructura: { "NombreApp": { "regions": [[x,y,w,h], ...], "texts": ["texto1", ...] } }
        self.profiles = {"Global": {"regions": [], "texts": []}}
        
        self.load()

    def load(self):
        """Carga los perfiles guardados desde el archivo de configuración."""
        if self.config_path and os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Migración: si existe 'shadow_regions' antiguo, moverlo a Global
                    old_regions = data.get("shadow_regions", [])
                    self.profiles = data.get("shadow_profiles", {"Global": {"regions": old_regions, "texts": []}})
                
                # Asegurar que Global siempre exista
                if "Global" not in self.profiles:
                    self.profiles["Global"] = {"regions": [], "texts": []}
                
                logger.info("ShadowManager: %d perfiles cargados.", len(self.profiles))
            except Exception as e:
                logger.error("Error al cargar sombras: %s", e)

    def save(self):
        """Guarda los perfiles actuales."""
        if not self.config_path:
            return
        
        try:
            data = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            
            data["shadow_profiles"] = self.profiles
            # Limpiar el campo viejo para no confundir
            if "shadow_regions" in data:
                del data["shadow_regions"]
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info("ShadowManager: Perfiles guardados.")
        except Exception as e:
            logger.error("Error al guardar sombras: %s", e)

    def set_app(self, app_name):
        """Cambia el perfil activo basado en el nombre de la aplicación."""
        if not app_name:
            app_name = "Global"
        
        if app_name != self.current_app:
            self.current_app = app_name
            if app_name not in self.profiles:
                self.profiles[app_name] = {"regions": [], "texts": []}
            logger.info("ShadowManager: Perfil cambiado a [%s]", app_name)

    def add_region(self, x, y, w, h):
        """Añade una región al perfil actual si no existe una muy similar."""
        profile = self.profiles.get(self.current_app, self.profiles["Global"])
        regions = profile["regions"]

        # Evitar duplicados exactos o muy cercanos
        for rx, ry, rw, rh in regions:
            if abs(x-rx) < 10 and abs(y-ry) < 10 and abs(w-rw) < 15 and abs(h-rh) < 15:
                return False
        
        regions.append([x, y, w, h])
        return True

    def add_text_shadow(self, text):
        """Añade un texto a la lista negra del perfil actual."""
        if not text or len(text) < 2:
            return False
        
        profile = self.profiles.get(self.current_app, self.profiles["Global"])
        texts = profile["texts"]
        
        text_clean = text.strip().lower()
        if text_clean not in texts:
            texts.append(text_clean)
            return True
        return False

    def clear(self):
        """Limpia las sombras del perfil actual."""
        if self.current_app in self.profiles:
            self.profiles[self.current_app] = {"regions": [], "texts": []}
        self.save()

    def clear_all(self):
        """Limpia todos los perfiles guardados."""
        self.profiles = {"Global": {"regions": [], "texts": []}}
        self.current_app = "Global"
        self.save()

    def toggle(self):
        """Activa o desactiva el filtrado."""
        self.is_enabled = not self.is_enabled
        return self.is_enabled

    def _calculate_overlap(self, r1, r2):
        """Calcula qué porcentaje de r1 está cubierto por r2."""
        x1, y1, w1, h1 = r1
        x2, y2, w2, h2 = r2
        
        dx = min(x1+w1, x2+w2) - max(x1, x2)
        dy = min(y1+h1, y2+h2) - max(y1, y2)
        
        if dx > 0 and dy > 0:
            overlap_area = dx * dy
            r1_area = w1 * h1
            return overlap_area / r1_area if r1_area > 0 else 0
        return 0

    def is_shadowed(self, element):
        """
        Verifica si un DetectedElement debe ser ignorado.
        Criterios:
        1. El texto está en la lista negra de textos.
        2. El área del elemento solapa significativamente con una región de sombra (>60%).
        """
        if not self.is_enabled:
            return False

        # 1. Verificar por Texto (en Global y en el perfil actual)
        text_clean = element.text.strip().lower()
        for p_name in ["Global", self.current_app]:
            if text_clean in self.profiles.get(p_name, {}).get("texts", []):
                return True

        # 2. Verificar por Región (en Global y en el perfil actual)
        elem_rect = [element.x, element.y, element.w, element.h]
        
        for p_name in ["Global", self.current_app]:
            regions = self.profiles.get(p_name, {}).get("regions", [])
            for s_rect in regions:
                # Si solapa más del 60%, a la sombra
                if self._calculate_overlap(elem_rect, s_rect) > 0.6:
                    return True
        
        return False

    def filter_elements(self, elements):
        """Filtra una lista de elementos quitando los que están en la sombra."""
        if not self.is_enabled:
            return elements
        return [e for e in elements if not self.is_shadowed(e)]
