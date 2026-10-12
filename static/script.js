let cameraStream = null;
let currentReportData = [];
let currentReportSessionId = '';
let classesLoaded = false;

document.addEventListener('DOMContentLoaded', () => {
    setupNavigation();
    setupEventListeners();
    setReportDate();
    initializeStaffSession();
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
        loadSessions();
    } else if (pageName === 'sessions') {
        loadClasses();
        loadSessions(localDateInputValue());
    } else if (pageName === 'staff') {
        loadStaffUsers();
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
    document.getElementById('faceEnrollmentForm').addEventListener('submit', saveFaceEnrollment);
    document.getElementById('cancelFaceEnrollmentBtn').addEventListener('click', () => {
        document.getElementById('faceEnrollmentDialog').close();
    });
    document.getElementById('studentsBody').addEventListener('click', (event) => {
        const enrollButton = event.target.closest('[data-enroll-student]');
        const deleteButton = event.target.closest('[data-delete-student-face]');
        if (enrollButton) {
            openFaceEnrollment(enrollButton.dataset.enrollStudent, enrollButton.dataset.studentName);
        } else if (deleteButton) {
            deleteStudentFace(deleteButton.dataset.deleteStudentFace);
        }
    });
    document.getElementById('generateReportBtn').addEventListener('click', generateReport);
    document.getElementById('exportReportBtn').addEventListener('click', exportReport);
    document.getElementById('reportBody').addEventListener('click', (event) => {
        const correctButton = event.target.closest('[data-correct-attendance]');
        const historyButton = event.target.closest('[data-correction-history]');
        const button = correctButton || historyButton;
        if (!button) return;
        const record = currentReportData.find(
            (item) => item.student_id === button.dataset.studentId,
        );
        if (!record) return;
        if (correctButton) openAttendanceCorrection(record);
        else loadCorrectionHistory(record);
    });
    document.getElementById('attendanceCorrectionForm').addEventListener('submit', saveAttendanceCorrection);
    document.getElementById('correctionStatus').addEventListener('change', updateCorrectionTimeFields);
    document.getElementById('cancelCorrectionBtn').addEventListener('click', () => {
        document.getElementById('attendanceCorrectionDialog').close();
    });
    document.getElementById('closeCorrectionHistoryBtn').addEventListener('click', () => {
        document.getElementById('correctionHistoryDialog').close();
    });
    document.getElementById('refreshDashboardBtn').addEventListener('click', loadDashboard);
    document.getElementById('startSessionForm').addEventListener('submit', startSession);
    document.getElementById('refreshSessionsBtn').addEventListener('click', loadSessions);
    document.getElementById('sessionsBody').addEventListener('click', (event) => {
        const button = event.target.closest('[data-close-session]');
        if (button) closeSession(button.dataset.closeSession);
    });
    document.getElementById('reportDate').addEventListener('change', loadSessions);
    document.getElementById('staffLoginForm').addEventListener('submit', staffLogin);
    document.getElementById('logoutBtn').addEventListener('click', staffLogout);
    document.getElementById('createTeacherForm').addEventListener('submit', createTeacher);
    document.getElementById('refreshStaffBtn').addEventListener('click', loadStaffUsers);
}

function setReportDate() {
    document.getElementById('reportDate').value = localDateInputValue();
}

function localDateInputValue(date = new Date()) {
    const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return localDate.toISOString().split('T')[0];
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
    if (res.status === 401 && data.message === 'Sign in required') {
        showStaffLogin();
    }
    return { res, data };
}

function showStaffLogin() {
    stopCamera();
    document.getElementById('appShell').hidden = true;
    document.getElementById('staffLoginPage').hidden = false;
    document.getElementById('staffIdentity').textContent = '';
    document.getElementById('staffUsersBody').innerHTML = '';
    document.getElementById('studentsBody').innerHTML = '';
    document.getElementById('summaryBody').innerHTML = '';
    document.getElementById('reportBody').innerHTML = '';
    document.getElementById('registrationForm').reset();
    document.getElementById('photoPreview').hidden = true;
    document.getElementById('photoPreview').removeAttribute('src');
    document.getElementById('faceEnrollmentForm').reset();
    const faceEnrollmentDialog = document.getElementById('faceEnrollmentDialog');
    if (faceEnrollmentDialog.open) faceEnrollmentDialog.close();
    document.getElementById('attendanceCorrectionForm').reset();
    const attendanceCorrectionDialog = document.getElementById('attendanceCorrectionDialog');
    if (attendanceCorrectionDialog.open) attendanceCorrectionDialog.close();
    delete attendanceCorrectionDialog.dataset.studentId;
    delete attendanceCorrectionDialog.dataset.sessionId;
    const correctionHistoryDialog = document.getElementById('correctionHistoryDialog');
    if (correctionHistoryDialog.open) correctionHistoryDialog.close();
    document.getElementById('correctionHistoryList').innerHTML = '';
    document.getElementById('correctionHistoryStudent').textContent = '';
    document.getElementById('imageUpload').value = '';
    document.getElementById('resultContent').innerHTML = '<p class="result-idle">Results appear here after a scan.</p>';
    currentReportData = [];
    currentReportSessionId = '';
}

async function initializeStaffSession() {
    try {
        const { res, data } = await apiJson('/api/auth/me');
        if (!res.ok) {
            showStaffLogin();
            return;
        }
        showStaffApp(data.user);
    } catch (err) {
        showStaffLogin();
        showNotification('Could not verify staff session: ' + err.message, 'error');
    }
}

function showStaffApp(user) {
    document.getElementById('staffLoginPage').hidden = true;
    document.getElementById('appShell').hidden = false;
    document.getElementById('staffIdentity').textContent = `${user.username} · ${user.role}`;
    document.querySelectorAll('[data-admin-only]').forEach((element) => {
        element.hidden = user.role !== 'admin';
    });
    showPage('dashboard', document.querySelector('[data-page="dashboard"]'));
    if (user.role === 'admin') loadStaffUsers();
}

async function staffLogin(event) {
    event.preventDefault();
    const button = document.getElementById('loginSubmitBtn');
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    button.disabled = true;
    try {
        const { res, data } = await apiJson('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (!res.ok || !data.success) {
            showNotification(data.message || 'Sign-in failed', 'error');
            return;
        }
        document.getElementById('staffLoginForm').reset();
        showStaffApp(data.user);
    } catch (err) {
        showNotification('Sign-in failed: ' + err.message, 'error');
    } finally {
        button.disabled = false;
    }
}

async function staffLogout() {
    try {
        const { res } = await apiJson('/api/auth/logout', { method: 'POST' });
        if (!res.ok) {
            showNotification('Could not sign out', 'error');
            return;
        }
        showStaffLogin();
    } catch (err) {
        showNotification('Could not sign out: ' + err.message, 'error');
    }
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
            displayRecognitionSuccess(data.student, data.confidence, data.attendance_status);
        } else {
            displayRecognitionError(data.message || 'Recognition failed');
        }
    } catch (err) {
        showNotification('Error during recognition: ' + err.message, 'error');
    } finally {
        resultPanel.classList.remove('busy');
    }
}

