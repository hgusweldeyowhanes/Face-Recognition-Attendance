// Global variables
let cameraStream = null;
let isCapturing = false;
let currentReportData = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializePage();
    setupEventListeners();
    loadDashboard();
    setReportDate();
});

// Page Navigation
function showPage(pageName) {
    // Hide all pages
    const pages = document.querySelectorAll('.page');
    pages.forEach(page => page.classList.remove('active'));
    
    // Show selected page
    document.getElementById(pageName).classList.add('active');
    
    // Update active nav button
    const navBtns = document.querySelectorAll('.nav-btn');
    navBtns.forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    
    // Load page-specific data
    if (pageName === 'register') {
        loadStudents();
        loadClasses();
    } else if (pageName === 'reports') {
        loadClasses();
    } else if (pageName === 'dashboard') {
        loadDashboard();
    }
}

// Initialize page
function initializePage() {
    // Set report date to today
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('reportDate').value = today;
}

// Setup event listeners
function setupEventListeners() {
    // Camera
    document.getElementById('cameraToggleBtn').addEventListener('click', toggleCamera);
    document.getElementById('captureBtn').addEventListener('click', captureAndRecognize);
    
    // File upload
    document.getElementById('imageUpload').addEventListener('change', previewImage);
    document.getElementById('uploadBtn').addEventListener('click', uploadAndRecognize);
    
    // Registration
    document.getElementById('registrationForm').addEventListener('submit', registerStudent);
    document.getElementById('facePhoto').addEventListener('change', previewPhoto);
    
    // Reports
    document.getElementById('generateReportBtn').addEventListener('click', generateReport);
    document.getElementById('exportReportBtn').addEventListener('click', exportReport);
}

// ============= DASHBOARD FUNCTIONS =============

function loadDashboard() {
    // Load summary
    fetch('/api/attendance/summary')
        .then(res => res.json())
        .then(data => {
            updateSummary(data);
        })
        .catch(err => console.error('Error loading summary:', err));
}

