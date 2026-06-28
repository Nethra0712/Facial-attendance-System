"""
Flask Web Application
Main application for facial recognition attendance system
"""

from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import cv2
import json
import time
import atexit
from datetime import datetime, date, time as dt_time, timedelta
from decimal import Decimal
import threading
import os
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

from face_recognition_module import FaceRecognitionSystem
from database_handler import DatabaseHandler

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default-fallback-key')

# Flask-Mail Configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

mail = Mail(app)

# Login Manager Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize systems
face_system = FaceRecognitionSystem()
db_handler = DatabaseHandler()

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['user_id']
        self.name = user_data['name']
        self.role = user_data['role']
        self.department = user_data['department']

@login_manager.user_loader
def load_user(user_id):
    user_data = db_handler.get_user(user_id)
    if user_data:
        return User(user_data)
    return None

# Global variables for video streaming
camera = None
recognition_active = False
last_recognition_time = {}  # Track last recognition time per user

# --- ROUTES ---

@app.route('/')
def landing():
    """Landing page"""
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        password = request.form.get('password')
        
        user_data = db_handler.get_user(user_id)
        if user_data and check_password_hash(user_data['password_hash'], password):
            user_obj = User(user_data)
            login_user(user_obj)
            if user_obj.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('employee_dashboard'))
        
        return render_template('login.html', error="Invalid credentials")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logout current user and release camera"""
    # Stop recognition and release hardware if it was running
    stop_recognition()
    release_camera()
    
    logout_user()
    return redirect(url_for('landing'))

# --- ADMIN ROUTES ---

@app.route('/admin')
@login_required
def admin_dashboard():
    """Admin Home page"""
    if current_user.role != 'admin':
        return redirect(url_for('employee_dashboard'))
    return render_template('index.html')

@app.route('/admin/register')
@login_required
def register_page():
    """User registration page"""
    if current_user.role != 'admin':
        return redirect(url_for('employee_dashboard'))
    return render_template('register.html')

@app.route('/admin/records')
@login_required
def records_page():
    """Attendance records page"""
    if current_user.role != 'admin':
        return redirect(url_for('employee_dashboard'))
    return render_template('records.html')

@app.route('/admin/payroll')
@login_required
def payroll_page():
    """Payroll records page"""
    if current_user.role != 'admin':
        return redirect(url_for('employee_dashboard'))
    return render_template('payroll.html')

# --- EMPLOYEE ROUTES ---

@app.route('/dashboard')
@login_required
def employee_dashboard():
    """Employee personal dashboard"""
    # Fetch employee's personal attendance
    attendance = db_handler.get_user_attendance_history(current_user.id)
    # Get user details for wage calc
    user_data = db_handler.get_user(current_user.id)
    daily_wage = float(user_data['daily_wage']) if user_data['daily_wage'] else 0.0
    total_payment = daily_wage * len(attendance)
    
    return render_template('employee_dashboard.html', 
                           attendance=attendance, 
                           total_payment=total_payment,
                           daily_wage=daily_wage)


# Global lock for camera access
camera_lock = threading.Lock()

def get_camera():
    """Get or initialize camera with robust Windows support and thread safety"""
    global camera
    with camera_lock:
        if camera is None or not camera.isOpened():
            logger.info("Attempting to open camera...")
            
            # On Windows, CAP_DSHOW is often faster and more reliable
            # We try standard index 0 first, then 1 as a fallback
            for index in [0, 1]:
                logger.info(f"Trying camera index {index} with CAP_DSHOW...")
                camera = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                
                if camera.isOpened():
                    logger.info(f"Camera successfully opened at index {index}")
                    # Allow hardware to settle
                    time.sleep(1.2)
                    return camera
                
                # Fallback to default backend if DSHOW fails
                logger.info(f"Falling back to default backend for index {index}...")
                camera = cv2.VideoCapture(index)
                if camera.isOpened():
                    logger.info(f"Camera successfully opened at index {index} (default backend)")
                    time.sleep(1.2)
                    return camera
            
            logger.error("CRITICAL: All camera initialization attempts failed!")
            camera = None
            
    return camera




def release_camera():
    """Release camera resource"""
    global camera
    if camera is not None:
        camera.release()
        camera = None

# Register cleanup for when the application stops
atexit.register(release_camera)


@app.route('/api/register_stream', methods=['POST'])
@login_required
def register_stream():
    """Streaming API for registration status updates"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
        
    data = request.json
    user_id = data.get('user_id')
    name = data.get('name')
    email = data.get('email', '')
    department = data.get('department', '')
    daily_wage = data.get('daily_wage', 0.0)
    password = data.get('password', '1234')

    if not user_id or not name:
        return jsonify({'success': False, 'message': 'User ID and Name are required'})

    def progress():
        try:
            yield json.dumps({'status': 'info', 'message': 'Camera initializing...'}) + '\n'
            
            # Hash password
            password_hash = generate_password_hash(password)
            
            # 1. Register in database
            db_success = db_handler.register_user(user_id, name, email, department, password_hash, 'employee', daily_wage)
            if not db_success:
                yield json.dumps({'status': 'error', 'message': 'User ID already exists'}) + '\n'
                return

            # 2. Capture images
            yield json.dumps({'status': 'info', 'message': 'Started capturing! Look at the camera window.'}) + '\n'
            face_success = face_system.capture_face_images(user_id, name, num_images=30)
            
            if not face_success:
                yield json.dumps({'status': 'error', 'message': 'Capture cancelled or failed'}) + '\n'
                return
                
            yield json.dumps({'status': 'info', 'message': 'Capturing finished! Training AI model...'}) + '\n'
            
            # 3. Train model
            train_success = face_system.train_model()
            if not train_success:
                yield json.dumps({'status': 'error', 'message': 'Model training failed'}) + '\n'
                return
                
            # 4. Finalize & Notify
            # Send digital notification to dashboard
            db_handler.add_message(
                user_id, 
                "Welcome to FaceAuth!", 
                f"Hello {name}, your account is now active. Your User ID is {user_id}. You can view your attendance and salary details here.",
                "welcome"
            )
            
            # Send welcome email
            if email:
                try:
                    msg = Message(
                        "Welcome to FaceAuth - Your Login Credentials",
                        recipients=[email]
                    )
                    msg.body = f"Hello {name},\n\nYour account has been successfully registered in the FaceAuth Attendance System.\n\n" \
                               f"Login Details:\n" \
                               f"User ID: {user_id}\n" \
                               f"Password: {password}\n\n" \
                               f"Please log in at: {request.host_url}\n\n" \
                               f"Best Regards,\nFaceAuth Team"
                    
                    # Run email sending in a separate thread to avoid blocking the generator
                    def send_async_email(app, msg):
                        try:
                            with app.app_context():
                                logger.info(f"Attempting to send email to {email}...")
                                mail.send(msg)
                                logger.info(f"Email sent successfully to {email}")
                        except Exception as e:
                            logger.error(f"ASYNC EMAIL ERROR: {e}")
                    
                    threading.Thread(target=send_async_email, args=(app, msg)).start()
                except Exception as mail_err:
                    logger.error(f"Failed to send welcome email: {mail_err}")

            yield json.dumps({'status': 'success', 'message': f'Registration complete! {name} is now enrolled.'}) + '\n'
            
        except Exception as e:
            yield json.dumps({'status': 'error', 'message': str(e)}) + '\n'

    return Response(progress(), mimetype='application/x-ndjson')


