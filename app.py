from flask import Flask, g, render_template, request, jsonify, session as staff_session
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import click
import sqlite3
import os
import re
import shutil
import logging
import face_recognition
import numpy as np
import cv2
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
from functools import wraps

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('presence')

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
DEBUG = os.getenv('FLASK_DEBUG', 'False' if FLASK_ENV == 'production' else 'True').lower() == 'true'
DATABASE = os.getenv('DATABASE_PATH', 'attendance.db')
FACES_DIR = os.getenv('FACES_FOLDER', 'known_faces').rstrip('/\\')
UPLOAD_DIR = os.getenv('UPLOAD_FOLDER', 'uploads').rstrip('/\\')
FACE_TOLERANCE = float(os.getenv('FACE_RECOGNITION_TOLERANCE', '0.6'))
MAX_UPLOAD_MB = float(os.getenv('MAX_UPLOAD_MB', '5'))
ALLOWED_EXTENSIONS = set(
    ext.strip().lower()
    for ext in os.getenv('ALLOWED_EXTENSIONS', 'jpg,jpeg,png,webp').split(',')
    if ext.strip()
)
CORS_ORIGINS = [o.strip() for o in os.getenv('CORS_ORIGINS', '*').split(',') if o.strip()]
ENABLE_EMAIL = os.getenv('ENABLE_EMAIL_NOTIFICATIONS', 'False').lower() == 'true'
MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.getenv('MAIL_PORT', '587'))
MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
HOST = os.getenv('HOST', '127.0.0.1')
PORT = int(os.getenv('PORT', '5000'))
FACE_CONSENT_VERSION = 'attendance-face-consent-v1'

