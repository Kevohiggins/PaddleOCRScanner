"""
Motor de Text-to-Speech con soporte para lectores de pantalla.
Prioridad: accessible_output2 (NVDA/JAWS) → SAPI5 (win32com) fallback.
"""

import logging

logger = logging.getLogger(__name__)


class TTSEngine:
    """Abstracción de salida de voz con cadena de fallback."""

    def __init__(self):
        self._ao2_output = None
        self._sapi_voice = None
        self._init_accessible_output2()
        if self._ao2_output is None:
            self._init_sapi()

    def _init_accessible_output2(self):
        """Intenta inicializar accessible_output2 para hablar directo al lector de pantalla."""
        try:
            from accessible_output2.outputs.auto import Auto
            self._ao2_output = Auto()
            logger.info("TTS: accessible_output2 inicializado (lector de pantalla detectado)")
        except Exception as e:
            logger.warning("TTS: accessible_output2 no disponible (%s), usando fallback SAPI5", e)

    def _init_sapi(self):
        """Fallback: SAPI5 via COM (siempre disponible en Windows)."""
        try:
            import win32com.client
            self._sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
            logger.info("TTS: SAPI5 inicializado como fallback")
        except Exception as e:
            logger.error("TTS: No se pudo inicializar SAPI5: %s", e)

    def speak(self, text: str, interrupt: bool = True):
        """
        Habla el texto dado.
        Si interrupt=True, corta cualquier speech anterior antes de hablar.
        """
        if not text:
            return

        # Intentar accessible_output2 primero
        if self._ao2_output is not None:
            try:
                self._ao2_output.output(text, interrupt=interrupt)
                return
            except Exception as e:
                logger.warning("TTS: Error en accessible_output2: %s, probando SAPI5", e)

        # Fallback SAPI5
        if self._sapi_voice is not None:
            try:
                # Flags: 1 = SVSFlagsAsync, 2 = SVSFPurgeBeforeSpeak
                flags = 3 if interrupt else 1
                self._sapi_voice.Speak(text, flags)
                return
            except Exception as e:
                logger.error("TTS: Error en SAPI5: %s", e)

        # Si todo falla, al menos mostrar en consola
        print(f"[TTS] {text}")

    def stop(self):
        """Detiene cualquier speech en curso."""
        if self._ao2_output is not None:
            try:
                self._ao2_output.output("", interrupt=True)
            except Exception:
                pass
        if self._sapi_voice is not None:
            try:
                self._sapi_voice.Speak("", 3)
            except Exception:
                pass
