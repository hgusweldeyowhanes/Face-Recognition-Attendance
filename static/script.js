let cameraStream = null;
let currentReportData = [];
let classesLoaded = false;

document.addEventListener('DOMContentLoaded', () => {
    setupNavigation();
    setupEventListeners();
    setReportDate();
    loadDashboard();
});

function setupNavigation() {
    document.querySelectorAll('.nav-btn').forEach((btn) => {
        btn.addEventListener('click', () => showPage(btn.dataset.page, btn));
    });
}

function showPage(pageName, activeBtn) {
    document.querySelectorAll('.page').forEach((page) => {
        const isActive = page.id === pageName;
        page.classList.toggle('active', isActive);
        page.hidden = !isActive;
    });

    document.querySelectorAll('.nav-btn').forEach((btn) => {
        const on = btn === activeBtn || btn.dataset.page === pageName;
        btn.classList.toggle('active', on);
        btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });

    if (pageName === 'register') {
        loadStudents();
        loadClasses();
    } else if (pageName === 'reports') {
        loadClasses();
    } else if (pageName === 'dashboard') {
        loadDashboard();
    } else if (pageName !== 'attendance') {
        stopCamera();
    }
}

function setupEventListeners() {
    document.getElementById('cameraToggleBtn').addEventListener('click', toggleCamera);
    document.getElementById('captureBtn').addEventListener('click', captureAndRecognize);
    document.getElementById('uploadBtn').addEventListener('click', uploadAndRecognize);
    document.getElementById('registrationForm').addEventListener('submit', registerStudent);
    document.getElementById('facePhoto').addEventListener('change', previewPhoto);
    document.getElementById('generateReportBtn').addEventListener('click', generateReport);
    document.getElementById('exportReportBtn').addEventListener('click', exportReport);
    document.getElementById('refreshDashboardBtn').addEventListener('click', loadDashboard);
}

