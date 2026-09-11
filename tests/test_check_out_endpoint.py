import os
import tempfile
import unittest
from datetime import datetime

import app as attendance_app


class CheckOutEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, 'attendance-test.db')
        attendance_app.DATABASE = self.db_path
        attendance_app.init_db()

        conn = attendance_app.get_db()
        conn.execute(
            '''INSERT INTO students (student_id, name, email, class_name, face_encoding)
               VALUES (?, ?, ?, ?, ?)''',
            ('STU1', 'Alice', 'alice@example.com', 'A', None),
        )
        conn.execute(
            '''INSERT INTO attendance (student_id, date, time_in, time_out, status)
               VALUES (?, ?, ?, ?, ?)''',
            ('STU1', datetime.now().strftime('%Y-%m-%d'), '08:00:00', None, 'Present'),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_check_out_endpoint_records_time_out(self):
        client = attendance_app.app.test_client()
        response = client.post(
            '/api/attendance/check-out',
            json={'student_id': 'STU1', 'time_out': '17:30:00'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['student_id'], 'STU1')
        self.assertEqual(payload['time_out'], '17:30:00')

        conn = attendance_app.get_db()
        row = conn.execute(
            'SELECT time_out FROM attendance WHERE student_id = ? AND date = ?',
            ('STU1', datetime.now().strftime('%Y-%m-%d')),
        ).fetchone()
        conn.close()
        self.assertEqual(row['time_out'], '17:30:00')


if __name__ == '__main__':
    unittest.main()
