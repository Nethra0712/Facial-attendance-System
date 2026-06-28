# Facial Attendance System

A web-based employee attendance system that uses real-time facial recognition to clock employees in and out, built with Flask, OpenCV, and the `face_recognition` library. It includes separate admin and employee dashboards, payroll, leave management, and holiday/off-day configuration.

## Features

- **Face-based attendance** — live webcam recognition marks attendance automatically via `/video_feed` and the recognition API
- **Admin dashboard** — register new employees (capturing face samples), train the recognition model, view/manage records
- **Employee dashboard** — personal attendance history and leave requests
- **Manual attendance** — admin override for marking attendance when face recognition isn't available
- **Payroll** — generate and email payroll slips to employees (via Flask-Mail)
- **Leave management** — employees request leave, admins approve/reject and track leave balances
- **Holidays & off-days** — admin-configurable calendar used in attendance/payroll calculations
- **Reports** — filtered/advanced attendance reporting
- **Authentication** — role-based login (admin / employee) via Flask-Login with hashed passwords

## Tech Stack

- **Backend:** Flask, Flask-Login, Flask-Mail
- **Face Recognition:** OpenCV, `face_recognition` (dlib-based), NumPy, Pillow
- **Database:** MySQL (`mysql-connector-python`)
- **Frontend:** HTML/CSS/JS (Jinja templates)
- **Data handling:** pandas

## Project Structure

```
facial_attendance_system/
├── app.py                      # Main Flask app and routes
├── face_recognition_module.py  # Face detection, training, and recognition logic
├── database_handler.py         # MySQL queries and data access layer
├── migrate.py                  # Database migration helper
├── database/
│   └── attendance_db.sql       # Schema: users, attendance, face_encodings, messages
├── models/
│   └── face_encodings.pkl      # Trained face encodings (generated, not in repo)
├── training_data/              # Per-employee face image samples (not in repo)
├── templates/                  # Jinja2 HTML templates (login, dashboards, reports, etc.)
├── static/
│   ├── css/style.css
│   └── js/script.js
└── requirements.txt
```

## Prerequisites

- Python 3.11+
- MySQL Server
- A webcam (for live recognition/registration)
- On Windows, building `dlib`/`face_recognition` may require [CMake](https://cmake.org/download/) and Visual C++ Build Tools

## Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/<your-username>/facial-attendance-system.git
   cd facial-attendance-system
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Set up the database**
   - Create a MySQL database and run the schema:
     ```bash
     mysql -u <user> -p <database_name> < database/attendance_db.sql
     ```
   - This creates the `users`, `attendance`, `face_encodings`, and `messages` tables.

4. **Configure environment variables**
   Create a `.env` file in the project root (this file is gitignored — never commit it):
   ```env
   DB_HOST=localhost
   DB_USER=your_db_user
   DB_PASSWORD=your_db_password
   DB_NAME=attendance_db
   FLASK_SECRET_KEY=replace-with-a-random-secret-key
   MAIL_SERVER=smtp.example.com
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USERNAME=your_email@example.com
   MAIL_PASSWORD=your_email_app_password
   MAIL_DEFAULT_SENDER=your_email@example.com
   ```

5. **Add training data**
   Create a `training_data/` folder with one subfolder per person (e.g. `EMP1/`, `ADMIN1/`), each containing several face photos. This folder is gitignored by default since it contains personal biometric images — keep it local or store it securely elsewhere.

6. **Run the app**
   ```bash
   python app.py
   ```
   Visit `http://localhost:5000` in your browser.

## Usage

1. Log in as an admin and register employees through **Admin → Register**, capturing face samples via webcam.
2. Train the model (`/api/train_model`) so new faces are recognized.
3. Start the live recognition feed to begin automatic attendance marking.
4. Employees log in to view their attendance, request leave, and check payroll info.
5. Admins manage holidays, off-days, manual attendance corrections, and generate reports from their dashboard.

## Security & Privacy Notes

- `.env`, `training_data/`, and trained model files are excluded via `.gitignore` — **do not commit real credentials or employee photos** to a public repository.
- Passwords are hashed with Werkzeug's `generate_password_hash`; never store plaintext passwords.
- Face images and encodings are biometric data — handle them in line with your organization's data protection policies and applicable privacy laws.

## License

This project is licensed under the MIT License (or update this section to match the license you select on GitHub).
