import cv2
import numpy as np

from PyQt6.QtCore import QObject, pyqtSignal

class OpenCVRecognizer(QObject):
    # Segnali per comunicare con l'interfaccia principale
    hand_position_signal = pyqtSignal(tuple) # Posizione della mano
    hand_gesture_signal = pyqtSignal(str) # Gesto rilevato
    face_emotion_signal = pyqtSignal(str) # Emozione rilevata

    def __init__(self):
        super().__init__()
        # Carica il classificatore per il rilevamento del volto
        # Qui si usa il modello Haar Cascade di OpenCV, un metodo classico
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        # Carica il modello per il riconoscimento delle emozioni
        # Se usi un modello Keras/TensorFlow, caricalo qui
        self.emotion_model = self.load_emotion_model()

    def load_emotion_model(self):
        # Implementa qui la logica per caricare il tuo modello di emozioni
        # Ad esempio, un modello .h5 o un classificatore SVM
        return None # Sostituisci con il tuo modello

    def process_frame(self, frame):
        # Rilevamento della mano (basato sul colore)
        self.detect_hand(frame)

        # Rilevamento del volto e delle emozioni
        self.detect_face_and_emotion(frame)

    def detect_hand(self, frame):
        # Implementa il rilevamento della mano basato sul colore
        # 1. Converti il frame in HSV (Hue, Saturation, Value)
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # 2. Definisci l'intervallo di colore della mano
        # Questi valori dipendono dal colore della pelle o da un guanto
        # Puoi usare l'Hue e la Saturation per isolare il colore
        lower_bound = np.array([0, 20, 70]) # Valori di esempio per la pelle
        upper_bound = np.array([20, 255, 255])

        # 3. Applica una maschera per isolare la mano
        mask = cv2.inRange(hsv_frame, lower_bound, upper_bound)

        # 4. Trova i contorni nella maschera
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            # Trova il contorno più grande, che presumibilmente è la mano
            max_contour = max(contours, key=cv2.contourArea)

            # Calcola il centroide del contorno per ottenere la posizione
            M = cv2.moments(max_contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                self.hand_position_signal.emit((cx, cy))

                # Riconosci il gesto (es. pugno o mano aperta)
                gesture = self.recognize_gesture_from_contour(max_contour)
                self.hand_gesture_signal.emit(gesture)

    def recognize_gesture_from_contour(self, contour):
        # Usa il "convex hull" per analizzare la forma della mano
        hull = cv2.convexHull(contour, returnPoints=False)

        if len(hull) > 3:
            defects = cv2.convexityDefects(contour, hull)
            if defects is not None:
                # La logica del riconoscimento dei gesti è complessa
                # Puoi contare il numero di "difetti" tra le dita per
                # distinguere tra pugno (pochi difetti) e mano aperta (molti difetti)
                # Ad esempio, un pugno chiuso ha meno difetti di una mano aperta
                # con 5 dita distese.
                # Questa è un'implementazione molto semplificata.
                finger_count = 0
                for i in range(defects.shape[0]):
                    s, e, f, d = defects[i, 0]
                    start = tuple(contour[s][0])
                    end = tuple(contour[e][0])
                    far = tuple(contour[f][0])

                    # Calcola l'angolo tra le dita per contare quante sono aperte
                    # Questo è solo un esempio. La logica reale è più complessa
                    # e richiede una calibrazione accurata.
                    a = np.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)
                    b = np.sqrt((far[0] - start[0])**2 + (far[1] - start[1])**2)
                    c = np.sqrt((end[0] - far[0])**2 + (end[1] - far[1])**2)
                    angle = np.degrees(np.arccos((b**2 + c**2 - a**2) / (2*b*c)))
                    if angle <= 90:
                        finger_count += 1

                if finger_count > 3:
                    return "Mano Aperta"
                else:
                    return "Pugno Chiuso"
        return "Nessun Gesto"

    def detect_face_and_emotion(self, frame):
        # Converti il frame in scala di grigi per il rilevamento del volto
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Rileva i volti nel frame
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)

        for (x, y, w, h) in faces:
            # Estrai la regione di interesse (ROI) del volto
            face_roi = gray[y:y+h, x:x+w]

            # Classifica l'emozione
            emotion = self.recognize_emotion_from_face(face_roi)
            self.face_emotion_signal.emit(emotion)

    def recognize_emotion_from_face(self, face_roi):
        if self.emotion_model is None:
            return "Modello non caricato"

        # 1. Pre-processa la ROI del volto (ridimensionamento, normalizzazione)
        # 2. Fai una previsione usando il tuo modello
        # 3. Restituisci il nome dell'emozione
        return "Felice" # Sostituisci con il risultato del tuo modello