if FLASK_ENV == 'production' and (
    len(SECRET_KEY) < 32
    or SECRET_KEY in (
        'dev-secret-key-change-me',
        'your-secret-key-here',
        'dev-secret-key',
        'change-this-to-a-long-random-string',
        'change-me-in-production-use-openssl-rand',
    )
):
    raise RuntimeError('Set a strong SECRET_KEY of at least 32 characters before running in production')

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = int(MAX_UPLOAD_MB * 1024 * 1024)
app.config['JSON_SORT_KEYS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = FLASK_ENV == 'production'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

if CORS_ORIGINS == ['*']:
    CORS(app)
else:
    CORS(app, origins=CORS_ORIGINS)

os.makedirs(FACES_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# In-memory face cache (encodings from DB)
_face_cache = {'encodings': None, 'ids': None, 'loaded_at': None}
_cache_lock = threading.Lock()


def get_db():
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        email TEXT,
        class_name TEXT,
        face_encoding BLOB,
        face_consent_at TEXT,
        face_consent_version TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    student_columns = {
        row['name'] for row in c.execute('PRAGMA table_info(students)').fetchall()
    }
    if 'face_consent_at' not in student_columns:
        c.execute('ALTER TABLE students ADD COLUMN face_consent_at TEXT')
    if 'face_consent_version' not in student_columns:
        c.execute('ALTER TABLE students ADD COLUMN face_consent_version TEXT')
    c.execute('''CREATE TABLE IF NOT EXISTS staff_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'teacher')),
        active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS class_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT NOT NULL,
        date DATE NOT NULL,
        started_at TEXT NOT NULL,
        grace_minutes INTEGER NOT NULL DEFAULT 10,
        ended_at TEXT
    )''')
    attendance_exists = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'attendance'"
    ).fetchone()
    if attendance_exists:
        attendance_columns = {
            row['name'] for row in c.execute('PRAGMA table_info(attendance)').fetchall()
        }
    else:
        attendance_columns = set()

    if attendance_exists and 'session_id' not in attendance_columns:
        c.execute('ALTER TABLE attendance RENAME TO attendance_legacy')

    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        date DATE NOT NULL,
        time_in TIME,
        time_out TIME,
        status TEXT DEFAULT 'Present',
        session_id INTEGER,
        FOREIGN KEY (student_id) REFERENCES students(student_id),
        FOREIGN KEY (session_id) REFERENCES class_sessions(id) ON DELETE CASCADE,
        UNIQUE(student_id, session_id)
    )''')
    if attendance_exists and 'session_id' not in attendance_columns:
        c.execute('''INSERT INTO attendance (id, student_id, date, time_in, time_out, status)
                     SELECT id, student_id, date, time_in, time_out, status
                     FROM attendance_legacy''')
        c.execute('DROP TABLE attendance_legacy')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        type TEXT,
        message TEXT,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(student_id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance(session_id)')
    c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_legacy_attendance_day
                 ON attendance(student_id, date) WHERE session_id IS NULL''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_sessions_class_date ON class_sessions(class_name, date)')
    c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_session_per_class
                 ON class_sessions(class_name, date) WHERE ended_at IS NULL''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_students_class ON students(class_name)')
    conn.commit()
    conn.close()


init_db()


def sanitize_id(value):
    if not value:
        return ''
    value = value.strip().replace('\\', '-').replace('/', '-')
    value = re.sub(r'[<>:"|?*\x00-\x1f]', '-', value)
    value = re.sub(r'[^A-Za-z0-9._-]+', '-', value)
    value = re.sub(r'-+', '-', value).strip(' .-')
    return value[:64]


def allowed_file(filename):
    if not filename or '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def safe_upload_path(filename):
    base = secure_filename(filename or 'capture.jpg') or 'capture.jpg'
    name, ext = os.path.splitext(base)
    if not ext or ext.lstrip('.').lower() not in ALLOWED_EXTENSIONS:
        ext = '.jpg'
    unique = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}{ext.lower()}"
    return os.path.join(UPLOAD_DIR, unique)


def encode_face(image_path):
    if not os.path.isfile(image_path):
        return None
    image = face_recognition.load_image_file(image_path)
    encodings = face_recognition.face_encodings(image)
    return encodings[0] if encodings else None


def invalidate_face_cache():
    with _cache_lock:
        _face_cache['encodings'] = None
        _face_cache['ids'] = None
        _face_cache['loaded_at'] = None


def load_known_faces():
    """Load encodings from DB (fast). Fall back to disk if blob missing."""
    with _cache_lock:
        cache_loaded = _face_cache['encodings'] is not None
        cached_encodings = _face_cache['encodings']
        cached_ids = _face_cache['ids']

    if cache_loaded:
        conn = get_db()
        authorized_ids = {
            row['student_id']
            for row in conn.execute(
                'SELECT student_id FROM students WHERE face_consent_at IS NOT NULL'
            ).fetchall()
        }
        conn.close()
        with _cache_lock:
            filtered = [
                (encoding, student_id)
                for encoding, student_id in zip(cached_encodings, cached_ids)
                if student_id in authorized_ids
            ]
            _face_cache['encodings'] = [encoding for encoding, _ in filtered]
            _face_cache['ids'] = [student_id for _, student_id in filtered]
            return _face_cache['encodings'], _face_cache['ids']

    known_encodings = []
    known_ids = []
    conn = get_db()
    rows = conn.execute(
        '''SELECT student_id, face_encoding FROM students
           WHERE face_encoding IS NOT NULL AND face_consent_at IS NOT NULL'''
    ).fetchall()
    authorized_ids = {
        row['student_id']
        for row in conn.execute(
            'SELECT student_id FROM students WHERE face_consent_at IS NOT NULL'
        ).fetchall()
    }
    conn.close()

    for row in rows:
        blob = row['face_encoding']
        if not blob:
            continue
        encoding = np.frombuffer(blob, dtype=np.float64)
        if encoding.size != 128:
            continue
        known_encodings.append(encoding)
        known_ids.append(row['student_id'])

    # Disk fallback for any student without a usable blob
    if not known_encodings and os.path.isdir(FACES_DIR):
        for person_name in os.listdir(FACES_DIR):
            person_dir = os.path.join(FACES_DIR, person_name)
            if person_name not in authorized_ids or not os.path.isdir(person_dir):
                continue
            for image_name in os.listdir(person_dir):
                image_path = os.path.join(person_dir, image_name)
                if not os.path.isfile(image_path):
                    continue
                encoding = encode_face(image_path)
                if encoding is not None:
                    known_encodings.append(encoding)
                    known_ids.append(person_name)

    with _cache_lock:
        _face_cache['encodings'] = known_encodings
        _face_cache['ids'] = known_ids
        _face_cache['loaded_at'] = datetime.utcnow()

    return known_encodings, known_ids


def get_student(student_id):
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM students WHERE student_id = ?', (student_id,)
    ).fetchone()
    conn.close()
    return row


def add_student(student_id, name, email, class_name, face_path, consent_confirmed=False):
    student_id = sanitize_id(student_id)
    name = (name or '').strip()
    class_name = (class_name or '').strip()
    email = (email or '').strip() or None

    if not student_id:
        return False, 'Invalid student ID (letters, numbers, dash/underscore only)'
    if not name:
        return False, 'Name is required'
    if not class_name:
        return False, 'Class is required'
    if not consent_confirmed:
        return False, 'Explicit face-data consent is required'
    if get_student(student_id):
        return False, 'Student ID already exists; use the roster to re-enroll the face'

    try:
        encoding = encode_face(face_path)
        if encoding is None:
            return False, 'No face detected in image'

        student_dir = os.path.join(FACES_DIR, student_id)
        os.makedirs(student_dir, exist_ok=True)
        face_save_path = os.path.join(student_dir, f'{student_id}.jpg')
        image = face_recognition.load_image_file(face_path)
        if not cv2.imwrite(face_save_path, cv2.cvtColor(image, cv2.COLOR_RGB2BGR)):
            return False, 'Failed to save face image'

        conn = get_db()
        try:
            conn.execute(
                '''INSERT INTO students (student_id, name, email, class_name, face_encoding)
                   VALUES (?, ?, ?, ?, ?)''',
                (student_id, name, email, class_name, encoding.tobytes()),
            )
            conn.execute(
                '''UPDATE students SET face_consent_at = ?, face_consent_version = ?
                   WHERE student_id = ?''',
                (
                    datetime.now().astimezone().isoformat(timespec='seconds'),
                    FACE_CONSENT_VERSION,
                    student_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        invalidate_face_cache()
        logger.info('Registered student %s (%s)', student_id, name)
        return True, 'Student added successfully'
    except sqlite3.IntegrityError:
        return False, 'Student ID already exists'
    except Exception as e:
        logger.exception('Failed to add student')
        return False, 'Registration failed' if FLASK_ENV == 'production' else str(e)


def update_student_face(student_id, face_path, consent_confirmed=False):
    student_id = sanitize_id(student_id)
    if not student_id:
        return False, 'Invalid student ID'
    if not consent_confirmed:
        return False, 'Explicit face-data consent is required'
    if not get_student(student_id):
        return False, 'Student not found'

    try:
        encoding = encode_face(face_path)
        if encoding is None:
            return False, 'No face detected in image'

        image = face_recognition.load_image_file(face_path)
        student_dir = os.path.join(FACES_DIR, student_id)
        os.makedirs(student_dir, exist_ok=True)
        face_save_path = os.path.join(student_dir, f'{student_id}.jpg')
        if not cv2.imwrite(face_save_path, cv2.cvtColor(image, cv2.COLOR_RGB2BGR)):
            return False, 'Failed to save face image'

        conn = get_db()
        try:
            conn.execute(
                '''UPDATE students
                   SET face_encoding = ?, face_consent_at = ?, face_consent_version = ?
                   WHERE student_id = ?''',
                (
                    encoding.tobytes(),
                    datetime.now().astimezone().isoformat(timespec='seconds'),
                    FACE_CONSENT_VERSION,
                    student_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        invalidate_face_cache()
        return True, 'Face data updated and consent recorded'
    except Exception as e:
        logger.exception('Failed to update face data for student %s', student_id)
        return False, 'Face data update failed' if FLASK_ENV == 'production' else str(e)


def mark_attendance(student_id, date, time_in, status='Present', time_out=None, session_id=None):
    try:
        conn = get_db()
        if session_id is not None:
            conn.execute(
                '''INSERT OR IGNORE INTO attendance
                   (student_id, date, time_in, time_out, status, session_id)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (student_id, date, time_in, time_out, status, session_id),
            )
            attendance = conn.execute(
                'SELECT status, time_in FROM attendance WHERE student_id = ? AND session_id = ?',
                (student_id, session_id),
            ).fetchone()
            conn.commit()
            return (True, attendance['status'], attendance['time_in']) if attendance else (False, None, None)

        existing = conn.execute(
            'SELECT id FROM attendance WHERE student_id = ? AND date = ? AND session_id IS NULL',
            (student_id, date),
        ).fetchone()
        if existing:
            conn.execute(
                'UPDATE attendance SET time_in = ?, time_out = COALESCE(?, time_out), status = ? WHERE student_id = ? AND date = ? AND session_id IS NULL',
                (time_in, time_out, status, student_id, date),
            )
        else:
            conn.execute(
                '''INSERT INTO attendance (student_id, date, time_in, time_out, status)
                   VALUES (?, ?, ?, ?, ?)''',
                (student_id, date, time_in, time_out, status),
            )
        conn.commit()
        return True, status, time_in
    except Exception:
        logger.exception('Failed to mark attendance')
        return False, None, None
    finally:
        if 'conn' in locals():
            conn.close()


