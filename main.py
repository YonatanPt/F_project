import sys
print(sys.executable)
import cv2
import time
import logging
from ultralytics import YOLO # זו הספרייה האמיתית

# --- קונפיגורציה ---
VIDEO_SOURCE = 0           # 0 למצלמת רשת
ALERT_THRESHOLD = 0.85     
SUSPICIOUS_THRESHOLD = 0.5 
DEBUG_MODE = True          

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# --- מחלקות ---

class ObjectDetector:
    """
    מממש את YOLOv8 האמיתי באמצעות ספריית Ultralytics.
    """
    def __init__(self):
        print("Loading Real YOLOv8 Model... (First time might take a moment)")
        # המודל 'yolov8n.pt' הוא גרסת ה-Nano (הכי מהירה וקלה למחשב נייד)
        # בפעם הראשונה זה יוריד את הקובץ אוטומטית מהאינטרנט
        self.model = YOLO("yolov8n.pt")
        
        # קודים של מחלקות ב-COCO Dataset שמעניינות אותנו
        # 0 = Person (אפשר להוסיף בעתיד: 2=Car, 16=Dog, 15=Cat)
        self.TARGET_CLASSES = [0] 

    def detect(self, frame):
        """
        מקבל פריים, מריץ YOLO, ומחזיר רשימה של זיהויים.
        """
        # הרצת המודל (verbose=False מונע הדפסות מיותרות בטרמינל)
        results = self.model(frame, verbose=False, conf=0.4) 
        
        parsed_detections = []
        
        # YOLO מחזיר אובייקט תוצאות מורכב, צריך לפרק אותו
        for result in results:
            boxes = result.boxes
            for box in boxes:
                # שליפת נתונים
                cls_id = int(box.cls[0])      # סוג האובייקט
                conf = float(box.conf[0])     # רמת ביטחון (0-1)
                x1, y1, x2, y2 = box.xyxy[0]  # קואורדינטות (פיקסלים)
                
                # המרה למספרים שלמים
                x, y = int(x1), int(y1)
                w, h = int(x2 - x1), int(y2 - y1)
                
                # סינון: שומרים רק אם זה "אדם" (Class 0)
                if cls_id in self.TARGET_CLASSES:
                    parsed_detections.append({
                        "bbox": [x, y, w, h],
                        "class_id": cls_id,
                        "conf": conf,
                        "label": self.model.names[cls_id] # למשל 'person'
                    })
                    
        return parsed_detections

class SimpleTracker:
    """
    טרקר פשוט מאוד (Placeholder).
    בפרויקט המלא נחליף את זה ב-ByteTrack/DeepSORT.
    כרגע: הוא לא באמת עוקב, אלא רק מעביר את הזיהוי הלאה ונותן לו ID זמני.
    """
    def __init__(self):
        self.fake_id_counter = 0

    def update(self, detections):
        # במערכת אמיתית כאן יהיה קוד שמשווה מיקומים בין פריימים
        tracked_objects = []
        
        for det in detections:
            # לצורך הדגמה בלבד - ממציאים ID
            # בפועל - ה-ID אמור להישאר קבוע לאותו אדם לאורך זמן
            obj = {
                "id": self.fake_id_counter, 
                "bbox": det["bbox"],
                "class": det["label"],
                "conf": det["conf"],
                "history_len": 100 # סתם מספר כדי שהלוגיקה תעבוד כרגע
            }
            tracked_objects.append(obj)
            self.fake_id_counter += 1 # בטרקר אמיתי זה לא עובד ככה!
            
        if self.fake_id_counter > 1000: self.fake_id_counter = 0
        return tracked_objects

class ThreatLogic:
    """
    האלגוריתם החכם (TTA).
    """
    def calculate_threat_score(self, obj_data):
        # כאן אנחנו משתמשים בנתונים האמיתיים מ-YOLO
        confidence = obj_data["conf"]
        
        # דוגמה ללוגיקה:
        # אם המודל מאוד בטוח (מעל 0.8) -> ציון גבוה
        # אם המודל מהסס (0.5) -> ציון נמוך
        
        score = confidence 
        
        # בונוס: אם הריבוע מאוד קטן (רעש רחוק) נוריד ציון
        _, _, w, h = obj_data['bbox']
        area = w * h
        if area < 5000: # קטן מדי
            score -= 0.2
            
        return max(0.0, min(score, 1.0)) # מוודא שהציון בין 0 ל-1

class AlertSystem:
    def trigger_alarm(self, obj_id, score):
        # מדפיס באדום (בטרמינלים שתומכים) או רגיל
        logging.info(f"🚨 ALARM! Person Detected! [ID:{obj_id}] Score: {score:.2f}")

# --- Main Pipeline ---

def main():
    cap = cv2.VideoCapture(VIDEO_SOURCE)
    
    # בדיקה שהמצלמה נפתחה
    if not cap.isOpened():
        print("Error: Could not open video source.")
        return

    # אתחול
    detector = ObjectDetector() # עכשיו זה YOLO אמיתי!
    tracker = SimpleTracker()
    logic = ThreatLogic()
    alerts = AlertSystem()
    
    print("Security System Active. Point camera at a person.")

    while True:
        ret, frame = cap.read()
        if not ret: break
        
        # 1. גילוי (YOLO)
        detections = detector.detect(frame)
        
        # 2. עקיבה
        tracked_objects = tracker.update(detections)
        
        # 3. לוגיקה ותצוגה
        for obj in tracked_objects:
            threat_score = logic.calculate_threat_score(obj)
            
            x, y, w, h = obj['bbox']
            label_text = f"{obj['class']} {threat_score:.2f}"
            
            # צבע לפי רמת איום
            if threat_score > ALERT_THRESHOLD:
                color = (0, 0, 255) # אדום
                alerts.trigger_alarm(obj['id'], threat_score)
            elif threat_score > SUSPICIOUS_THRESHOLD:
                color = (0, 165, 255) # כתום
            else:
                color = (0, 255, 0) # ירוק
            
            # ציור הריבוע
            cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
            cv2.putText(frame, label_text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        cv2.imshow('Real YOLO Security', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