function updateSummary(data) {
    let totalStudents = 0;
    let presentToday = 0;
    
    // Update class-wise summary
    const summaryBody = document.getElementById('summaryBody');
    summaryBody.innerHTML = '';
    
    data.forEach(item => {
        totalStudents += item.total_students;
        presentToday += item.present_today;
        
        const percentage = ((item.present_today / item.total_students) * 100).toFixed(1);
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${item.class}</td>
            <td>${item.total_students}</td>
            <td>${item.present_today}</td>
            <td>${item.absent_today}</td>
            <td>${percentage}%</td>
        `;
        summaryBody.appendChild(row);
    });
    
    // Update summary cards
    document.querySelector('#totalStudentsCard .summary-value').textContent = totalStudents;
    document.querySelector('#presentTodayCard .summary-value').textContent = presentToday;
    document.querySelector('#absentTodayCard .summary-value').textContent = totalStudents - presentToday;
}

// ============= CAMERA FUNCTIONS =============

async function toggleCamera() {
    const btn = document.getElementById('cameraToggleBtn');
    
    if (cameraStream) {
        stopCamera();
        btn.textContent = 'Start Camera';
        btn.classList.remove('active');
    } else {
        try {
            await startCamera();
            btn.textContent = 'Stop Camera';
            btn.classList.add('active');
        } catch (err) {
            showNotification('Camera access denied', 'error');
        }
    }
}

async function startCamera() {
    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: 'user',
                width: { ideal: 640 },
                height: { ideal: 480 }
            },
            audio: false
        });
        
        document.getElementById('cameraFeed').srcObject = cameraStream;
    } catch (err) {
        throw new Error('Could not access camera: ' + err.message);
    }
}

function stopCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
        cameraStream = null;
        document.getElementById('cameraFeed').srcObject = null;
    }
}

async function captureAndRecognize() {
    if (!cameraStream) {
        showNotification('Please start the camera first', 'error');
        return;
    }
    
    const canvas = document.getElementById('canvas');
    const video = document.getElementById('cameraFeed');
    const ctx = canvas.getContext('2d');
    
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0);
    
    canvas.toBlob(blob => {
        recognizeFromBlob(blob);
    }, 'image/jpeg');
}

// ============= IMAGE UPLOAD FUNCTIONS =============

function previewImage(e) {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
            // Image will be uploaded with the button click
        };
        reader.readAsDataURL(file);
    }
}

function uploadAndRecognize() {
    const file = document.getElementById('imageUpload').files[0];
    
    if (!file) {
        showNotification('Please select an image', 'error');
        return;
    }
    
    recognizeFromBlob(file);
}

function recognizeFromBlob(blob) {
    const formData = new FormData();
    formData.append('image', blob, 'capture.jpg');
    
    fetch('/api/recognize', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            displayRecognitionSuccess(data.student);
        } else {
            displayRecognitionError(data.message);
        }
    })
    .catch(err => {
        showNotification('Error during recognition: ' + err.message, 'error');
    });
}

function displayRecognitionSuccess(student) {
    const resultDiv = document.getElementById('recognitionResult');
    const contentDiv = document.getElementById('resultContent');
    
    const time = new Date().toLocaleTimeString();
    contentDiv.innerHTML = `
        <div style="text-align: center; padding: 1rem;">
            <h3>✓ Attendance Marked Successfully</h3>
            <p><strong>Student:</strong> ${student.name}</p>
            <p><strong>ID:</strong> ${student.student_id}</p>
            <p><strong>Class:</strong> ${student.class}</p>
            <p><strong>Time:</strong> ${time}</p>
        </div>
    `;
    
    resultDiv.classList.add('success');
    resultDiv.classList.remove('error');
    showNotification(`Welcome ${student.name}!`, 'success');
}

function displayRecognitionError(message) {
    const resultDiv = document.getElementById('recognitionResult');
    const contentDiv = document.getElementById('resultContent');
    
    contentDiv.innerHTML = `
        <div style="text-align: center;">
            <h3>✗ Recognition Failed</h3>
            <p>${message}</p>
        </div>
    `;
    
    resultDiv.classList.add('error');
    resultDiv.classList.remove('success');
}

// ============= REGISTRATION FUNCTIONS =============

function previewPhoto(e) {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
            const preview = document.getElementById('photoPreview');
            preview.src = event.target.result;
            preview.style.display = 'block';
        };
        reader.readAsDataURL(file);
    }
}

function registerStudent(e) {
    e.preventDefault();
    
    const formData = new FormData();
    formData.append('student_id', document.getElementById('studentId').value);
    formData.append('name', document.getElementById('studentName').value);
    formData.append('email', document.getElementById('studentEmail').value);
    formData.append('class_name', document.getElementById('studentClass').value);
    
    const photoFile = document.getElementById('facePhoto').files[0];
    if (!photoFile) {
        showNotification('Please select a face photo', 'error');
        return;
    }
    
    formData.append('image', photoFile);
    
    fetch('/api/students/add', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showNotification(data.message, 'success');
            document.getElementById('registrationForm').reset();
            document.getElementById('photoPreview').style.display = 'none';
            loadStudents();
        } else {
            showNotification(data.message, 'error');
        }
    })
    .catch(err => {
        showNotification('Error: ' + err.message, 'error');
    });
}

function loadStudents() {
    fetch('/api/students')
        .then(res => res.json())
        .then(data => {
            const tbody = document.getElementById('studentsBody');
            tbody.innerHTML = '';
            
            data.forEach(student => {
                const row = document.createElement('tr');
                const date = new Date(student.created_at).toLocaleDateString();
                row.innerHTML = `
                    <td>${student.student_id}</td>
                    <td>${student.name}</td>
                    <td>${student.email || '-'}</td>
                    <td>${student.class_name}</td>
                    <td>${date}</td>
                `;
                tbody.appendChild(row);
            });
            
            if (data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5">No students registered yet</td></tr>';
            }
        })
        .catch(err => console.error('Error loading students:', err));
}

// ============= REPORTS FUNCTIONS =============

function loadClasses() {
    fetch('/api/classes')
        .then(res => res.json())
        .then(data => {
            const select = document.getElementById('reportClass');
            const options = select.innerHTML;
            select.innerHTML = options; // Keep the "All Classes" option
            
            data.forEach(className => {
                const option = document.createElement('option');
                option.value = className;
                option.textContent = className;
                select.appendChild(option);
            });
        })
        .catch(err => console.error('Error loading classes:', err));
}

function setReportDate() {
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('reportDate').value = today;
}

function generateReport() {
    const date = document.getElementById('reportDate').value;
    const classFilter = document.getElementById('reportClass').value;
    
    if (!date) {
        showNotification('Please select a date', 'error');
        return;
    }
    
    let url = `/api/attendance/report?date=${date}`;
    if (classFilter) {
        url += `&class=${classFilter}`;
    }
    
    fetch(url)
        .then(res => res.json())
        .then(data => {
            currentReportData = data;
            displayReport(data);
            showNotification('Report generated successfully', 'success');
        })
        .catch(err => {
            showNotification('Error generating report: ' + err.message, 'error');
        });
}

function displayReport(data) {
    const tbody = document.getElementById('reportBody');
    tbody.innerHTML = '';
    
    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6">No records found</td></tr>';
        return;
    }
    
    data.forEach(record => {
        const row = document.createElement('tr');
        const status = record.status || 'Absent';
        const statusColor = status === 'Present' ? '#28a745' : '#dc3545';
        
        row.innerHTML = `
            <td>${record.student_id}</td>
            <td>${record.name}</td>
            <td>${record.class}</td>
            <td>${record.date || '-'}</td>
            <td>${record.time_in || '-'}</td>
            <td style="color: ${statusColor}; font-weight: bold;">${status}</td>
        `;
        tbody.appendChild(row);
    });
}

function exportReport() {
    if (currentReportData.length === 0) {
        showNotification('Please generate a report first', 'error');
        return;
    }
    
    // Create CSV
    let csv = 'Student ID,Name,Class,Date,Time In,Status\n';
    
    currentReportData.forEach(record => {
        csv += `${record.student_id},"${record.name}",${record.class},"${record.date || ''}","${record.time_in || ''}",${record.status || 'Absent'}\n`;
    });
    
    // Download CSV
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `attendance_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
    showNotification('Report exported successfully', 'success');
}

// ============= UTILITY FUNCTIONS =============

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopCamera();
});