function displayRecognitionSuccess(student, confidence, attendanceStatus) {
    const resultDiv = document.getElementById('recognitionResult');
    const contentDiv = document.getElementById('resultContent');
    const time = new Date().toLocaleTimeString();
    const conf = confidence != null ? Math.round(confidence * 100) : null;

    contentDiv.innerHTML = `
        <h3>${escapeHtml(attendanceStatus || 'Checked in')}</h3>
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
    if (!document.getElementById('faceConsent').checked) {
        showNotification('Confirm face-data consent before registering', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('student_id', document.getElementById('studentId').value.trim());
    formData.append('name', document.getElementById('studentName').value.trim());
    formData.append('email', document.getElementById('studentEmail').value.trim());
    formData.append('class_name', document.getElementById('studentClass').value.trim());
    formData.append('image', photoFile);
    formData.append('face_consent', 'true');

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
            tbody.innerHTML = '<tr><td colspan="8" class="empty">No students registered yet</td></tr>';
            return;
        }

        data.forEach((student) => {
            const date = student.created_at ? new Date(student.created_at).toLocaleDateString() : '—';
            const faceStatus = student.face_data_present
                ? (student.face_consent_at ? 'Active' : 'Consent missing')
                : 'Not stored';
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${escapeHtml(student.student_id)}</td>
                <td>${escapeHtml(student.name)}</td>
                <td>${escapeHtml(student.email || '—')}</td>
                <td>${escapeHtml(student.class_name)}</td>
                <td>${escapeHtml(date)}</td>
                <td>${student.face_consent_at ? `Recorded ${escapeHtml(new Date(student.face_consent_at).toLocaleDateString())}` : 'Not recorded'}</td>
                <td>${faceStatus}</td>
                <td class="student-face-actions">
                    <button type="button" class="btn btn-secondary btn-small" data-enroll-student="${escapeHtml(student.student_id)}" data-student-name="${escapeHtml(student.name)}">Update / consent</button>
                    ${student.face_data_present ? `<button type="button" class="btn btn-ghost btn-small" data-delete-student-face="${escapeHtml(student.student_id)}">Delete face data</button>` : ''}
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (err) {
        console.error(err);
    }
}

function openFaceEnrollment(studentId, studentName) {
    const dialog = document.getElementById('faceEnrollmentDialog');
    dialog.dataset.studentId = studentId;
    document.getElementById('faceEnrollmentStudent').textContent = `${studentName} (${studentId})`;
    document.getElementById('faceEnrollmentForm').reset();
    dialog.showModal();
}

async function saveFaceEnrollment(event) {
    event.preventDefault();
    const dialog = document.getElementById('faceEnrollmentDialog');
    const file = document.getElementById('replacementFacePhoto').files[0];
    if (!file || !document.getElementById('replacementFaceConsent').checked) {
        showNotification('Choose a photo and confirm current consent', 'error');
        return;
    }
    const button = document.getElementById('saveFaceEnrollmentBtn');
    const formData = new FormData();
    formData.append('image', file);
    formData.append('face_consent', 'true');
    button.disabled = true;
    try {
        const studentId = dialog.dataset.studentId;
        const { res, data } = await apiJson(
            `/api/students/${encodeURIComponent(studentId)}/face-data`,
            { method: 'POST', body: formData },
        );
        if (!res.ok || !data.success) {
            showNotification(data.message || 'Could not update face data', 'error');
            return;
        }
        dialog.close();
        showNotification(data.message, 'success');
        await loadStudents();
    } catch (err) {
        showNotification('Could not update face data: ' + err.message, 'error');
    } finally {
        button.disabled = false;
    }
}

async function deleteStudentFace(studentId) {
    if (!window.confirm('Delete this student’s stored face image and encoding? Attendance history will remain.')) {
        return;
    }
    try {
        const { res, data } = await apiJson(
            `/api/students/${encodeURIComponent(studentId)}/face-data`,
            {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm: true }),
            },
        );
        if (!res.ok || !data.success) {
            showNotification(data.message || 'Could not delete face data', 'error');
            return;
        }
        showNotification(data.message, 'success');
        await loadStudents();
    } catch (err) {
        showNotification('Could not delete face data: ' + err.message, 'error');
    }
}

async function loadClasses(force = false) {
    if (classesLoaded && !force) return;
    try {
        const { data } = await apiJson('/api/classes');
        const reportSelect = document.getElementById('reportClass');
        const currentReportClass = reportSelect.value;
        reportSelect.innerHTML = '<option value="">All classes</option>';
        const sessionSelect = document.getElementById('sessionClass');
        const currentSessionClass = sessionSelect.value;
        sessionSelect.innerHTML = '<option value="">Select a class</option>';
        (Array.isArray(data) ? data : []).forEach((className) => {
            const option = document.createElement('option');
            option.value = className;
            option.textContent = className;
            reportSelect.appendChild(option);
            const sessionOption = option.cloneNode(true);
            sessionSelect.appendChild(sessionOption);
        });
        if (currentReportClass) reportSelect.value = currentReportClass;
        if (currentSessionClass) sessionSelect.value = currentSessionClass;
        classesLoaded = true;
    } catch (err) {
        console.error(err);
    }
}

async function loadStaffUsers() {
    try {
        const { res, data } = await apiJson('/api/admin/users');
        if (!res.ok) {
            showNotification(data.message || 'Could not load staff accounts', 'error');
            return;
        }
        const tbody = document.getElementById('staffUsersBody');
        tbody.innerHTML = '';
        if (!Array.isArray(data) || !data.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty">No staff accounts found</td></tr>';
            return;
        }
        data.forEach((user) => {
            const row = document.createElement('tr');
            const created = user.created_at ? new Date(user.created_at).toLocaleDateString() : '—';
            row.innerHTML = `
                <td>${escapeHtml(user.username)}</td>
                <td>${escapeHtml(user.role)}</td>
                <td>${user.active ? 'Active' : 'Disabled'}</td>
                <td>${escapeHtml(created)}</td>
            `;
            tbody.appendChild(row);
        });
    } catch (err) {
        showNotification('Could not load staff accounts: ' + err.message, 'error');
    }
}

async function createTeacher(event) {
    event.preventDefault();
    const button = document.getElementById('createTeacherBtn');
    const username = document.getElementById('teacherUsername').value.trim();
    const password = document.getElementById('teacherPassword').value;
    button.disabled = true;
    try {
        const { res, data } = await apiJson('/api/admin/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (!res.ok || !data.success) {
            showNotification(data.message || 'Could not create teacher', 'error');
            return;
        }
        document.getElementById('createTeacherForm').reset();
        showNotification(`Teacher account ${data.user.username} created`, 'success');
        await loadStaffUsers();
    } catch (err) {
        showNotification('Could not create teacher: ' + err.message, 'error');
    } finally {
        button.disabled = false;
    }
}

async function loadSessions(dateOverride = '') {
    const date = (typeof dateOverride === 'string' && dateOverride)
        || document.getElementById('reportDate').value
        || localDateInputValue();
    try {
        const { data } = await apiJson(`/api/sessions?date=${encodeURIComponent(date)}`);
        const sessions = Array.isArray(data) ? data : [];
        const tbody = document.getElementById('sessionsBody');
        tbody.innerHTML = '';
        if (!sessions.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty">No sessions for this date</td></tr>';
        }

        sessions.forEach((session) => {
            const row = document.createElement('tr');
            const started = session.started_at ? new Date(session.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—';
            const state = session.ended_at ? 'Closed' : 'Active';
            row.innerHTML = `
                <td>${escapeHtml(session.class_name)}</td>
                <td>${escapeHtml(started)}</td>
                <td>${session.grace_minutes} min</td>
                <td>${session.checked_in_count}/${session.enrolled_count}</td>
                <td>${session.late_count}</td>
                <td>${session.absent_count}</td>
                <td><span class="status-pill ${session.ended_at ? 'closed' : 'present'}">${state}</span></td>
                <td>${session.ended_at ? '' : `<button type="button" class="btn btn-secondary btn-small" data-close-session="${session.id}">Close</button>`}</td>
            `;
            tbody.appendChild(row);
        });

        if (date === document.getElementById('reportDate').value) {
            const reportSelect = document.getElementById('reportSession');
            const currentSession = reportSelect.value;
            reportSelect.innerHTML = '<option value="">Whole day</option>';
            sessions.forEach((session) => {
                const option = document.createElement('option');
                option.value = session.id;
                option.textContent = `${session.class_name} · ${new Date(session.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}${session.ended_at ? '' : ' · active'}`;
                reportSelect.appendChild(option);
            });
            if (currentSession && sessions.some((session) => String(session.id) === currentSession)) {
                reportSelect.value = currentSession;
            }
        }
    } catch (err) {
        console.error(err);
        showNotification('Could not load sessions', 'error');
    }
}

async function startSession(event) {
    event.preventDefault();
    const button = document.getElementById('startSessionBtn');
    const className = document.getElementById('sessionClass').value;
    const graceMinutes = document.getElementById('sessionGrace').value;
    button.disabled = true;
    try {
        const { res, data } = await apiJson('/api/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ class_name: className, grace_minutes: Number(graceMinutes) }),
        });
        if (!res.ok || !data.success) {
            showNotification(data.message || 'Could not start session', 'error');
            return;
        }
        showNotification(`Session started for ${className}`, 'success');
        await loadSessions();
    } catch (err) {
        showNotification('Could not start session: ' + err.message, 'error');
    } finally {
        button.disabled = false;
    }
}

async function closeSession(sessionId) {
    try {
        const { res, data } = await apiJson(`/api/sessions/${encodeURIComponent(sessionId)}/close`, {
            method: 'POST',
        });
        if (!res.ok || !data.success) {
            showNotification(data.message || 'Could not close session', 'error');
            return;
        }
        showNotification('Session closed; absences recorded', 'success');
        await loadSessions();
        await loadDashboard();
    } catch (err) {
        showNotification('Could not close session: ' + err.message, 'error');
    }
}

async function generateReport(showReadyNotification = true) {
    const date = document.getElementById('reportDate').value;
    const classFilter = document.getElementById('reportClass').value;
    const sessionFilter = document.getElementById('reportSession').value;
    if (!date) {
        showNotification('Please select a date', 'error');
        return;
    }

    let url = `/api/attendance/report?date=${encodeURIComponent(date)}`;
    if (classFilter) url += `&class=${encodeURIComponent(classFilter)}`;
    if (sessionFilter) url += `&session_id=${encodeURIComponent(sessionFilter)}`;

    try {
        const { res, data } = await apiJson(url);
        if (!res.ok || !Array.isArray(data)) {
            showNotification(data.message || 'Could not generate report', 'error');
            return;
        }
        currentReportData = Array.isArray(data) ? data : [];
        currentReportSessionId = sessionFilter;
        displayReport(currentReportData);
        if (showReadyNotification) showNotification('Report ready', 'success');
    } catch (err) {
        showNotification('Error generating report: ' + err.message, 'error');
    }
}

function displayReport(data) {
    const tbody = document.getElementById('reportBody');
    tbody.innerHTML = '';

    if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty">No records found</td></tr>';
        return;
    }

    data.forEach((record) => {
        const status = record.status || 'Absent';
        const pillClass = status === 'Present' ? 'present' : (status === 'Late' ? 'late' : 'absent');
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${escapeHtml(record.student_id)}</td>
            <td>${escapeHtml(record.name)}</td>
            <td>${escapeHtml(record.class)}</td>
            <td>${escapeHtml(record.date || '—')}</td>
            <td>${escapeHtml(record.time_in || '—')}</td>
            <td>${escapeHtml(record.time_out || '—')}</td>
            <td><span class="status-pill ${pillClass}">${escapeHtml(status)}</span></td>
            <td class="report-actions">
                ${currentReportSessionId ? `
                    <button type="button" class="btn btn-secondary btn-small"
                            data-correct-attendance data-student-id="${escapeHtml(record.student_id)}">Correct</button>
                    <button type="button" class="btn btn-ghost btn-small"
                            data-correction-history data-student-id="${escapeHtml(record.student_id)}">History</button>
                ` : '<span class="optional">Choose a session</span>'}
            </td>
        `;
        tbody.appendChild(row);
    });
}

