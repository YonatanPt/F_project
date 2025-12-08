// יש לוודא שהקישור לספריית SocketIO נוסף ל-index.html:
// <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>

// כתובת ה-Backend שבה השרת רץ (כפי שהוגדר ב-main.py)
const socket = io('http://127.0.0.1:5000');
const alertsList = document.getElementById('alertsList');

// 1. קבלת הודעות התראה (האירוע 'new_alert' נשלח מ-main.py)
socket.on('new_alert', function (data) {
    const timestamp = data.timestamp;
    const listItem = document.createElement("li");
    listItem.classList.add("alert-item");

    // בונה את הודעת ההתראה
    listItem.innerHTML = `🚨 התראה חדשה: ID ${data.track_id} נשאר ${data.duration} באזור המסוכן (בשעה: ${timestamp})`;

    // הוספת ההתראה לראש הרשימה
    alertsList.prepend(listItem);
});

socket.on('connect', function () {
    console.log('Connected to backend via SocketIO');
});

socket.on('disconnect', function () {
    console.warn('Disconnected from backend');
});