# import sys
# import os
# import cv2
# import time
# import logging
# import sqlite3
# import numpy as np
# from datetime import datetime

# # --- 1. Fix for YOLO on Windows (Lapx) ---
# try:
#     import lapx
#     sys.modules['lap'] = lapx
# except ImportError:
#     pass

# from ultralytics import YOLO

# # --- Configuration ---
# VIDEO_SOURCE = 0

# ALERT_THRESHOLD = 0.85      
# MIN_DURATION_FOR_ALERT = 2.0 
# ALERT_COOLDOWN = 60.0       

# # --- הגדרת האזור האסור: חצי מסך ימין ---
# # רזולוציה: 640x480
# # אמצע הרוחב הוא 320.
# # כל מה שמימין לקו (גדול מ-320) הוא סכנה.
# ROI_POINTS = np.array([
#     [320, 0],    # אמצע למעלה
#     [640, 0],    # ימין למעלה
#     [640, 480],  # ימין למטה
#     [320, 480]   # אמצע למטה
# ], np.int32)

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# # --- 2. Database Manager ---
# class DBManager:
#     def __init__(self, db_name="security_log.db"):
#         self.db_name = db_name
#         self.init_db()

#     def init_db(self):
#         try:
#             conn = sqlite3.connect(self.db_name)
#             cursor = conn.cursor()
#             cursor.execute('''
#                 CREATE TABLE IF NOT EXISTS alerts (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     timestamp TEXT NOT NULL,
#                     track_id INTEGER,
#                     threat_score REAL,
#                     image_path TEXT
#                 )
#             ''')
#             conn.commit()
#             conn.close()
#         except Exception as e:
#             print(f"DB Error: {e}")

#     def insert_alert(self, track_id, threat_score, image_path):
#         try:
#             conn = sqlite3.connect(self.db_name)
#             cursor = conn.cursor()
#             current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#             cursor.execute('''
#                 INSERT INTO alerts (timestamp, track_id, threat_score, image_path)
#                 VALUES (?, ?, ?, ?)
#             ''', (current_time, track_id, threat_score, image_path))
#             conn.commit()
#             conn.close()
#             print(f"💾 Logged to DB: ID {track_id}")
#         except Exception as e:
#             print(f"Failed to save to DB: {e}")

# # --- 3. Core Logic Classes ---

# class ObjectDetector:
#     def __init__(self):
#         print("Loading YOLOv8...")
#         self.model = YOLO("yolov8n.pt")
#         self.TARGET_CLASSES = [0] 

#     def detect_and_track(self, frame):
#         results = self.model.track(frame, persist=True, verbose=False, conf=0.4, tracker="bytetrack.yaml")
#         parsed_detections = []
        
#         for result in results:
#             boxes = result.boxes
#             if boxes.id is None: continue

#             track_ids = boxes.id.int().cpu().tolist()
#             for i, box in enumerate(boxes):
#                 if int(box.cls[0]) in self.TARGET_CLASSES:
#                     x1, y1, x2, y2 = box.xyxy[0]
#                     parsed_detections.append({
#                         "bbox": [int(x1), int(y1), int(x2-x1), int(y2-y1)],
#                         "conf": float(box.conf[0]),
#                         "track_id": track_ids[i]
#                     })
#         return parsed_detections

# class TimeTracker:
#     def __init__(self):
#         self.appearance_history = {}

#     def process_time(self, detections, is_inside_zone):
#         tracked_objects = []
#         current_time = time.time()
        
#         for det in detections:
#             obj_id = det['track_id']
            
#             # בדיקה אם האובייקט נמצא באזור הסכנה
#             if is_inside_zone(det['bbox']):
#                 if obj_id not in self.appearance_history:
#                     self.appearance_history[obj_id] = current_time
                
#                 duration = current_time - self.appearance_history[obj_id]
#             else:
#                 self.appearance_history.pop(obj_id, None)
#                 duration = 0.0
            
#             tracked_objects.append({
#                 "id": obj_id,
#                 "bbox": det["bbox"],
#                 "conf": det["conf"],
#                 "duration": duration,
#                 "in_zone": duration > 0
#             })
#         return tracked_objects

# class AlertSystem:
#     def __init__(self, db_manager):
#         self.db = db_manager
#         self.alert_folder = "alert_images"
#         if not os.path.exists(self.alert_folder): os.makedirs(self.alert_folder)
#         self.last_alert_times = {}

