# visual_background.py

import cv2
import logging
from PyQt6.QtCore import QThread, pyqtSignal, QSize, Qt
from PyQt6.QtGui import QImage, QPixmap

class VideoThread(QThread):
    """
    Thread per la cattura e l'elaborazione del flusso video dalla webcam.
    """
    change_pixmap_signal = pyqtSignal(QImage)
    status_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._run_flag = True
        self.face_detection_enabled = False
        self.hand_detection_enabled = False

    def run(self):
        """Metodo principale del thread."""
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.status_signal.emit("Errore: Impossibile aprire la webcam.")
            self._run_flag = False
            return

        self.status_signal.emit("Webcam avviata. Caricamento...")

        while self._run_flag:
            ret, frame = self.cap.read()
            if ret:
                # ==========================================================
                # Modifica qui per invertire orizzontalmente l'immagine
                # Il valore 1 indica l'inversione orizzontale.
                # ==========================================================
                frame = cv2.flip(frame, 1)

                # ==========================================================
                # Logica di rilevamento (face/hand) va qui...
                # Per ora, la lasciamo vuota.
                # ==========================================================

                # Converti il frame in QImage e invialo al segnale
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                self.change_pixmap_signal.emit(qt_image)
            else:
                self.status_signal.emit("Errore di lettura del frame dalla webcam.")
                break

        # Rilascia la webcam quando il thread si ferma
        self.cap.release()
        logging.info("VideoThread terminato e webcam rilasciata.")

    def stop(self):
        """Termina il thread in modo sicuro."""
        self._run_flag = False
        self.wait()