def validate_date(value):
    if not value or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return False
    try:
        datetime.strptime(value, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def session_rows(date):
    conn = get_db()
    rows = conn.execute(
        '''SELECT cs.id, cs.class_name, cs.date, cs.started_at, cs.grace_minutes, cs.ended_at,
                  COUNT(DISTINCT s.student_id) AS enrolled_count,
                  COUNT(DISTINCT CASE WHEN a.status IN ('Present', 'Late') THEN a.student_id END) AS checked_in_count,
                  COUNT(DISTINCT CASE WHEN a.status = 'Late' THEN a.student_id END) AS late_count,
                  COUNT(DISTINCT CASE WHEN a.status = 'Absent' THEN a.student_id END) AS absent_count
           FROM class_sessions cs
           LEFT JOIN students s ON s.class_name = cs.class_name
           LEFT JOIN attendance a ON a.session_id = cs.id
           WHERE cs.date = ?
           GROUP BY cs.id
           ORDER BY cs.started_at DESC''',
        (date,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def check_out_student(student_id, date=None, time_out=None, session_id=None):
    student_id = sanitize_id(student_id)
    if not student_id:
        return False, 'Invalid student ID'
    if not time_out:
        time_out = datetime.now().strftime('%H:%M:%S')
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    try:
        conn = get_db()
        if session_id is not None:
            row = conn.execute(
                '''SELECT id FROM attendance
                   WHERE student_id = ? AND date = ? AND session_id = ?
                     AND session_id IN (
                         SELECT id FROM class_sessions WHERE ended_at IS NULL
                     )
                     AND status IN ('Present', 'Late')''',
                (student_id, date, session_id),
            ).fetchone()
        else:
            row = conn.execute(
                '''SELECT id FROM attendance
                   WHERE student_id = ? AND date = ? AND status IN ('Present', 'Late')
                     AND (
                         session_id IS NULL OR session_id IN (
                             SELECT id FROM class_sessions WHERE ended_at IS NULL
                         )
                     )
                   ORDER BY session_id DESC LIMIT 1''',
                (student_id, date),
            ).fetchone()
        if not row:
            conn.close()
            return False, 'No attendance record found for today'
        conn.execute(
            'UPDATE attendance SET time_out = ? WHERE id = ?',
            (time_out, row['id']),
        )
        conn.commit()
        conn.close()
        return True, 'Checked out successfully'
    except Exception:
        logger.exception('Failed to check out')
        return False, 'Check-out failed'


def send_notification(student_id, message_type, message):
    try:
        conn = get_db()
        conn.execute(
            '''INSERT INTO notifications (student_id, type, message)
               VALUES (?, ?, ?)''',
            (student_id, message_type, message),
        )
        conn.commit()
        row = conn.execute(
            'SELECT email FROM students WHERE student_id = ?', (student_id,)
        ).fetchone()
        conn.close()

        if row and row['email'] and ENABLE_EMAIL:
            thread = threading.Thread(
                target=send_email, args=(row['email'], message_type, message), daemon=True
            )
            thread.start()
    except Exception:
        logger.exception('Notification error')


def send_email(email, message_type, message):
    if not ENABLE_EMAIL or not MAIL_USERNAME or not MAIL_PASSWORD:
        return
    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_USERNAME
        msg['To'] = email
        msg['Subject'] = f'Presence — {message_type.title()}'
        msg.attach(MIMEText(message, 'plain'))
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=20) as server:
            if MAIL_USE_TLS:
                server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)
    except Exception:
        logger.exception('Email error')


def api_error(message, status=400):
    return jsonify({'success': False, 'message': message}), status


@app.before_request
def require_staff_api_session():
    if not request.path.startswith('/api/') or request.path == '/api/auth/login':
        return None

    origin = request.headers.get('Origin')
    if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
        return api_error('Cross-origin requests are not allowed', 403)

    user_id = staff_session.get('staff_user_id')
    if not user_id:
        return api_error('Sign in required', 401)

    conn = get_db()
    user = conn.execute(
        'SELECT id, username, role, active FROM staff_users WHERE id = ?',
        (user_id,),
    ).fetchone()
    conn.close()
    if not user or not user['active']:
        staff_session.clear()
        return api_error('Sign in required', 401)

    g.staff_user = dict(user)
    return None


def require_role(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.staff_user['role'] not in roles:
                return api_error('Insufficient permissions', 403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.cli.command('create-admin')
def create_admin_command():
    """Create an administrator account from the command line."""
    username = click.prompt('Admin username').strip().lower()
    if not re.fullmatch(r'[a-zA-Z0-9._-]{3,64}', username):
        raise click.ClickException('Use 3-64 letters, numbers, dots, dashes, or underscores.')

    password = click.prompt('Admin password', hide_input=True, confirmation_prompt=True)
    if len(password) < 12:
        raise click.ClickException('Password must be at least 12 characters.')

    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO staff_users (username, password_hash, role) VALUES (?, ?, ?)',
            (username, generate_password_hash(password), 'admin'),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise click.ClickException('That username already exists.')
    finally:
        conn.close()
    click.echo(f'Administrator "{username}" created.')


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html', app_name='Presence')


@app.route('/health')
def health():
    db_ok = False
    try:
        conn = get_db()
        conn.execute('SELECT 1')
        conn.close()
        db_ok = True
    except Exception:
        logger.exception('Health check DB failed')

    status = 200 if db_ok else 503
    return jsonify({
        'status': 'ok' if db_ok else 'degraded',
        'database': db_ok,
        'env': FLASK_ENV,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }), status


@app.route('/api/auth/login', methods=['POST'])
def staff_login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_error('Request body must be a JSON object')
    raw_username = payload.get('username')
    password = payload.get('password')
    if not isinstance(raw_username, str) or not isinstance(password, str):
        return api_error('Username and password are required')
    username = raw_username.strip().lower()
    if not username or not password:
        return api_error('Username and password are required')

    conn = get_db()
    user = conn.execute(
        'SELECT id, username, password_hash, role, active FROM staff_users WHERE username = ?',
        (username,),
    ).fetchone()
    conn.close()
    if not user or not user['active'] or not check_password_hash(user['password_hash'], password):
        return api_error('Invalid username or password', 401)

    staff_session.clear()
    staff_session['staff_user_id'] = user['id']
    staff_session.permanent = True
    return jsonify({
        'success': True,
        'user': {'id': user['id'], 'username': user['username'], 'role': user['role']},
    })


@app.route('/api/auth/logout', methods=['POST'])
def staff_logout():
    staff_session.clear()
    return jsonify({'success': True})


@app.route('/api/auth/me', methods=['GET'])
def staff_me():
    return jsonify({
        'user': {
            'id': g.staff_user['id'],
            'username': g.staff_user['username'],
            'role': g.staff_user['role'],
        },
    })


@app.route('/api/admin/users', methods=['GET'])
@require_role('admin')
def list_staff_users():
    conn = get_db()
    users = conn.execute(
        'SELECT id, username, role, active, created_at FROM staff_users ORDER BY username'
    ).fetchall()
    conn.close()
    return jsonify([dict(user) for user in users])


@app.route('/api/admin/users', methods=['POST'])
@require_role('admin')
def create_teacher():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_error('Request body must be a JSON object')
    raw_username = payload.get('username')
    password = payload.get('password')
    if not isinstance(raw_username, str) or not isinstance(password, str):
        return api_error('Username and password are required')
    username = raw_username.strip().lower()
    if not re.fullmatch(r'[a-zA-Z0-9._-]{3,64}', username):
        return api_error('Username must be 3-64 letters, numbers, dots, dashes, or underscores')
    if len(password) < 12:
        return api_error('Password must be at least 12 characters')

    conn = get_db()
    try:
        cursor = conn.execute(
            'INSERT INTO staff_users (username, password_hash, role) VALUES (?, ?, ?)',
            (username, generate_password_hash(password), 'teacher'),
        )
        conn.commit()
        user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        return api_error('That username already exists', 409)
    finally:
        conn.close()
    return jsonify({
        'success': True,
        'user': {'id': user_id, 'username': username, 'role': 'teacher'},
    }), 201


@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    date = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')
    if not validate_date(date):
        return api_error('date must use YYYY-MM-DD format')
    return jsonify(session_rows(date))


@app.route('/api/sessions', methods=['POST'])
def start_session():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return api_error('Request body must be a JSON object')
    class_name = (payload.get('class_name') or '').strip()
    grace_minutes = payload.get('grace_minutes', 10)
    if not class_name:
        return api_error('class_name is required')
    if isinstance(grace_minutes, bool) or not str(grace_minutes).isdigit():
        return api_error('grace_minutes must be a whole number from 0 to 120')
    grace_minutes = int(grace_minutes)
    if not 0 <= grace_minutes <= 120:
        return api_error('grace_minutes must be a whole number from 0 to 120')

    now = datetime.now().astimezone()
    conn = get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        class_exists = conn.execute(
            'SELECT 1 FROM students WHERE class_name = ? LIMIT 1', (class_name,)
        ).fetchone()
        if not class_exists:
            conn.rollback()
            return api_error('No registered students found for this class', 404)
        active = conn.execute(
            'SELECT id FROM class_sessions WHERE class_name = ? AND date = ? AND ended_at IS NULL',
            (class_name, now.strftime('%Y-%m-%d')),
        ).fetchone()
        if active:
            conn.rollback()
            return api_error('This class already has an active session', 409)
        cursor = conn.execute(
            '''INSERT INTO class_sessions (class_name, date, started_at, grace_minutes)
               VALUES (?, ?, ?, ?)''',
            (class_name, now.strftime('%Y-%m-%d'), now.isoformat(timespec='seconds'), grace_minutes),
        )
        session_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        return api_error('This class already has an active session', 409)
    except Exception:
        conn.rollback()
        logger.exception('Failed to start class session')
        return api_error('Could not start class session', 500)
    finally:
        conn.close()

    return jsonify({
        'success': True,
        'session': {
            'id': session_id,
            'class_name': class_name,
            'date': now.strftime('%Y-%m-%d'),
            'started_at': now.isoformat(timespec='seconds'),
            'grace_minutes': grace_minutes,
            'ended_at': None,
        },
    }), 201


@app.route('/api/sessions/<int:session_id>/close', methods=['POST'])
def close_session(session_id):
    now = datetime.now().astimezone().isoformat(timespec='seconds')
    conn = get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        session = conn.execute(
            'SELECT id, class_name, date, ended_at FROM class_sessions WHERE id = ?',
            (session_id,),
        ).fetchone()
        if not session:
            conn.rollback()
            return api_error('Session not found', 404)
        if session['ended_at']:
            conn.rollback()
            return api_error('Session is already closed', 409)

        conn.execute(
            '''INSERT OR IGNORE INTO attendance
               (student_id, date, status, session_id)
               SELECT s.student_id, ?, 'Absent', ?
               FROM students s
               WHERE s.class_name = ?
                 AND NOT EXISTS (
                     SELECT 1 FROM attendance a
                     WHERE a.student_id = s.student_id AND a.session_id = ?
                 )''',
            (session['date'], session_id, session['class_name'], session_id),
        )
        conn.execute(
            'UPDATE class_sessions SET ended_at = ? WHERE id = ?',
            (now, session_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception('Failed to close class session %s', session_id)
        return api_error('Could not close class session', 500)
    finally:
        conn.close()

    return jsonify({
        'success': True,
        'message': 'Session closed and absences recorded',
        'sessions': session_rows(session['date']),
    })


@app.route('/api/students', methods=['GET'])
@require_role('admin')
def get_students():
    conn = get_db()
    students = conn.execute(
        '''SELECT id, student_id, name, email, class_name, face_consent_at,
                  face_encoding IS NOT NULL AS has_encoding, created_at
           FROM students ORDER BY name'''
    ).fetchall()
    conn.close()
    result = []
    for student in students:
        row = dict(student)
        student_dir = os.path.join(FACES_DIR, sanitize_id(row['student_id']))
        row['face_data_present'] = bool(row.pop('has_encoding') or os.path.lexists(student_dir))
        result.append(row)
    return jsonify(result)


@app.route('/api/students/add', methods=['POST'])
@require_role('admin')
def add_student_api():
    if 'image' not in request.files:
        return api_error('No image provided')

    file = request.files['image']
    if not file or not file.filename:
        return api_error('No image provided')
    if not allowed_file(file.filename):
        return api_error(f'Invalid file type. Allowed: {", ".join(sorted(ALLOWED_EXTENSIONS))}')

    student_id = request.form.get('student_id')
    name = request.form.get('name')
    email = request.form.get('email')
    class_name = request.form.get('class_name')

    if not all([student_id, name, class_name]):
        return api_error('Missing required fields')
    if request.form.get('face_consent') != 'true':
        return api_error('Explicit face-data consent is required')

    student_id = sanitize_id(student_id)
    if not student_id:
        return api_error('Invalid student ID. Use letters, numbers, dash or underscore (no / or \\).')

    temp_path = safe_upload_path(file.filename)
    try:
        file.save(temp_path)
        success, message = add_student(
            student_id,
            name,
            email,
            class_name,
            temp_path,
            consent_confirmed=True,
        )
        status = 200 if success else 400
        return jsonify({'success': success, 'message': message}), status
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route('/api/students/<student_id>/face-data', methods=['POST'])
@require_role('admin')
def re_enroll_student_face(student_id):
    if request.form.get('face_consent') != 'true':
        return api_error('Explicit face-data consent is required')
    file = request.files.get('image')
    if not file or not file.filename:
        return api_error('No image provided')
    if not allowed_file(file.filename):
        return api_error(f'Invalid file type. Allowed: {", ".join(sorted(ALLOWED_EXTENSIONS))}')

    temp_path = safe_upload_path(file.filename)
    try:
        file.save(temp_path)
        success, message = update_student_face(
            student_id,
            temp_path,
            consent_confirmed=True,
        )
        return jsonify({'success': success, 'message': message}), 200 if success else 400
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route('/api/students/<student_id>/face-data', methods=['DELETE'])
@require_role('admin')
def delete_student_face(student_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get('confirm') is not True:
        return api_error('Explicit confirmation is required to delete face data')
    student_id = sanitize_id(student_id)
    if not student_id:
        return api_error('Invalid student ID')

    conn = get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        student = conn.execute(
            'SELECT student_id FROM students WHERE student_id = ?',
            (student_id,),
        ).fetchone()
        if not student:
            conn.rollback()
            return api_error('Student not found', 404)
        conn.execute(
            '''UPDATE students
               SET face_encoding = NULL, face_consent_at = NULL, face_consent_version = NULL
               WHERE student_id = ?''',
            (student_id,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception('Failed to revoke face data for student %s', student_id)
        return api_error('Could not revoke face data', 500)
    finally:
        conn.close()

    invalidate_face_cache()
    faces_root = os.path.abspath(FACES_DIR)
    student_dir = os.path.abspath(os.path.join(FACES_DIR, student_id))
    try:
        if os.path.commonpath([faces_root, student_dir]) != faces_root:
            raise ValueError('Student face directory is outside the face storage directory')
        if os.path.islink(student_dir) or os.path.isfile(student_dir):
            os.remove(student_dir)
        elif os.path.isdir(student_dir):
            shutil.rmtree(student_dir)
    except Exception:
        logger.exception('Face data revoked but image files could not be fully removed for %s', student_id)
        return jsonify({
            'success': False,
            'face_data_inactive': True,
            'message': 'Recognition is disabled, but stored face files could not be fully deleted. Contact the system administrator.',
        }), 500

    return jsonify({
        'success': True,
        'message': 'Face image, encoding, and consent record deleted; attendance history was retained.',
    })


@app.route('/api/recognize', methods=['POST'])
def recognize_face():
    if 'image' not in request.files:
        return api_error('No image provided')

    file = request.files['image']
    if not file or not file.filename:
        return api_error('No image provided')

    temp_path = safe_upload_path(file.filename or 'capture.jpg')
    try:
        file.save(temp_path)
        image = face_recognition.load_image_file(temp_path)
        face_encodings = face_recognition.face_encodings(image)

        if not face_encodings:
            return api_error('No face detected in image')

        known_encodings, known_ids = load_known_faces()
        if not known_encodings:
            return api_error('No students registered yet')

        distances = face_recognition.face_distance(known_encodings, face_encodings[0])
        best_match_index = int(np.argmin(distances))
        best_distance = float(distances[best_match_index])
        matches = face_recognition.compare_faces(
            known_encodings, face_encodings[0], tolerance=FACE_TOLERANCE
        )

        if matches[best_match_index]:
            student_id = known_ids[best_match_index]
            student = get_student(student_id)
            if student:
                if not student['face_consent_at']:
                    return api_error('Face recognition consent is not active', 403)
                now = datetime.now().astimezone()
                today = now.strftime('%Y-%m-%d')
                conn = get_db()
                session = conn.execute(
                    '''SELECT id, started_at, grace_minutes FROM class_sessions
                       WHERE class_name = ? AND date = ? AND ended_at IS NULL''',
                    (student['class_name'], today),
                ).fetchone()
                conn.close()
                if not session:
                    return api_error(
                        'No active session for this class. Ask the teacher to start one.',
                        409,
                    )

                session_start = datetime.fromisoformat(session['started_at'])
                time_now = now.strftime('%H:%M:%S')
                grace_ends = session_start + timedelta(minutes=session['grace_minutes'])
                attendance_status = 'Late' if now >= grace_ends else 'Present'
                marked, attendance_status, time_now = mark_attendance(
                    student_id,
                    today,
                    time_now,
                    status=attendance_status,
                    session_id=session['id'],
                )
                if not marked:
                    return api_error('Could not save attendance', 500)
                send_notification(student_id, 'attendance', f'Attendance marked at {time_now}')
                return jsonify({
                    'success': True,
                    'message': f"Welcome {student['name']} — {attendance_status.lower()}",
                    'attendance_status': attendance_status,
                    'session_id': session['id'],
                    'confidence': round(max(0.0, 1.0 - best_distance), 3),
                    'student': {
                        'id': student['id'],
                        'student_id': student['student_id'],
                        'name': student['name'],
                        'class': student['class_name'],
                    },
                })

        return api_error('Face not recognized', 401)
    except Exception as e:
        logger.exception('Recognition failed')
        msg = 'Recognition failed' if FLASK_ENV == 'production' else str(e)
        return api_error(msg, 500)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route('/api/attendance/report', methods=['GET'])
def get_attendance_report():
    date = request.args.get('date')
    class_name = request.args.get('class')
    raw_session_id = request.args.get('session_id')
    if raw_session_id and not raw_session_id.isdigit():
        return api_error('session_id must be a positive integer')
    session_id = int(raw_session_id) if raw_session_id else None
    if date and not validate_date(date):
        return api_error('date must use YYYY-MM-DD format')

    conn = get_db()
    if session_id is not None:
        session = conn.execute(
            'SELECT class_name, date FROM class_sessions WHERE id = ?', (session_id,)
        ).fetchone()
        if not session:
            conn.close()
            return api_error('Session not found', 404)
        if date and date != session['date']:
            conn.close()
            return api_error('Session does not belong to the selected date')
        conditions = ['s.class_name = ?']
        params = [session['date'], session_id, session['class_name']]
        if class_name:
            conditions.append('s.class_name = ?')
            params.append(class_name)
        rows = conn.execute(
            f'''SELECT s.student_id, s.name, s.class_name AS class, ? AS date,
                       a.time_in, COALESCE(a.status, 'Absent') AS status
                FROM students s
                LEFT JOIN attendance a
                  ON a.student_id = s.student_id AND a.session_id = ?
                WHERE {' AND '.join(conditions)}
                ORDER BY s.name''',
            params,
        ).fetchall()
    else:
        attendance_filter = 'WHERE date = ?' if date else ''
        attendance_params = [date] if date else []
        conditions = []
        params = []
        if class_name:
            conditions.append('s.class_name = ?')
            params.append(class_name)
        rows = conn.execute(
            f'''SELECT s.student_id, s.name, s.class_name AS class,
                       COALESCE(a.date, ?) AS date, a.time_in,
                       COALESCE(a.status, 'Absent') AS status
                FROM students s
                LEFT JOIN (
                    SELECT student_id, date, MIN(time_in) AS time_in,
                           CASE MAX(CASE status WHEN 'Late' THEN 2
                                                WHEN 'Present' THEN 1 ELSE 0 END)
                               WHEN 2 THEN 'Late' WHEN 1 THEN 'Present' ELSE 'Absent' END AS status
                    FROM attendance
                    {attendance_filter}
                    GROUP BY student_id, date
                ) a ON a.student_id = s.student_id
                {f"WHERE {' AND '.join(conditions)}" if conditions else ''}
                ORDER BY s.name''',
            [date, *attendance_params, *params],
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/attendance/summary', methods=['GET'])
def get_attendance_summary():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    rows = conn.execute(
        '''SELECT s.class_name AS class,
                  COUNT(DISTINCT s.id) AS total_students,
                  COUNT(DISTINCT CASE WHEN a.status IN ('Present', 'Late') THEN s.id END) AS present_today
           FROM students s
           LEFT JOIN attendance a ON s.student_id = a.student_id AND a.date = ?
           GROUP BY s.class_name
           ORDER BY s.class_name''',
        (today,),
    ).fetchall()
    conn.close()

    return jsonify([{
        'class': r['class'],
        'total_students': r['total_students'],
        'present_today': r['present_today'] or 0,
        'absent_today': r['total_students'] - (r['present_today'] or 0),
    } for r in rows])


@app.route('/api/attendance/check-out', methods=['POST'])
def check_out_api():
    payload = request.get_json(silent=True) or request.form.to_dict(flat=True)
    if not isinstance(payload, dict):
        return api_error('Request body must be an object', 400)
    student_id = (payload or {}).get('student_id') or request.form.get('student_id')
    time_out = (payload or {}).get('time_out') or request.form.get('time_out')
    raw_session_id = (payload or {}).get('session_id')

    if not student_id:
        return api_error('student_id is required', 400)
    if raw_session_id is not None and not str(raw_session_id).isdigit():
        return api_error('session_id must be a positive integer', 400)

    session_id = int(raw_session_id) if raw_session_id is not None else None
    success, message = check_out_student(
        student_id,
        time_out=time_out,
        session_id=session_id,
    )
    if not success:
        return api_error(message, 400)

    return jsonify({
        'success': True,
        'message': message,
        'student_id': sanitize_id(student_id),
        'time_out': time_out or datetime.now().strftime('%H:%M:%S'),
        'session_id': session_id,
    })


@app.route('/api/student/<student_id>/history', methods=['GET'])
def get_student_history(student_id):
    days = request.args.get('days', 30, type=int)
    days = max(1, min(days, 365))
    date_from = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    conn = get_db()
    rows = conn.execute(
        '''SELECT date, time_in, time_out, status FROM attendance
           WHERE student_id = ? AND date >= ?
           ORDER BY date DESC''',
        (sanitize_id(student_id), date_from),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/classes', methods=['GET'])
def get_classes():
    conn = get_db()
    rows = conn.execute(
        'SELECT DISTINCT class_name FROM students WHERE class_name IS NOT NULL ORDER BY class_name'
    ).fetchall()
    conn.close()
    return jsonify([r['class_name'] for r in rows])


@app.errorhandler(413)
def too_large(_e):
    return api_error(f'File too large. Max {MAX_UPLOAD_MB}MB', 413)


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith('/api/'):
        return api_error('Not found', 404)
    return render_template('index.html', app_name='Presence'), 404


@app.errorhandler(500)
def server_error(_e):
    logger.exception('Unhandled server error')
    return api_error('Internal server error', 500)


if __name__ == '__main__':
    if FLASK_ENV == 'production':
        from waitress import serve
        logger.info('Presence starting (production) on %s:%s', HOST, PORT)
        serve(app, host=HOST, port=PORT, threads=4)
    else:
        logger.info('Presence starting (development) on %s:%s', HOST, PORT)
        app.run(debug=DEBUG, host=HOST, port=PORT)