#     def trigger_alarm(self, obj_id, score, frame):
#         current_time = time.time()
#         if obj_id in self.last_alert_times:
#             if current_time - self.last_alert_times[obj_id] < ALERT_COOLDOWN: return 

#         self.last_alert_times[obj_id] = current_time
#         filename = f"alert_id{obj_id}_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
#         filepath = os.path.join(self.alert_folder, filename)
#         cv2.imwrite(filepath, frame)
#         self.db.insert_alert(obj_id, score, filepath)
#         logging.info(f"🚨 INTRUSION DETECTED! Saved: {filename}")

# # --- Helper: Check ANY PART inside ---
# def check_if_any_part_inside(bbox):
#     x, y, w, h = bbox
#     corners = [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]
#     for point in corners:
#         if cv2.pointPolygonTest(ROI_POINTS, point, False) >= 0:
#             return True
#     return False

# # --- Main Pipeline ---

# def main():
#     db = DBManager()
#     cap = cv2.VideoCapture(VIDEO_SOURCE)
#     # קיבוע רזולוציה ל-640x480
#     cap.set(3, 640)
#     cap.set(4, 480)
    
#     detector = ObjectDetector() 
#     time_tracker = TimeTracker()
#     alerts = AlertSystem(db)
    
#     print("✅ System Active: RIGHT SIDE IS DANGER ZONE.")

#     while True:
#         ret, frame = cap.read()
#         if not ret: break

#         detections = detector.detect_and_track(frame)
#         tracked_objects = time_tracker.process_time(detections, check_if_any_part_inside)
        
#         # --- ציור אזור החצי-מסך (אנכי) ---
#         # קו חוצה באמצע המסך (מלמעלה למטה)
#         cv2.line(frame, (320, 0), (320, 480), (255, 0, 0), 2)
        
#         # צביעת החצי הימני באדום שקוף
#         overlay = frame.copy()
#         cv2.rectangle(overlay, (320, 0), (640, 480), (0, 0, 255), -1)
#         cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
#         # -----------------------------

#         for obj in tracked_objects:
#             duration = obj['duration']
#             x, y, w, h = obj['bbox']
            
#             if not obj['in_zone']:
#                 color = (200, 200, 200) # אפור - בטוח
#                 label = "Safe Zone"
#                 thickness = 1
#             else:
#                 # בתוך האזור המסוכן (צד ימין)
#                 if duration < MIN_DURATION_FOR_ALERT:
#                     color = (0, 165, 255) # כתום
#                     label = f"Entering... {duration:.1f}s"
#                     thickness = 2
#                 else:
#                     color = (0, 0, 255) # אדום
#                     label = f"ALARM! {duration:.1f}s"
#                     thickness = 3
#                     alerts.trigger_alarm(obj['id'], obj['conf'], frame)

#             cv2.rectangle(frame, (x, y), (x+w, y+h), color, thickness)
#             cv2.putText(frame, f"ID:{obj['id']} {label}", (x, y-10), 
#                         cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

#         cv2.imshow('Smart Security - Left/Right Zone', frame)
#         if cv2.waitKey(1) & 0xFF == ord('q'): break

#     cap.release()
#     cv2.destroyAllWindows()

# if __name__ == "__main__":
#     main()



#///////////////////////////////////////



# import sys
# import os
# import cv2
# import time
# import logging
# import sqlite3
# import numpy as np
# from datetime import datetime
# from flask import Flask, Response
# from flask_socketio import SocketIO, emit

# # --- 1. Fix for YOLO on Windows (Lapx) ---
# try:
#     import lapx
#     sys.modules['lap'] = lapx
# except ImportError:
#     pass

# from ultralytics import YOLO

# # --- Configuration ---
# VIDEO_SOURCE = 0

# ALERT_THRESHOLD = 0.85
# MIN_DURATION_FOR_ALERT = 2.0
# ALERT_COOLDOWN = 60.0

# # --- הגדרת האזור האסור לחצי הימני ברזולוציה 640x480 (X>=320) ---
# # רוחב: 640, גובה: 480. האזור המסוכן מתחיל ב-X=320.
# ROI_POINTS = np.array([
#     [320, 0],
#     [640, 0],
#     [640, 480],
#     [320, 480]
# ], np.int32)

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# # --- הגדרת שרת רשת גלובלי ---
# app = Flask(__name__)
# socketio = SocketIO(app, cors_allowed_origins="*")