function openAttendanceCorrection(record) {
    const dialog = document.getElementById('attendanceCorrectionDialog');
    const form = document.getElementById('attendanceCorrectionForm');
    form.reset();
    dialog.dataset.studentId = record.student_id;
    dialog.dataset.sessionId = currentReportSessionId;
    document.getElementById('correctionStudent').textContent =
        `${record.name} (${record.student_id}) · ${record.date}`;
    document.getElementById('correctionStatus').value = record.status || 'Absent';
    document.getElementById('correctionTimeIn').value = record.time_in || '';
    document.getElementById('correctionTimeOut').value = record.time_out || '';
    updateCorrectionTimeFields();
    dialog.showModal();
}

function updateCorrectionTimeFields() {
    const absent = document.getElementById('correctionStatus').value === 'Absent';
    const times = document.getElementById('correctionTimes');
    const timeIn = document.getElementById('correctionTimeIn');
    const timeOut = document.getElementById('correctionTimeOut');
    times.hidden = absent;
    timeIn.required = !absent;
    timeIn.disabled = absent;
    timeOut.disabled = absent;
}

async function saveAttendanceCorrection(event) {
    event.preventDefault();
    const dialog = document.getElementById('attendanceCorrectionDialog');
    const button = document.getElementById('saveCorrectionBtn');
    const status = document.getElementById('correctionStatus').value;
    const payload = {
        session_id: dialog.dataset.sessionId,
        student_id: dialog.dataset.studentId,
        status,
        reason: document.getElementById('correctionReason').value.trim(),
        time_in: status === 'Absent' ? null : document.getElementById('correctionTimeIn').value,
        time_out: status === 'Absent' ? null : document.getElementById('correctionTimeOut').value,
    };

    button.disabled = true;
    try {
        const { res, data } = await apiJson('/api/attendance/correct', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok || !data.success) {
            showNotification(data.message || 'Could not correct attendance', 'error');
            return;
        }
        dialog.close();
        showNotification(data.message, 'success');
        await generateReport(false);
        await loadDashboard();
    } catch (err) {
        showNotification('Could not correct attendance: ' + err.message, 'error');
    } finally {
        button.disabled = false;
    }
}

