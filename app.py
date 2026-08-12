from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import sqlite3
import os
import face_recognition
import numpy as np
import cv2
from datetime import datetime, timedelta
import json
from pathlib import Path
import base64
from io import BytesIO
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading

app = Flask(__name__)
CORS(app)

# Configuration
DATABASE = 'attendance.db'
FACES_DIR = 'known_faces'
UPLOAD_DIR = 'uploads'

# Create directories if they don't exist
os.makedirs(FACES_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Database initialization
def init_db():
    """Initialize database with required tables"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Students table
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        email TEXT,
        class_name TEXT,
        face_encoding BLOB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Attendance table
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        date DATE NOT NULL,
        time_in TIME,
        time_out TIME,
        status TEXT DEFAULT 'Present',
        FOREIGN KEY (student_id) REFERENCES students(student_id),
        UNIQUE(student_id, date)
    )''')
    
    # Notification logs
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        type TEXT,
        message TEXT,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(student_id)
    )''')
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

# Face encoding functions
def encode_face(image_path):
    """Encode a face image to get its face encoding"""
    image = face_recognition.load_image_file(image_path)
    encodings = face_recognition.face_encodings(image)
    if encodings:
        return encodings[0]
    return None

def load_known_faces():
    """Load all known face encodings from the faces directory"""
    known_encodings = []
    known_names = []
    
    for person_name in os.listdir(FACES_DIR):
        person_dir = os.path.join(FACES_DIR, person_name)
        if not os.path.isdir(person_dir):
            continue
            
        for image_name in os.listdir(person_dir):
            image_path = os.path.join(person_dir, image_name)
            encoding = encode_face(image_path)
            if encoding is not None:
                known_encodings.append(encoding)
                known_names.append(person_name)
    
    return known_encodings, known_names

# Database functions
def get_student(student_id):
    """Get student details from database"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM students WHERE student_id = ?', (student_id,))
    student = c.fetchone()
    conn.close()
    return student

def add_student(student_id, name, email, class_name, face_path):
    """Add a new student to the database"""
    try:
        encoding = encode_face(face_path)
        if encoding is None:
            return False, "No face detected in image"
        
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute('''INSERT INTO students (student_id, name, email, class_name, face_encoding)
                     VALUES (?, ?, ?, ?, ?)''',
                  (student_id, name, email, class_name, encoding.tobytes()))
        conn.commit()
        conn.close()
        
        # Save face image
        student_dir = os.path.join(FACES_DIR, student_id)
        os.makedirs(student_dir, exist_ok=True)
        cv2.imwrite(os.path.join(student_dir, f'{name}.jpg'), 
                   cv2.cvtColor(face_recognition.load_image_file(face_path), cv2.COLOR_RGB2BGR))
        
        return True, "Student added successfully"
    except sqlite3.IntegrityError:
        return False, "Student ID already exists"
    except Exception as e:
        return False, str(e)

def mark_attendance(student_id, date, time_in, status='Present'):
    """Mark attendance for a student"""
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        # Check if attendance already exists
        c.execute('SELECT id FROM attendance WHERE student_id = ? AND date = ?',
                 (student_id, date))
        existing = c.fetchone()
        
        if existing:
            c.execute('UPDATE attendance SET time_in = ?, status = ? WHERE student_id = ? AND date = ?',
                     (time_in, status, student_id, date))
        else:
            c.execute('''INSERT INTO attendance (student_id, date, time_in, status)
                        VALUES (?, ?, ?, ?)''',
                     (student_id, date, time_in, status))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        return False

def send_notification(student_id, message_type, message):
    """Send notification and log it"""
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute('''INSERT INTO notifications (student_id, type, message)
                     VALUES (?, ?, ?)''',
                 (student_id, message_type, message))
        conn.commit()
        
        # Get student email
        c.execute('SELECT email FROM students WHERE student_id = ?', (student_id,))
        result = c.fetchone()
        conn.close()
        
        if result and result[0]:
            # Send email in background thread
            thread = threading.Thread(target=send_email, args=(result[0], message_type, message))
            thread.daemon = True
            thread.start()
    except Exception as e:
        print(f"Notification error: {e}")

def send_email(email, message_type, message):
    """Send email notification (configure with your email settings)"""
    # This is a placeholder - configure with your email service
    pass

# API Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/students', methods=['GET'])
def get_students():
    """Get all students"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT id, student_id, name, email, class_name, created_at FROM students')
    students = c.fetchall()
    conn.close()
    
    return jsonify([{
        'id': s[0],
        'student_id': s[1],
        'name': s[2],
        'email': s[3],
        'class_name': s[4],
        'created_at': s[5]
    } for s in students])

@app.route('/api/students/add', methods=['POST'])
def add_student_api():
    """Add new student with face image"""
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'No image provided'}), 400
    
    file = request.files['image']
    student_id = request.form.get('student_id')
    name = request.form.get('name')
    email = request.form.get('email')
    class_name = request.form.get('class_name')
    
    if not all([student_id, name, class_name]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
    
    # Save uploaded file temporarily
    temp_path = os.path.join(UPLOAD_DIR, file.filename)
    file.save(temp_path)
    
    success, message = add_student(student_id, name, email, class_name, temp_path)
    
    # Clean up temp file
    if os.path.exists(temp_path):
        os.remove(temp_path)
    
    return jsonify({'success': success, 'message': message})

@app.route('/api/recognize', methods=['POST'])
def recognize_face():
    """Recognize face from uploaded image and mark attendance"""
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'No image provided'}), 400
    
    file = request.files['image']
    temp_path = os.path.join(UPLOAD_DIR, file.filename)
    file.save(temp_path)
    
    try:
        # Load image and get face encoding
        image = face_recognition.load_image_file(temp_path)
        face_encodings = face_recognition.face_encodings(image)
        
        if not face_encodings:
            return jsonify({'success': False, 'message': 'No face detected in image'}), 400
        
        # Load known faces
        known_encodings, known_names = load_known_faces()
        
        if not known_encodings:
            return jsonify({'success': False, 'message': 'No students registered yet'}), 400
        
        # Compare faces
        matches = face_recognition.compare_faces(known_encodings, face_encodings[0], tolerance=0.6)
        distances = face_recognition.face_distance(known_encodings, face_encodings[0])
        
        best_match_index = np.argmin(distances)
        
        if matches[best_match_index]:
            student_id = known_names[best_match_index]
            student = get_student(student_id)
            
            if student:
                # Mark attendance
                today = datetime.now().strftime('%Y-%m-%d')
                time_now = datetime.now().strftime('%H:%M:%S')
                
                mark_attendance(student_id, today, time_now)
                
                # Send notification
                send_notification(student_id, 'attendance', 
                                f'Attendance marked at {time_now}')
                
                return jsonify({
                    'success': True,
                    'message': f'Welcome {student[2]}',
                    'student': {
                        'id': student[0],
                        'student_id': student[1],
                        'name': student[2],
                        'class': student[4]
                    }
                })
        
        return jsonify({'success': False, 'message': 'Face not recognized'}), 401
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.route('/api/attendance/report', methods=['GET'])
def get_attendance_report():
    """Get attendance report"""
    date = request.args.get('date')
    class_name = request.args.get('class')
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    if date and class_name:
        c.execute('''SELECT s.student_id, s.name, s.class_name, a.date, a.time_in, a.status
                     FROM students s
                     LEFT JOIN attendance a ON s.student_id = a.student_id AND a.date = ?
                     WHERE s.class_name = ?
                     ORDER BY s.name''', (date, class_name))
    elif date:
        c.execute('''SELECT s.student_id, s.name, s.class_name, a.date, a.time_in, a.status
                     FROM students s
                     LEFT JOIN attendance a ON s.student_id = a.student_id AND a.date = ?
                     ORDER BY s.name''', (date,))
    else:
        c.execute('''SELECT s.student_id, s.name, s.class_name, a.date, a.time_in, a.status
                     FROM students s
                     LEFT JOIN attendance a ON s.student_id = a.student_id
                     ORDER BY s.name''')
    
    records = c.fetchall()
    conn.close()
    
    return jsonify([{
        'student_id': r[0],
        'name': r[1],
        'class': r[2],
        'date': r[3],
        'time_in': r[4],
        'status': r[5] or 'Absent'
    } for r in records])

@app.route('/api/attendance/summary', methods=['GET'])
def get_attendance_summary():
    """Get attendance summary by class"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('''SELECT s.class_name, COUNT(DISTINCT s.id) as total_students,
                 COUNT(DISTINCT CASE WHEN a.status = 'Present' THEN s.id END) as present_today
                 FROM students s
                 LEFT JOIN attendance a ON s.student_id = a.student_id 
                    AND a.date = DATE('now')
                 GROUP BY s.class_name''')
    
    summary = c.fetchall()
    conn.close()
    
    return jsonify([{
        'class': s[0],
        'total_students': s[1],
        'present_today': s[2] or 0,
        'absent_today': (s[1] - (s[2] or 0))
    } for s in summary])

@app.route('/api/student/<student_id>/history', methods=['GET'])
def get_student_history(student_id):
    """Get attendance history for a student"""
    days = request.args.get('days', 30, type=int)
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    date_from = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    c.execute('''SELECT date, time_in, status FROM attendance
                 WHERE student_id = ? AND date >= ?
                 ORDER BY date DESC''', (student_id, date_from))
    
    records = c.fetchall()
    conn.close()
    
    return jsonify([{
        'date': r[0],
        'time_in': r[1],
        'status': r[2]
    } for r in records])

@app.route('/api/classes', methods=['GET'])
def get_classes():
    """Get all unique classes"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT DISTINCT class_name FROM students ORDER BY class_name')
    classes = c.fetchall()
    conn.close()
    
    return jsonify([c[0] for c in classes])

if __name__ == '__main__':
    app.run(debug=True, port=5000)