# # --- 2. Database Manager ---
# class DBManager:
#     def __init__(self, db_name="security_log.db"):
#         self.db_name = db_name
#         self.init_db()

#     def init_db(self):
#         try:
#             conn = sqlite3.connect(self.db_name)
#             cursor = conn.cursor()
#             cursor.execute('''
#                 CREATE TABLE IF NOT EXISTS alerts (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     timestamp TEXT NOT NULL,
#                     track_id INTEGER,
#                     threat_score REAL,
#                     image_path TEXT
#                 )
#             ''')
#             conn.commit()
#             conn.close()
#         except Exception as e:
#             print(f"DB Error: {e}")

#     def insert_alert(self, track_id, threat_score, image_path):
#         try:
#             conn = sqlite3.connect(self.db_name)
#             cursor = conn.cursor()
#             current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#             cursor.execute('''
#                 INSERT INTO alerts (timestamp, track_id, threat_score, image_path)
#                 VALUES (?, ?, ?, ?)
#             ''', (current_time, track_id, threat_score, image_path))
#             conn.commit()
#             conn.close()
#             print(f"💾 Logged to DB: ID {track_id}")
#         except Exception as e:
#             print(f"Failed to save to DB: {e}")

# # --- 3. Core Logic Classes ---

# class ObjectDetector:
#     def __init__(self):
#         print("Loading YOLOv8...")
#         self.model = YOLO("yolov8n.pt")
#         self.TARGET_CLASSES = [0] 

#     def detect_and_track(self, frame):
#         # 💡 תיקון ביצועים: imgsz=320 כדי להפחית עומס CPU
#         results = self.model.track(frame, 
#                                   persist=True, 
#                                   verbose=False, 
#                                   conf=0.4, 
#                                   tracker="bytetrack.yaml",
#                                   imgsz=320) 
#         parsed_detections = []
        
#         for result in results:
#             boxes = result.boxes
#             if boxes.id is None: continue

#             track_ids = boxes.id.int().cpu().tolist()
#             for i, box in enumerate(boxes):
#                 if int(box.cls[0]) in self.TARGET_CLASSES:
#                     x1, y1, x2, y2 = box.xyxy[0]
#                     parsed_detections.append({
#                         "bbox": [int(x1), int(y1), int(x2-x1), int(y2-y1)],
#                         "conf": float(box.conf[0]),
#                         "track_id": track_ids[i]
#                     })
#         return parsed_detections

# class TimeTracker:
#     def __init__(self):
#         self.appearance_history = {}

#     def process_time(self, detections, is_inside_zone):
#         tracked_objects = []
#         current_time = time.time()
        
#         for det in detections:
#             obj_id = det['track_id']
            
#             if is_inside_zone(det['bbox']):
#                 if obj_id not in self.appearance_history:
#                     self.appearance_history[obj_id] = current_time
                
#                 duration = current_time - self.appearance_history[obj_id]
#             else:
#                 self.appearance_history.pop(obj_id, None)
#                 duration = 0.0
                
#             tracked_objects.append({
#                 "id": obj_id,
#                 "bbox": det["bbox"],
#                 "conf": det["conf"],
#                 "duration": duration,
#                 "in_zone": duration > 0
#             })
#         return tracked_objects


# class AlertSystem:
#     def __init__(self, db_manager):
#         self.db = db_manager
#         self.alert_folder = "alert_images"
#         if not os.path.exists(self.alert_folder): os.makedirs(self.alert_folder)
#         self.last_alert_times = {}

#     def trigger_alarm_and_emit(self, obj_id, score, frame):
#         current_time = time.time()
#         if obj_id in self.last_alert_times:
#             if current_time - self.last_alert_times[obj_id] < ALERT_COOLDOWN: 
#                 return False 
        
#         self.last_alert_times[obj_id] = current_time
#         filename = f"alert_id{obj_id}_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
#         filepath = os.path.join(self.alert_folder, filename)
#         cv2.imwrite(filepath, frame)
#         self.db.insert_alert(obj_id, score, filepath)
#         logging.info(f"🚨 INTRUSION DETECTED! Saved: {filename}")
        
