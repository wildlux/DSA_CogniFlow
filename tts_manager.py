# tts_manager.py

from PyQt6.QtCore import QThread, pyqtSignal
import logging
import sys

# Tentativo di importazione del modulo 'parla' per la sintesi vocale
try:
    from parla import TTSManager
    logging.info("Modulo 'parla' caricato con successo.")
except ImportError:
    logging.error("Impossibile importare il modulo 'parla'. Assicurati che il file '__init__.py' si trovi nella cartella 'parla' e che contenga le classi e le funzioni necessarie.")
    class TTSManager:
        def __init__(self, voice_name):
            logging.warning(f"Usando una classe TTSManager di fallback per la voce: {voice_name}")
        def speak(self, text, speed=1.0, pitch=1.0):
            logging.info(f"FALLBACK TTS: Tentativo di leggere il testo: {text} (velocità={speed}, intonazione={pitch})")

# Voci di sistema predefinite per la sintesi vocale.
VOCI_DI_SISTEMA = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe",
    "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome",
    "Algenib", "Rasalgethi", "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux",
    "Pulcherrima", "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager",
    "Sulafat"
]

class TTSThread(QThread):
    """
    Thread dedicato per la lettura vocale del testo utilizzando il TTSManager,
    evitando di bloccare l'interfaccia utente.
    """
    finished_reading = pyqtSignal()
    started_reading = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, text_to_read, selected_voice, speed=1.0, pitch=1.0):
        super().__init__()
        self.text_to_read = text_to_read
        self.selected_voice = selected_voice
        self.speed = speed
        self.pitch = pitch
        self._is_running = True
        self.tts_manager = None

    def run(self):
        """Esegue la sintesi vocale in un thread separato."""
        try:
            self.tts_manager = TTSManager(self.selected_voice)
            self.started_reading.emit()
            logging.info(f"Lettura in corso con la voce '{self.selected_voice}': {self.text_to_read}")
            self.tts_manager.speak(self.text_to_read, speed=self.speed, pitch=self.pitch)
            if self._is_running:
                self.finished_reading.emit()
        except Exception as e:
            logging.error(f"Errore nel thread di lettura vocale: {e}")
            self.error_occurred.emit(str(e))

    def stop(self):
        """Ferma il thread in modo sicuro."""
        self._is_running = False
        self.wait()
