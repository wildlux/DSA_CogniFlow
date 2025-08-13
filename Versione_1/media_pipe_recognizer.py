import cv2
import mediapipe as mp
import numpy as np

from PyQt6.QtCore import QObject, pyqtSignal

class MediaPipeRecognizer(QObject):
    # Segnali per comunicare con l'interfaccia principale
    hand_position_signal = pyqtSignal(tuple) # Invia le coordinate della mano
    hand_gesture_signal = pyqtSignal(str) # Invia il nome del gesto
    face_emotion_signal = pyqtSignal(str) # Invia l'emozione rilevata

    def __init__(self):
        super().__init__()
        self.mp_hands = mp.solutions.hands
        self.mp_face_detection = mp.solutions.face_detection
        self.hands = self.mp_hands.Hands(min_detection_confidence=0.7, min_tracking_confidence=0.5)
        self.face_detection = self.mp_face_detection.FaceDetection(min_detection_confidence=0.7)

        # Inizializza un classificatore di emozioni (per il volto)
        # Sostituisci con il tuo modello di classificazione delle emozioni
        self.emotion_classifier = self.load_emotion_model()

    def load_emotion_model(self):
        # Placeholder: Carica qui il tuo modello di machine learning per le emozioni
        # Potrebbe essere un modello Keras/TensorFlow pre-addestrato
        return None # Ritorna il modello caricato

    def process_frame(self, frame):
        # Converte l'immagine da BGR (OpenCV) a RGB (MediaPipe)
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Elabora le mani
        hands_results = self.hands.process(image_rgb)
        if hands_results.multi_hand_landmarks:
            for hand_landmarks in hands_results.multi_hand_landmarks:
                # Trova la posizione della mano (es. centro o polso)
                index_finger_tip = hand_landmarks.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_TIP]
                h, w, c = frame.shape
                cx, cy = int(index_finger_tip.x * w), int(index_finger_tip.y * h)
                self.hand_position_signal.emit((cx, cy))

                # Riconosci il gesto (es. pugno chiuso, indice alzato)
                gesture = self.recognize_gesture(hand_landmarks)
                if gesture:
                    self.hand_gesture_signal.emit(gesture)

        # Elabora il volto
        face_results = self.face_detection.process(image_rgb)
        if face_results.detections:
            for detection in face_results.detections:
                # Usa un classificatore per riconoscere l'emozione
                # Devi implementare la logica per estrarre il volto e passarlo al modello
                emotion = self.recognize_emotion(frame, detection)
                if emotion:
                    self.face_emotion_signal.emit(emotion)

    def recognize_gesture(self, hand_landmarks):
        # Semplice logica di esempio per un gesto di "pugno chiuso"
        thumb_tip = hand_landmarks.landmark[self.mp_hands.HandLandmark.THUMB_TIP]
        index_tip = hand_landmarks.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_TIP]
        middle_tip = hand_landmarks.landmark[self.mp_hands.HandLandmark.MIDDLE_FINGER_TIP]
        ring_tip = hand_landmarks.landmark[self.mp_hands.HandLandmark.RING_FINGER_TIP]
        pinky_tip = hand_landmarks.landmark[self.mp_hands.HandLandmark.PINKY_TIP]

        # Se tutte le punte delle dita sono al di sotto dei nodi intermedi, è un pugno
        if (index_tip.y > hand_landmarks.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_PIP].y and
            middle_tip.y > hand_landmarks.landmark[self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP].y and
            ring_tip.y > hand_landmarks.landmark[self.mp_hands.HandLandmark.RING_FINGER_PIP].y and
            pinky_tip.y > hand_landmarks.landmark[self.mp_hands.HandLandmark.PINKY_PIP].y):
            return "Pugno Chiuso"

        # Aggiungi qui la logica per altri gesti...

        return "Nessun Gesto"

    def recognize_emotion(self, frame, detection):
        if not self.emotion_classifier:
            return "Modello non caricato"

        # 1. Estrai la regione del volto dal frame video
        bboxC = detection.location_data.relative_bounding_box
        ih, iw, _ = frame.shape
        x, y, w, h = int(bboxC.xmin * iw), int(bboxC.ymin * ih), int(bboxC.width * iw), int(bboxC.height * ih)
        face_roi = frame[y:y+h, x:x+w]

        # 2. Pre-processa il volto per il modello (es. ridimensionamento, normalizzazione)
        # face_preprocessed = ...

        # 3. Fai la previsione con il modello
        # prediction = self.emotion_classifier.predict(face_preprocessed)

        # 4. Restituisci l'emozione con la probabilità più alta
        # return emotion_label[np.argmax(prediction)]
        return "Felice" # Esempio statico

---

### Modifiche a `MainWindow`

Nella tua classe `MainWindow` (che non hai fornito, ma che probabilmente esiste), dovrai connettere il `MediaPipeRecognizer` al thread video (`VideoThread`).

1.  **Instanza del Riconoscitore**: Crea un'istanza del `MediaPipeRecognizer`.
2.  **Connessione Segnali**: Collega i segnali del `MediaPipeRecognizer` agli slot (metodi) della tua `MainWindow` per gestire i dati ricevuti (ad esempio, per muovere un widget).
3.  **Integrazione con `VideoThread`**: Modifica la `VideoThread` per passargli un'istanza del `MediaPipeRecognizer`.
4.  **Gestione del Drag and Drop**: Quando ricevi il segnale `hand_position_signal`, puoi aggiornare la posizione del widget selezionato. Il segnale `hand_gesture_signal` (es. "Pugno Chiuso") può essere usato per "afferrare" e "rilasciare" il widget.

Ecco un esempio di come potresti integrare il `MediaPipeRecognizer` nella tua `MainWindow`:

```python
# Nel tuo file main.py o dove si trova la classe MainWindow
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # ... (altri widget)

        self.recognizer = MediaPipeRecognizer()

        self.video_thread = VideoThread()
        self.video_thread.change_pixmap_signal.connect(self.update_video_frame)
        self.video_thread.start()

        # Collega i segnali del riconoscimento ai metodi di gestione
        self.recognizer.hand_position_signal.connect(self.handle_hand_position)
        self.recognizer.hand_gesture_signal.connect(self.handle_hand_gesture)
        self.recognizer.face_emotion_signal.connect(self.handle_face_emotion)

    def update_video_frame(self, cv_img):
        # Qui ricevi il frame video da VideoThread
        # Prima di visualizzarlo, lo passi al riconoscitore
        self.recognizer.process_frame(cv_img)
        # Poi converti il frame e lo visualizzi come al solito
        # ...

    def handle_hand_position(self, pos):
        # Metodo per aggiornare la posizione di un widget trascinato
        # self.current_dragged_widget.move(pos)
        pass

    def handle_hand_gesture(self, gesture):
        if gesture == "Pugno Chiuso":
            # Inizia il trascinamento
            pass
        elif gesture == "Mano Aperta":
            # Rilascia il widget
            pass

    def handle_face_emotion(self, emotion):
        # Fai qualcosa in base all'emozione rilevata (es. cambia colore UI)
        print(f"Emozione rilevata: {emotion}")

    # Aggiungi qui la gestione del widget da trascinare
    # ...