#         return True

# # --- Helper: Check ANY PART inside ---
# def check_if_any_part_inside(bbox):
#     x, y, w, h = bbox
#     corners = [(x, y), (x+w, y), (x, y+h), (x+w, y+h)]
#     for point in corners:
#         if cv2.pointPolygonTest(ROI_POINTS, point, False) >= 0:
#             return True
#     return False


# # --- Main Generator ---

# db = DBManager()
# detector = ObjectDetector()
# time_tracker = TimeTracker()
# alerts = AlertSystem(db)

# def generate_frames():
#     """לכידת פריימים, עיבוד, בקרת FPS והזרמה."""
#     cap = cv2.VideoCapture(VIDEO_SOURCE)
    
#     # הגדרת רזולוציה ל-640x480
#     cap.set(3, 640) 
#     cap.set(4, 480) 

#     if not cap.isOpened():
#         logging.error("Failed to open video source.")
#         return

#     logging.info("✅ System Active: RIGHT SIDE (320-640) IS DANGER ZONE.")

#     # --- בקרת FPS ---
#     TARGET_FPS = 10.0 # 💡 יעד FPS מופחת
#     FRAME_DELAY = 1.0 / TARGET_FPS 
#     last_frame_time = time.time()
#     # ------------------

#     while True:
#         # --- תזמון ---
#         current_time = time.time()
#         time_elapsed = current_time - last_frame_time

#         if time_elapsed < FRAME_DELAY:
#             time.sleep(FRAME_DELAY - time_elapsed)
#             current_time = time.time() 
        
#         last_frame_time = current_time
#         # --- סוף תזמון ---
        
#         ret, frame = cap.read()
#         if not ret: 
#              time.sleep(1)
#              continue

#         detections = detector.detect_and_track(frame)
#         tracked_objects = time_tracker.process_time(detections, check_if_any_part_inside)
        
#         # --- ציור אזור החצי-מסך (החל מ-320) ---
#         overlay = frame.copy()
#         cv2.rectangle(overlay, (320, 0), (640, 480), (0, 0, 255), -1)
#         cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
        
#         for obj in tracked_objects:
#             duration = obj['duration']
#             x, y, w, h = obj['bbox']
            
#             # --- לוגיקת צבע והתראה ---
#             if not obj['in_zone']:
#                 color = (200, 200, 200) 
#                 label = "Safe Zone"
#                 thickness = 1
#             else:
#                 if duration < MIN_DURATION_FOR_ALERT:
#                     color = (0, 165, 255) 
#                     label = f"Entering... {duration:.1f}s"
#                     thickness = 2
#                 else:
#                     color = (0, 0, 255) 
#                     label = f"ALARM! {duration:.1f}s"
#                     thickness = 3
                    
#                     if alerts.trigger_alarm_and_emit(obj['id'], obj['conf'], frame):
#                          socketio.emit('new_alert', {
#                              'track_id': obj['id'],
#                              'duration': f"{duration:.1f}s",
#                              'timestamp': datetime.now().strftime("%H:%M:%S")
#                          }, namespace='/', broadcast=True)
            
#             cv2.rectangle(frame, (x, y), (x+w, y+h), color, thickness)
#             cv2.putText(frame, f"ID:{obj['id']} {label}", (x, y-10),
#                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
#         # קידוד והזרמה (M-JPEG)
#         ret, buffer = cv2.imencode('.jpg', frame)
#         frame_bytes = buffer.tobytes()

#         yield (b'--frame\r\n'
#                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

#     cap.release()

# # --- 7. הגדרת מסלולים והפעלה ---

# @app.route('/video_feed')
# def video_feed():
#     """מסלול הזרמת הווידאו"""
#     return Response(generate_frames(),
#                     mimetype='multipart/x-mixed-replace; boundary=frame')

# @app.route('/')
# def index_route():
#     """מסלול בסיסי לבדיקה"""
#     return "Smart Security Backend Running."

# if __name__ == "__main__":
#     socketio.run(app, host='127.0.0.1', port=5000, debug=True)


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

# --- 1. Fix for YOLO on Windows (Lapx) & YOLO Import ---
try:
    import lapx
    sys.modules['lap'] = lapx
except ImportError:
    pass
