# speech_recognition_manager.py

from PyQt6.QtCore import QThread, pyqtSignal
import speech_recognition as sr
import logging

class SpeechRecognitionThread(QThread):
    """
    Thread per il riconoscimento vocale asincrono, evitando di bloccare
    l'interfaccia utente.
    """
    recognized_text = pyqtSignal(str)
    recognition_error = pyqtSignal(str)

    def __init__(self, lang_code='it-IT', parent=None):
        super().__init__(parent)
        self.recognizer = sr.Recognizer()
        self.lang_code = lang_code
        self._running = True

    def run(self):
        """Esegue il riconoscimento vocale in un thread separato."""
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source)
                logging.info("In ascolto per il riconoscimento vocale...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                logging.info("Riconoscimento in corso...")
                text = self.recognizer.recognize_google(audio, language=self.lang_code)
                self.recognized_text.emit(text)
        except sr.WaitTimeoutError:
            logging.warning("Tempo di attesa scaduto per il riconoscimento vocale.")
            self.recognition_error.emit("Tempo di attesa scaduto. Nessun input vocale ricevuto.")
        except sr.UnknownValueError:
            logging.warning("Impossibile riconoscere il testo dal segnale audio.")
            self.recognition_error.emit("Impossibile riconoscere il testo. Riprova.")
        except sr.RequestError as e:
            logging.error(f"Errore dal servizio di riconoscimento vocale: {e}")
            self.recognition_error.emit(f"Errore dal servizio di riconoscimento vocale; {e}")
        except Exception as e:
            logging.error(f"Si è verificato un errore inaspettato nel riconoscimento vocale: {e}")
            self.recognition_error.emit(f"Si è verificato un errore inaspettato: {e}")

    def stop(self):
        """Ferma il thread in modo sicuro."""
        self._running = False
        self.wait()
