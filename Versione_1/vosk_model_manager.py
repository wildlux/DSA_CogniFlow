import os
import shutil
import logging
import requests
import zipfile
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QComboBox,
    QMessageBox, QProgressDialog, QTabWidget,
    QWidget, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QIcon

class VoskModelManager:
    """
    Gestisce il download e l'installazione dei modelli Vosk.
    """
    def __init__(self):
        self.models_dir = "vosk_models"
        self.model_urls = {
            "vosk-model-small-it-0.22": "https://alphacephei.com/vosk/models/vosk-model-small-it-0.22.zip",
            "vosk-model-it-0.22": "https://alphacephei.com/vosk/models/vosk-model-it-0.22.zip"
        }
        self.download_queue = []
        self.model_info = self._get_model_info()

        if not os.path.exists(self.models_dir):
            os.makedirs(self.models_dir)
            logging.info(f"Creata la directory: {self.models_dir}")

    def _get_model_info(self):
        """
        Restituisce un dizionario con i nomi dei modelli come chiavi
        e le loro informazioni come valori.
        """
        info = {
            "vosk-model-small-it-0.22": {
                "name": "Italiano (Piccolo)",
                "size": "50 MB",
                "description": "Modello italiano leggero per riconoscimento più veloce.",
                "url": self.model_urls["vosk-model-small-it-0.22"],
            },
            "vosk-model-it-0.22": {
                "name": "Italiano (Standard)",
                "size": "1.4 GB",
                "description": "Modello italiano completo per una maggiore accuratezza.",
                "url": self.model_urls["vosk-model-it-0.22"],
            }
        }
        return info

    def get_installed_models(self):
        """
        Restituisce una lista dei modelli installati.
        """
        installed = []
        if os.path.exists(self.models_dir):
            for item in os.listdir(self.models_dir):
                if os.path.isdir(os.path.join(self.models_dir, item)):
                    installed.append(item)
        return installed

    def update_model_list(self):
        """
        Aggiorna la lista dei modelli nella UI. Questo metodo va implementato nella classe `OptionsDialog`.
        """
        pass

    def download_model(self, model_name, progress_callback=None):
        """
        Scarica e installa un modello Vosk.
        """
        model_url = self.model_urls.get(model_name)
        if not model_url:
            logging.error(f"URL non trovato per il modello: {model_name}")
            return False

        zip_path = os.path.join(self.models_dir, f"{model_name}.zip")
        extracted_path = os.path.join(self.models_dir, model_name)

        if os.path.exists(extracted_path):
            logging.info(f"Il modello '{model_name}' è già installato.")
            return True

        logging.info(f"Inizio download di {model_name} da {model_url}")

        try:
            response = requests.get(model_url, stream=True)
            response.raise_for_status()

            total_size_bytes = int(response.headers.get('content-length', 0))
            downloaded_bytes = 0

            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded_bytes += len(chunk)
                    if progress_callback and total_size_bytes > 0:
                        progress = int((downloaded_bytes / total_size_bytes) * 100)
                        progress_callback(progress, f"Download in corso: {progress}%")

            logging.info(f"Download di {model_name}.zip completato.")

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                root_folder_name = os.path.commonpath(zip_ref.namelist())
                zip_ref.extractall(self.models_dir)

                extracted_root_path = os.path.join(self.models_dir, root_folder_name)
                if root_folder_name != model_name:
                    if os.path.exists(extracted_root_path):
                        os.rename(extracted_root_path, extracted_path)

            os.remove(zip_path)
            logging.info(f"Installazione di {model_name} completata.")
            return True

        except requests.exceptions.RequestException as e:
            logging.error(f"Errore di rete durante il download: {e}")
            if os.path.exists(zip_path):
                os.remove(zip_path)
            return False
        except zipfile.BadZipFile:
            logging.error(f"Il file scaricato '{zip_path}' non è un file zip valido.")
            if os.path.exists(zip_path):
                os.remove(zip_path)
            return False
        except Exception as e:
            logging.error(f"Si è verificato un errore durante l'installazione: {e}")
            if os.path.exists(zip_path):
                os.remove(zip_path)
            return False

    def delete_model(self, model_name):
        """
        Elimina un modello Vosk installato.
        """
        model_path = os.path.join(self.models_dir, model_name)
        if os.path.exists(model_path):
            try:
                shutil.rmtree(model_path)
                logging.info(f"Modello '{model_name}' eliminato con successo.")
                return True
            except Exception as e:
                logging.error(f"Errore durante l'eliminazione del modello '{model_name}': {e}")
                return False
        return False