from ultralytics import YOLO

# --- Configuration & Global State ---
VIDEO_SOURCE = 0 # ודא שזהו מקור הווידאו הנכון שלך
ALERT_THRESHOLD = 0.85
MIN_DURATION_FOR_ALERT = 2.0
ALERT_COOLDOWN = 60.0
# FPS ייעודי לעיבוד YOLO (YOLO Process FPS).
YOLO_PROCESS_FPS = 5.0 
FRAME_DELAY_YOLO = 1.0 / YOLO_PROCESS_FPS

# הגדרת האזור האסור לחצי הימני ברזולוציה 640x480
ROI_POINTS = np.array([
    [320, 0], [640, 0], [640, 480], [320, 480]
], np.int32)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# משתנים גלובליים משותפים ל-Threading
GLOBAL_FRAME = None # הפריים המעובד האחרון
FRAME_LOCK = threading.Lock() # מנעול לגישה בטוחה ל-GLOBAL_FRAME

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
        self.TARGET_CLASSES = [0] # Person

    def detect_and_track(self, frame):
        # ייעול: imgsz=320 כדי להפחית עומס CPU
        results = self.model.track(frame, 
                                     persist=True, 
                                     verbose=False, 
                                     conf=0.4, 
                                     tracker="bytetrack.yaml",
                                     imgsz=320) 
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
        
        current_ids = {obj['id'] for obj in tracked_objects}
        keys_to_delete = [k for k in self.appearance_history if k not in current_ids]
        for k in keys_to_delete:
            self.appearance_history.pop(k, None)

        return tracked_objects


class AlertSystem:
    def __init__(self, db_manager):
        self.db = db_manager
        self.alert_folder = "alert_images"
        if not os.path.exists(self.alert_folder): os.makedirs(self.alert_folder)
        self.last_alert_times = {}

    def trigger_alarm_and_emit(self, obj_id, score, frame):
        current_time = time.time()
        if obj_id in self.last_alert_times:
            if current_time - self.last_alert_times[obj_id] < ALERT_COOLDOWN: 
                return False 
        
        self.last_alert_times[obj_id] = current_time
        filename = f"alert_id{obj_id}_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(self.alert_folder, filename)
        
        cv2.imwrite(filepath, frame) 
        self.db.insert_alert(obj_id, score, filepath)
        logging.info(f"🚨 INTRUSION DETECTED! Saved: {filename}")
        
        return True

def check_if_any_part_inside(bbox):
    x, y, w, h = bbox
    # נבדוק רק את המרכז של הבאונדינג בוקס לייעול
    center_x = x + w // 2
    center_y = y + h // 2
    center_point = (center_x, center_y)
    
    if cv2.pointPolygonTest(ROI_POINTS, center_point, False) >= 0:
        return True
    return False

# --- 4. Threaded Camera Processor ---

