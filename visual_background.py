# visual_background.py

import cv2
import numpy as np
import logging
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

# ==============================================================================
# Inizializzazione e Configurazione per il Rilevamento Visivo
# ==============================================================================

# Inizializzazione del classificatore a cascata di Haar per il rilevamento del volto.
# Il codice per il rilevamento del volto è stato spostato in questo file per
# incapsulare la logica visiva e renderla un modulo separato.
face_cascade = None
try:
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    logging.info("Classificatore viso caricato correttamente")
except Exception as e:
    logging.error(f"Errore nel caricare il classificatore di cascata: {e}")

class VideoThread(QThread):
    """
    Thread dedicato per la cattura video dalla webcam e rilevamento.
    Si occupa di acquisire i frame, applicare il rilevamento di volti e mani
    e inviare i frame elaborati all'interfaccia utente (UI).
    """
    # Segnale per inviare l'immagine elaborata all'UI
    change_pixmap_signal = pyqtSignal(QImage)
    # Segnale per inviare messaggi di stato all'UI
    status_signal = pyqtSignal(str)

    def __init__(self, face_detection_enabled=False, hand_detection_enabled=False, hand_color_range=None):
        """
        Inizializza il thread con le impostazioni per il rilevamento.
        :param face_detection_enabled: Booleano per abilitare/disabilitare il rilevamento del volto.
        :param hand_detection_enabled: Booleano per abilitare/disabilitare il rilevamento della mano.
        :param hand_color_range: Tupla contenente i valori HSV minimo e massimo per il colore della mano.
        """
        super().__init__()
        self._run_flag = True
        self.face_detection_enabled = face_detection_enabled
        self.hand_detection_enabled = hand_detection_enabled
        # Impostazione predefinita per il rilevamento del colore della mano
        self.hand_color_range = hand_color_range if hand_color_range else (np.array([0, 100, 100]), np.array([10, 255, 255]))
        self.cap = None

    def run(self):
        """
        Ciclo principale del thread. Cattura il video dalla webcam,
        applica i rilevamenti e invia i frame all'interfaccia.
        """
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.status_signal.emit("❌ Webcam non disponibile")
            self._run_flag = False
            return

        while self._run_flag:
            ret, frame = self.cap.read()
            if ret:
                # Capovolge il frame orizzontalmente per un effetto "specchio"
                frame = cv2.flip(frame, 1)

                # Rilevamento del volto
                if self.face_detection_enabled and face_cascade is not None:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                    for (x, y, w, h) in faces:
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (46, 140, 219), 2)

                # Rilevamento della mano basato sul colore (da implementare)
                if self.hand_detection_enabled:
                    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                    mask = cv2.inRange(hsv, self.hand_color_range[0], self.hand_color_range[1])
                    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                    if contours:
                        max_contour = max(contours, key=cv2.contourArea)
                        if cv2.contourArea(max_contour) > 5000:
                            (x, y, w, h) = cv2.boundingRect(max_contour)
                            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                            cv2.putText(frame, "Mano rilevata", (x, y - 10),
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

                # Conversione del frame per l'utilizzo in PyQt6
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                q_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                self.change_pixmap_signal.emit(q_image)

        # Rilascio della webcam quando il thread si ferma
        if self.cap:
            self.cap.release()

    def stop(self):
        """
        Metodo per fermare il thread in modo sicuro.
        Imposta il flag di esecuzione su False e attende la terminazione del thread.
        """
        self._run_flag = False
        self.wait()
