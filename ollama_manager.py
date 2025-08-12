# ollama_manager.py
import requests
import logging
from PyQt6.QtCore import QThread, pyqtSignal

class OllamaThread(QThread):
    """
    Thread dedicato per l'interazione con il modello Ollama (LLM) per
    evitare di bloccare l'interfaccia utente durante le richieste API.
    """
    ollama_response = pyqtSignal(str)
    ollama_error = pyqtSignal(str)

    def __init__(self, prompt, model="llava:7b", parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.model = model

    def run(self):
        """Esegue la richiesta all'API di Ollama in un thread separato."""
        try:
            logging.info(f"Invio prompt a Ollama. Modello: {self.model}, Prompt: {self.prompt}")
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": self.model,
                "prompt": self.prompt,
                "stream": False
            }

            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()

            data = response.json()
            full_response = data.get("response", "Nessuna risposta ricevuta.")

            self.ollama_response.emit(full_response.strip())

        except requests.exceptions.ConnectionError:
            self.ollama_error.emit("Errore di connessione: Il server Ollama non è raggiungibile. Assicurati che sia in esecuzione.")
        except requests.exceptions.RequestException as e:
            self.ollama_error.emit(f"Errore nella richiesta Ollama: {e}")
        except Exception as e:
            self.ollama_error.emit(f"Si è verificato un errore inaspettato: {e}")

class OllamaModelsThread(QThread):
    """
    Thread per recuperare la lista dei modelli Ollama disponibili.
    """
    models_list = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def run(self):
        try:
            url = "http://localhost:11434/api/tags"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            models_data = response.json().get('models', [])
            model_names = [model.get('name') for model in models_data]
            self.models_list.emit(model_names)
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit("Errore di connessione: Il server Ollama non è raggiungibile.")
        except requests.exceptions.RequestException as e:
            self.error_occurred.emit(f"Errore nella richiesta dei modelli: {e}")
        except Exception as e:
            self.error_occurred.emit(f"Si è verificato un errore inaspettato: {e}")
