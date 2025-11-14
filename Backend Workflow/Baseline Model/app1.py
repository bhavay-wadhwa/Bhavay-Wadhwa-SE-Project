from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import sqlite3
import os
import threading
import time
from datetime import datetime
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_PATH = os.path.join(BASE_DIR, "detections.db")

app = Flask(__name__, template_folder="Frontend-Files/templates", static_folder="Frontend-Files/static")
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory settings
settings = {
    "threshold": 2.0,     # meters (example)
    "alerts_enabled": True
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS detections
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, obj_type TEXT, distance REAL)''')
    conn.commit()
    conn.close()

def record_detection(obj_type, distance):
    ts = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO detections (ts, obj_type, distance) VALUES (?, ?, ?)", (ts, obj_type, distance))
    conn.commit()
    conn.close()
    return {"ts": ts, "obj_type": obj_type, "distance": distance}

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/stats')
def stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM detections")
    total = c.fetchone()[0]
    conn.close()
    return jsonify({"total_detections": total, "threshold": settings["threshold"], "alerts_enabled": settings["alerts_enabled"]})

@app.route('/history')
def history():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT ts, obj_type, distance FROM detections ORDER BY id DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"ts": r[0], "obj_type": r[1], "distance": r[2]} for r in rows])

@app.route('/set_threshold', methods=["POST"])
def set_threshold():
    data = request.json or {}
    try:
        t = float(data.get("threshold"))
        settings["threshold"] = t
        return jsonify({"ok": True, "threshold": settings["threshold"]})
    except Exception:
        return jsonify({"ok": False}), 400

@app.route('/toggle_alert', methods=["POST"])
def toggle_alert():
    data = request.json or {}
    enabled = bool(data.get("enabled"))
    settings["alerts_enabled"] = enabled
    return jsonify({"ok": True, "alerts_enabled": settings["alerts_enabled"]})

@app.route('/upload_photo', methods=["POST"])
def upload_photo():
    f = request.files.get("file")
    if not f:
        return "No file", 400
    filename = secure_filename(f.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    f.save(path)
    # Placeholder: analyze image -> here we simulate detection
    # In real app call your detector and get distance/object type
    simulated = simulate_detection_from_file(path)
    det = record_detection(simulated["obj_type"], simulated["distance"])
    # Emit via socket if below threshold and alerts enabled
    if settings["alerts_enabled"] and det["distance"] <= settings["threshold"]:
        socketio.emit('detection', det)
    return jsonify({"ok": True, "detection": det})

@app.route('/upload_video_feed', methods=["POST"])
def upload_video_feed():
    f = request.files.get("file")
    if not f:
        return "No file", 400
    filename = secure_filename(f.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    f.save(path)
    # In production you may spawn a background worker to process frames
    # Here we simulate multiple detections asynchronously
    threading.Thread(target=simulate_video_processing, args=(path,)).start()
    return jsonify({"ok": True, "message": "Video uploaded. Processing started."})

def simulate_detection_from_file(path):
    # Simple simulation: choose object and distance based on filename hash
    h = sum(bytearray(path.encode('utf-8'))) % 10
    obj = "pedestrian" if h % 2 == 0 else "vehicle"
    distance = round(0.5 + (h / 10.0) * 5.0, 2)
    return {"obj_type": obj, "distance": distance}

def simulate_video_processing(path):
    # Emit some simulated detections spaced over time
    for i in range(4):
        det = simulate_detection_from_file(path + str(i))
        rec = record_detection(det["obj_type"], det["distance"])
        if settings["alerts_enabled"] and rec["distance"] <= settings["threshold"]:
            socketio.emit('detection', rec)
        time.sleep(2)

@socketio.on('connect')
def handle_connect():
    emit('settings', settings)

if __name__ == '__main__':
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)