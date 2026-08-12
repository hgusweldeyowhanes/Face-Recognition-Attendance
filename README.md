# Presence

Face recognition attendance for classrooms. Flask API + modern web UI. Students register with a photo; check-in uses the camera or an upload.

## Features

- Face check-in (camera or photo upload)
- Student registration with validation-safe IDs
- Live overview by class
- Attendance reports + CSV export
- Encoding cache (DB-backed) for faster recognition
- `/health` endpoint for monitoring
- Production server via Waitress
- Docker Compose ready

## Quick start (local)

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # or: cp .env.example .env
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

**Note:** `dlib` / `face-recognition` can be slow to install on Windows. If a pinned dlib version fails, the requirements already allow `dlib>=19.24.2`.

## Production

1. Set a strong `SECRET_KEY` and `FLASK_ENV=production` in `.env`.
2. Set `FLASK_DEBUG=False`.
3. Restrict `CORS_ORIGINS` to your domain.
4. Run with Waitress:

```bash
# Option A — through app entry (production mode)
set FLASK_ENV=production
python app.py

# Option B — explicit Waitress
waitress-serve --host=0.0.0.0 --port=5000 --threads=4 wsgi:app
```

### Docker

```bash
# Generate a secret, then:
set SECRET_KEY=your-long-random-secret
docker compose up --build -d
```

Health check: `GET /health`

## Environment

See `.env.example` for all options. Important ones:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Required strong secret in production |
| `FLASK_ENV` | `development` or `production` |
| `FACE_RECOGNITION_TOLERANCE` | Lower = stricter (default `0.6`) |
| `MAX_UPLOAD_MB` | Upload size limit (default `5`) |
| `ENABLE_EMAIL_NOTIFICATIONS` | Optional SMTP alerts |

## Project layout

```
├── app.py              # Application + API
├── wsgi.py             # Production WSGI entry
├── templates/          # UI
├── static/             # CSS / JS
├── known_faces/        # Face images (runtime)
├── uploads/            # Temp uploads (runtime)
├── Dockerfile
└── docker-compose.yml
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI |
| GET | `/health` | Health probe |
| GET | `/api/students` | List students |
| POST | `/api/students/add` | Register + face photo |
| POST | `/api/recognize` | Recognize + mark present |
| GET | `/api/attendance/summary` | Class summary |
| GET | `/api/attendance/report` | Filtered report |
| GET | `/api/classes` | Distinct classes |
| GET | `/api/student/<id>/history` | History |

## Student IDs

Use IDs like `MI-01` — **no** `/` or `\` (those create folders on disk).

## License

Use freely for education and internal deployments.