class CameraProcessor(threading.Thread):
    
    def __init__(self, detector, time_tracker, alerts):
        super().__init__()
        self.cap = cv2.VideoCapture(VIDEO_SOURCE)
        self.detector = detector
        self.time_tracker = time_tracker
        self.alerts = alerts
        self.running = True

        if not self.cap.isOpened():
            logging.error("❌ Failed to open video source (Check VIDEO_SOURCE variable).")
            self.running = False
            return
            
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480) 
        logging.info(f"✅ Camera Processor Thread Active. YOLO @ {YOLO_PROCESS_FPS} FPS.")

    def run(self):
        global GLOBAL_FRAME
        last_frame_time = time.time()
        
        while self.running:
            
            # בקרת FPS פנימית לעיבוד ה-YOLO
            current_time = time.time()
            time_to_wait = FRAME_DELAY_YOLO - (current_time - last_frame_time)
            if time_to_wait > 0:
                 time.sleep(time_to_wait)
                 current_time = time.time()
            last_frame_time = current_time
            
            ret, frame = self.cap.read()
            if not ret: 
                time.sleep(0.1) 
                continue
                
            # 1. עיבוד ה-AI
            detections = self.detector.detect_and_track(frame.copy())
            tracked_objects = self.time_tracker.process_time(detections, check_if_any_part_inside)

            # 2. ציור וטריגר התראות
            temp_frame = self._draw_and_alert(frame.copy(), tracked_objects)

            # 3. שמירת הפריים המעובד (בטוח Thread)
            with FRAME_LOCK:
                GLOBAL_FRAME = temp_frame
                
    def _draw_and_alert(self, frame, tracked_objects):
        """פונקציה פרטית לציור ההתראות והגדרת ה-Trigger."""
        
        # ציור מלבן הגבול
        cv2.rectangle(frame, (320, 0), (640, 480), (0, 0, 255), 2)
        
        for obj in tracked_objects:
            duration = obj['duration']
            x, y, w, h = obj['bbox']
            
            # לוגיקת צבע והתראה
            if not obj['in_zone']:
                color, label, thickness = (200, 200, 200), "Safe Zone", 1
            else:
                if duration < MIN_DURATION_FOR_ALERT:
                    color, label, thickness = (0, 165, 255), f"Entering... {duration:.1f}s", 2
                else:
                    color, label, thickness = (0, 0, 255), f"ALARM! {duration:.1f}s", 3
                    
                    # 🚨 תיקון ה-SocketIO: שימוש ב-socketio.server.emit לשליחה מ-Thread
                    if self.alerts.trigger_alarm_and_emit(obj['id'], obj['conf'], frame):
                         socketio.server.emit('new_alert', {
                            'track_id': obj['id'],
                            'duration': f"{duration:.1f}s",
                            'timestamp': datetime.now().strftime("%H:%M:%S")
                         }, namespace='/') 
                         
            # ציור ה-BBox והטקסט
            cv2.rectangle(frame, (x, y), (x+w, y+h), color, thickness)
            cv2.putText(frame, f"ID:{obj['id']} {label}", (x, y-10),
                         cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
        return frame
            
    def stop(self):
        self.running = False
        if self.cap.isOpened():
            self.cap.release()
        logging.info("✅ Camera Processor Thread stopped cleanly.")


# --- 5. Flask App Setup ---
app = Flask(__name__)
# שימוש ב-allow_unsafe_werkzeug=True רק לצורך Debugging/פיתוח
socketio = SocketIO(app, cors_allowed_origins="*")

# אתחול
db = DBManager()
detector = ObjectDetector()
time_tracker = TimeTracker()
alerts = AlertSystem(db)
# אתחול והפעלת ה-Thread של העיבוד
processor_thread = CameraProcessor(detector, time_tracker, alerts)
processor_thread.start()

# --- 6. Main Generator (Only for Streaming) ---

def generate_frames():
    """מסלול הזרמת הווידאו. רק מושך את הפריים הגלובלי המעובד."""
    global GLOBAL_FRAME
    
    # בקרת FPS של הסטרימינג ללקוח (10 FPS)
    STREAM_FPS = 10.0
    FRAME_DELAY_STREAM = 1.0 / STREAM_FPS
    last_yield_time = time.time()
    
    while True:
        # 1. תזמון
        current_time = time.time()
        time_to_wait = FRAME_DELAY_STREAM - (current_time - last_yield_time)
        if time_to_wait > 0:
             time.sleep(time_to_wait)
             current_time = time.time()
        last_yield_time = current_time

        # 2. משיכת הפריים המעובד האחרון (בטוח Thread)
        with FRAME_LOCK:
            frame_to_stream = GLOBAL_FRAME
        
        if frame_to_stream is None:
            continue
            
        # 3. קידוד (M-JPEG)
        # 💡 ייעול: הגדרת איכות JPEG מפורשת (80)
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
        ret, buffer = cv2.imencode('.jpg', frame_to_stream, encode_param)
        frame_bytes = buffer.tobytes()

        # 4. הזרמה (M-JPEG over HTTP)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# --- 7. הגדרת מסלולים והפעלה ---

@app.route('/video_feed')
def video_feed():
    """מסלול הזרמת הווידאו."""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index_route():
    """מסלול בסיסי לבדיקה."""
    return "Smart Security Backend Running. YOLO processing is in background thread."

if __name__ == "__main__":
    try:
        # מומלץ להריץ על 0.0.0.0 כדי שיהיה נגיש מחוץ ל-localhost
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # חשוב לכבות את ה-Thread בצורה מסודרת
        if 'processor_thread' in locals() and processor_thread.is_alive():
             processor_thread.stop()
             processor_thread.join()
        print("Threads stopped. Application closed.")