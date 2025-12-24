import sys
import os
import cv2
import time
import logging
import sqlite3
import numpy as np
import threading
from datetime import datetime
from flask import Flask, Response
from flask_socketio import SocketIO, emit

# תיקון עבור YOLO בסביבות לינוקס/Windows
try:
    import lapx
    sys.modules['lap'] = lapx
except ImportError:
    pass
from ultralytics import YOLO

# --- הגדרות ---
# שים לב: ב-Render '0' לא יעבוד. תצטרך להחליף לכתובת RTSP בעתיד.
VIDEO_SOURCE = os.environ.get("VIDEO_URL", 0) 
ALERT_THRESHOLD = 0.85
MIN_DURATION_FOR_ALERT = 2.0
ALERT_COOLDOWN = 60.0
YOLO_PROCESS_FPS = 5.0  
FRAME_DELAY_YOLO = 1.0 / YOLO_PROCESS_FPS

ROI_POINTS = np.array([[320, 0], [640, 0], [640, 480], [320, 480]], np.int32)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

GLOBAL_FRAME = None 
FRAME_LOCK = threading.Lock()

# --- ניהול בסיס נתונים ---
class DBManager:
    def __init__(self, db_name="security_log.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    track_id INTEGER,
                    threat_score REAL,
                    image_path TEXT
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"DB Error: {e}")

    def insert_alert(self, track_id, threat_score, image_path):
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute('INSERT INTO alerts (timestamp, track_id, threat_score, image_path) VALUES (?, ?, ?, ?)', 
                           (current_time, track_id, threat_score, image_path))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Failed to save to DB: {e}")

# --- לוגיקה מרכזית ---
class ObjectDetector:
    def __init__(self):
        logging.info("Loading YOLOv8...")
        self.model = YOLO("yolov8n.pt")
        self.TARGET_CLASSES = [0] # Person

    def detect_and_track(self, frame):
        try:
            results = self.model.track(frame, persist=True, verbose=False, conf=0.4, imgsz=320)
            parsed_detections = []
            for result in results:
                boxes = result.boxes
                if boxes is None or boxes.id is None: continue
                track_ids = boxes.id.int().cpu().tolist()
                for i, box in enumerate(boxes):
                    if int(box.cls[0]) in self.TARGET_CLASSES:
                        x1, y1, x2, y2 = box.xyxy[0]
                        parsed_detections.append({
                            "bbox": [int(x1), int(y1), int(x2-x1), int(y2-y1)],
                            "conf": float(box.conf[0]),
                            "track_id": track_ids[i]
                        })
            return parsed_detections
        except Exception as e:
            return []

class TimeTracker:
    def __init__(self):
        self.appearance_history = {}

    def process_time(self, detections, is_inside_zone):
        tracked_objects = []
        current_time = time.time()
        for det in detections:
            obj_id = det['track_id']
            if is_inside_zone(det['bbox']):
                if obj_id not in self.appearance_history:
                    self.appearance_history[obj_id] = current_time
                duration = current_time - self.appearance_history[obj_id]
            else:
                self.appearance_history.pop(obj_id, None)
                duration = 0.0
            tracked_objects.append({"id": obj_id, "bbox": det["bbox"], "conf": det["conf"], "duration": duration, "in_zone": duration > 0})
        return tracked_objects

class AlertSystem:
    def __init__(self, db_manager):
        self.db = db_manager
        self.alert_folder = "alert_images"
        if not os.path.exists(self.alert_folder): os.makedirs(self.alert_folder)
        self.last_alert_times = {}

    def trigger_alarm_and_emit(self, obj_id, score, frame):
        current_time = time.time()
        if obj_id in self.last_alert_times and current_time - self.last_alert_times[obj_id] < ALERT_COOLDOWN:
            return False
        self.last_alert_times[obj_id] = current_time
        filename = f"alert_id{obj_id}_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(self.alert_folder, filename)
        cv2.imwrite(filepath, frame)
        self.db.insert_alert(obj_id, score, filepath)
        return True

def check_if_any_part_inside(bbox):
    x, y, w, h = bbox
    center_point = (x + w // 2, y + h // 2)
    return cv2.pointPolygonTest(ROI_POINTS, center_point, False) >= 0

# --- עיבוד המצלמה ב-Thread ---
class CameraProcessor(threading.Thread):
    def __init__(self, detector, time_tracker, alerts):
        super().__init__()
        self.detector = detector
        self.time_tracker = time_tracker
        self.alerts = alerts
        self.running = True
        self.cap = cv2.VideoCapture(VIDEO_SOURCE)

    def run(self):
        global GLOBAL_FRAME
        last_frame_time = time.time()
        while self.running:
            if not self.cap.isOpened():
                logging.error("Camera source not found. Retrying...")
                time.sleep(5)
                self.cap = cv2.VideoCapture(VIDEO_SOURCE)
                continue

            ret, frame = self.cap.read()
            if not ret: continue
            
            detections = self.detector.detect_and_track(frame.copy())
            tracked_objects = self.time_tracker.process_time(detections, check_if_any_part_inside)
            
            # ציור
            cv2.rectangle(frame, (320, 0), (640, 480), (0, 0, 255), 2)
            for obj in tracked_objects:
                x, y, w, h = obj['bbox']
                color = (0, 0, 255) if obj['duration'] >= MIN_DURATION_FOR_ALERT else (0, 165, 255)
                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                if obj['duration'] >= MIN_DURATION_FOR_ALERT:
                    if self.alerts.trigger_alarm_and_emit(obj['id'], obj['conf'], frame):
                        socketio.emit('new_alert', {'id': obj['id']})

            with FRAME_LOCK:
                GLOBAL_FRAME = frame
            time.sleep(FRAME_DELAY_YOLO)

    def stop(self):
        self.running = False
        if self.cap.isOpened(): self.cap.release()

# --- Flask & SocketIO ---
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

db = DBManager()
detector = ObjectDetector()
time_tracker = TimeTracker()
alerts = AlertSystem(db)
processor = CameraProcessor(detector, time_tracker, alerts)
processor.start()

@app.route('/')
def index():
    return "Backend is running. Port: " + os.environ.get("PORT", "5000")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