function setReportDate() {
    document.getElementById('reportDate').value = new Date().toISOString().split('T')[0];
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

async function apiJson(url, options) {
    const res = await fetch(url, options);
    let data = null;
    try {
        data = await res.json();
    } catch (_) {
        data = { success: false, message: 'Invalid server response' };
    }
    return { res, data };
}

async function loadDashboard() {
    try {
        const { data } = await apiJson('/api/attendance/summary');
        updateSummary(Array.isArray(data) ? data : []);
    } catch (err) {
        console.error(err);
        showNotification('Could not load dashboard', 'error');
    }
}

function updateSummary(data) {
    let totalStudents = 0;
    let presentToday = 0;
    const summaryBody = document.getElementById('summaryBody');
    summaryBody.innerHTML = '';

    if (!data.length) {
        summaryBody.innerHTML = '<tr><td colspan="5" class="empty">No classes yet — register students to begin</td></tr>';
    }

    data.forEach((item) => {
        totalStudents += item.total_students;
        presentToday += item.present_today;
        const percentage = item.total_students
            ? ((item.present_today / item.total_students) * 100).toFixed(0)
            : '0';

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${escapeHtml(item.class)}</td>
            <td>${item.total_students}</td>
            <td>${item.present_today}</td>
            <td>${item.absent_today}</td>
            <td>
                <span class="rate-bar">
                    <span class="rate-track"><span class="rate-fill" style="width:${percentage}%"></span></span>
                    ${percentage}%
                </span>
            </td>
        `;
        summaryBody.appendChild(row);
    });

    document.querySelector('#totalStudentsCard .stat-value').textContent = totalStudents;
    document.querySelector('#presentTodayCard .stat-value').textContent = presentToday;
    document.querySelector('#absentTodayCard .stat-value').textContent = Math.max(0, totalStudents - presentToday);
}

async function toggleCamera() {
    const btn = document.getElementById('cameraToggleBtn');
    const captureBtn = document.getElementById('captureBtn');
    const hint = document.getElementById('cameraHint');

    if (cameraStream) {
        stopCamera();
        btn.textContent = 'Start camera';
        captureBtn.disabled = true;
        hint.textContent = 'Camera off';
        return;
    }

    try {
        await startCamera();
        btn.textContent = 'Stop camera';
        captureBtn.disabled = false;
        hint.textContent = 'Live';
    } catch (_) {
        showNotification('Camera access denied or unavailable', 'error');
    }
}

async function startCamera() {
    cameraStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
    });
    document.getElementById('cameraFeed').srcObject = cameraStream;
}

function stopCamera() {
    if (!cameraStream) return;
    cameraStream.getTracks().forEach((track) => track.stop());
    cameraStream = null;
    const video = document.getElementById('cameraFeed');
    if (video) video.srcObject = null;
    const captureBtn = document.getElementById('captureBtn');
    if (captureBtn) captureBtn.disabled = true;
    const btn = document.getElementById('cameraToggleBtn');
    if (btn) btn.textContent = 'Start camera';
    const hint = document.getElementById('cameraHint');
    if (hint) hint.textContent = 'Camera off';
}

async function captureAndRecognize() {
    if (!cameraStream) {
        showNotification('Start the camera first', 'error');
        return;
    }

    const canvas = document.getElementById('canvas');
    const video = document.getElementById('cameraFeed');
    const ctx = canvas.getContext('2d');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    ctx.drawImage(video, 0, 0);

    canvas.toBlob((blob) => {
        if (!blob) {
            showNotification('Could not capture frame', 'error');
            return;
        }
        recognizeFromBlob(blob);
    }, 'image/jpeg', 0.92);
}

function uploadAndRecognize() {
    const file = document.getElementById('imageUpload').files[0];
    if (!file) {
        showNotification('Select an image first', 'error');
        return;
    }
    recognizeFromBlob(file);
}

async function recognizeFromBlob(blob) {
    const formData = new FormData();
    formData.append('image', blob, 'capture.jpg');

    const resultPanel = document.getElementById('recognitionResult');
    resultPanel.classList.add('busy');

    try {
        const { data } = await apiJson('/api/recognize', { method: 'POST', body: formData });
        if (data.success) {
            displayRecognitionSuccess(data.student, data.confidence);
        } else {
            displayRecognitionError(data.message || 'Recognition failed');
        }
    } catch (err) {
        showNotification('Error during recognition: ' + err.message, 'error');
    } finally {
        resultPanel.classList.remove('busy');
    }
}

function displayRecognitionSuccess(student, confidence) {
    const resultDiv = document.getElementById('recognitionResult');
    const contentDiv = document.getElementById('resultContent');
    const time = new Date().toLocaleTimeString();
    const conf = confidence != null ? Math.round(confidence * 100) : null;

    contentDiv.innerHTML = `
        <h3>Checked in</h3>
        <p><strong>${escapeHtml(student.name)}</strong></p>
        <p>ID ${escapeHtml(student.student_id)} · ${escapeHtml(student.class)}</p>
        <p>${escapeHtml(time)}${conf != null ? ` · ${conf}% match` : ''}</p>
    `;
    resultDiv.classList.add('success');
    resultDiv.classList.remove('error');
    showNotification(`Welcome ${student.name}`, 'success');
}

function displayRecognitionError(message) {
    const resultDiv = document.getElementById('recognitionResult');
    const contentDiv = document.getElementById('resultContent');
    contentDiv.innerHTML = `
        <h3>Not recognized</h3>
        <p>${escapeHtml(message)}</p>
    `;
    resultDiv.classList.add('error');
    resultDiv.classList.remove('success');
}

function previewPhoto(e) {
    const file = e.target.files[0];
    const preview = document.getElementById('photoPreview');
    if (!file) {
        preview.hidden = true;
        preview.removeAttribute('src');
        return;
    }
    const reader = new FileReader();
    reader.onload = (event) => {
        preview.src = event.target.result;
        preview.hidden = false;
    };
    reader.readAsDataURL(file);
}

async function registerStudent(e) {
    e.preventDefault();
    const submitBtn = document.getElementById('registerSubmitBtn');
    const photoFile = document.getElementById('facePhoto').files[0];
    if (!photoFile) {
        showNotification('Please select a face photo', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('student_id', document.getElementById('studentId').value.trim());
    formData.append('name', document.getElementById('studentName').value.trim());
    formData.append('email', document.getElementById('studentEmail').value.trim());
    formData.append('class_name', document.getElementById('studentClass').value.trim());
    formData.append('image', photoFile);

    submitBtn.disabled = true;
    submitBtn.textContent = 'Registering…';

    try {
        const { data } = await apiJson('/api/students/add', { method: 'POST', body: formData });
        if (data.success) {
            showNotification(data.message, 'success');
            document.getElementById('registrationForm').reset();
            document.getElementById('photoPreview').hidden = true;
            classesLoaded = false;
            loadStudents();
            loadClasses(true);
        } else {
            showNotification(data.message || 'Registration failed', 'error');
        }
    } catch (err) {
        showNotification('Error: ' + err.message, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Register student';
    }
}

async function loadStudents() {
    try {
        const { data } = await apiJson('/api/students');
        const tbody = document.getElementById('studentsBody');
        tbody.innerHTML = '';

        if (!Array.isArray(data) || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty">No students registered yet</td></tr>';
            return;
        }

        data.forEach((student) => {
            const date = student.created_at ? new Date(student.created_at).toLocaleDateString() : '—';
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${escapeHtml(student.student_id)}</td>
                <td>${escapeHtml(student.name)}</td>
                <td>${escapeHtml(student.email || '—')}</td>
                <td>${escapeHtml(student.class_name)}</td>
                <td>${escapeHtml(date)}</td>
            `;
            tbody.appendChild(row);
        });
    } catch (err) {
        console.error(err);
    }
}

