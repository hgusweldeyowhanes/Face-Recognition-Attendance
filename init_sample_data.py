"""
Sample Data Initialization Script
This script populates the database with sample students for testing.
Run this AFTER creating student face photos in the known_faces/ folder.
"""

import sqlite3
import os
from datetime import datetime, timedelta
import face_recognition
import numpy as np

DATABASE = 'attendance.db'
FACES_DIR = 'known_faces'

def init_database():
    """Create database tables if they don't exist"""
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

def add_sample_student(student_id, name, email, class_name):
    """Add a sample student without face encoding (for testing)"""
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        # Create a dummy face encoding for testing
        dummy_encoding = np.random.randn(128).tobytes()
        
        c.execute('''INSERT INTO students (student_id, name, email, class_name, face_encoding)
                     VALUES (?, ?, ?, ?, ?)''',
                  (student_id, name, email, class_name, dummy_encoding))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        print(f"⚠️  Student {student_id} already exists, skipping...")
        return False

def add_sample_attendance(student_id, num_days=30):
    """Add sample attendance records for the past N days"""
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        base_date = datetime.now()
        
        for i in range(num_days):
            # Skip weekends for more realistic data
            current_date = base_date - timedelta(days=i)
            
            # Skip Sundays (6) and Saturdays (5) occasionally
            if current_date.weekday() >= 5 and np.random.random() > 0.3:
                continue
            
            # 90% chance of being present
            if np.random.random() < 0.9:
                status = 'Present'
                hour = np.random.randint(8, 11)
                minute = np.random.randint(0, 60)
                time_in = f"{hour:02d}:{minute:02d}:00"
            else:
                status = 'Absent'
                time_in = None
            
            date_str = current_date.strftime('%Y-%m-%d')
            
            try:
                c.execute('''INSERT INTO attendance 
                             (student_id, date, time_in, status)
                             VALUES (?, ?, ?, ?)''',
                         (student_id, date_str, time_in, status))
            except sqlite3.IntegrityError:
                # Record already exists, skip
                pass
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error adding attendance for {student_id}: {e}")
        return False

def main():
    """Initialize database with sample data"""
    
    print("🎓 Face Recognition Attendance System - Sample Data Initialization")
    print("=" * 60)
    
    # Initialize database
    print("\n📦 Initializing database...")
    init_database()
    print("✅ Database initialized")
    
    # Sample students data
    sample_students = [
        # Class 10-A
        ('STU001', 'Aarav Patel', 'aarav.patel@school.edu', '10-A'),
        ('STU002', 'Bhavna Singh', 'bhavna.singh@school.edu', '10-A'),
        ('STU003', 'Chirag Kumar', 'chirag.kumar@school.edu', '10-A'),
        ('STU004', 'Deepika Sharma', 'deepika.sharma@school.edu', '10-A'),
        ('STU005', 'Esha Gupta', 'esha.gupta@school.edu', '10-A'),
        
        # Class 10-B
        ('STU006', 'Fahad Ali', 'fahad.ali@school.edu', '10-B'),
        ('STU007', 'Gita Reddy', 'gita.reddy@school.edu', '10-B'),
        ('STU008', 'Harsh Verma', 'harsh.verma@school.edu', '10-B'),
        ('STU009', 'Ishita Nair', 'ishita.nair@school.edu', '10-B'),
        ('STU010', 'Jatin Malhotra', 'jatin.malhotra@school.edu', '10-B'),
        
        # Class 11-A
        ('STU011', 'Kavya Iyer', 'kavya.iyer@school.edu', '11-A'),
        ('STU012', 'Lav Saxena', 'lav.saxena@school.edu', '11-A'),
        ('STU013', 'Meera Kapoor', 'meera.kapoor@school.edu', '11-A'),
        ('STU014', 'Nikhil Chopra', 'nikhil.chopra@school.edu', '11-A'),
        ('STU015', 'Olivia D\'souza', 'olivia.dsouza@school.edu', '11-A'),
        
        # Class 11-B
        ('STU016', 'Priya Bhat', 'priya.bhat@school.edu', '11-B'),
        ('STU017', 'Qasim Khan', 'qasim.khan@school.edu', '11-B'),
        ('STU018', 'Rhea Kulkarni', 'rhea.kulkarni@school.edu', '11-B'),
        ('STU019', 'Samir Desai', 'samir.desai@school.edu', '11-B'),
        ('STU020', 'Tara Pillai', 'tara.pillai@school.edu', '11-B'),
    ]
    
    # Add sample students
    print("\n👥 Adding sample students...")
    added_count = 0
    for student_id, name, email, class_name in sample_students:
        if add_sample_student(student_id, name, email, class_name):
            print(f"✅ Added: {student_id} - {name} ({class_name})")
            added_count += 1
        else:
            print(f"⏭️  Skipped: {student_id} - {name}")
    
    print(f"\n📊 Total students added: {added_count}")
    
    # Add sample attendance data
    print("\n📅 Adding sample attendance records (past 30 days)...")
    
    for student_id, name, _, _ in sample_students:
        add_sample_attendance(student_id, num_days=30)
        print(f"✅ Added attendance for {student_id} - {name}")
    
    # Print statistics
    print("\n📈 Database Statistics:")
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM students')
    student_count = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM attendance')
    attendance_count = c.fetchone()[0]
    
    c.execute('SELECT DISTINCT class_name FROM students')
    classes = [row[0] for row in c.fetchall()]
    
    c.execute('SELECT COUNT(*) FROM attendance WHERE status = "Present"')
    present_count = c.fetchone()[0]
    
    conn.close()
    
    print(f"   • Total Students: {student_count}")
    print(f"   • Total Attendance Records: {attendance_count}")
    print(f"   • Classes: {', '.join(classes)}")
    print(f"   • Total Present: {present_count}")
    print(f"   • Total Absent: {attendance_count - present_count}")
    
    print("\n" + "=" * 60)
    print("✅ Sample data initialization complete!")
    print("\nYou can now:")
    print("  1. Start the application: python app.py")
    print("  2. Visit: http://localhost:5000")
    print("  3. View the dashboard to see statistics")
    print("  4. Generate reports for different classes and dates")
    print("\n⚠️  Note: These students have dummy face encodings.")
    print("   To register real faces, use the 'Register Student' tab.")
    print("=" * 60)

if __name__ == '__main__':
    main()
