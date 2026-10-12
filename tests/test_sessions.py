import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from io import BytesIO

import numpy as np
import pytest

os.environ["DATABASE_PATH"] = os.path.join(
    tempfile.gettempdir(), f"presence-session-tests-{os.getpid()}.sqlite3"
)

import app as attendance_app


@pytest.fixture(autouse=True)
def fresh_database(tmp_path, monkeypatch):
    monkeypatch.setattr(attendance_app, "DATABASE", str(tmp_path / "attendance.db"))
    attendance_app.init_db()


@pytest.fixture
def client():
    return attendance_app.app.test_client()


def add_student(student_id, class_name="10-A"):
    conn = attendance_app.get_db()
    conn.execute(
        "INSERT INTO students (student_id, name, class_name) VALUES (?, ?, ?)",
        (student_id, student_id, class_name),
    )
    conn.commit()
    conn.close()


def test_start_session_validates_class_and_prevents_two_active_sessions(client):
    add_student("STU-1")

    missing_class = client.post(
        "/api/sessions", json={"class_name": "11-B", "grace_minutes": 10}
    )
    assert missing_class.status_code == 404

    started = client.post(
        "/api/sessions", json={"class_name": "10-A", "grace_minutes": 10}
    )
    assert started.status_code == 201
    assert started.json["session"]["grace_minutes"] == 10

    duplicate = client.post("/api/sessions", json={"class_name": "10-A"})
    assert duplicate.status_code == 409


def test_close_session_marks_unchecked_students_absent_and_reports_session(client):
    add_student("STU-1")
    add_student("STU-2")
    started = client.post("/api/sessions", json={"class_name": "10-A"})
    session_id = started.json["session"]["id"]

    conn = attendance_app.get_db()
    conn.execute(
        '''INSERT INTO attendance (student_id, date, time_in, status, session_id)
           VALUES (?, ?, ?, ?, ?)''',
        ("STU-1", started.json["session"]["date"], "09:05:00", "Late", session_id),
    )
    conn.commit()
    conn.close()

    closed = client.post(f"/api/sessions/{session_id}/close")
    assert closed.status_code == 200
    assert closed.json["sessions"][0]["absent_count"] == 1

    report = client.get(f"/api/attendance/report?session_id={session_id}")
    assert report.status_code == 200
    assert {row["student_id"]: row["status"] for row in report.json} == {
        "STU-1": "Late",
        "STU-2": "Absent",
    }

    duplicate_close = client.post(f"/api/sessions/{session_id}/close")
    assert duplicate_close.status_code == 409


def test_recognition_marks_late_arrival_for_active_session(client, monkeypatch):
    add_student("STU-1")
    started = client.post(
        "/api/sessions", json={"class_name": "10-A", "grace_minutes": 10}
    )
    session_id = started.json["session"]["id"]
    old_start = (datetime.now().astimezone() - timedelta(minutes=15)).isoformat()
    conn = attendance_app.get_db()
    conn.execute(
        "UPDATE class_sessions SET started_at = ? WHERE id = ?",
        (old_start, session_id),
    )
    conn.commit()
    conn.close()

    encoding = np.ones(128)
    monkeypatch.setattr(
        attendance_app, "load_known_faces", lambda: ([encoding], ["STU-1"])
    )
    monkeypatch.setattr(
        attendance_app.face_recognition,
        "load_image_file",
        lambda _path: np.zeros((2, 2, 3), dtype=np.uint8),
    )
    monkeypatch.setattr(
        attendance_app.face_recognition, "face_encodings", lambda _image: [encoding]
    )
    monkeypatch.setattr(
        attendance_app.face_recognition,
        "face_distance",
        lambda _known, _face: np.array([0.1]),
    )
    monkeypatch.setattr(
        attendance_app.face_recognition,
        "compare_faces",
        lambda _known, _face, tolerance: [True],
    )
    monkeypatch.setattr(attendance_app, "send_notification", lambda *_args: None)

    response = client.post(
        "/api/recognize",
        data={"image": (BytesIO(b"fake image"), "capture.jpg")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.json["attendance_status"] == "Late"
    assert response.json["session_id"] == session_id

    conn = attendance_app.get_db()
    row = conn.execute(
        "SELECT status FROM attendance WHERE student_id = ? AND session_id = ?",
        ("STU-1", session_id),
    ).fetchone()
    conn.close()
    assert row["status"] == "Late"


def test_init_db_migrates_legacy_daily_attendance(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(attendance_app, "DATABASE", str(db_path))
    conn = sqlite3.connect(db_path)
    conn.execute(
        '''CREATE TABLE students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            class_name TEXT,
            face_encoding BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''
    )
    conn.execute(
        '''CREATE TABLE attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            date DATE NOT NULL,
            time_in TIME,
            time_out TIME,
            status TEXT DEFAULT 'Present',
            UNIQUE(student_id, date)
        )'''
    )
    conn.execute(
        "INSERT INTO students (student_id, name, class_name) VALUES ('STU-1', 'Student', '10-A')"
    )
    conn.execute(
        "INSERT INTO attendance (student_id, date, time_in, status) VALUES ('STU-1', '2026-10-01', '09:00', 'Present')"
    )
    conn.commit()
    conn.close()

    attendance_app.init_db()

    conn = attendance_app.get_db()
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(attendance)")}
    record = conn.execute("SELECT * FROM attendance").fetchone()
    conn.close()
    assert "session_id" in columns
    assert record["student_id"] == "STU-1"
    assert record["date"] == "2026-10-01"
    assert record["session_id"] is None
