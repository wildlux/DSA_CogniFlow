import os
import logging
from PyQt6.QtCore import QThread, pyqtSignal
import json

try:
    import vosk
    import pyaudio
except ImportError as e:
    logging.error(f"Errore: Assicurati che le librerie 'vosk' e 'pyaudio' siano installate. {e}")

class SpeechRecognitionThread(QThread):
    """
    Thread per il riconoscimento vocale con timeout sul silenzio.
    """
    # Segnali per comunicare con l'interfaccia utente
    model_status = pyqtSignal(str)
    recognized_text = pyqtSignal(str)
    recognition_error = pyqtSignal(str)
    stopped_by_silence = pyqtSignal()

    def __init__(self, vosk_model_name):
        super().__init__()
        self.vosk_model_name = vosk_model_name
        self.running = True
        self.SILENCE_TIMEOUT_SECONDS = 3  # Timeout in secondi per il silenzio

    def run(self):
        vosk_model_path = os.path.join("vosk_models", self.vosk_model_name)

        if not os.path.exists(vosk_model_path):
            error_msg = f"Modello Vosk non trovato in {vosk_model_path}"
            logging.error(error_msg)
            self.model_status.emit(f"Errore: {error_msg}")
            self.recognition_error.emit(error_msg)
            return

        try:
            self.model_status.emit(f"Caricamento modello Vosk: {self.vosk_model_name}")
            model = vosk.Model(vosk_model_path)

            # Parametri per il flusso audio
            SAMPLE_RATE = 16000
            CHUNK_SIZE = 4000

            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16,
                            channels=1,
                            rate=SAMPLE_RATE,
                            input=True,
                            frames_per_buffer=CHUNK_SIZE)

            recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE)

            self.model_status.emit("In ascolto...")
            logging.info("Riconoscimento vocale avviato...")

            silent_chunks_count = 0
            silent_chunks_threshold = (SAMPLE_RATE / CHUNK_SIZE) * self.SILENCE_TIMEOUT_SECONDS

            while self.running:
                data = stream.read(CHUNK_SIZE, exception_on_overflow=False)

                if not data:
                    continue

                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get('text')
                    if text:
                        self.recognized_text.emit(text)
                        logging.info(f"Testo riconosciuto: {text}")
                        silent_chunks_count = 0 # Reimposta il contatore del silenzio

                else: # Il risultato non è un testo completo (probabilmente silenzio)
                    partial_result = json.loads(recognizer.PartialResult())
                    if not partial_result.get('partial', '').strip():
                        silent_chunks_count += 1
                        if silent_chunks_count > silent_chunks_threshold:
                            self.running = False # Ferma il ciclo
                            self.stopped_by_silence.emit() # Emette un segnale che il thread si è fermato per silenzio
                            break
                    else:
                        silent_chunks_count = 0 # Reimposta il contatore se c'è attività vocale

        except Exception as e:
            error_msg = f"Errore fatale nel thread di riconoscimento vocale: {e}"
            logging.error(error_msg)
            self.recognition_error.emit(error_msg)
        finally:
            # Assicura che il flusso audio venga sempre chiuso correttamente
            if 'stream' in locals() and stream.is_active():
                stream.stop_stream()
                stream.close()
            if 'p' in locals():
                p.terminate()

        self.model_status.emit("Riconoscimento vocale terminato")
        logging.info("Riconoscimento vocale terminato.")

    def stop(self):
        self.running = False
        self.wait() # Attende la chiusura del thread
