# Quick Start Guide

Get the Face Recognition Attendance System up and running in 5 minutes!

## Prerequisites

- Python 3.8+
- Webcam
- Modern web browser

## Step 1: Install (2 minutes)

```bash
# Extract the project files
# Navigate to project directory
cd face-recognition-attendance

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

> **Troubleshooting:** If pip install fails, try upgrading pip first:
> ```bash
> pip install --upgrade pip
> ```

## Step 2: Run the Application (1 minute)

```bash
python app.py
```

You should see:
```
 * Running on http://127.0.0.1:5000
```

Open your browser and go to: **http://localhost:5000**

## Step 3: Register Students (2 minutes)

1. Click **"Register Student"** tab
2. Fill in the form:
   - **Student ID:** `STU001`
   - **Name:** `John Doe`
   - **Email:** `john@school.edu` (optional)
   - **Class:** `10-A`
   - **Face Photo:** Upload a clear front-facing photo
3. Click **"Register Student"**
4. Repeat for more students

## Step 4: Mark Attendance (Starting automatic process)

### Option A: Using Webcam
1. Click **"Mark Attendance"** tab
2. Click **"Start Camera"**
3. Position your face in the camera
4. Click **"Capture & Recognize"**
5. System marks your attendance if recognized

### Option B: Upload Photo
1. Click **"Mark Attendance"** tab
2. In "Upload Image" section:
   - Select a student's face photo
   - Click **"Upload & Recognize"**

## Step 5: View Reports

1. Click **"Reports"** tab
2. Select a date
3. Optionally select a class
4. Click **"Generate Report"**
5. View attendance records or export to CSV

## Features Quick Reference

| Feature | Location | How to |
|---------|----------|--------|
| Dashboard | Main page | Auto-loads on start |
| Register Students | Register Student tab | Fill form + Upload photo |
| Mark Attendance | Mark Attendance tab | Camera or Upload image |
| View Reports | Reports tab | Select date + Generate |
| Export CSV | Reports tab | After generating report |
| View Students | Register Student tab | Bottom of page |

## Common Issues & Solutions

### Issue: "No module named 'flask'"
**Solution:** Make sure virtual environment is activated
```bash
# Check: (venv) should appear in your terminal
# If not, activate:
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate      # Windows
```

### Issue: "Camera permission denied"
**Solution:** Grant browser permission to access camera
- Check your browser's permission settings
- Try a different browser (Chrome recommended)
- Ensure no other app is using the camera

### Issue: "dlib installation fails"
**Solution:** Use pre-built wheels
```bash
pip install dlib --prefer-binary
```

### Issue: "Face not recognized"
**Solution:** Ensure:
- Student is registered with clear photo
- Good lighting in current environment
- Face is clearly visible in camera

### Issue: "Database errors after restart"
**Solution:** Reset database
```bash
# Delete the database file
rm attendance.db  # Linux/Mac
del attendance.db  # Windows
# Restart application - new database will be created
python app.py
```

## Test Workflow

Try this workflow to test the system:

1. **Register 3 sample students:**
   - STU001 | Alice Johnson | 10-A
   - STU002 | Bob Smith | 10-A
   - STU003 | Carol Davis | 10-B

2. **Mark attendance for 2 students:**
   - Alice: Upload photo 2 times
   - Bob: Use webcam capture

3. **Check dashboard:**
   - See 3 total students
   - See 2 present, 1 absent

4. **Generate report:**
   - Filter by today's date
   - See both present and absent

5. **Export CSV:**
   - Download and open in Excel/Sheets

## System Information

- **Database:** SQLite (attendance.db)
- **Student Faces:** stored in `known_faces/` folder
- **Web Framework:** Flask
- **Face Recognition:** face_recognition library
- **UI:** HTML5 + CSS3 + Vanilla JavaScript

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Tab` | Navigate between fields |
| `Enter` | Submit forms |
| `Esc` | Close dialogs |

## Browser Compatibility

✅ Google Chrome (Recommended)
✅ Mozilla Firefox
✅ Safari 14+
✅ Edge

## Next Steps

After getting started:

1. **Configure Email** - Enable notifications in `app.py`
2. **Deploy Online** - Use Gunicorn + Nginx for production
3. **Backup Data** - Regularly backup `attendance.db`
4. **Customize UI** - Modify `templates/index.html` and `static/style.css`
5. **Add More Features** - Extend `app.py` with additional functionality

## Getting Help

- Check README.md for detailed documentation
- Review error messages in browser console (F12)
- Check application terminal for logs
- Ensure all dependencies are installed

## Performance Tips

- Use high-quality face photos (500x500px or larger)
- Ensure good lighting during capture
- Close unnecessary applications for better performance
- Use Chrome for best compatibility

---

**Enjoy using Face Recognition Attendance System! 🎓**

Need more help? Read the full README.md file.
