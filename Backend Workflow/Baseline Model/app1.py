import os
import time
import sqlite3
from queue import Queue, Empty
from threading import Thread
from datetime import datetime
from functools import lru_cache
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, jsonify
from flask_compress import Compress
from flask_socketio import SocketIO, emit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_PATH = os.path.join(BASE_DIR, "detections.db")

DB_POOL_MAX = 5
BACKGROUND_WORKERS = 3
TASK_QUEUE = Queue()
DB_POOL = Queue(maxsize=DB_POOL_MAX)

app = Flask(__name__, template_folder="Frontend-Files/templates", static_folder="Frontend-Files/static")
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")
Compress(app)

settings = {"threshold": 2.0, "alerts_enabled": True}
camera_active = False

def _create_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def initialize_db_pool():
    conn = _create_conn()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS detections (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, obj_type TEXT, distance REAL)')
    conn.commit()
    conn.close()
    for _ in range(DB_POOL_MAX):
        try:
            DB_POOL.put_nowait(_create_conn())
        except:
            break

def get_db_conn(timeout=0.01):
    try:
        conn = DB_POOL.get(timeout=timeout)
    except Empty:
        conn = _create_conn()
    return conn

def release_db_conn(conn):
    try:
        DB_POOL.put_nowait(conn)
    except:
        try:
            conn.close()
        except:
            pass

@lru_cache(maxsize=32)
def get_cached_total_detections():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM detections")
    total = c.fetchone()[0]
    release_db_conn(conn)
    return total

@lru_cache(maxsize=32)
def get_cached_history(limit=50):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT ts, obj_type, distance FROM detections ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    release_db_conn(conn)
    return tuple(rows)

def invalidate_caches():
    get_cached_total_detections.cache_clear()
    get_cached_history.cache_clear()

def worker():
    while True:
        func, args = TASK_QUEUE.get()
        try:
            func(*args)
        except Exception as e:
            print("[worker] Task error:", e)
        TASK_QUEUE.task_done()

for _ in range(BACKGROUND_WORKERS):
    t = Thread(target=worker, daemon=True)
    t.start()

def record_detection(obj_type, distance):
    ts = datetime.utcnow().isoformat()
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO detections (ts, obj_type, distance) VALUES (?, ?, ?)", (ts, obj_type, distance))
    conn.commit()
    release_db_conn(conn)
    invalidate_caches()
    return {"ts": ts, "obj_type": obj_type, "distance": distance}

def simulate_detection_from_file(path):
    h = sum(bytearray(path.encode('utf-8'))) % 100
    obj = "pedestrian" if (h % 2 == 0) else "vehicle"
    distance = round(0.5 + (h / 100.0) * 5.0, 2)
    return {"obj_type": obj, "distance": distance}

def process_video_async(path):
    for i in range(4):
        det = simulate_detection_from_file(path + str(i))
        rec = record_detection(det["obj_type"], det["distance"])
        if settings["alerts_enabled"] and rec["distance"] <= settings["threshold"]:
            socketio.emit('detection', rec)
        time.sleep(2)

@app.after_request
def add_cache_headers(response):
    response.headers["Cache-Control"] = "public, max-age=604800"
    return response

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/stats')
def stats():
    total = get_cached_total_detections()
    return jsonify({"total_detections": total, "threshold": settings["threshold"], "alerts_enabled": settings["alerts_enabled"]})

@app.route('/history')
def history():
    rows = get_cached_history(50)
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

@app.route('/toggle_camera', methods=['POST'])
def toggle_camera():
    global camera_active
    camera_active = not camera_active
    return ("Camera turned on" if camera_active else "Camera turned off"), 200

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
    simulated = simulate_detection_from_file(path)
    det = record_detection(simulated["obj_type"], simulated["distance"])
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
    TASK_QUEUE.put((process_video_async, (path,)))
    return jsonify({"ok": True, "message": "Video uploaded. Processing started."})

@socketio.on('connect')
def handle_connect():
    emit('settings', settings)

def _startup():
    initialize_db_pool()

if __name__ == '__main__':
    _startup()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)