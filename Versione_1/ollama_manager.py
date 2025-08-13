# ollama_manager.py

import requests
import json
import logging
from PyQt6.QtCore import QThread, pyqtSignal

class OllamaModelsThread(QThread):
    """
    Thread per recuperare la lista dei modelli Ollama disponibili.
    """
    models_list = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def run(self):
        try:
            logging.info("Recupero modelli Ollama disponibili...")
            response = requests.get("http://localhost:11434/api/tags")
            response.raise_for_status() # Lancia un'eccezione per risposte HTTP non riuscite
            data = response.json()
            models = [m['name'] for m in data.get('models', [])]

            if not models:
                self.error_occurred.emit("Nessun modello Ollama trovato. Assicurati di averne scaricato almeno uno con 'ollama pull <nome_modello>'.")
                return

            logging.info(f"Modelli Ollama trovati: {models}")
            self.models_list.emit(models)
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit("Errore di connessione a Ollama. Assicurati che il servizio sia in esecuzione.")
        except requests.exceptions.RequestException as e:
            self.error_occurred.emit(f"Errore nella richiesta a Ollama: {e}")
        except json.JSONDecodeError:
            self.error_occurred.emit("Risposta non valida da Ollama.")


class OllamaThread(QThread):
    """
    Thread per inviare una richiesta a Ollama e ricevere la risposta.
    """
    ollama_response = pyqtSignal(str)
    ollama_error = pyqtSignal(str)

    def __init__(self, prompt, model="llava:7b", parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.model = model

    def run(self):
        try:
            logging.info(f"Invio prompt a Ollama con il modello '{self.model}'...")

            headers = {"Content-Type": "application/json"}
            data = {
                "model": self.model,
                "prompt": self.prompt,
                "stream": False # Semplifichiamo disabilitando lo streaming
            }

            response = requests.post(
                "http://localhost:11434/api/generate",
                headers=headers,
                data=json.dumps(data)
            )
            response.raise_for_status()

            # La risposta non è un singolo oggetto JSON, ma una sequenza di oggetti.
            # Se lo streaming è disabilitato, avremo un solo oggetto.
            data = response.json()

            full_response = data.get('response', '')

            if full_response:
                logging.info("Risposta da Ollama ricevuta con successo.")
                self.ollama_response.emit(full_response.strip())
            else:
                self.ollama_error.emit("Nessuna risposta valida da Ollama.")

        except requests.exceptions.ConnectionError:
            self.ollama_error.emit("Errore di connessione. Assicurati che il servizio Ollama sia attivo.")
        except requests.exceptions.RequestException as e:
            self.ollama_error.emit(f"Errore nella richiesta Ollama: {e}")
        except json.JSONDecodeError:
            self.ollama_error.emit("Risposta non valida da Ollama. Assicurati che il server sia configurato correttamente.")
