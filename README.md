# ProctorAI

ProctorAI is a local-first online assessment application with student exam taking, administrator exam management, explainable behavioural event scoring, and a human review queue. This workspace began empty; the current application is a functional MVP with a seeded sample exam and demo accounts.

## What works

- Student registration/login, password hashing, JWT sessions, role checks, student dashboard and profile.
- Admin dashboard, student listing/search, exam create/publish/delete, active-session overview, event review, results and CSV export.
- A published 30-minute Python Test with ten easy multiple-choice questions, alongside the sample CS exam. Published exams with multiple-choice and descriptive questions, timed attempt flow, answer autosave, resume of an open attempt, explicit camera consent, automatic timeout submission, and objective grading. Descriptive answers are marked for administrator review.
- Local webcam frame analysis via OpenCV + MediaPipe Face Landmarker Tasks. The setup script installs the model into `backend/models/face_landmarker.task`. The browser sends a small, transient frame to the local FastAPI service on the same machine every ~1.8 seconds; the service processes it in memory and does not write or forward frames. Persistent records contain event summaries only.
- Explainable score bands and contribution factors. Scores are not findings of cheating and never trigger an automatic penalty.
- Student notices for local camera signals, shown on the next analyzed frame (about every 1.8 seconds). Five notices pause the attempt with saved answers intact and send it for administrator review; the system does not assign a zero or decide misconduct.
- Window switches and detectable PrintScreen/Ctrl+P attempts are recorded in the administrator activity queue. The third recorded window switch ends the attempt and sends it for review.
- Responsive landing page, student experience and administrator workspace.

## Project layout

```text
frontend/                 React + TypeScript + Vite + Tailwind
  src/App.tsx             Public, student and administrator interfaces
  src/api.ts              Local REST client and token handling
  src/style.css           Responsive product styling
backend/
  app/main.py             FastAPI routes and application setup
  app/models.py           SQLAlchemy entities
  app/security.py         Password hashing, JWT and role checks
  app/scoring.py          Explainable heuristic scoring
  app/vision.py           Transient OpenCV / MediaPipe frame analysis
  app/database.py         SQLAlchemy database configuration
  tests/                  Backend tests
```

## Requirements

- Python 3.12 recommended (MediaPipe wheels vary by operating system and Python version).
- Node.js 20+ and npm.
- A modern browser and camera for proctored attempts. Camera access is available on `localhost` or HTTPS.

## Run locally

Open the `E:\VIBETHON\ml` folder in VS Code. Run this once in the integrated PowerShell terminal to build the backend environment, install dependencies and create `backend/.env`:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

After setup, start both services together from **Terminal → Run Task → ProctorAI: Start both**. VS Code opens separate terminals for the API and web app.

You can also start them manually in two terminals at the project root.

### 1. Start the backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API documentation is at <http://127.0.0.1:8000/docs>. The SQLite database is created in `backend/proctorai.db` on first start. To disable sample-account seeding, set `SEED_DEMO=false` in `backend/.env`.

### 2. Start the frontend

```powershell
cd frontend
npm run dev
```

Open <http://localhost:5173>. The frontend uses `http://127.0.0.1:8000/api` by default. For a different local API origin, set `VITE_API_URL` before starting Vite (for example, `$env:VITE_API_URL='http://127.0.0.1:8000/api'`).

### Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Administrator | `admin@proctorai.example.com` | `AdminDemo2026!` |
| Student | `student@proctorai.example.com` | `StudentDemo2026!` |

These are seeded demo records, not real users or exam results. Change them or disable seeding before any shared deployment. Set a unique `JWT_SECRET` in `backend/.env`; the built-in fallback is for local development only.

## Tests and build

```powershell
cd backend
python -m pytest
cd ..\frontend
npm test
npm run build
```

Backend tests cover security helpers and score behaviour; frontend tests cover pure scoring display helpers. Run these from the relevant directory after installing dependencies.

## Privacy and safeguards

- The browser requests video only after a student checks an explicit consent box and selects “Allow camera & start”. No audio is requested.
- Webcam frames are temporarily sent to the local API on `127.0.0.1` for local MediaPipe analysis. The frame bytes are decoded in memory; no image or video file is persisted. Administrators see session status and event summaries, never a live video feed.
- Only aggregated event type, duration, timestamps and review notes are stored. Use local disk access controls appropriate to your institution. Delete the SQLite file to remove local data (after stopping the server).
- A gaze estimate is sensitive to lighting, camera placement, glasses, disability and individual differences. It is a coarse signal, not proof. Review events with context and give students an avenue to explain them.
- Browsers cannot reliably prevent operating-system screenshot tools, external cameras or every capture shortcut. ProctorAI blocks the context menu and common PrintScreen/Ctrl+P keys where the browser exposes them, and records detectable attempts; do not present this as guaranteed screenshot prevention.
- Scoring uses a small transparent heuristic with per-event weights and duration caps, not a trained cheating classifier. No model accuracy is claimed. The optional scikit-learn dependency is reserved for future validated anomaly analysis; it is not used to make decisions in this MVP.
- No external AI service, paid API or video-storage service is used. Google-hosted fonts are not required; interface typography uses local system fonts.

## Current limitations

- SQLite tables are initialized on startup; Alembic migration files are not yet included. Back up the database before upgrades. Exam options and autosaved answers use JSON columns in this MVP; dedicated normalized option, answer, student-profile and score-history tables remain future schema work.
- Admin editing supports creating and deleting exams in the current UI. The API supports update, but a dedicated rich edit/question bank workflow is not yet exposed.
- Schedule timestamps, password reset/email delivery, manual marking UI for written answers, detailed profile editing, and configurable score thresholds are not implemented in this MVP. These require institutional workflows or email configuration.
- Camera compatibility is intended for Chromium-style browsers on localhost; it could not be exercised in this environment. MediaPipe runtime installation requires a platform-supported Python 3.12 wheel. If unavailable, the exam flow remains usable, and the student sees that face signals are unavailable rather than being told monitoring succeeded.
- Webcam analysis currently estimates face count and coarse horizontal gaze. Head pose, eye direction calibration, robust temporal classifier validation, accessibility tuning and independent performance evaluation remain future work.

## Security notes

Use HTTPS and a production-grade secret before deployment. Configure `CORS_ORIGINS`, restrict access to the database and API, rotate demo passwords, add rate limiting and audit/retention policies, and review applicable privacy and examination policies. This local MVP is not a compliance certification.