async function loadClasses(force = false) {
    if (classesLoaded && !force) return;
    try {
        const { data } = await apiJson('/api/classes');
        const select = document.getElementById('reportClass');
        const current = select.value;
        select.innerHTML = '<option value="">All classes</option>';
        (Array.isArray(data) ? data : []).forEach((className) => {
            const option = document.createElement('option');
            option.value = className;
            option.textContent = className;
            select.appendChild(option);
        });
        if (current) select.value = current;
        classesLoaded = true;
    } catch (err) {
        console.error(err);
    }
}

async function generateReport() {
    const date = document.getElementById('reportDate').value;
    const classFilter = document.getElementById('reportClass').value;
    if (!date) {
        showNotification('Please select a date', 'error');
        return;
    }

    let url = `/api/attendance/report?date=${encodeURIComponent(date)}`;
    if (classFilter) url += `&class=${encodeURIComponent(classFilter)}`;

    try {
        const { data } = await apiJson(url);
        currentReportData = Array.isArray(data) ? data : [];
        displayReport(currentReportData);
        showNotification('Report ready', 'success');
    } catch (err) {
        showNotification('Error generating report: ' + err.message, 'error');
    }
}

function displayReport(data) {
    const tbody = document.getElementById('reportBody');
    tbody.innerHTML = '';

    if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">No records found</td></tr>';
        return;
    }

    data.forEach((record) => {
        const status = record.status || 'Absent';
        const pillClass = status === 'Present' ? 'present' : 'absent';
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${escapeHtml(record.student_id)}</td>
            <td>${escapeHtml(record.name)}</td>
            <td>${escapeHtml(record.class)}</td>
            <td>${escapeHtml(record.date || '—')}</td>
            <td>${escapeHtml(record.time_in || '—')}</td>
            <td><span class="status-pill ${pillClass}">${escapeHtml(status)}</span></td>
        `;
        tbody.appendChild(row);
    });
}

function exportReport() {
    if (!currentReportData.length) {
        showNotification('Generate a report first', 'error');
        return;
    }

    let csv = 'Student ID,Name,Class,Date,Time In,Status\n';
    currentReportData.forEach((record) => {
        csv += `${record.student_id},"${String(record.name || '').replace(/"/g, '""')}",${record.class},"${record.date || ''}","${record.time_in || ''}",${record.status || 'Absent'}\n`;
    });

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `attendance_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    a.remove();
    showNotification('CSV exported', 'success');
}

function showNotification(message, type = 'info') {
    const root = document.getElementById('toast-root');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    root.appendChild(toast);
    setTimeout(() => toast.remove(), 3200);
}

window.addEventListener('beforeunload', stopCamera);