async function loadCorrectionHistory(record) {
    const dialog = document.getElementById('correctionHistoryDialog');
    const list = document.getElementById('correctionHistoryList');
    document.getElementById('correctionHistoryStudent').textContent =
        `${record.name} (${record.student_id}) · ${record.date}`;
    list.innerHTML = '<li class="empty">Loading correction history…</li>';
    dialog.showModal();
    try {
        const query = new URLSearchParams({
            session_id: currentReportSessionId,
            student_id: record.student_id,
        });
        const { res, data } = await apiJson(`/api/attendance/corrections?${query}`);
        if (!res.ok || !Array.isArray(data)) {
            list.innerHTML = `<li class="empty">${escapeHtml(data.message || 'Could not load correction history')}</li>`;
            return;
        }
        if (!data.length) {
            list.innerHTML = '<li class="empty">No corrections recorded for this session.</li>';
            return;
        }
        list.innerHTML = data.map((item) => {
            const time = item.corrected_at
                ? new Date(item.corrected_at).toLocaleString()
                : 'Unknown time';
            const timeChanges = [];
            if (item.previous_time_in !== item.new_time_in) {
                timeChanges.push(`Time in: ${item.previous_time_in || '—'} → ${item.new_time_in || '—'}`);
            }
            if (item.previous_time_out !== item.new_time_out) {
                timeChanges.push(`Time out: ${item.previous_time_out || '—'} → ${item.new_time_out || '—'}`);
            }
            return `
                <li>
                    <strong>${escapeHtml(item.previous_status)} → ${escapeHtml(item.new_status)}</strong>
                    ${timeChanges.length ? `<p>${timeChanges.map(escapeHtml).join('<br>')}</p>` : ''}
                    <p>${escapeHtml(item.reason)}</p>
                    <small>${escapeHtml(item.staff_username)} · ${escapeHtml(time)}</small>
                </li>
            `;
        }).join('');
    } catch (err) {
        list.innerHTML = `<li class="empty">${escapeHtml(err.message || 'Could not load correction history')}</li>`;
    }
}

function exportReport() {
    if (!currentReportData.length) {
        showNotification('Generate a report first', 'error');
        return;
    }

    let csv = 'Student ID,Name,Class,Date,Time In,Time Out,Status\n';
    currentReportData.forEach((record) => {
        csv += `${record.student_id},"${String(record.name || '').replace(/"/g, '""')}",${record.class},"${record.date || ''}","${record.time_in || ''}","${record.time_out || ''}",${record.status || 'Absent'}\n`;
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
