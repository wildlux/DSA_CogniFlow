import sys
import threading
import cv2
import json
import logging
import time
from datetime import datetime
import numpy as np
import subprocess
import re
import requests
import base64
import simpleaudio as sa
import wave
import os
from io import BytesIO
import speech_recognition as sr
from PyQt6.QtCore import (
    QThread, pyqtSignal, QTimer, Qt, QMimeData, QPoint, QObject, QSize,
    QPropertyAnimation, QRect, QEvent, QBuffer, QIODevice, QDir
)
from PyQt6.QtGui import QImage, QPixmap, QDrag, QCursor, QIcon, QPainter, QPen, QColor, QFont, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QSizePolicy,
    QLabel, QPushButton, QHBoxLayout, QComboBox, QLineEdit, QFrame, QGridLayout,
    QDialog, QTextEdit, QTabWidget, QCheckBox, QSlider, QRadioButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView, QStackedWidget,
    QScrollArea, QSpacerItem, QGroupBox, QMenu, QColorDialog, QFileDialog,
    QInputDialog, QToolButton
)

# IMPORTAZIONE MODULI LOCALI
from visual_background import VideoThread
from ollama_manager import OllamaThread, OllamaModelsThread
from tts_manager import TTSThread, VOCI_DI_SISTEMA, GTTS_LANGUAGES
from speech_recognition_manager import SpeechRecognitionThread
from vosk_model_manager import VoskModelManager

# ==============================================================================
# Inizializzazione e Configurazione Globale
# ==============================================================================

# ==============================================================================
# Classi per la gestione dei Thread asincroni (NON visivi)
# ==============================================================================

# Le classi SpeechRecognitionThread e TTSThread sono state spostate nei rispettivi moduli

# ==============================================================================
# Componenti UI Custom
# ==============================================================================

class DraggableTextWidget(QFrame):
    def __init__(self, text, settings, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setMinimumHeight(60)
        self.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.7);
                border-radius: 15px;
                margin: 5px;
                color: black;
            }
            QPushButton {
                background-color: rgba(0, 0, 0, 0.2);
                border: 1px solid rgba(0, 0, 0, 0.3);
                border-radius: 12px;
                padding: 5px 10px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.3);
            }
            QLabel {
                color: black;
            }
        """)

        self.tts_thread = None
        self.is_reading = False
        self.settings = settings
        self.original_text = text

        layout = QHBoxLayout(self)
        self.text_label = QLabel(text)
        self.text_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.text_label.setWordWrap(True)
        self.text_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.text_label.customContextMenuRequested.connect(self.show_context_menu)

        layout.addWidget(self.text_label, 1)

        button_layout = QVBoxLayout()
        self.read_button = QPushButton("🔊")
        self.read_button.setFixedSize(25, 25)
        self.read_button.setToolTip("Leggi testo")
        self.read_button.clicked.connect(self.toggle_read_text)

        self.delete_button = QPushButton("❌")
        self.delete_button.setFixedSize(25, 25)
        self.delete_button.setToolTip("Elimina")
        self.delete_button.clicked.connect(self.delete_self)

        button_layout.addWidget(self.read_button)
        button_layout.addWidget(self.delete_button)
        layout.addLayout(button_layout)

        self.setAcceptDrops(True)
        self.start_pos = None

    def show_context_menu(self, pos):
        """Mostra il menu contestuale per il widget."""
        context_menu = QMenu(self)
        edit_action = context_menu.addAction("Modifica Testo")
        action = context_menu.exec(self.mapToGlobal(pos))
        if action == edit_action:
            new_text, ok = QInputDialog.getMultiLineText(self, "Modifica Testo", "Modifica il contenuto del widget:", self.text_label.text())
            if ok:
                self.text_label.setText(new_text)

    def mousePressEvent(self, event):
        """Gestisce l'evento di pressione del mouse per iniziare il trascinamento."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = event.pos()

    def mouseMoveEvent(self, event):
        """Gestisce il movimento del mouse per il trascinamento."""
        if event.buttons() == Qt.MouseButton.LeftButton and self.start_pos:
            distance = (event.pos() - self.start_pos).manhattanLength()
            if distance > QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(self.text_label.text())
                drag.setMimeData(mime)
                drag.setPixmap(self.grab())
                drag.exec(Qt.DropAction.CopyAction) # Usa CopyAction per duplicare il testo

    def toggle_read_text(self):
        """Avvia o ferma la lettura del testo usando il thread."""
        if not self.is_reading:
            self.start_reading()
        else:
            self.stop_reading()

    def start_reading(self):
        """Avvia il thread di lettura vocale."""
        if self.tts_thread and self.tts_thread.isRunning():
            return

        self.is_reading = True
        self.read_button.setText("⏹️")
        self.read_button.setStyleSheet("background-color: #e74c3c; color: white;")

        selected_engine = self.settings.get('tts_engine', 'pyttsx3')
        voice_or_lang_combo_text = self.settings.get('tts_voice_or_lang', 'Zephyr (Fallback)')
        speed = self.settings.get('tts_speed', 1.0)
        pitch = self.settings.get('tts_pitch', 1.0)

        # Estrai l'ID della voce o il codice lingua in base al motore TTS
        voice_or_lang = ''
        if selected_engine == 'pyttsx3':
            # Cerca l'ID della voce basandosi sul nome selezionato
            selected_voice_info = next(
                (voice for voice in VOCI_DI_SISTEMA if voice['name'] == voice_or_lang_combo_text),
                None
            )
            voice_or_lang = selected_voice_info['id'] if selected_voice_info else 'fallback'
        elif selected_engine == 'gTTS':
            lang_code_match = re.search(r'\(([^)]+)\)', voice_or_lang_combo_text)
            voice_or_lang = lang_code_match.group(1) if lang_code_match else 'it'

        self.tts_thread = TTSThread(self.text_label.text(), selected_engine, voice_or_lang, speed, pitch)
        self.tts_thread.started_reading.connect(self.on_reading_started)
        self.tts_thread.finished_reading.connect(self.on_reading_finished)
        self.tts_thread.error_occurred.connect(self.on_reading_error)
        self.tts_thread.start()

    def stop_reading(self):
        """Ferma il thread di lettura vocale."""
        if self.tts_thread and self.tts_thread.isRunning():
            self.tts_thread.stop()
        self.is_reading = False
        self.read_button.setText("🔊")
        self.read_button.setStyleSheet("")
        logging.info("Lettura testo interrotta.")

    def on_reading_started(self):
        """Gestisce l'inizio della lettura."""
        logging.info("Lettura del testo iniziata.")

    def on_reading_finished(self):
        """Gestisce la fine della lettura."""
        self.is_reading = False
        self.read_button.setText("🔊")
        self.read_button.setStyleSheet("")
        logging.info("Lettura testo completata.")
        self.tts_thread = None

    def on_reading_error(self, message):
        """Gestisce gli errori durante la lettura."""
        self.is_reading = False
        self.read_button.setText("🔊")
        self.read_button.setStyleSheet("")
        logging.error(f"Errore durante la lettura vocale: {message}")
        self.tts_thread = None
        QMessageBox.critical(self.parent(), "Errore TTS", message)

    def delete_self(self):
        """Rimuove il widget dall'interfaccia."""
        if self.is_reading:
            self.stop_reading()
        self.setParent(None)
        self.deleteLater()

class LogEmitter(QObject):
    """Oggetto QObject per emettere segnali di log."""
    new_record = pyqtSignal(str)
    error_occurred = pyqtSignal()

