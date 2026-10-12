import os
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import patch

import numpy as np
from werkzeug.security import check_password_hash, generate_password_hash

os.environ["DATABASE_PATH"] = os.path.join(
    tempfile.gettempdir(), f"presence-session-tests-{os.getpid()}.sqlite3"
)

import app as attendance_app


class ClassSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        attendance_app.DATABASE = os.path.join(self.temp_dir.name, "attendance.db")
        attendance_app.init_db()
        self.client = attendance_app.app.test_client()
        conn = attendance_app.get_db()
        conn.execute(
            'INSERT INTO staff_users (username, password_hash, role) VALUES (?, ?, ?)',
            ('admin', generate_password_hash('AdminPassword123!'), 'admin'),
        )
        conn.commit()
        conn.close()
        self.assertEqual(
            self.client.post(
                '/api/auth/login',
                json={'username': 'admin', 'password': 'AdminPassword123!'},
            ).status_code,
            200,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def add_student(self, student_id, class_name="10-A"):
        conn = attendance_app.get_db()
        conn.execute(
            '''INSERT INTO students (student_id, name, class_name, face_consent_at, face_consent_version)
               VALUES (?, ?, ?, ?, ?)''',
            (
                student_id,
                student_id,
                class_name,
                datetime.now().astimezone().isoformat(timespec='seconds'),
                attendance_app.FACE_CONSENT_VERSION,
            ),
        )
        conn.commit()
        conn.close()

    def test_home_page_includes_session_management(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Class sessions", response.data)
        self.assertIn(b"startSessionForm", response.data)

    def test_staff_login_is_required_and_admin_can_create_teacher(self):
        anonymous = attendance_app.app.test_client()
        self.assertEqual(anonymous.get('/api/students').status_code, 401)
        self.assertEqual(anonymous.get('/health').status_code, 200)
        self.assertEqual(
            anonymous.post(
                '/api/auth/login',
                json={'username': 'admin', 'password': 'wrong-password'},
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.get(
                '/api/auth/me',
                headers={'Origin': 'https://untrusted.example'},
            ).status_code,
            403,
        )

        response = self.client.post(
            '/api/admin/users',
            json={'username': 'teacher.one', 'password': 'TeacherPassword123!'},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json['user']['role'], 'teacher')

        conn = attendance_app.get_db()
        stored_hash = conn.execute(
            'SELECT password_hash FROM staff_users WHERE username = ?',
            ('teacher.one',),
        ).fetchone()['password_hash']
        conn.close()
        self.assertTrue(check_password_hash(stored_hash, 'TeacherPassword123!'))
        self.assertNotEqual(stored_hash, 'TeacherPassword123!')

        teacher = attendance_app.app.test_client()
        login = teacher.post(
            '/api/auth/login',
            json={'username': 'teacher.one', 'password': 'TeacherPassword123!'},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(
            teacher.post(
                '/api/admin/users',
                json={'username': 'teacher.two', 'password': 'TeacherPassword456!'},
            ).status_code,
            403,
        )
        self.assertEqual(teacher.get('/api/students').status_code, 403)

    def test_admin_cli_can_create_initial_administrator(self):
        runner = attendance_app.app.test_cli_runner()
        result = runner.invoke(
            args=['create-admin'],
            input='second-admin\nSecondAdminPassword123!\nSecondAdminPassword123!\n',
        )
        self.assertEqual(result.exit_code, 0, result.output)
        conn = attendance_app.get_db()
        user = conn.execute(
            'SELECT role, password_hash FROM staff_users WHERE username = ?',
            ('second-admin',),
        ).fetchone()
        conn.close()
        self.assertEqual(user['role'], 'admin')
        self.assertTrue(check_password_hash(user['password_hash'], 'SecondAdminPassword123!'))

    def test_student_registration_requires_explicit_face_consent(self):
        response = self.client.post(
            '/api/students/add',
            data={
                'student_id': 'STU-1',
                'name': 'Student',
                'class_name': '10-A',
                'image': (BytesIO(b'fake image'), 'face.jpg'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('consent', response.json['message'].lower())
        conn = attendance_app.get_db()
        count = conn.execute('SELECT COUNT(*) AS count FROM students').fetchone()['count']
        conn.close()
        self.assertEqual(count, 0)

    def test_re_enrollment_records_new_consent_for_legacy_student(self):
        self.add_student('STU-1')
        conn = attendance_app.get_db()
        conn.execute(
            'UPDATE students SET face_encoding = NULL, face_consent_at = NULL, face_consent_version = NULL WHERE student_id = ?',
            ('STU-1',),
        )
        conn.commit()
        conn.close()

        with tempfile.TemporaryDirectory() as temp_dir:
            faces_dir = os.path.join(temp_dir, 'faces')
            uploads_dir = os.path.join(temp_dir, 'uploads')
            os.makedirs(uploads_dir)
            with ExitStack() as stack:
                stack.enter_context(patch.object(attendance_app, 'FACES_DIR', faces_dir))
                stack.enter_context(patch.object(attendance_app, 'UPLOAD_DIR', uploads_dir))
                stack.enter_context(patch.object(attendance_app, 'encode_face', return_value=np.ones(128)))
                stack.enter_context(
                    patch.object(
                        attendance_app.face_recognition,
                        'load_image_file',
                        return_value=np.zeros((2, 2, 3), dtype=np.uint8),
                    )
                )
                stack.enter_context(patch.object(attendance_app.cv2, 'imwrite', return_value=True))
                response = self.client.post(
                    '/api/students/STU-1/face-data',
                    data={
                        'face_consent': 'true',
                        'image': (BytesIO(b'fake image'), 'replacement.jpg'),
                    },
                    content_type='multipart/form-data',
                )
            self.assertEqual(response.status_code, 200)

        conn = attendance_app.get_db()
        student = conn.execute(
            'SELECT face_encoding, face_consent_at, face_consent_version FROM students WHERE student_id = ?',
            ('STU-1',),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(student['face_encoding'])
        self.assertIsNotNone(student['face_consent_at'])
        self.assertEqual(student['face_consent_version'], attendance_app.FACE_CONSENT_VERSION)

    def test_delete_face_data_keeps_attendance_and_excludes_face_from_recognition(self):
        self.add_student('STU-1')
        conn = attendance_app.get_db()
        conn.execute(
            'UPDATE students SET face_encoding = ? WHERE student_id = ?',
            (np.ones(128).tobytes(), 'STU-1'),
        )
        conn.execute(
            '''INSERT INTO attendance (student_id, date, time_in, status)
               VALUES (?, ?, ?, ?)''',
            ('STU-1', datetime.now().strftime('%Y-%m-%d'), '09:00:00', 'Present'),
        )
        conn.commit()
        conn.close()

        with tempfile.TemporaryDirectory() as faces_dir:
            student_dir = os.path.join(faces_dir, 'STU-1')
            os.makedirs(student_dir)
            with open(os.path.join(student_dir, 'STU-1.jpg'), 'wb') as image:
                image.write(b'private face image')
            with patch.object(attendance_app, 'FACES_DIR', faces_dir):
                attendance_app.invalidate_face_cache()
                self.assertEqual(len(attendance_app.load_known_faces()[0]), 1)
                roster = self.client.get('/api/students')
                self.assertEqual(roster.status_code, 200)
                self.assertTrue(roster.json[0]['face_data_present'])
                self.assertNotIn('face_encoding', roster.json[0])
                response = self.client.delete(
                    '/api/students/STU-1/face-data',
                    json={'confirm': True},
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(os.path.exists(student_dir))
                self.assertEqual(attendance_app.load_known_faces(), ([], []))

        conn = attendance_app.get_db()
        student = conn.execute(
            'SELECT face_encoding, face_consent_at, face_consent_version FROM students WHERE student_id = ?',
            ('STU-1',),
        ).fetchone()
        history = conn.execute(
            'SELECT status FROM attendance WHERE student_id = ?',
            ('STU-1',),
        ).fetchone()
        conn.close()
        self.assertIsNone(student['face_encoding'])
        self.assertIsNone(student['face_consent_at'])
        self.assertIsNone(student['face_consent_version'])
        self.assertEqual(history['status'], 'Present')

    def test_start_session_validates_class_and_prevents_two_active_sessions(self):
        self.add_student("STU-1")

        missing_class = self.client.post(
            "/api/sessions", json={"class_name": "11-B", "grace_minutes": 10}
        )
        self.assertEqual(missing_class.status_code, 404)

        started = self.client.post(
            "/api/sessions", json={"class_name": "10-A", "grace_minutes": 10}
        )
        self.assertEqual(started.status_code, 201)
        self.assertEqual(started.json["session"]["grace_minutes"], 10)

        duplicate = self.client.post("/api/sessions", json={"class_name": "10-A"})
        self.assertEqual(duplicate.status_code, 409)

    def test_close_session_marks_unchecked_students_absent_and_reports_session(self):
        self.add_student("STU-1")
        self.add_student("STU-2")
        started = self.client.post("/api/sessions", json={"class_name": "10-A"})
        session_id = started.json["session"]["id"]

        conn = attendance_app.get_db()
        conn.execute(
            '''INSERT INTO attendance (student_id, date, time_in, status, session_id)
               VALUES (?, ?, ?, ?, ?)''',
            ("STU-1", started.json["session"]["date"], "09:05:00", "Late", session_id),
        )
        conn.commit()
        conn.close()

        closed = self.client.post(f"/api/sessions/{session_id}/close")
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json["sessions"][0]["absent_count"], 1)

        report = self.client.get(f"/api/attendance/report?session_id={session_id}")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(
            {row["student_id"]: row["status"] for row in report.json},
            {"STU-1": "Late", "STU-2": "Absent"},
        )

        duplicate_close = self.client.post(f"/api/sessions/{session_id}/close")
        self.assertEqual(duplicate_close.status_code, 409)

    def test_attendance_corrections_update_record_and_keep_audit_history(self):
        self.add_student('STU-1')
        started = self.client.post('/api/sessions', json={'class_name': '10-A'})
        session_id = started.json['session']['id']
        self.client.post(f'/api/sessions/{session_id}/close')

        missing_reason = self.client.post(
            '/api/attendance/correct',
            json={
                'session_id': session_id,
                'student_id': 'STU-1',
                'status': 'Present',
                'time_in': '08:55',
                'reason': ' ',
            },
        )
        self.assertEqual(missing_reason.status_code, 400)

        first_correction = self.client.post(
            '/api/attendance/correct',
            json={
                'session_id': session_id,
                'student_id': 'STU-1',
                'status': 'Present',
                'time_in': '08:55',
                'time_out': '15:00',
                'reason': 'Teacher verified sign-in sheet',
            },
        )
        self.assertEqual(first_correction.status_code, 200)
        second_correction = self.client.post(
            '/api/attendance/correct',
            json={
                'session_id': session_id,
                'student_id': 'STU-1',
                'status': 'Late',
                'time_in': '09:05:00',
                'time_out': None,
                'reason': 'Arrival time was entered incorrectly',
            },
        )
        self.assertEqual(second_correction.status_code, 200)

        report = self.client.get(f'/api/attendance/report?session_id={session_id}')
        self.assertEqual(report.status_code, 200)
        report_row = report.json[0]
        self.assertEqual(report_row['status'], 'Late')
        self.assertEqual(report_row['time_in'], '09:05:00')
        self.assertEqual(report_row['session_id'], session_id)
        self.assertIsNotNone(report_row['attendance_id'])

        history = self.client.get(
            f'/api/attendance/corrections?session_id={session_id}&student_id=STU-1'
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json), 2)
        self.assertEqual(
            [(item['previous_status'], item['new_status']) for item in history.json],
            [('Present', 'Late'), ('Absent', 'Present')],
        )
        self.assertEqual(history.json[0]['staff_username'], 'admin')

    def test_attendance_correction_cannot_target_a_different_class(self):
        self.add_student('STU-1', class_name='10-A')
        started = self.client.post('/api/sessions', json={'class_name': '10-A'})
        self.add_student('STU-2', class_name='11-B')

        response = self.client.post(
            '/api/attendance/correct',
            json={
                'session_id': started.json['session']['id'],
                'student_id': 'STU-2',
                'status': 'Absent',
                'reason': 'Wrong student was marked present',
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_recognition_marks_late_arrival_for_active_session(self):
        self.add_student("STU-1")
        started = self.client.post(
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
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(attendance_app, "load_known_faces", return_value=([encoding], ["STU-1"]))
            )
            stack.enter_context(
                patch.object(
                    attendance_app.face_recognition,
                    "load_image_file",
                    return_value=np.zeros((2, 2, 3)),
                )
            )
            stack.enter_context(
                patch.object(attendance_app.face_recognition, "face_encodings", return_value=[encoding])
            )
            stack.enter_context(
                patch.object(
                    attendance_app.face_recognition,
                    "face_distance",
                    return_value=np.array([0.1]),
                )
            )
            stack.enter_context(
                patch.object(attendance_app.face_recognition, "compare_faces", return_value=[True])
            )
            stack.enter_context(patch.object(attendance_app, "send_notification"))
            response = self.client.post(
                "/api/recognize",
                data={"image": (BytesIO(b"fake image"), "capture.jpg")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["attendance_status"], "Late")
        self.assertEqual(response.json["session_id"], session_id)

        conn = attendance_app.get_db()
        row = conn.execute(
            "SELECT status FROM attendance WHERE student_id = ? AND session_id = ?",
            ("STU-1", session_id),
        ).fetchone()
        conn.close()
        self.assertEqual(row["status"], "Late")

    def test_check_out_preserves_late_status_across_multiple_sessions(self):
        self.add_student("STU-1")
        first = self.client.post("/api/sessions", json={"class_name": "10-A"})
        first_id = first.json["session"]["id"]
        conn = attendance_app.get_db()
        conn.execute(
            '''INSERT INTO attendance (student_id, date, time_in, status, session_id)
               VALUES (?, ?, ?, ?, ?)''',
            ("STU-1", first.json["session"]["date"], "09:05:00", "Late", first_id),
        )
        conn.commit()
        conn.close()
        self.client.post(f"/api/sessions/{first_id}/close")

        second = self.client.post("/api/sessions", json={"class_name": "10-A"})
        second_id = second.json["session"]["id"]
        conn = attendance_app.get_db()
        conn.execute(
            '''INSERT INTO attendance (student_id, date, time_in, status, session_id)
               VALUES (?, ?, ?, ?, ?)''',
            ("STU-1", second.json["session"]["date"], "10:00:00", "Present", second_id),
        )
        conn.commit()
        conn.close()

        checked_out = self.client.post(
            "/api/attendance/check-out",
            json={"student_id": "STU-1", "time_out": "11:00:00"},
        )
        self.assertEqual(checked_out.status_code, 200)

        conn = attendance_app.get_db()
        statuses = {
            row["session_id"]: (row["status"], row["time_out"])
            for row in conn.execute(
                "SELECT session_id, status, time_out FROM attendance WHERE student_id = ?",
                ("STU-1",),
            )
        }
        conn.close()
        self.assertEqual(statuses[first_id], ("Late", None))
        self.assertEqual(statuses[second_id], ("Present", "11:00:00"))

    def test_init_db_migrates_legacy_daily_attendance(self):
        db_path = os.path.join(self.temp_dir.name, "legacy.db")
        attendance_app.DATABASE = db_path
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
        conn.execute(
            'UPDATE students SET face_encoding = ? WHERE student_id = ?',
            (np.ones(128).tobytes(), 'STU-1'),
        )
        conn.commit()
        conn.close()

        attendance_app.init_db()

        conn = attendance_app.get_db()
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(attendance)")}
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        record = conn.execute("SELECT * FROM attendance").fetchone()
        migrated_student = conn.execute(
            'SELECT face_consent_at, face_consent_version FROM students WHERE student_id = ?',
            ('STU-1',),
        ).fetchone()
        conn.close()
        self.assertIn("session_id", columns)
        self.assertEqual(record["student_id"], "STU-1")
        self.assertEqual(record["date"], "2026-10-01")
        self.assertIsNone(record["session_id"])
        self.assertIsNone(migrated_student['face_consent_at'])
        self.assertIsNone(migrated_student['face_consent_version'])
        self.assertIn('attendance_corrections', tables)
        with tempfile.TemporaryDirectory() as faces_dir:
            with patch.object(attendance_app, 'FACES_DIR', faces_dir):
                attendance_app.invalidate_face_cache()
                self.assertEqual(attendance_app.load_known_faces(), ([], []))


if __name__ == "__main__":
    unittest.main()
