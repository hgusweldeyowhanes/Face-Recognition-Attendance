# Face Recognition Attendance System

A complete face recognition-based attendance system for educational institutions. This system uses Python, Flask, OpenCV, and face_recognition library to automate student attendance marking.

## Features

✅ **Face Recognition** - Automated attendance marking using face recognition
✅ **Student Management** - Register new students with face photos
✅ **Real-time Camera Feed** - Live camera capture and recognition
✅ **Attendance Tracking** - Database storage of all attendance records
✅ **Reports & Analytics** - Generate and export attendance reports
✅ **Class-wise Summary** - View attendance statistics by class
✅ **Email Notifications** - Send notifications for attendance marking
✅ **Responsive UI** - Modern web interface for desktop and mobile
✅ **CSV Export** - Export attendance records to CSV format
✅ **Dashboard** - Real-time overview of attendance statistics

## System Requirements

- **Python** 3.8 or higher
- **Webcam** for capture and recognition
- **Modern Web Browser** (Chrome, Firefox, Safari, Edge)
- **8GB RAM** minimum (for face recognition processing)
- **SSD Storage** recommended for better performance

## Installation

### 1. Clone or Download the Project

```bash
git clone <repository-url>
cd face-recognition-attendance
```

### 2. Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Note:** If you encounter issues installing `face-recognition`, you may need to install dlib first:

```bash
# Windows
pip install dlib

# Linux
sudo apt-get install build-essential cmake
sudo apt-get install libopenblas-dev liblapack-dev
pip install dlib

# Mac
brew install cmake
pip install dlib
```

### 4. Run the Application

```bash
python app.py
```

The application will start on `http://localhost:5000`

## Folder Structure

```
face-recognition-attendance/
│
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── attendance.db         # SQLite database (auto-created)
│
├── templates/
│   └── index.html        # Web interface template
│
├── static/
│   ├── style.css         # Stylesheet
│   └── script.js         # Frontend JavaScript
│
├── known_faces/          # Stores student face images (auto-created)
│   └── <student_id>/
│       └── <image.jpg>
│
└── uploads/              # Temporary upload folder (auto-created)
    └── <temp_images>
```

## Usage Guide

### Dashboard
- View real-time attendance statistics
- See class-wise summary
- Monitor present/absent students for the day

### Register Student
1. Click "Register Student" tab
2. Enter student details:
   - Student ID (unique)
   - Full Name
   - Email (optional)
   - Class Name
   - Face Photo (clear, front-facing photo)
3. Click "Register Student"
4. View all registered students in the list below

### Mark Attendance
Two methods available:

**Method 1: Camera Capture**
1. Click "Mark Attendance" tab
2. Click "Start Camera"
3. Position face in camera view
4. Click "Capture & Recognize"
5. System will identify and mark attendance

**Method 2: Upload Image**
1. Click "Mark Attendance" tab
2. In "Upload Image" section, select an image
3. Click "Upload & Recognize"
4. System will process and mark attendance

### Generate Reports
1. Click "Reports" tab
2. Select date and class (optional)
3. Click "Generate Report"
4. View attendance records in table
5. Click "Export to CSV" to download

## API Endpoints

### Student Management
- `GET /api/students` - Get all students
- `POST /api/students/add` - Register new student

### Attendance
- `POST /api/recognize` - Recognize face and mark attendance
- `GET /api/attendance/report` - Get attendance report
- `GET /api/attendance/summary` - Get class-wise summary
- `GET /api/student/<id>/history` - Get student attendance history

### Classes
- `GET /api/classes` - Get all unique classes

## Database Schema

### Students Table
```sql
CREATE TABLE students (
    id INTEGER PRIMARY KEY,
    student_id TEXT UNIQUE,
    name TEXT,
    email TEXT,
    class_name TEXT,
    face_encoding BLOB,
    created_at TIMESTAMP
)
```

### Attendance Table
```sql
CREATE TABLE attendance (
    id INTEGER PRIMARY KEY,
    student_id TEXT,
    date DATE,
    time_in TIME,
    time_out TIME,
    status TEXT,
    UNIQUE(student_id, date)
)
```

### Notifications Table
```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY,
    student_id TEXT,
    type TEXT,
    message TEXT,
    sent_at TIMESTAMP
)
```

## Configuration

### Email Notifications
To enable email notifications, configure in `app.py`:

```python
def send_email(email, message_type, message):
    """Configure your email service here"""
    # Example using Gmail SMTP
    sender_email = "your-email@gmail.com"
    sender_password = "your-app-password"
    # Configure SMTP settings
```

### Face Recognition Tolerance
Adjust face recognition accuracy in `app.py`:
- Lower tolerance (0.4-0.5): More strict, fewer false matches
- Higher tolerance (0.6-0.8): More lenient, more matches

```python
matches = face_recognition.compare_faces(
    known_encodings, 
    face_encodings[0], 
    tolerance=0.6  # Adjust this value
)
```

## Troubleshooting

### Camera Not Detected
- Ensure camera is connected and not in use by other applications
- Grant browser permission to access camera
- Check browser console for errors

### Face Not Recognized
- Ensure good lighting and clear face photo
- Update student photo quality
- Check face recognition tolerance setting
- Ensure student face photo is registered first

### Database Errors
- Delete `attendance.db` file to reset database
- Check database file permissions
- Ensure SQLite is installed

### Dependencies Installation Issues

**For dlib installation:**
```bash
# Option 1: Use pre-built wheel
pip install dlib --prefer-binary

# Option 2: Build from source (takes time)
pip install dlib

# Option 3: Use conda (if installed)
conda install dlib
```

## Performance Tips

1. **Image Quality**: Use clear, front-facing photos for registration
2. **Lighting**: Ensure good lighting during face capture
3. **Database**: Consider indexing student_id for faster queries
4. **Face Encoding Cache**: Implement caching for known faces to improve performance
5. **Image Size**: Optimize image size for faster processing

## Security Considerations

1. **Database Security**: Use strong passwords if deploying with authentication
2. **Face Data Privacy**: Store face encodings securely
3. **API Security**: Implement authentication for production deployment
4. **HTTPS**: Use HTTPS in production environment
5. **Data Backup**: Regular backup of attendance database

## Deployment

### Local Network Deployment
```bash
# Run with public network access
python app.py --host=0.0.0.0 --port=5000
```

### Production Deployment (Gunicorn)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Docker Deployment
Create a `Dockerfile`:
```dockerfile
FROM python:3.9
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```

## Future Enhancements

- [ ] Mobile app integration
- [ ] Multi-camera support
- [ ] Liveness detection (prevent spoofing)
- [ ] Admin authentication
- [ ] Advanced analytics and reports
- [ ] Integration with school management systems
- [ ] Parent notifications via SMS
- [ ] Attendance patterns analysis
- [ ] Biometric ID integration
- [ ] Cloud backup support

## License

This project is open source and available for educational use.

## Support

For issues, questions, or suggestions, please refer to the documentation or contact support.

## Contributing

Contributions are welcome! Please follow the coding standards and submit pull requests for review.

---

**Last Updated:** 2024
**Version:** 1.0