class TextEditLogger(logging.Handler):
    """Handler di logging personalizzato che emette segnali a un QTextEdit."""
    def __init__(self, log_emitter, parent=None):
        super().__init__()
        self.log_emitter = log_emitter
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        msg = self.format(record)
        self.log_emitter.new_record.emit(msg)
        if record.levelno >= logging.ERROR:
            self.log_emitter.error_occurred.emit()

# ==============================================================================
# Dialogo di configurazione
# ==============================================================================

class ConfigurationDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Menu di Configurazione")
        self.setModal(True)
        self.resize(1000, 700) # Resized to be larger
        self.settings = settings or {}
        self.vosk_downloader_thread = None # Riferimento al thread di download Vosk
        self.tts_test_thread = None # Mantiene un riferimento al thread di prova

        self.setup_ui()
        self.load_settings()
        self.ollama_models_thread = OllamaModelsThread()
        self.ollama_models_thread.models_list.connect(self.update_ollama_models)
        self.ollama_models_thread.error_occurred.connect(self.on_ollama_models_error)
        self.ollama_models_thread.start()

    def setup_ui(self):
        """Configura l'interfaccia utente del dialogo."""
        layout = QVBoxLayout(self)

        # Tab Widget
        self.tab_widget = QTabWidget()
        self.setup_ai_tab()
        self.setup_ui_tab()
        self.setup_tts_tab()
        self.setup_gestures_tab()
        self.setup_empathy_tab()
        self.setup_library_tab()
        self.setup_data_tab()
        layout.addWidget(self.tab_widget)

        # Pulsanti Applica e Chiudi in basso
        bottom_button_layout = QHBoxLayout()
        bottom_button_layout.addStretch(1)

        apply_btn = QPushButton("Applica ✅")
        apply_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        apply_btn.clicked.connect(self.apply_changes)
        bottom_button_layout.addWidget(apply_btn)

        close_menu_btn = QPushButton("Chiudi ➡️")
        close_menu_btn.clicked.connect(self.reject)
        bottom_button_layout.addWidget(close_menu_btn)

        layout.addLayout(bottom_button_layout)

    def setup_ai_tab(self):
        """Configura il tab per le impostazioni dell'IA."""
        ai_widget = QWidget()
        layout = QVBoxLayout(ai_widget)

        ai_group = QGroupBox("Selezione AI")
        ai_layout = QVBoxLayout(ai_group)
        self.ollama_model_combo = QComboBox()
        self.ollama_model_combo.addItem("Caricamento modelli...")
        ai_layout.addWidget(QLabel("Modello Ollama:"))
        ai_layout.addWidget(self.ollama_model_combo)

        test_ollama_btn = QPushButton("Testa Connessione & Modelli")
        test_ollama_btn.clicked.connect(self.test_ollama_connection)
        ai_layout.addWidget(test_ollama_btn)

        self.ollama_status_label = QLabel("Stato: In attesa di caricamento...")
        self.ollama_status_label.setStyleSheet("color: #4a90e2;")
        ai_layout.addWidget(self.ollama_status_label)
        layout.addWidget(ai_group)

        trigger_group = QGroupBox("Trigger per AI")
        trigger_layout = QVBoxLayout(trigger_group)
        trigger_layout.addWidget(QLabel("Imposta una parola d'ordine per inviare il testo all'AI:"))
        self.ai_trigger_input = QLineEdit("++++")
        trigger_layout.addWidget(self.ai_trigger_input)
        layout.addWidget(trigger_group)

        layout.addStretch()
        self.tab_widget.addTab(ai_widget, "Configurazione AI")

    def setup_ui_tab(self):
        """Configura il tab per le impostazioni dell'UI."""
        ui_widget = QWidget()
        layout = QVBoxLayout(ui_widget)

        button_colors_group = QGroupBox("Colori Pulsanti Principali")
        colors_grid = QGridLayout(button_colors_group)

        self.add_btn_color = QPushButton("Inserisci testo")
        self.add_btn_color.clicked.connect(lambda: self.open_color_dialog(self.add_btn_color))
        colors_grid.addWidget(self.add_btn_color, 0, 0)

        self.ai_btn_color = QPushButton("🧠 AI")
        self.ai_btn_color.clicked.connect(lambda: self.open_color_dialog(self.ai_btn_color))
        colors_grid.addWidget(self.ai_btn_color, 0, 1)

        self.voice_btn_color = QPushButton("🎤 Voce")
        self.voice_btn_color.clicked.connect(lambda: self.open_color_dialog(self.voice_btn_color))
        colors_grid.addWidget(self.voice_btn_color, 0, 2)

        self.hands_btn_color = QPushButton("✋ Mani")
        self.hands_btn_color.clicked.connect(lambda: self.open_color_dialog(self.hands_btn_color))
        colors_grid.addWidget(self.hands_btn_color, 1, 0)

        self.face_btn_color = QPushButton("😊 Faccia")
        self.face_btn_color.clicked.connect(lambda: self.open_color_dialog(self.face_btn_color))
        colors_grid.addWidget(self.face_btn_color, 1, 1)

        self.clean_btn_color = QPushButton("🧹 Pulisci")
        self.clean_btn_color.clicked.connect(lambda: self.open_color_dialog(self.clean_btn_color))
        colors_grid.addWidget(self.clean_btn_color, 2, 0)

        self.options_btn_color = QPushButton("⚙️ Opzioni")
        self.options_btn_color.clicked.connect(lambda: self.open_color_dialog(self.options_btn_color))
        colors_grid.addWidget(self.options_btn_color, 3, 0)

        self.log_btn_color = QPushButton("📊 Log")
        self.log_btn_color.clicked.connect(lambda: self.open_color_dialog(self.log_btn_color))
        colors_grid.addWidget(self.log_btn_color, 3, 1)

        layout.addWidget(button_colors_group)

        layout.addStretch()
        self.tab_widget.addTab(ui_widget, "Comportamento & UI")

    def setup_tts_tab(self):
        """Configura il tab per la sintesi vocale."""
        tts_widget = QWidget()
        layout = QVBoxLayout(tts_widget)

        tts_config_group = QGroupBox("Sintesi Vocale (TTS)")
        tts_config_layout = QVBoxLayout(tts_config_group)

        # Nuovo selettore del sintetizzatore vocale
        tts_config_layout.addWidget(QLabel("Sintetizzatore Vocale:"))
        self.tts_engine_combo = QComboBox()
        self.tts_engine_combo.addItems(['pyttsx3', 'gTTS', 'Piper (WIP)'])
        self.tts_engine_combo.currentIndexChanged.connect(self.update_voice_combo)
        tts_config_layout.addWidget(self.tts_engine_combo)

        # Selettore Sesso (visibile solo per pyttsx3)
        self.tts_gender_combo = QComboBox()
        self.tts_gender_combo.addItems(['Qualsiasi', 'Maschile', 'Femminile'])
        self.tts_gender_combo.currentIndexChanged.connect(self.update_voice_combo)
        tts_config_layout.addWidget(QLabel("Sesso Voce (se disponibile):"))
        tts_config_layout.addWidget(self.tts_gender_combo)

        # Selettore Voce/Lingua
        tts_config_layout.addWidget(QLabel("Nome Voce / Lingua:"))
        self.tts_voice_combo = QComboBox()
        self.update_voice_combo()
        tts_config_layout.addWidget(self.tts_voice_combo)

        advanced_params_group = QGroupBox("Parametri avanzati")
        advanced_params_layout = QGridLayout(advanced_params_group)

        advanced_params_layout.addWidget(QLabel("Velocità (0.5 - 2.0):"), 0, 0)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(50, 200)
        self.speed_slider.setValue(100)
        self.speed_label = QLabel("1.0x")
        self.speed_slider.valueChanged.connect(lambda value: self.speed_label.setText(f"{value/100:.1f}x"))
        advanced_params_layout.addWidget(self.speed_slider, 0, 1)
        advanced_params_layout.addWidget(self.speed_label, 0, 2)

        advanced_params_layout.addWidget(QLabel("Intonazione (0.5 - 2.0):"), 1, 0)
        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setRange(50, 200)
        self.pitch_slider.setValue(100)
        self.pitch_label = QLabel("1.0x")
        self.pitch_slider.valueChanged.connect(lambda value: self.pitch_label.setText(f"{value/100:.1f}x"))
        advanced_params_layout.addWidget(self.pitch_slider, 1, 1)
        advanced_params_layout.addWidget(self.pitch_label, 1, 2)

        tts_config_layout.addWidget(advanced_params_group)

        test_group = QGroupBox("Prova la Sintesi Vocale")
        test_layout = QVBoxLayout(test_group)
        self.tts_test_text = QTextEdit()
        self.tts_test_text.setPlaceholderText("Inserisci qui il testo da testare...")
        self.tts_test_text.setText("Questo è un esempio di sintesi vocale in italiano")
        test_layout.addWidget(self.tts_test_text)

        self.test_tts_button = QPushButton("Prova Sintesi Vocale 🔊")
        self.test_tts_button.clicked.connect(self.test_tts)
        test_layout.addWidget(self.test_tts_button)

        tts_config_layout.addWidget(test_group)
        layout.addWidget(tts_config_group)

        layout.addStretch()
        self.tab_widget.addTab(tts_widget, "Sintesi Vocale")

    def update_voice_combo(self):
        """Aggiorna il combobox delle voci/lingue in base al motore TTS e al sesso selezionati."""
        selected_engine = self.tts_engine_combo.currentText()
        self.tts_voice_combo.clear()
        self.tts_gender_combo.setEnabled(selected_engine == 'pyttsx3')

        if selected_engine == 'pyttsx3':
            selected_gender = self.tts_gender_combo.currentText()
            filtered_voices = [
                voice['name'] for voice in VOCI_DI_SISTEMA
                if selected_gender == 'Qualsiasi' or voice['gender'] == selected_gender
            ]
            self.tts_voice_combo.addItems(filtered_voices)
        elif selected_engine == 'gTTS':
            self.tts_voice_combo.addItems([f"{lang_name} ({lang_code})" for lang_code, lang_name in GTTS_LANGUAGES.items()])
        elif selected_engine == 'Piper (WIP)':
            self.tts_voice_combo.addItem("Installare i modelli Piper...")

    def setup_gestures_tab(self):
        """Configura il tab per i gesti e i suoni, inclusa la selezione del modello Vosk."""
        gestures_widget = QWidget()
        layout = QVBoxLayout(gestures_widget)

        layout.addWidget(QLabel("Riconoscimento Vocale"))
        layout.addWidget(QLabel("Seleziona il modello Vosk da utilizzare:"))
        self.language_combo = QComboBox()
        self.language_combo.addItems([
            "vosk-model-small-it-0.22",
            "vosk-model-it-0.22",
            "vosk-model-small-en-us-0.15",
        ])
        layout.addWidget(self.language_combo)

        layout.addWidget(QLabel("Riconoscimento Gesti Mano"))
        layout.addWidget(QLabel("Timeout per la selezione (in ms):"))
        self.timeout_input = QLineEdit("500")
        layout.addWidget(self.timeout_input)

        hand_color_group = QGroupBox("Rilevamento Mani")
        hand_color_layout = QHBoxLayout(hand_color_group)
        self.hand_color_label = QLabel("Colore mano:")
        hand_color_layout.addWidget(self.hand_color_label)
        self.hand_color_picker_btn = QPushButton("Scegli Colore...")
        self.hand_color_picker_btn.clicked.connect(self.choose_hand_color)
        hand_color_layout.addWidget(self.hand_color_picker_btn)
        layout.addWidget(hand_color_group)

        layout.addStretch()
        self.tab_widget.addTab(gestures_widget, "Gesti & Suoni")

    def setup_empathy_tab(self):
        """Configura il tab per le impostazioni di empatia."""
        empathy_widget = QWidget()
        layout = QVBoxLayout(empathy_widget)

        face_recognition_group = QGroupBox("Riconoscimento Facciale (Genitore Empatico)")
        face_layout = QVBoxLayout(face_recognition_group)
        face_layout.addWidget(QLabel("Attiva la funzione d'emergenza \"genitore empatico\":"))
        self.face_recognition_cb = QCheckBox("Abilita")
        face_layout.addWidget(self.face_recognition_cb)

        layout.addWidget(face_recognition_group)
        layout.addStretch()
        self.tab_widget.addTab(empathy_widget, "Genitore Empatico")

    def check_status_of_libraries(self):
        """Verifica se le librerie e i moduli essenziali sono installati e caricabili."""
        status = {}
        # Controlla le librerie di terze parti
        status['ollama'] = self._check_import('requests') and self._check_import('json')
        status['PyQt6'] = self._check_import('PyQt6.QtWidgets')
        status['OpenCV'] = self._check_import('cv2')
        status['SpeechRecognition'] = self._check_import('speech_recognition')
        status['simpleaudio'] = self._check_import('simpleaudio')
        status['pyttsx3'] = self._check_import('pyttsx3')
        status['vosk'] = self._check_import('vosk')
        status['gTTS'] = self._check_import('gtts')

        # Controlla i moduli personalizzati
        status['visual_background'] = self._check_import('visual_background')
        status['ollama_manager'] = self._check_import('ollama_manager')
        status['tts_manager'] = self._check_import('tts_manager')
        status['speech_recognition_manager'] = self._check_import('speech_recognition_manager')
        status['vosk_model_manager'] = self._check_import('vosk_model_manager')

        # Controlla se i modelli Vosk esistono
        for model in ["vosk-model-small-it-0.22", "vosk-model-it-0.22"]:
            model_path = os.path.join("vosk_models", model)
            status[f"vosk_model_{model}"] = os.path.exists(model_path)

        return status

    def _check_import(self, module_name):
        """Funzione helper per controllare se un modulo può essere importato."""
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False

    def setup_library_tab(self):
        """Configura il tab per la gestione delle librerie e dei modelli Vosk."""
        library_widget = QWidget()
        layout = QVBoxLayout(library_widget)
        self.library_table = QTableWidget()
        self.library_table.setColumnCount(3)
        self.library_table.setHorizontalHeaderLabels(["Libreria/Modello", "Stato", "Azione"])
        self.library_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.library_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.library_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        libraries_to_check = {
            "Ollama": "requests",
            "PyQt6": "PyQt6",
            "OpenCV": "cv2",
            "SpeechRecognition": "speech_recognition",
            "simpleaudio": "simpleaudio",
            "pyttsx3": "pyttsx3",
            "vosk": "vosk",
            "gTTS": "gtts",
            "vosk-model-small-it-0.22": "vosk-model-small-it-0.22",
            "vosk-model-it-0.22": "vosk-model-it-0.22"
        }

        library_statuses = self.check_status_of_libraries()

        self.library_table.setRowCount(len(libraries_to_check))
        for row, (name, _) in enumerate(libraries_to_check.items()):
            if name.startswith("vosk-model"):
                is_installed = library_statuses.get(f"vosk_model_{name}", False)
                status_text = "Installato ✅" if is_installed else "Non installato ❌"
                status_color = QColor(0, 150, 0) if is_installed else QColor(200, 0, 0)

                name_item = QTableWidgetItem(f"Modello Vosk: {name}")
                self.library_table.setItem(row, 0, name_item)

                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(status_color)
                self.library_table.setItem(row, 1, status_item)

                action_button = QPushButton("Scarica" if not is_installed else "Elimina")
                action_button.setEnabled(not self.vosk_downloader_thread or not self.vosk_downloader_thread.isRunning())
                action_button.clicked.connect(lambda checked, lib=name: self.handle_vosk_download(lib))
                self.library_table.setCellWidget(row, 2, action_button)
            else:
                is_installed = library_statuses.get(name.lower().replace(' ', '_'), False)
                status_text = "Installata ✅" if is_installed else "Non installata ❌"
                status_color = QColor(0, 150, 0) if is_installed else QColor(200, 0, 0)

                name_item = QTableWidgetItem(name)
                self.library_table.setItem(row, 0, name_item)

                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(status_color)
                self.library_table.setItem(row, 1, status_item)

                action_button = QPushButton("Apri Docs")
                action_button.clicked.connect(
                    lambda checked, lib=name: self.handle_library_action(lib, "Apri Docs")
                )
                self.library_table.setCellWidget(row, 2, action_button)

        layout.addWidget(self.library_table)
        self.download_status_label = QLabel("Stato download: In attesa...")
        layout.addWidget(self.download_status_label)
        layout.addStretch()
        self.tab_widget.addTab(library_widget, "Gestione Librerie")

    def handle_vosk_download(self, model_name):
        """Gestisce il download o l'eliminazione dei modelli Vosk."""
        if os.path.exists(os.path.join("vosk_models", model_name)):
            # Elimina il modello
            reply = QMessageBox.question(self, "Elimina Modello", f"Sei sicuro di voler eliminare il modello Vosk '{model_name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    shutil.rmtree(os.path.join("vosk_models", model_name))
                    QMessageBox.information(self, "Modello Eliminato", f"Il modello '{model_name}' è stato eliminato.")
                    self.setup_library_tab()
                except Exception as e:
                    QMessageBox.critical(self, "Errore", f"Errore durante l'eliminazione del modello: {e}")
            return

        # Avvia il download
        self.vosk_downloader_thread = VoskModelManager(model_name)
        self.vosk_downloader_thread.download_progress.connect(self.update_download_progress)
        self.vosk_downloader_thread.download_finished.connect(self.on_download_finished)
        self.vosk_downloader_thread.download_error.connect(self.on_download_error)
        self.vosk_downloader_thread.start()

        self.download_status_label.setText(f"Download di '{model_name}' in corso...")
        self.set_library_buttons_enabled(False)

    def update_download_progress(self, value):
        """Aggiorna la barra di stato del download."""
        self.download_status_label.setText(f"Download in corso... {value}%")

    def on_download_finished(self, message):
        """Gestisce la fine del download."""
        self.download_status_label.setText(f"Stato download: {message}")
        self.set_library_buttons_enabled(True)
        self.setup_library_tab()

    def on_download_error(self, message):
        """Gestisce un errore durante il download."""
        self.download_status_label.setText(f"Stato download: Errore - {message}")
        QMessageBox.critical(self, "Errore Download", message)
        self.set_library_buttons_enabled(True)
        self.setup_library_tab()

    def set_library_buttons_enabled(self, enabled):
        """Abilita o disabilita i pulsanti nella tabella delle librerie."""
        for row in range(self.library_table.rowCount()):
            widget = self.library_table.cellWidget(row, 2)
            if widget:
                widget.setEnabled(enabled)

    def setup_data_tab(self):
        """Configura il tab per la gestione dei dati."""
        data_widget = QWidget()
        layout = QVBoxLayout(data_widget)

        data_group = QGroupBox("Gestione Dati e Log")
        data_layout = QVBoxLayout(data_group)

        self.download_logs_btn = QPushButton("Scarica i log emozioni")
        self.download_logs_btn.clicked.connect(self.download_logs)
        data_layout.addWidget(self.download_logs_btn)

        data_layout.addStretch()
        layout.addWidget(data_group)
        layout.addStretch()

        self.tab_widget.addTab(data_widget, "Gestione Dati")

    def update_ollama_models(self, model_names):
        """Aggiorna il QComboBox con i modelli Ollama disponibili."""
        self.ollama_model_combo.clear()
        if model_names:
            self.ollama_model_combo.addItems(model_names)
            self.ollama_status_label.setText("Stato: Connesso")
            self.ollama_status_label.setStyleSheet("color: #4CAF50;")
        else:
            self.ollama_model_combo.addItem("Nessun modello trovato.")
            self.ollama_status_label.setText("Stato: Nessun modello trovato.")
            self.ollama_status_label.setStyleSheet("color: orange;")

    def on_ollama_models_error(self, message):
        """Gestisce gli errori durante il recupero dei modelli Ollama."""
        self.ollama_model_combo.clear()
        self.ollama_model_combo.addItem("Errore di caricamento")
        self.ollama_status_label.setText(f"Stato: {message}")
        self.ollama_status_label.setStyleSheet("color: red;")
        QMessageBox.warning(self, "Errore Ollama", message)

    def load_settings(self):
        """Carica le impostazioni attuali dal file settings.json."""
        if os.path.exists("settings.json"):
            try:
                with open("settings.json", "r") as f:
                    self.settings = json.load(f)
                self.update_ui_from_settings()
            except Exception as e:
                logging.error(f"Errore nel caricare le impostazioni: {e}")
                self.settings = {}

    def update_ui_from_settings(self):
        """Aggiorna i widget del dialogo con le impostazioni caricate."""
        self.ollama_model_combo.setCurrentText(self.settings.get('ollama_model', 'llava:7b'))
        self.tts_engine_combo.setCurrentText(self.settings.get('tts_engine', 'pyttsx3'))
        self.tts_gender_combo.setCurrentText(self.settings.get('tts_gender', 'Qualsiasi'))
        self.update_voice_combo() # Aggiorna le voci/lingue in base al motore e al sesso
        self.tts_voice_combo.setCurrentText(self.settings.get('tts_voice_or_lang', 'Zephyr (Fallback)'))
        self.face_recognition_cb.setChecked(self.settings.get('face_recognition', False))
        self.timeout_input.setText(str(self.settings.get('timeout', 500)))

        # Aggiorna il modello Vosk
        vosk_model = self.settings.get('vosk_model', 'vosk-model-small-it-0.22')
        self.language_combo.setCurrentText(vosk_model)

        self.add_btn_color.setStyleSheet(f"background-color: {self.settings.get('add_btn_color', '#4a90e2')};")
        self.ai_btn_color.setStyleSheet(f"background-color: {self.settings.get('ai_btn_color', '#4a90e2')};")
        self.hands_btn_color.setStyleSheet(f"background-color: {self.settings.get('hands_btn_color', '#4a90e2')};")
        self.face_btn_color.setStyleSheet(f"background-color: {self.settings.get('face_btn_color', '#4a90e2')};")
        self.clean_btn_color.setStyleSheet(f"background-color: {self.settings.get('clean_btn_color', '#4a90e2')};")
        self.options_btn_color.setStyleSheet(f"background-color: {self.settings.get('options_btn_color', '#4a90e2')};")
        self.log_btn_color.setStyleSheet(f"background-color: {self.settings.get('log_btn_color', '#4a90e2')};")
        self.voice_btn_color.setStyleSheet(f"background-color: {self.settings.get('voice_btn_color', '#4a90e2')};")

    def _get_button_color(self, button, default_color):
        """
        Estrae il colore di sfondo da un QPushButton in modo sicuro.
        Se non trova il colore, restituisce il valore di default.
        """
        style_sheet = button.styleSheet()
        match = re.search(r'background-color: (.+?);', style_sheet)
        if match:
            return match.group(1).strip()
        return default_color

    def get_settings(self):
        """Restituisce le impostazioni correnti dai widget in modo robusto."""
        settings = {
            'ollama_model': self.ollama_model_combo.currentText(),
            'tts_engine': self.tts_engine_combo.currentText(),
            'tts_voice_or_lang': self.tts_voice_combo.currentText(),
            'tts_gender': self.tts_gender_combo.currentText(), # Nuova impostazione
            'tts_speed': self.speed_slider.value() / 100.0,
            'tts_pitch': self.pitch_slider.value() / 100.0,
            'face_recognition': self.face_recognition_cb.isChecked(),
            'timeout': int(self.timeout_input.text()),
            'vosk_model': self.language_combo.currentText(),
            'add_btn_color': self._get_button_color(self.add_btn_color, '#4a90e2'),
            'ai_btn_color': self._get_button_color(self.ai_btn_color, '#4a90e2'),
            'hands_btn_color': self._get_button_color(self.hands_btn_color, '#4a90e2'),
            'face_btn_color': self._get_button_color(self.face_btn_color, '#4a90e2'),
            'clean_btn_color': self._get_button_color(self.clean_btn_color, '#4a90e2'),
            'options_btn_color': self._get_button_color(self.options_btn_color, '#4a90e2'),
            'log_btn_color': self._get_button_color(self.log_btn_color, '#4a90e2'),
            'voice_btn_color': self._get_button_color(self.voice_btn_color, '#4a90e2'),
        }
        return settings

    def apply_changes(self):
        """Applica le modifiche del dialogo e le salva nel file."""
        self.settings = self.get_settings()
        try:
            with open("settings.json", "w") as f:
                json.dump(self.settings, f, indent=4)
            QMessageBox.information(
                self,
                "Impostazioni Applicate",
                "Le modifiche sono state applicate con successo."
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Errore di salvataggio",
                f"Si è verificato un errore durante il salvataggio delle impostazioni:\n{e}"
            )
        self.parent().apply_settings(self.settings)
        self.accept()

    def test_tts(self):
        """
        Avvia la sintesi vocale per il testo di prova.
        Se un test è già in corso, ferma il thread precedente.
        """
        if self.tts_test_thread and self.tts_test_thread.isRunning():
            self.tts_test_thread.stop()
            self.tts_test_thread.wait()
            self.tts_test_thread = None
            logging.info("Test precedente interrotto.")

        text = self.tts_test_text.toPlainText()
        if not text:
            QMessageBox.warning(self, "Attenzione", "Inserisci del testo per la prova.")
            return

        engine = self.tts_engine_combo.currentText()
        voice_name_from_combo = self.tts_voice_combo.currentText()

        voice_or_lang = ''
        if engine == 'pyttsx3':
            # Cerca l'ID della voce basandosi sul nome selezionato
            selected_voice_info = next(
                (voice for voice in VOCI_DI_SISTEMA if voice['name'] == voice_name_from_combo),
                None
            )
            voice_or_lang = selected_voice_info['id'] if selected_voice_info else 'fallback'
        elif engine == 'gTTS':
            lang_code_match = re.search(r'\(([^)]+)\)', voice_name_from_combo)
            voice_or_lang = lang_code_match.group(1) if lang_code_match else 'it'

        speed = self.speed_slider.value() / 100.0
        pitch = self.pitch_slider.value() / 100.0

        self.test_tts_button.setText("In riproduzione...")
        self.test_tts_button.setEnabled(False)

        # La logica del thread è ora unificata, ma gestisce motori diversi
        self.tts_test_thread = TTSThread(text, engine, voice_or_lang, speed, pitch)
        self.tts_test_thread.finished_reading.connect(self.on_tts_test_finished)
        self.tts_test_thread.error_occurred.connect(self.on_tts_test_error)
        self.tts_test_thread.start()

    def on_tts_test_finished(self):
        """Gestisce il termine della riproduzione di prova."""
        self.test_tts_button.setText("Prova Sintesi Vocale 🔊")
        self.test_tts_button.setEnabled(True)
        # Rilascia il riferimento al thread per permetterne la distruzione
        if self.tts_test_thread:
            self.tts_test_thread = None

    def on_tts_test_error(self, message):
        """Gestisce un errore nella riproduzione di prova."""
        QMessageBox.critical(self, "Errore TTS", message)
        self.on_tts_test_finished()

    def test_ollama_connection(self):
        """Testa la connessione a Ollama."""
        QMessageBox.information(
            self,
            "Test Connessione Ollama",
            "Funzionalità di test da implementare."
        )

    def download_logs(self):
        """Scarica i log su un file di testo."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Scarica Log",
            os.path.join(os.getcwd(), "saved_data", "log_emozioni.txt"),
            "File di testo (*.txt);;Tutti i file (*)"
        )

        if file_path:
            try:
                # Per ora, non abbiamo un log persistente, quindi salviamo un placeholder.
                # In una versione più avanzata, leggeremmo da un file di log effettivo.
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("Log temporaneo salvato. Implementare un sistema di log persistente per una funzionalità completa.")
                QMessageBox.information(
                    self,
                    "Salvataggio Log",
                    f"I log sono stati salvati correttamente in:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Errore di salvataggio",
                    f"Si è verificato un errore durante il salvataggio dei log:\n{e}"
                )

    def open_color_dialog(self, button):
        """Apre un selettore di colori per i pulsanti."""
        color = QColorDialog.getColor()
        if color.isValid():
            button.setStyleSheet(f"background-color: {color.name()};")

    def choose_hand_color(self):
        """Sceglie il colore della mano per il rilevamento."""
        QMessageBox.information(
            self,
            "Selettore Colore Mano",
            "Funzionalità da implementare per la calibrazione del colore."
        )

    def handle_library_action(self, library, action):
        """Gestisce le azioni per le librerie."""
        QMessageBox.information(
            self,
            f"Azione Libreria",
            f"Azione '{action}' richiesta per la libreria '{library}'."
        )

# ==============================================================================
# Classe Principale dell'Applicazione
# ==============================================================================

class MainWindow(QMainWindow):
    """
    La classe principale dell'applicazione, che gestisce l'interfaccia utente.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Assistente per Dislessia")
        self.setGeometry(100, 100, 1400, 800)
        self.settings = {}
        self.ollama_thread = None
        self.speech_rec_thread = None
        self.is_listening = False

        # Configurazione logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        # Creazione della directory per il salvataggio dei file, se non esiste
        for d in ["saved_data", "vosk_models"]:
            if not os.path.exists(d):
                os.makedirs(d)

        # Carica le impostazioni all'avvio
        self.load_settings()

        # Applica il tema al caricamento (un solo tema ora)
        self.setStyleSheet(self.load_theme())

        # Widget per lo sfondo video
        self.video_background_label = QLabel(self)
        self.video_background_label.setGeometry(self.rect())
        self.video_background_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_background_label.setStyleSheet("background-color: black;")
        self.video_background_label.setText("Caricamento video...")
        self.video_background_label.setFont(QFont('Arial', 18))
        self.video_background_label.setStyleSheet("color: white; background-color: black;")

        self.central_widget = QWidget(self)
        self.central_widget.setStyleSheet("background-color: rgba(0, 0, 0, 0);")
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)

        # Sezione in alto: Opzioni e Salva su file
        self.top_buttons_layout = QHBoxLayout()
        self.btn_options = QPushButton("⚙️ Opzioni")
        self.top_buttons_layout.addWidget(self.btn_options)
        self.top_buttons_layout.addStretch(1)
        self.btn_save_file = QPushButton("💾 Salva su file")
        self.top_buttons_layout.addWidget(self.btn_save_file)
        self.main_layout.addLayout(self.top_buttons_layout)

        # Sezione centrale: Le 3 colonne
        self.center_layout = QHBoxLayout()

        # Colonna A: Contenuti pensieri creativi (era Pensierini)
        self.pensierini_frame = QFrame()
        self.pensierini_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.pensierini_frame.setFrameShadow(QFrame.Shadow.Raised)
        self.pensierini_frame.setStyleSheet("background-color: rgba(255, 255, 255, 0.5); border-radius: 15px;")
        self.pensierini_layout = QVBoxLayout(self.pensierini_frame)
        pensierini_label = QLabel("📝 Contenuti pensieri creativi (A)")
        pensierini_label.setStyleSheet("font-weight: bold; font-size: 16px; color: black; background: transparent;")
        self.draggable_widgets_scroll = QScrollArea()
        self.draggable_widgets_scroll.setWidgetResizable(True)
        self.draggable_widgets_content = QWidget()
        self.draggable_widgets_layout = QVBoxLayout(self.draggable_widgets_content)
        self.draggable_widgets_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.draggable_widgets_scroll.setWidget(self.draggable_widgets_content)
        self.pensierini_layout.addWidget(pensierini_label)
        self.pensierini_layout.addWidget(self.draggable_widgets_scroll)
        self.center_layout.addWidget(self.pensierini_frame, 1)

        # Colonna B: Area di Lavoro (centrale)
        self.work_area_main_frame = QFrame()
        self.work_area_main_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.work_area_main_frame.setFrameShadow(QFrame.Shadow.Raised)
        self.work_area_main_frame.setStyleSheet("background-color: rgba(255, 255, 255, 0.7); border-radius: 15px;")
        self.work_area_main_layout = QVBoxLayout(self.work_area_main_frame)
        work_area_main_label = QLabel("🎯 Area di Lavoro (B)")
        work_area_main_label.setStyleSheet("font-weight: bold; font-size: 16px; color: black; background: transparent;")
        self.work_area_main_text_edit = QTextEdit()
        self.work_area_main_text_edit.setPlaceholderText("Trascina qui i 'pensierini' per elaborare il testo...")
        self.work_area_main_text_edit.setStyleSheet("background-color: transparent; border: none;")
        self.work_area_main_text_edit.setAcceptDrops(True)
        self.work_area_main_text_edit.dragEnterEvent = self.dragEnterEvent
        self.work_area_main_text_edit.dropEvent = self.dropEvent
        self.work_area_main_layout.addWidget(work_area_main_label)
        self.work_area_main_layout.addWidget(self.work_area_main_text_edit)
        self.center_layout.addWidget(self.work_area_main_frame, 2)

        # Colonna C: Dettagli (era Colonna 1)
        self.work_area_left_frame = QFrame()
        self.work_area_left_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.work_area_left_frame.setFrameShadow(QFrame.Shadow.Raised)
        self.work_area_left_frame.setStyleSheet("background-color: rgba(255, 255, 255, 0.7); border-radius: 15px;")
        self.work_area_left_layout = QVBoxLayout(self.work_area_left_frame)
        work_area_left_label = QLabel("📋 Dettagli (C)")
        work_area_left_label.setStyleSheet("font-weight: bold; font-size: 16px; color: black; background: transparent;")
        self.work_area_left_text_edit = QTextEdit()
        self.work_area_left_text_edit.setPlaceholderText("Inizia a scrivere o a registrare qui...")
        self.work_area_left_text_edit.setStyleSheet("background-color: transparent; border: none;")
        self.work_area_left_layout.addWidget(work_area_left_label)
        self.work_area_left_layout.addWidget(self.work_area_left_text_edit)
        self.center_layout.addWidget(self.work_area_left_frame, 1)

        self.main_layout.addLayout(self.center_layout, 1)

        # Sezione in basso: Pulsanti di controllo e log
        self.bottom_container_layout = QVBoxLayout()

        # Layout per i pulsanti di controllo
        self.bottom_buttons_layout = QHBoxLayout()
        self.btn_add_widget = QPushButton("Inserisci testo")
        self.btn_voice = QPushButton("🎤 Voce") # New voice button
        self.btn_ai = QPushButton("🧠 AI")
        self.btn_hands = QPushButton("✋ Mani ❌")
        self.btn_face = QPushButton("😊 Faccia ❌")
        self.btn_clean = QPushButton("🧹 Pulisci")

        self.bottom_buttons_layout.addWidget(self.btn_add_widget)
        self.bottom_buttons_layout.addWidget(self.btn_voice) # Add new button here
        self.bottom_buttons_layout.addWidget(self.btn_ai)
        self.bottom_buttons_layout.addWidget(self.btn_hands)
        self.bottom_buttons_layout.addWidget(self.btn_face)
        self.bottom_buttons_layout.addWidget(self.btn_clean)
        self.bottom_buttons_layout.addStretch(1)

        self.bottom_container_layout.addLayout(self.bottom_buttons_layout)

        # Layout per l'input di testo e il log terminale
        self.input_log_layout = QHBoxLayout()

        # Input per i "pensierini"
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Scrivi un nuovo 'pensierino' e premi Invio...")
        self.input_field.returnPressed.connect(self.add_text_to_pensierini_from_input)
        self.input_log_layout.addWidget(self.input_field, 1)

        # Pulsante per il log
        self.log_button_layout = QVBoxLayout()
        self.btn_log = QPushButton("📊 Mostra Log")
        self.btn_log.setCheckable(True)
        self.btn_log.setEnabled(True) # Always enabled now
        self.btn_log.clicked.connect(self.toggle_log_visibility)
        self.log_button_layout.addWidget(self.btn_log)
        self.input_log_layout.addLayout(self.log_button_layout)

        self.bottom_container_layout.addLayout(self.input_log_layout)

        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setStyleSheet("background-color: #2e2e2e; color: #ffffff; font-family: monospace;")
        self.log_text_edit.setMinimumHeight(150)
        self.log_text_edit.hide() # Nascosto di default
        self.bottom_container_layout.addWidget(self.log_text_edit)

        self.main_layout.addLayout(self.bottom_container_layout)

        self.log_emitter = LogEmitter()
        self.log_emitter.new_record.connect(self.log_text_edit.append)
        self.log_emitter.error_occurred.connect(self.on_log_error)
        self.handler = TextEditLogger(self.log_emitter)
        logging.getLogger().addHandler(self.handler)

        # Connessione dei segnali
        self.btn_options.clicked.connect(self.open_settings)
        self.btn_ai.clicked.connect(self.handle_ai_button)
        self.btn_voice.clicked.connect(self.handle_voice_button)
        self.btn_hands.clicked.connect(self.handle_hands_button)
        self.btn_face.clicked.connect(self.handle_face_button)
        self.btn_clean.clicked.connect(self.handle_clean_button)
        self.btn_save_file.clicked.connect(self.save_to_file)
        self.btn_add_widget.clicked.connect(self.add_text_to_pensierini_from_input)

        # Implementazione dei tasti rapidi
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self.save_to_file)

        self.shortcut_open = QShortcut(QKeySequence("Ctrl+O"), self)
        self.shortcut_open.activated.connect(self.open_file)

        self.shortcut_log = QShortcut(QKeySequence(Qt.Key.Key_F12), self)
        self.shortcut_log.activated.connect(self.toggle_log_visibility)

        # Thread per il video
        self.video_thread = VideoThread()
        self.video_thread.change_pixmap_signal.connect(self.update_video_frame)
        self.video_thread.status_signal.connect(self.update_video_status)
        self.video_thread.start()

        # Applica le impostazioni iniziali ai thread
        self.apply_settings(self.settings)

    def resizeEvent(self, event):
        """Re-implementa resizeEvent per ridimensionare lo sfondo video."""
        self.video_background_label.setGeometry(self.rect())
        super().resizeEvent(event)

    def dragEnterEvent(self, event):
        """Permette il drop se i dati sono di tipo testo."""
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Gestisce il drop del testo nell'area di lavoro principale."""
        if event.mimeData().hasText():
            text_to_append = event.mimeData().text()
            current_text = self.work_area_main_text_edit.toPlainText()
            self.work_area_main_text_edit.setText(current_text + "\n" + text_to_append)
            event.acceptProposedAction()

    def load_settings(self):
        """Carica le impostazioni all'avvio dell'applicazione."""
        if os.path.exists("settings.json"):
            try:
                with open("settings.json", "r") as f:
                    self.settings = json.load(f)
            except Exception as e:
                logging.error(f"Errore nel caricare le impostazioni: {e}")
                self.settings = {}
        else:
            self.settings = {}

    def apply_settings(self, settings):
        """Applica le impostazioni caricate ai thread e all'UI."""
        self.settings = settings

        # Applica impostazioni al video thread
        self.video_thread.face_detection_enabled = self.settings.get('face_recognition', False)
        self.video_thread.hand_detection_enabled = self.settings.get('hand_recognition', False)

        # Applica impostazioni ai pulsanti
        self.btn_add_widget.setStyleSheet(f"background-color: {self.settings.get('add_btn_color', '#4a90e2')}; color: white;")
        self.btn_ai.setStyleSheet(f"background-color: {self.settings.get('ai_btn_color', '#4a90e2')}; color: white;")
        self.btn_voice.setStyleSheet(f"background-color: {self.settings.get('voice_btn_color', '#4a90e2')}; color: white;")
        self.btn_hands.setStyleSheet(f"background-color: {self.settings.get('hands_btn_color', '#4a90e2')}; color: white;")
        self.btn_face.setStyleSheet(f"background-color: {self.settings.get('face_btn_color', '#4a90e2')}; color: white;")
        self.btn_clean.setStyleSheet(f"background-color: {self.settings.get('clean_btn_color', '#4a90e2')}; color: white;")
        self.btn_options.setStyleSheet(f"background-color: {self.settings.get('options_btn_color', '#4a90e2')}; color: white;")
        self.btn_log.setStyleSheet(f"background-color: {self.settings.get('log_btn_color', '#4a90e2')}; color: white;")

        # Aggiorna lo stato visivo dei pulsanti di toggle
        self.update_button_state(self.btn_hands, self.video_thread.hand_detection_enabled, "Mani")
        self.update_button_state(self.btn_face, self.video_thread.face_detection_enabled, "Faccia")

        logging.info("Impostazioni aggiornate e applicate.")

    def load_theme(self):
        """Carica un tema CSS da un file (un solo tema ora)."""
        return """
            QMainWindow {
                background-color: #f0f0f0;
            }
            QPushButton {
                border-radius: 10px;
                padding: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a9df7;
            }
            QPushButton[checkable=true][checked=false] {
                background-color: #95a5a6;
            }
            QTextEdit, QLineEdit {
                border-radius: 15px;
                padding: 10px;
                background-color: white;
                font-size: 14px;
            }
            QFrame {
                border: none;
            }
        """

    def update_button_state(self, button, is_enabled, name):
        """Aggiorna lo stato visivo di un pulsante di toggle."""
        icon_status = "✅" if is_enabled else "❌"
        button.setText(f"{name} {icon_status}")
        if is_enabled:
            button.setStyleSheet("background-color: #4CAF50; color: white;")
        else:
            color_name = f'{name.lower().split()[0]}_btn_color'
            button.setStyleSheet(f"background-color: {self.settings.get(color_name, '#4a90e2')}; color: white;")


    def open_settings(self):
        """Apre il dialogo di configurazione."""
        dialog = ConfigurationDialog(self, settings=self.settings)
        dialog.exec()

    def on_log_error(self):
        """Gestisce un errore di logging per mostrare il log terminale."""
        if not self.log_text_edit.isVisible():
            self.toggle_log_visibility()

    def add_text_to_pensierini_from_input(self):
        """
        Aggiunge un nuovo "pensierino" all'area usando il testo dal campo di input.
        """
        text = self.input_field.text().strip()
        if text:
            new_widget = DraggableTextWidget(text, self.settings)
            self.draggable_widgets_layout.addWidget(new_widget)
            self.input_field.clear()

    def add_text_to_pensierini(self, text):
        """
        Aggiunge il testo alla colonna dei pensierini.
        """
        if text:
            new_widget = DraggableTextWidget(text, self.settings)
            self.draggable_widgets_layout.addWidget(new_widget)
            self.input_field.clear()

    def update_video_frame(self, image):
        """Aggiorna il frame del video con l'immagine passata."""
        if image is None:
            self.video_background_label.setText("Errore: Impossibile acquisire il frame video.")
            return

        pixmap = QPixmap.fromImage(image)
        scaled_pixmap = pixmap.scaled(
            self.video_background_label.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
        )
        self.video_background_label.setPixmap(scaled_pixmap)

        # Nascondi il testo di caricamento una volta che i frame iniziano ad arrivare
        if self.video_background_label.text().startswith("Caricamento"):
            self.video_background_label.setText("")

    def update_video_status(self, message):
        """Aggiorna lo stato del video."""
        self.video_background_label.setText(message)

    def save_to_file(self):
        """
        Salva il contenuto dell'area di lavoro (B) e dei "pensierini" (A)
        in un file .txt dopo aver chiesto all'utente il percorso.
        """
        # Contenuto della Colonna B (Area di Lavoro)
        main_text = self.work_area_main_text_edit.toPlainText()

        # Contenuto della Colonna A (Contenuti pensieri creativi)
        pensierini_texts = [
            self.draggable_widgets_layout.itemAt(i).widget().text_label.text()
            for i in range(self.draggable_widgets_layout.count())
        ]
        pensierini_text_combined = "\n".join(pensierini_texts)

        combined_text = (
            "Contenuti pensieri creativi (A):\n"
            "------------------------------------\n"
            f"{pensierini_text_combined}\n\n"
            "Area di Lavoro (B):\n"
            "------------------------------------\n"
            f"{main_text}"
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva i contenuti",
            os.path.join(os.getcwd(), "saved_data", "contenuti_salvati.txt"),
            "File di testo (*.txt);;Tutti i file (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(combined_text)

                QMessageBox.information(
                    self,
                    "Salvataggio completato",
                    f"I contenuti sono stati salvati correttamente in:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Errore di salvataggio",
                    f"Si è verificato un errore durante il salvataggio del file:\n{e}"
                )

    def open_file(self):
        """Apre un file di testo e carica il suo contenuto nell'area di lavoro principale."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Apri un file",
            os.getcwd(),
            "File di testo (*.txt);;Tutti i file (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.work_area_main_text_edit.clear()
                    self.work_area_main_text_edit.setText(content)
                QMessageBox.information(
                    self,
                    "File Aperto",
                    f"Contenuto del file caricato nell'area di lavoro."
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Errore di apertura",
                    f"Si è verificato un errore durante l'apertura del file:\n{e}"
                )

    def toggle_log_visibility(self):
        """Mostra o nasconde il log terminale."""
        is_visible = self.log_text_edit.isVisible()
        self.log_text_edit.setVisible(not is_visible)
        self.btn_log.setText("📊 Nascondi Log" if not is_visible else "📊 Mostra Log")

    def handle_ai_button(self):
        """
        Gestisce il click del pulsante AI. Prende il testo dal campo di input in basso,
        lo invia a Ollama e gestisce la risposta.
        """
        prompt = self.input_field.text().strip()
        if not prompt:
            QMessageBox.warning(self, "Attenzione", "Il campo di input è vuoto. Inserisci del testo prima di usare l'AI.")
            return

        self.btn_ai.setEnabled(False)
        original_text = self.btn_ai.text()
        self.btn_ai.setText("🧠 AI (In Caricamento...)")

        selected_model = self.settings.get('ollama_model', 'llava:7b')
        self.ollama_thread = OllamaThread(prompt, model=selected_model)
        self.ollama_thread.ollama_response.connect(self.on_ollama_response)
        self.ollama_thread.ollama_error.connect(self.on_ollama_error)
        self.ollama_thread.finished.connect(lambda: self.on_ollama_finished(original_text))
        self.ollama_thread.start()

    def on_ollama_response(self, response):
        """Gestisce la risposta di Ollama."""
        # Aggiunge un "pensierino" con la risposta completa
        new_widget = DraggableTextWidget(response, self.settings)
        self.draggable_widgets_layout.addWidget(new_widget)

        # Aggiunge la risposta completa all'area di lavoro principale
        self.work_area_main_text_edit.append(f"\n\n--- Risposta AI da {self.settings.get('ollama_model', 'N/D')} ---\n")
        self.work_area_main_text_edit.append(response)

        # Pulisce il campo di input in basso dopo l'invio
        self.input_field.clear()

    def on_ollama_error(self, message):
        """Gestisce gli errori della richiesta a Ollama."""
        QMessageBox.critical(self, "Errore AI", message)
        logging.error(f"Errore Ollama: {message}")

    def on_ollama_finished(self, original_text):
        """Riabilita il pulsante e ripristina il testo originale quando il thread finisce."""
        self.btn_ai.setEnabled(True)
        self.btn_ai.setText(original_text)

    def handle_voice_button(self):
        """Avvia o ferma il riconoscimento vocale."""
        if self.is_listening:
            # Se il riconoscimento è in corso, lo ferma
            self.is_listening = False
            if self.speech_rec_thread and self.speech_rec_thread.isRunning():
                self.speech_rec_thread.stop()
            self.btn_voice.setText("🎤 Voce")
            self.btn_voice.setStyleSheet(f"background-color: {self.settings.get('voice_btn_color', '#4a90e2')}; color: white;")
        else:
            # Se il riconoscimento è fermo, lo avvia
            self.is_listening = True
            self.btn_voice.setEnabled(False) # Disabilita il pulsante durante il caricamento
            self.btn_voice.setText("🎤 Avvio in corso...")
            self.btn_voice.setStyleSheet("background-color: #e74c3c; color: white;")

            vosk_model_name = self.settings.get('vosk_model', 'vosk-model-small-it-0.22')
            self.speech_rec_thread = SpeechRecognitionThread(vosk_model_name)

            # Connette i segnali prima di avviare il thread
            self.speech_rec_thread.model_status.connect(self.update_speech_rec_status)
            self.speech_rec_thread.recognized_text.connect(self.on_voice_recognized)
            self.speech_rec_thread.recognition_error.connect(self.on_voice_error)
            self.speech_rec_thread.finished.connect(self.on_speech_rec_finished)
            self.speech_rec_thread.start()

    def update_speech_rec_status(self, message):
        """Aggiorna il testo del pulsante voce con lo stato del riconoscimento."""
        self.btn_voice.setText(f"🎤 {message}")
        if "Errore" in message or "terminato" in message:
            self.on_speech_rec_finished()

    def on_voice_recognized(self, text):
        """Riceve il testo riconosciuto e lo inserisce nella colonna A."""
        self.add_text_to_pensierini(text)

    def on_voice_error(self, message):
        """Mostra un messaggio di errore in caso di fallimento del riconoscimento vocale."""
        QMessageBox.warning(self, "Riconoscimento Vocale", message)
        self.on_speech_rec_finished()

    def on_speech_rec_finished(self):
        """Riabilita il pulsante voce quando il thread termina."""
        self.is_listening = False
        self.btn_voice.setEnabled(True)
        self.btn_voice.setText("🎤 Voce")
        self.btn_voice.setStyleSheet(f"background-color: {self.settings.get('voice_btn_color', '#4a90e2')}; color: white;")
        if self.speech_rec_thread:
            self.speech_rec_thread.stop()
            self.speech_rec_thread = None

    def handle_hands_button(self):
        """Gestisce il click del pulsante Rilevamento Mani."""
        self.video_thread.hand_detection_enabled = not self.video_thread.hand_detection_enabled
        self.update_button_state(self.btn_hands, self.video_thread.hand_detection_enabled, "Mani")

    def handle_face_button(self):
        """Gestisce il click del pulsante Rilevamento Faccia."""
        self.video_thread.face_detection_enabled = not self.video_thread.face_detection_enabled
        self.update_button_state(self.btn_face, self.video_thread.face_detection_enabled, "Faccia")

    def handle_clean_button(self):
        """Pulisce il campo di input in basso e l'area di dettaglio (C)."""
        self.work_area_left_text_edit.clear()
        self.input_field.clear()
        QMessageBox.information(self, "Pulisci", "L'area di input e la colonna 'Dettagli' sono state pulite.")

    def closeEvent(self, event):
        """Gestisce la chiusura dell'applicazione."""
        logging.getLogger().removeHandler(self.handler)
        self.video_thread.stop()
        if self.speech_rec_thread and self.speech_rec_thread.isRunning():
            self.speech_rec_thread.stop()
        event.accept()

# ==============================================================================
# Funzione Principale per l'Esecuzione
# ==============================================================================
def main():
    """Funzione principale per avviare l'applicazione."""
    app = QApplication(sys.argv)
    app.setApplicationName("Assistente per Dislessia")
    app.setOrganizationName("DSA Helper")

    try:
        app.setWindowIcon(QIcon("icon.png"))
    except Exception as e:
        logging.warning(f"Impossibile caricare 'icon.png': {e}")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
