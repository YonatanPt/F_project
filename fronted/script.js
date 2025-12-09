//// יש לוודא שהקישור לספריית SocketIO נוסף ל-index.html:
//// <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>

//// כתובת ה-Backend שבה השרת רץ (כפי שהוגדר ב-main.py)
//const socket = io('http://127.0.0.1:5000');
//const alertsList = document.getElementById('alertsList');

//// 1. קבלת הודעות התראה (האירוע 'new_alert' נשלח מ-main.py)
//socket.on('new_alert', function (data) {
//    const timestamp = data.timestamp;
//    const listItem = document.createElement("li");
//    listItem.classList.add("alert-item");

//    // בונה את הודעת ההתראה
//    listItem.innerHTML = `🚨 התראה חדשה: ID ${data.track_id} נשאר ${data.duration} באזור המסוכן (בשעה: ${timestamp})`;

//    // הוספת ההתראה לראש הרשימה
//    alertsList.prepend(listItem);
//});

//socket.on('connect', function () {
//    console.log('Connected to backend via SocketIO');
//});

//socket.on('disconnect', function () {
//    console.warn('Disconnected from backend');
//});


// script.js - קוד משודרג להצגת תמונה ועיצוב

// יש לוודא שהקישור לספריית SocketIO נוסף ל-index.html:
// <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>

// כתובת ה-Backend שבה השרת רץ (כפי שהוגדר ב-main.py)
const SOCKET_URL = 'http://127.0.0.1:5000';
const socket = io(SOCKET_URL);
const alertsList = document.getElementById('alertsList');

let alertCounter = 0; // מונה התראות חזותי

// 1. קבלת הודעות התראה (האירוע 'new_alert' נשלח מ-main.py)
socket.on('new_alert', function (data) {
    alertCounter++;
    const timestamp = data.timestamp;

    // יצירת פריט רשימה חדש
    const listItem = document.createElement("li");
    // מוסיף את הקלאס שהוגדר ב-CSS לעיצוב יפה יותר
    listItem.classList.add("alert-item");

    // ******************************************************************************************
    // בניית נתיב התמונה - זהו החלק הקריטי:
    // הנחה: ה-Backend שומר קובץ בפורמט: alert_id[ID]_[YYYYMMDD]_[HHMMSS].jpg
    // וה-Flask app הוגדר לשרת את הקבצים תחת הנתיב /alert_images/
    //
    // בניית שם הקובץ:
    const now = new Date();
    // יצירת פורמט תאריך YYYYMMDD:
    const datePart = now.getFullYear().toString() + (now.getMonth() + 1).toString().padStart(2, '0') + now.getDate().toString().padStart(2, '0');
    // יצירת פורמט זמן HHMMSS (בלי הנקודות):
    const timePart = timestamp.replace(/:/g, '');

    // שימו לב: יש לוודא שה-Backend משתמש בפורמט זהה (ID_YYYYMMDD_HHMMSS.jpg)!
    const filename = `alert_id${data.track_id}_${datePart}_${timePart}.jpg`;
    const imageUrl = `${SOCKET_URL}/alert_images/${filename}`;
    // ******************************************************************************************

    // בונה את הודעת ההתראה עם כל הפרטים והתמונה (משתמש בקלאסים מה-CSS המעוצב)
    listItem.innerHTML = `
        <div class="alert-header">
            <span class="alert-count">#${alertCounter}</span>
            <span class="alert-title">🚨 התראה: חדירה לאזור מסוכן</span>
        </div>
        <div class="alert-details">
            <p><strong>מזהה אובייקט (ID):</strong> ${data.track_id}</p>
            <p><strong>משך זמן באזור:</strong> ${data.duration}</p>
            <p class="alert-timestamp">זמן: ${timestamp}</p>
        </div>
        <div class="alert-image-container">
            <img src="${imageUrl}" 
                 alt="צילום התראה - ID ${data.track_id}" 
                 class="alert-screenshot"
                 onerror="this.onerror=null; this.src='placeholder.jpg'; this.alt='תמונה לא נמצאה';">
        </div>
    `;

    // הוספת ההתראה לראש הרשימה
    alertsList.prepend(listItem);
});

socket.on('connect', function () {
    console.log('✅ Connected to backend via SocketIO');
});

socket.on('disconnect', function () {
    console.warn('❌ Disconnected from backend');
});