class OptionsDialog(QDialog):
    """
    Finestra di dialogo per la gestione delle opzioni e dei modelli Vosk.
    """
    def __init__(self, manager, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Opzioni e Gestione Modelli")
        self.setGeometry(200, 200, 600, 400)
        self.manager = manager
        self.settings = settings

        self.layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.setup_general_tab()
        self.setup_library_tab()

        self.layout.addWidget(self.tabs)

    def setup_general_tab(self):
        """
        Imposta la scheda delle impostazioni generali.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel("<h2>Impostazioni Generali</h2>"))
        layout.addWidget(QLabel("Seleziona il modello Vosk da utilizzare:"))

        self.model_combo_box = QComboBox()
        layout.addWidget(self.model_combo_box)

        spacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        layout.addItem(spacer)

        self.tabs.addTab(tab, "Generale")

        self.model_combo_box.currentTextChanged.connect(self.save_model_setting)
        self.update_combo_box()

    def setup_library_tab(self):
        """
        Imposta la scheda per la gestione dei modelli Vosk.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel("<h2>Gestione Librerie</h2>"))

        self.model_table = QTableWidget()
        self.model_table.setColumnCount(4)
        self.model_table.setHorizontalHeaderLabels(["Nome", "Dimensioni", "Stato", "Azione"])
        self.model_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.model_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.model_table)

        self.tabs.addTab(tab, "Gestione Librerie")

        self.update_table()

    def update_combo_box(self):
        """
        Aggiorna la lista dei modelli nel QComboBox.
        """
        self.model_combo_box.clear()
        installed_models = self.manager.get_installed_models()

        if not installed_models:
            self.model_combo_box.addItem("Nessun modello installato")
            self.model_combo_box.setEnabled(False)
        else:
            self.model_combo_box.setEnabled(True)
            self.model_combo_box.addItems(installed_models)

            selected_model = self.settings.value("vosk_model", "")
            if selected_model in installed_models:
                self.model_combo_box.setCurrentText(selected_model)

    def save_model_setting(self, model_name):
        """
        Salva il modello selezionato nelle impostazioni.
        """
        self.settings.setValue("vosk_model", model_name)
        logging.info(f"Impostazione salvata: vosk_model = {model_name}")

    def update_table(self):
        """
        Popola la tabella con le informazioni sui modelli.
        """
        self.model_table.setRowCount(len(self.manager.model_info))
        installed_models = self.manager.get_installed_models()

        for row, (model_id, info) in enumerate(self.manager.model_info.items()):
            self.model_table.setItem(row, 0, QTableWidgetItem(info["name"]))
            self.model_table.setItem(row, 1, QTableWidgetItem(info["size"]))

            is_installed = model_id in installed_models
            status_text = "Installato" if is_installed else "Non installato"
            self.model_table.setItem(row, 2, QTableWidgetItem(status_text))

            action_button = QPushButton("Elimina" if is_installed else "Scarica")
            action_button.setStyleSheet("QPushButton {padding: 5px;}")

            if is_installed:
                action_button.clicked.connect(lambda _, m=model_id: self.handle_delete_model(m))
                action_button.setStyleSheet("background-color: #ffcccc;")
            else:
                action_button.clicked.connect(lambda _, m=model_id: self.handle_download_model(m))
                action_button.setStyleSheet("background-color: #ccffcc;")

            self.model_table.setCellWidget(row, 3, action_button)

        self.model_table.resizeColumnsToContents()
        self.model_table.resizeRowsToContents()

    def handle_download_model(self, model_name):
        """
        Gestisce il processo di download con una barra di avanzamento.
        """
        progress_dialog = QProgressDialog(f"Download di {self.manager.model_info[model_name]['name']}", "Annulla", 0, 100, self)
        progress_dialog.setWindowTitle("Download in corso")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setAutoClose(False)
        progress_dialog.setMinimumWidth(300)

        def update_progress(value, text):
            progress_dialog.setValue(value)
            progress_dialog.setLabelText(text)
            if progress_dialog.wasCanceled():
                logging.info("Download annullato dall'utente.")
                return False
            return True

        progress_dialog.show()

        download_success = self.manager.download_model(model_name, progress_callback=update_progress)

        progress_dialog.close()

        if download_success:
            QMessageBox.information(self, "Download Completato", f"Il modello '{self.manager.model_info[model_name]['name']}' è stato installato con successo.")
            self.update_table()
            self.update_combo_box()
        else:
            QMessageBox.warning(self, "Errore di Download", f"Si è verificato un errore durante il download o l'installazione del modello '{self.manager.model_info[model_name]['name']}'.")

    def handle_delete_model(self, model_name):
        """
        Gestisce l'eliminazione di un modello con conferma.
        """
        reply = QMessageBox.question(self, 'Conferma eliminazione',
                                    f"Sei sicuro di voler eliminare il modello '{self.manager.model_info[model_name]['name']}'?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            if self.manager.delete_model(model_name):
                QMessageBox.information(self, "Eliminazione Completata", f"Il modello '{self.manager.model_info[model_name]['name']}' è stato eliminato.")
                self.update_table()
                self.update_combo_box()
            else:
                QMessageBox.warning(self, "Errore", f"Impossibile eliminare il modello '{self.manager.model_info[model_name]['name']}'.")
