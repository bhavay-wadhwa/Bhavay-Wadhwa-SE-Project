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

# -------------------------
# Configuration
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_PATH = os.path.join(BASE_DIR, "detections.db")

# DB pool size and background workers
DB_POOL_MAX = 5
BACKGROUND_WORKERS = 3
TASK_QUEUE = Queue()
DB_POOL = Queue(maxsize=DB_POOL_MAX)

# Flask app + SocketIO
app = Flask(
    __name__,
    template_folder="Frontend-Files/templates",
    static_folder="Frontend-Files/static"
)
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
# Use eventlet/gevent if available; leave async_mode None to auto-select if you prefer.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# Response compression
Compress(app)

# In-memory settings
settings = {
    "threshold": 2.0,     # meters (example)
    "alerts_enabled": True
}

# -------------------------
# Database helpers & pool
# -------------------------
def _create_conn():
    # Important: check_same_thread=False so multiple threads can use connections from pool
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db_pool():
    """Create DB file and pre-populate pool with a couple of connections."""
    # Ensure DB file and table exist first
    conn = _create_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS detections
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, obj_type TEXT, distance REAL)''')
    conn.commit()
    conn.close()

    # Fill pool with a few connections
    for _ in range(DB_POOL_MAX):
        try:
            DB_POOL.put_nowait(_create_conn())
        except:
            break

def get_db_conn(timeout=0.01):
    """Get a connection from the pool or create a new one if pool empty."""
    try:
        conn = DB_POOL.get(timeout=timeout)
    except Empty:
        conn = _create_conn()
    return conn

def release_db_conn(conn):
    """Return connection back to pool if space available, else close."""
    try:
        DB_POOL.put_nowait(conn)
    except:
        try:
            conn.close()
        except:
            pass

# -------------------------
# Caching (with invalidation)
# -------------------------
@lru_cache(maxsize=32)
def cached_total_detections():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM detections")
    total = c.fetchone()[0]
    release_db_conn(conn)
    return total

@lru_cache(maxsize=32)
def cached_history(limit=50):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT ts, obj_type, distance FROM detections ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    release_db_conn(conn)
    return tuple(rows)  # immutable for caching

def clear_caches():
    cached_total_detections.cache_clear()
    cached_history.cache_clear()

# -------------------------
# Task queue + workers
# -------------------------
def worker():
    while True:
        func, args = TASK_QUEUE.get()
        try:
            func(*args)
        except Exception as e:
            # In production use proper logging
            print("[worker] Task error:", e)
        TASK_QUEUE.task_done()

for _ in range(BACKGROUND_WORKERS):
    t = Thread(target=worker, daemon=True)
    t.start()

# -------------------------
# Detection helpers
# -------------------------
def record_detection(obj_type, distance):
    """
    Record detection to DB and clear caches so stats/hist are fresh.
    Returns the detection dict.
    """
    ts = datetime.utcnow().isoformat()
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO detections (ts, obj_type, distance) VALUES (?, ?, ?)", (ts, obj_type, distance))
    conn.commit()
    release_db_conn(conn)

    # Invalidate caches so next /stats or /history returns updated data
    clear_caches()

    return {"ts": ts, "obj_type": obj_type, "distance": distance}

def simulate_detection_from_file(path):
    # Deterministic-ish simulation based on filename to mimic detection.
    h = sum(bytearray(path.encode('utf-8'))) % 100
    obj = "pedestrian" if (h % 2 == 0) else "vehicle"
    # produce a distance in [0.5, 5.5]
    distance = round(0.5 + (h / 100.0) * 5.0, 2)
    return {"obj_type": obj, "distance": distance}

def simulate_video_processing(path):
    # Simulate multiple detections spaced over time (this runs in background worker)
    for i in range(4):
        det = simulate_detection_from_file(path + str(i))
        rec = record_detection(det["obj_type"], det["distance"])
        if settings["alerts_enabled"] and rec["distance"] <= settings["threshold"]:
            # broadcast to connected clients
            socketio.emit('detection', rec)
        time.sleep(2)

# -------------------------
# Routes / Endpoints
# -------------------------
@app.after_request
def add_cache_headers(response):
    # Cache static assets aggressively on client side (tweak as needed)
    response.headers["Cache-Control"] = "public, max-age=604800"  # 7 days
    return response

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/stats')
def stats():
    # Use cached total; note caches are invalidated on every write
    total = cached_total_detections()
    return jsonify({"total_detections": total, "threshold": settings["threshold"], "alerts_enabled": settings["alerts_enabled"]})

@app.route('/history')
def history():
    rows = cached_history(50)
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

    # Simulated detection. Replace with your real detector call.
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

    # Queue background processing (non-blocking HTTP response)
    TASK_QUEUE.put((simulate_video_processing, (path,)))
    return jsonify({"ok": True, "message": "Video uploaded. Processing started."})

# -------------------------
# SocketIO handlers
# -------------------------
@socketio.on('connect')
def handle_connect():
    # Send current settings on connect
    emit('settings', settings)

# -------------------------
# App init & run
# -------------------------
def _startup():
    init_db_pool()

if __name__ == '__main__':
    _startup()
    # For development only. For production use Gunicorn + eventlet/gevent (see notes below).
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)

# -------------------------
# Deployment Notes (read me)
# -------------------------
# - This file uses `flask_compress` for gzip/deflate responses. Install:
#     pip install flask-compress
#
# - SocketIO async mode set to "eventlet". For best production support install:
#     pip install eventlet
#   OR
#     pip install gevent gevent-websocket
#
# - Production server examples (run from terminal):
#   With eventlet:
#     gunicorn -k eventlet -w 1 app:app
#
#   With gevent-websocket worker (if using gevent):
#     gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 4 app:app
#
# - Use Nginx as a reverse proxy for TLS, buffering/static file serving, and connection limits.
# - If you want distributed task processing or stronger durability:
#     • Replace TASK_QUEUE + worker threads with Celery + Redis/RabbitMQ.
#     • Use Redis for caching (instead of in-process lru_cache) if running multiple app instances.
#
# - Tweak DB_POOL_MAX and BACKGROUND_WORKERS according to available CPU/RAM.
#
# That's it — drop this in place of your previous file and run. If you'd like:
# - I can convert this to use Celery + Redis for scalable video processing,
# - Or swap the sqlite DB for PostgreSQL + connection pooling (psycopg2 / asyncpg).
#
# Tell me which further upgrade you'd like and I'll produce the code.