@app.route('/api/register_user', methods=['POST'])
@login_required
def register_user():
    """API endpoint to register new user"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    try:
        data = request.json
        user_id = data.get('user_id')
        name = data.get('name')
        email = data.get('email', '')
        department = data.get('department', '')
        daily_wage = data.get('daily_wage', 0.0)
        password = data.get('password', '1234') # Default password if not provided
        
        if not user_id or not name:
            return jsonify({'success': False, 'message': 'User ID and Name are required'})
        
        # Hash password
        password_hash = generate_password_hash(password)
        
        # Register in database
        db_success = db_handler.register_user(user_id, name, email, department, password_hash, 'employee', daily_wage)
        
        if not db_success:
            return jsonify({'success': False, 'message': 'User ID already exists'})
        
        # Capture face images
        face_success = face_system.capture_face_images(user_id, name, num_images=30)
        
        if not face_success:
            return jsonify({'success': False, 'message': 'Failed to capture face images'})
        
        # Train model with new data
        train_success = face_system.train_model()
        
        if not train_success:
            return jsonify({'success': False, 'message': 'Failed to train model'})
        
        return jsonify({'success': True, 'message': f'User {name} registered successfully!'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/train_model', methods=['POST'])
@login_required
def train_model():
    """API endpoint to train/retrain the model"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    try:
        success = face_system.train_model()
        if success:
            return jsonify({'success': True, 'message': 'Model trained successfully!'})
        else:
            return jsonify({'success': False, 'message': 'No training data found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/get_users', methods=['GET'])
@login_required
def get_users():
    """Get all registered users"""
    try:
        users = db_handler.get_all_users()
        # Convert datetime/decimal objects to JSON-safe types
        for user in users:
            for key, value in user.items():
                if isinstance(value, (datetime, date, dt_time, timedelta)):
                    user[key] = str(value)
                elif isinstance(value, Decimal):
                    user[key] = float(value)
            
            # Don't send password hashes to frontend
            if 'password_hash' in user:
                del user['password_hash']
                
        return jsonify({'success': True, 'users': users})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/get_attendance', methods=['GET'])
@login_required
def get_attendance():
    """Get attendance records"""
    try:
        date_query = request.args.get('date')
        records = db_handler.get_attendance_records(date_query)
        
        # Admin can see all, employees only theirs
        authorized_records = []
        for record in records:
            if current_user.role != 'admin' and record['user_id'] != current_user.id:
                continue
            
            # Serialize for JSON
            for key, value in record.items():
                if isinstance(value, (datetime, date, dt_time, timedelta)):
                    record[key] = str(value)
                elif isinstance(value, Decimal):
                    record[key] = float(value)
            authorized_records.append(record)
                
        return jsonify({'success': True, 'records': authorized_records})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/start_recognition', methods=['POST'])
@login_required
def start_recognition():
    """Start face recognition for attendance"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    global recognition_active
    logger.info("API call: start_recognition")
    
    try:
        # Explicitly touch the camera to ensure it turns on immediately
        # We do this before model loading so the user gets a live feed even if training is needed
        cam = get_camera()
        if cam is None:
            logger.error("start_recognition: Camera hardware could not be initialized.")
            return jsonify({'success': False, 'message': 'Camera hardware not detected or busy'})
            
        # Load model for recognition
        if not face_system.load_model():
            logger.warning("Recognition active but model is not trained. Showing live feed only.")
            # We still return success: true but with a warning, or just let recognition_active be True
            # and the generator will handle the 'Unknown/Paused' states.
            recognition_active = True
            return jsonify({'success': True, 'message': 'Camera active (No model found - please Register/Train)'})
        
        recognition_active = True
        logger.info("Recognition state set to ACTIVE and model loaded")
        return jsonify({'success': True, 'message': 'Recognition started'})
    except Exception as e:
        logger.error(f"Error in start_recognition API: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/stop_recognition', methods=['POST'])
@login_required
def stop_recognition():
    """Stop face recognition"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    global recognition_active
    recognition_active = False
    release_camera()
    return jsonify({'success': True, 'message': 'Recognition stopped'})


def mark_attendance_background(user_id, name):
    """Background task to mark attendance without blocking the video feed"""
    try:
        # Each thread gets its own database connection via the context manager
        success = db_handler.mark_attendance(user_id, name)
        if success:
            logger.info(f"Background attendance marked for {name} ({user_id})")
    except Exception as e:
        logger.error(f"BACKGROUND ATTENDANCE ERROR for {user_id}: {e}")

def generate_frames():
    """Generate video frames with face recognition"""
    global recognition_active, last_recognition_time
    
    camera = get_camera()
    
    # Get user names from database
    users = db_handler.get_all_users()
    user_names = {user['user_id']: user['name'] for user in users}
    
    # Optimization: process every other frame to reduce lag
    process_this_frame = True
    last_recognized_faces = []

    while True:
        success, frame = camera.read()
        if not success:
            break
        
        if recognition_active:
            # Recognize faces only on selected frames
            if process_this_frame:
                last_recognized_faces = face_system.recognize_face(frame)
                
                # Mark attendance for recognized faces
                for face in last_recognized_faces:
                    user_id = face['user_id']
                    confidence = face['confidence']
                    
                    # Only mark attendance if confidence is high enough and not recently marked
                    if user_id != "Unknown" and confidence > 0.5:
                        current_time = time.time()
                        
                        # Prevent marking multiple times (5 second cooldown)
                        if user_id not in last_recognition_time or \
                           (current_time - last_recognition_time[user_id]) > 5:
                            
                            name = user_names.get(user_id, user_id)
                            # Update cooldown immediately to prevent starting multiple threads
                            last_recognition_time[user_id] = current_time
                            
                            # Start database operation in background thread
                            threading.Thread(
                                target=mark_attendance_background, 
                                args=(user_id, name),
                                daemon=True
                            ).start()
            
            # Draw boxes and names (using results from the last processed frame)
            frame = face_system.draw_face_boxes(frame, last_recognized_faces, user_names)
            
            # Toggle frame processing
            process_this_frame = not process_this_frame
            
            # Add status text
            cv2.putText(frame, "RECOGNITION ACTIVE", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        else:
            cv2.putText(frame, "RECOGNITION PAUSED", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        # Encode frame
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/delete_user', methods=['POST'])
@login_required
def delete_user():
    """Delete a user"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    try:
        data = request.json
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'message': 'User ID required'})
        
        # Delete from database
        success = db_handler.delete_user(user_id)
        
        if success:
            # Retrain model
            face_system.train_model()
            return jsonify({'success': True, 'message': 'User deleted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to delete user'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/get_payroll', methods=['GET'])
@login_required
def get_payroll():
    """Get payroll for all employees"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    try:
        payroll = db_handler.get_monthly_payroll()
        return jsonify({'success': True, 'payroll': payroll})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/send_payroll_slip', methods=['POST'])
@login_required
def send_payroll_slip():
    """Admin endpoint to send a digital payment slip to an employee"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    try:
        data = request.json
        user_id = data.get('user_id')
        name = data.get('name')
        total_payment = data.get('total_payment')
        days_present = data.get('days_present')
        month = datetime.now().strftime("%B %Y")
        
        title = f"Payment Slip - {month}"
        msg = f"Hello {name}, your payment slip for {month} has been generated.\n\n" \
              f"Summary:\n" \
              f"- Days Present: {days_present}\n" \
              f"- Total Payout: LKR {total_payment}\n\n" \
              f"This is an automated notification."
              
        success = db_handler.add_message(user_id, title, msg, 'slip')
        
        if success:
            return jsonify({'success': True, 'message': f'Slip sent to {name}'})
        else:
            return jsonify({'success': False, 'message': 'Failed to send slip'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/get_messages', methods=['GET'])
@login_required
def get_messages():
    """Get notifications for the current employee"""
    try:
        messages = db_handler.get_user_messages(current_user.id)
        # Convert created_at to string
        for msg in messages:
            if 'created_at' in msg:
                msg['created_at'] = str(msg['created_at'])
        return jsonify({'success': True, 'messages': messages})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/mark_message_read', methods=['POST'])
@login_required
def mark_message_read():
    """Mark a notification as read"""
    try:
        data = request.json
        msg_id = data.get('id')
        db_handler.mark_message_read(msg_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/test_email')
@login_required
def test_email():
    """Manual test to verify SMTP configuration"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    try:
        msg = Message(
            "FaceAuth SMTP Test",
            recipients=[current_user.id] # Placeholder, though IDs aren't usually emails
        )
        # Using the actual username for the test if possible
        recipient = os.environ.get('MAIL_USERNAME', 'nethunawarathna@gmail.com')
        msg.recipients = [recipient]
        msg.body = "This is a test email to verify your FaceAuth SMTP settings. If you received this, your email configuration is correct!"
        
        mail.send(msg)
        return jsonify({'success': True, 'message': f'Test email sent successfully to {recipient}!'})
    except Exception as e:
        logger.error(f"SMTP TEST FAILED: {e}")
        return jsonify({'success': False, 'message': f'SMTP Error: {str(e)}'})

# --- LEAVES ---

@app.route('/admin/leaves')
@login_required
def admin_leaves():
    if current_user.role != 'admin':
        return redirect(url_for('employee_dashboard'))
    return render_template('admin_leaves.html')

@app.route('/employee/leaves')
@login_required
def employee_leaves():
    return render_template('employee_leaves.html')

@app.route('/api/request_leave', methods=['POST'])
@login_required
def request_leave():
    data = request.json
    success, message = db_handler.add_leave(
        current_user.id,
        data.get('date'),
        data.get('type'),
        data.get('reason')
    )
    return jsonify({'success': success, 'message': message})

@app.route('/api/get_leave_balance', methods=['GET'])
@login_required
def get_leave_balance():
    status = db_handler.get_monthly_leave_status(current_user.id)
    return jsonify({'success': True, 'balance': status})

@app.route('/api/get_leaves', methods=['GET'])
@login_required
def get_leaves():
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    
    # Employees can only see their own leaves
    if current_user.role != 'admin':
        user_id = current_user.id
        
    leaves = db_handler.get_leaves(user_id, status)
    return jsonify({'success': True, 'leaves': leaves})

@app.route('/api/update_leave', methods=['POST'])
@login_required
def update_leave():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    data = request.json
    success = db_handler.update_leave_status(data.get('id'), data.get('status'))
    
    # Notify user
    leave_data = None
    if success:
        # Get user_id for notification
        all_leaves = db_handler.get_leaves(status=data.get('status'))
        for l in all_leaves:
            if str(l['id']) == str(data.get('id')):
                db_handler.add_message(
                    l['user_id'],
                    f"Leave Request {data.get('status')}",
                    f"Your leave request for {l['leave_date']} has been {data.get('status').lower()}.",
                    'info'
                )
                break

    return jsonify({'success': success})

# --- HOLIDAYS & OFF DAYS ---

@app.route('/admin/holidays')
@login_required
def holidays_page():
    if current_user.role != 'admin':
        return redirect(url_for('employee_dashboard'))
    return render_template('holidays.html')

@app.route('/api/manage_holiday', methods=['POST'])
@login_required
def manage_holiday():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    data = request.json
    action = data.get('action')
    if action == 'add':
        success = db_handler.add_holiday(data.get('date'), data.get('description'))
    elif action == 'delete':
        success = db_handler.delete_holiday(data.get('id'))
    return jsonify({'success': success})

@app.route('/api/get_holidays', methods=['GET'])
@login_required
def get_holidays():
    holidays = db_handler.get_holidays()
    return jsonify({'success': True, 'holidays': holidays})

@app.route('/api/manage_off_day', methods=['POST'])
@login_required
def manage_off_day():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    data = request.json
    action = data.get('action')
    if action == 'add':
        success = db_handler.add_off_day(data.get('user_id'), data.get('date'))
    elif action == 'delete':
        success = db_handler.delete_off_day(data.get('id'))
    return jsonify({'success': success})

@app.route('/api/get_off_days', methods=['GET'])
@login_required
def get_off_days():
    user_id = request.args.get('user_id')
    # Admin can see all, employees only theirs
    if current_user.role != 'admin':
        user_id = current_user.id
    off_days = db_handler.get_off_days(user_id)
    return jsonify({'success': True, 'off_days': off_days})

# --- MANUAL ATTENDANCE & REPORTS ---

@app.route('/admin/manual_attendance')
@login_required
def manual_attendance_page():
    if current_user.role != 'admin':
        return redirect(url_for('employee_dashboard'))
    return render_template('manual_attendance.html')

@app.route('/api/mark_manual', methods=['POST'])
@login_required
def mark_manual_attendance():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    data = request.json
    user_id = data.get('user_id')
    user_data = db_handler.get_user(user_id)
    if not user_data:
        return jsonify({'success': False, 'message': 'User not found'})
    
    success = db_handler.mark_attendance_manual(
        user_id,
        user_data['name'],
        data.get('date'),
        data.get('time_in')
    )
    return jsonify({'success': success})

@app.route('/admin/reports')
@login_required
def reports_page():
    if current_user.role != 'admin':
        return redirect(url_for('employee_dashboard'))
    return render_template('advanced_reports.html')

@app.route('/api/get_filtered_report', methods=['GET'])
@login_required
def get_filtered_report():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    user_id = request.args.get('user_id', 'all')
    
    report = db_handler.get_filtered_report(start_date, end_date, user_id)
    return jsonify({'success': True, 'report': report})

if __name__ == '__main__':
    print("\n" + "="*60)
    print("FACIAL RECOGNITION ATTENDANCE SYSTEM")
    print("="*60)
    print("\nSystem Status:")
    print("   * Flask server starting...")
    print("   * Database handler initialized")
    print("   * Face recognition system ready")
    print("\nAccess the application at:")
    print("   > http://localhost:5000")
    print("\nMake sure XAMPP MySQL is running!")
    print("="*60 + "\n")
    
    app.run(debug=True, threaded=True, use_reloader=True)