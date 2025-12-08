import sys
import os
import cv2
import time
import logging
import sqlite3
import numpy as np
from datetime import datetime

# --- 1. Fix for YOLO on Windows (Lapx) ---
try:
    import lapx
    sys.modules['lap'] = lapx
except ImportError:
    pass

from ultralytics import YOLO

# --- Configuration ---
VIDEO_SOURCE = 0

ALERT_THRESHOLD = 0.85      
MIN_DURATION_FOR_ALERT = 2.0 
ALERT_COOLDOWN = 60.0       

# --- הגדרת האזור האסור: חצי מסך ימין ---
# רזולוציה: 640x480
# אמצע הרוחב הוא 320.
# כל מה שמימין לקו (גדול מ-320) הוא סכנה.
ROI_POINTS = np.array([
    [320, 0],    # אמצע למעלה
    [640, 0],    # ימין למעלה
    [640, 480],  # ימין למטה
    [320, 480]   # אמצע למטה
], np.int32)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# --- 2. Database Manager ---
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
            print(f"DB Error: {e}")

    def insert_alert(self, track_id, threat_score, image_path):
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute('''
                INSERT INTO alerts (timestamp, track_id, threat_score, image_path)
                VALUES (?, ?, ?, ?)
            ''', (current_time, track_id, threat_score, image_path))
            conn.commit()
            conn.close()
            print(f"💾 Logged to DB: ID {track_id}")
        except Exception as e:
            print(f"Failed to save to DB: {e}")

# --- 3. Core Logic Classes ---

class ObjectDetector:
    def __init__(self):
        print("Loading YOLOv8...")
        self.model = YOLO("yolov8n.pt")
        self.TARGET_CLASSES = [0] 

    def detect_and_track(self, frame):
        results = self.model.track(frame, persist=True, verbose=False, conf=0.4, tracker="bytetrack.yaml")
        parsed_detections = []
        
        for result in results:
            boxes = result.boxes
            if boxes.id is None: continue

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

class TimeTracker:
    def __init__(self):
        self.appearance_history = {}

    def process_time(self, detections, is_inside_zone):
        tracked_objects = []
        current_time = time.time()
        
        for det in detections:
            obj_id = det['track_id']
            
            # בדיקה אם האובייקט נמצא באזור הסכנה
            if is_inside_zone(det['bbox']):
                if obj_id not in self.appearance_history:
                    self.appearance_history[obj_id] = current_time
                
                duration = current_time - self.appearance_history[obj_id]
            else:
                self.appearance_history.pop(obj_id, None)
                duration = 0.0
            
            tracked_objects.append({
                "id": obj_id,
                "bbox": det["bbox"],
                "conf": det["conf"],
                "duration": duration,
                "in_zone": duration > 0
            })
        return tracked_objects

class AlertSystem:
    def __init__(self, db_manager):
        self.db = db_manager
        self.alert_folder = "alert_images"
        if not os.path.exists(self.alert_folder): os.makedirs(self.alert_folder)
        self.last_alert_times = {}

    def trigger_alarm(self, obj_id, score, frame):
        current_time = time.time()
        if obj_id in self.last_alert_times:
            if current_time - self.last_alert_times[obj_id] < ALERT_COOLDOWN: return 

        self.last_alert_times[obj_id] = current_time
        filename = f"alert_id{obj_id}_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(self.alert_folder, filename)
        cv2.imwrite(filepath, frame)
        self.db.insert_alert(obj_id, score, filepath)
        logging.info(f"🚨 INTRUSION DETECTED! Saved: {filename}")

# --- Helper: Check ANY PART inside ---
def check_if_any_part_inside(bbox):
    x, y, w, h = bbox
    corners = [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]
    for point in corners:
        if cv2.pointPolygonTest(ROI_POINTS, point, False) >= 0:
            return True
    return False

# --- Main Pipeline ---

def main():
    db = DBManager()
    cap = cv2.VideoCapture(VIDEO_SOURCE)
    # קיבוע רזולוציה ל-640x480
    cap.set(3, 640)
    cap.set(4, 480)
    
    detector = ObjectDetector() 
    time_tracker = TimeTracker()
    alerts = AlertSystem(db)
    
    print("✅ System Active: RIGHT SIDE IS DANGER ZONE.")

    while True:
        ret, frame = cap.read()
        if not ret: break

        detections = detector.detect_and_track(frame)
        tracked_objects = time_tracker.process_time(detections, check_if_any_part_inside)
        
        # --- ציור אזור החצי-מסך (אנכי) ---
        # קו חוצה באמצע המסך (מלמעלה למטה)
        cv2.line(frame, (320, 0), (320, 480), (255, 0, 0), 2)
        
        # צביעת החצי הימני באדום שקוף
        overlay = frame.copy()
        cv2.rectangle(overlay, (320, 0), (640, 480), (0, 0, 255), -1)
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
        # -----------------------------

        for obj in tracked_objects:
            duration = obj['duration']
            x, y, w, h = obj['bbox']
            
            if not obj['in_zone']:
                color = (200, 200, 200) # אפור - בטוח
                label = "Safe Zone"
                thickness = 1
            else:
                # בתוך האזור המסוכן (צד ימין)
                if duration < MIN_DURATION_FOR_ALERT:
                    color = (0, 165, 255) # כתום
                    label = f"Entering... {duration:.1f}s"
                    thickness = 2
                else:
                    color = (0, 0, 255) # אדום
                    label = f"ALARM! {duration:.1f}s"
                    thickness = 3
                    alerts.trigger_alarm(obj['id'], obj['conf'], frame)

            cv2.rectangle(frame, (x, y), (x+w, y+h), color, thickness)
            cv2.putText(frame, f"ID:{obj['id']} {label}", (x, y-10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        cv2.imshow('Smart Security - Left/Right Zone', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()