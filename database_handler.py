"""
Database Handler Module
Manages all database operations for the attendance system
"""

import mysql.connector
from datetime import datetime, date, time, timedelta
import logging
import os
from contextlib import contextmanager
from decimal import Decimal

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseHandler:
    """Handles all database operations using thread-safe connection management"""
    
    def __init__(self):
        """Initialize database configuration"""
        self.config = {
            'host': os.environ.get('DB_HOST', 'localhost'),
            'user': os.environ.get('DB_USER', 'root'), 
            'password': os.environ.get('DB_PASSWORD', ''),  
            'database': os.environ.get('DB_NAME', 'attendance_system')
        }
    
    @contextmanager
    def db_session(self, commit=False):
        """
        Thread-safe context manager for database operations.
        Ensures each request gets its own connection and cursor.
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(**self.config)
            cursor = connection.cursor(dictionary=True)
            yield cursor
            if commit:
                connection.commit()
        except mysql.connector.Error as e:
            logger.error(f"Database error: {e}")
            if connection:
                connection.rollback()
            raise e
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def register_user(self, user_id, name, email="", department="", password_hash="", role="employee", daily_wage=0.0):
        """Register a new user"""
        try:
            with self.db_session(commit=True) as cursor:
                query = """
                    INSERT INTO users (user_id, name, email, department, password_hash, role, daily_wage) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (user_id, name, email, department, password_hash, role, daily_wage))
                return True
        except mysql.connector.IntegrityError:
            logger.warning(f"User ID {user_id} already exists")
            return False
        except Exception as e:
            logger.error(f"Error registering user: {e}")
            return False

    def get_user(self, user_id):
        """Retrieve user information"""
        try:
            with self.db_session() as cursor:
                query = "SELECT * FROM users WHERE user_id = %s"
                cursor.execute(query, (user_id,))
                return cursor.fetchone()
        except Exception:
            return None

    def get_all_users(self):
        """Get all registered users"""
        try:
            with self.db_session() as cursor:
                query = "SELECT * FROM users ORDER BY registration_date DESC"
                cursor.execute(query)
                return cursor.fetchall()
        except Exception:
            return []

    def mark_attendance(self, user_id, name):
        """Mark daily attendance"""
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            current_time = now.strftime("%H:%M:%S")

            with self.db_session(commit=True) as cursor:
                # Check if already marked
                check_query = "SELECT * FROM attendance WHERE user_id = %s AND date = %s"
                cursor.execute(check_query, (user_id, today))
                if cursor.fetchone():
                    return False
                
                # Insert new record
                insert_query = """
                    INSERT INTO attendance (user_id, name, date, time_in) 
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(insert_query, (user_id, name, today, current_time))
                return True
        except Exception:
            return False

    def get_attendance_records(self, date=None):
        """Get attendance records"""
        try:
            with self.db_session() as cursor:
                if date:
                    query = "SELECT * FROM attendance WHERE date = %s ORDER BY time_in DESC"
                    cursor.execute(query, (date,))
                else:
                    query = "SELECT * FROM attendance ORDER BY date DESC, time_in DESC LIMIT 100"
                    cursor.execute(query)
                return cursor.fetchall()
        except Exception:
            return []

    def get_user_attendance_history(self, user_id):
        """Get personal history"""
        try:
            with self.db_session() as cursor:
                query = "SELECT * FROM attendance WHERE user_id = %s ORDER BY date DESC"
                cursor.execute(query, (user_id,))
                return cursor.fetchall()
        except Exception:
            return []

    def delete_user(self, user_id):
        """Delete a user"""
        try:
            with self.db_session(commit=True) as cursor:
                query = "DELETE FROM users WHERE user_id = %s"
                cursor.execute(query, (user_id,))
                return True
        except Exception:
            return False

    def create_admin_account(self, password_hash):
        """Create default admin"""
        admin = self.get_user('admin')
        if not admin:
            self.register_user('admin', 'System Administrator', 'admin@system.local', 'Administration', password_hash, 'admin', 0.0)

    def add_message(self, user_id, title, msg, type='info'):
        """Create a new message for a user"""
        try:
            with self.db_session(commit=True) as cursor:
                query = """
                    INSERT INTO messages (user_id, title, message, type) 
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(query, (user_id, title, msg, type))
                return True
        except Exception as e:
            logger.error(f"Error adding message: {e}")
            return False

    def get_user_messages(self, user_id):
        """Retrieve all messages for a specific user"""
        try:
            with self.db_session() as cursor:
                query = "SELECT * FROM messages WHERE user_id = %s ORDER BY created_at DESC"
                cursor.execute(query, (user_id,))
                return cursor.fetchall()
        except Exception:
            return []

    def mark_message_read(self, message_id):
        """Mark a notification as read"""
        try:
            with self.db_session(commit=True) as cursor:
                query = "UPDATE messages SET is_read = TRUE WHERE id = %s"
                cursor.execute(query, (message_id,))
                return True
        except Exception:
            return False

    def get_monthly_payroll(self):

        """Calculate payroll and fix Decimal serialization issues"""
        try:
            with self.db_session() as cursor:
                query = """
                    SELECT u.user_id, u.name, u.department, u.daily_wage, 
                           COUNT(a.id) as days_present,
                           (u.daily_wage * COUNT(a.id)) as total_payment
                    FROM users u
                    LEFT JOIN attendance a ON u.user_id = a.user_id 
                    WHERE u.role = 'employee'
                    GROUP BY u.user_id, u.name, u.department, u.daily_wage
                """
                cursor.execute(query)
                results = cursor.fetchall()
                
                # Convert Decimal fields to float for JSON compatibility
                serializable_results = []
                for row in results:
                    processed_row = dict(row)
                    for key, value in processed_row.items():
                        if isinstance(value, Decimal):
                            processed_row[key] = float(value)
                    serializable_results.append(processed_row)
                    
                return serializable_results
        except Exception as e:
            logger.error(f"Payroll error: {e}")
            return []

    # --- ADVANCED FEATURES ---

    LEAVE_LIMITS = {
        'Casual': 3,
        'Medical': 3,
        'Short': 4
    }

    def add_leave(self, user_id, leave_date, leave_type, reason):
        """Request a leave with limits validation"""
        try:
            # Monthly validation
            target_date = datetime.strptime(leave_date, '%Y-%m-%d')
            month = target_date.month
            year = target_date.year

            with self.db_session() as cursor:
                # Count current month leaves (Pending or Approved)
                query = """
                    SELECT COUNT(*) as count FROM leaves 
                    WHERE user_id = %s AND type = %s 
                    AND MONTH(leave_date) = %s AND YEAR(leave_date) = %s
                    AND status IN ('Pending', 'Approved')
                """
                cursor.execute(query, (user_id, leave_type, month, year))
                result = cursor.fetchone()
                current_count = result['count'] if result else 0

                limit = self.LEAVE_LIMITS.get(leave_type, 0)
                if current_count >= limit:
                    return False, f"Monthly limit reached for {leave_type} leaves ({limit} days)"

            # Proceed with insertion if limit not reached
            with self.db_session(commit=True) as cursor:
                query = """
                    INSERT INTO leaves (user_id, leave_date, type, status, reason) 
                    VALUES (%s, %s, %s, 'Pending', %s)
                """
                cursor.execute(query, (user_id, leave_date, leave_type, reason))
                return True, "Leave request submitted successfully"
        except Exception as e:
            logger.error(f"Error adding leave: {e}")
            return False, str(e)

    def get_monthly_leave_status(self, user_id):
        """Get remaining leaves for the current month"""
        try:
            now = datetime.now()
            month = now.month
            year = now.year
            
            status = []
            for l_type, limit in self.LEAVE_LIMITS.items():
                with self.db_session() as cursor:
                    query = """
                        SELECT COUNT(*) as count FROM leaves 
                        WHERE user_id = %s AND type = %s 
                        AND MONTH(leave_date) = %s AND YEAR(leave_date) = %s
                        AND status IN ('Pending', 'Approved')
                    """
                    cursor.execute(query, (user_id, l_type, month, year))
                    result = cursor.fetchone()
                    used = result['count'] if result else 0
                    
                    status.append({
                        'type': l_type,
                        'limit': limit,
                        'used': used,
                        'remaining': max(0, limit - used)
                    })
            return status
        except Exception as e:
            logger.error(f"Error fetching leave status: {e}")
            return []

    def get_leaves(self, user_id=None, status=None):
        """Get leave requests"""
        try:
            with self.db_session() as cursor:
                query = "SELECT l.*, u.name FROM leaves l JOIN users u ON l.user_id = u.user_id"
                params = []
                where_clauses = []
                
                if user_id:
                    where_clauses.append("l.user_id = %s")
                    params.append(user_id)
                if status:
                    where_clauses.append("l.status = %s")
                    params.append(status)
                
                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)
                
                query += " ORDER BY l.leave_date DESC"
                cursor.execute(query, tuple(params))
                results = cursor.fetchall()
                # Convert dates to string for JSON
                for row in results:
                    for key, val in row.items():
                        if isinstance(val, (datetime, date, time, timedelta)):
                            row[key] = str(val)
                        elif isinstance(val, Decimal):
                            row[key] = float(val)
                return results
        except Exception as e:
            logger.error(f"Error getting leaves: {e}")
            return []

    def update_leave_status(self, leave_id, status):
        """Approve or reject a leave"""
        try:
            with self.db_session(commit=True) as cursor:
                query = "UPDATE leaves SET status = %s WHERE id = %s"
                cursor.execute(query, (status, leave_id))
                return True
        except Exception as e:
            logger.error(f"Error updating leave status: {e}")
            return False

    def add_holiday(self, holiday_date, description):
        """Add a public holiday"""
        try:
            with self.db_session(commit=True) as cursor:
                query = "INSERT INTO holidays (holiday_date, description) VALUES (%s, %s)"
                cursor.execute(query, (holiday_date, description))
                return True
        except Exception as e:
            logger.error(f"Error adding holiday: {e}")
            return False

    def get_holidays(self):
        """Get all holidays"""
        try:
            with self.db_session() as cursor:
                query = "SELECT * FROM holidays ORDER BY holiday_date DESC"
                cursor.execute(query)
                results = cursor.fetchall()
                for row in results:
                    for key, val in row.items():
                        if isinstance(val, (datetime, date, time, timedelta)):
                            row[key] = str(val)
                        elif isinstance(val, Decimal):
                            row[key] = float(val)
                return results
        except Exception:
            return []

    def delete_holiday(self, holiday_id):
        """Remove a holiday"""
        try:
            with self.db_session(commit=True) as cursor:
                query = "DELETE FROM holidays WHERE id = %s"
                cursor.execute(query, (holiday_id,))
                return True
        except Exception:
            return False

    def add_off_day(self, user_id, off_date):
        """Add an off-day for a specific user"""
        try:
            with self.db_session(commit=True) as cursor:
                query = "INSERT INTO off_days (user_id, off_date) VALUES (%s, %s)"
                cursor.execute(query, (user_id, off_date))
                return True
        except Exception as e:
            logger.error(f"Error adding off-day: {e}")
            return False

    def get_off_days(self, user_id=None):
        """Get off-days"""
        try:
            with self.db_session() as cursor:
                query = "SELECT o.*, u.name FROM off_days o JOIN users u ON o.user_id = u.user_id"
                if user_id:
                    query += " WHERE o.user_id = %s"
                    cursor.execute(query, (user_id,))
                else:
                    cursor.execute(query)
                results = cursor.fetchall()
                for row in results:
                    for key, val in row.items():
                        if isinstance(val, (datetime, date, time, timedelta)):
                            row[key] = str(val)
                        elif isinstance(val, Decimal):
                            row[key] = float(val)
                return results
        except Exception:
            return []

    def delete_off_day(self, off_id):
        """Remove an off-day"""
        try:
            with self.db_session(commit=True) as cursor:
                query = "DELETE FROM off_days WHERE id = %s"
                cursor.execute(query, (off_id,))
                return True
        except Exception:
            return False

    def mark_attendance_manual(self, user_id, name, date, time_in):
        """Mark attendance manually"""
        try:
            with self.db_session(commit=True) as cursor:
                # Check if already exists
                check_query = "SELECT * FROM attendance WHERE user_id = %s AND date = %s"
                cursor.execute(check_query, (user_id, date))
                if cursor.fetchone():
                    # Update existing record if exists
                    update_query = "UPDATE attendance SET time_in = %s WHERE user_id = %s AND date = %s"
                    cursor.execute(update_query, (time_in, user_id, date))
                else:
                    # Insert new record
                    insert_query = "INSERT INTO attendance (user_id, name, date, time_in) VALUES (%s, %s, %s, %s)"
                    cursor.execute(insert_query, (user_id, name, date, time_in))
                return True
        except Exception as e:
            logger.error(f"Error marking manual attendance: {e}")
            return False

    def get_filtered_report(self, start_date, end_date, user_id=None):
        """Get comprehensive attendance report with filtering"""
        try:
            with self.db_session() as cursor:
                query = """
                    SELECT a.*, u.department 
                    FROM attendance a
                    JOIN users u ON a.user_id = u.user_id
                    WHERE a.date BETWEEN %s AND %s
                """
                params = [start_date, end_date]
                
                if user_id and user_id != 'all':
                    query += " AND a.user_id = %s"
                    params.append(user_id)
                
                query += " ORDER BY a.date DESC, a.time_in DESC"
                cursor.execute(query, tuple(params))
                results = cursor.fetchall()
                for row in results:
                    for key, val in row.items():
                        if isinstance(val, (datetime, date, time, timedelta)):
                            row[key] = str(val)
                        elif isinstance(val, Decimal):
                            row[key] = float(val)
                return results
        except Exception as e:
            logger.error(f"Error getting filtered report: {e}")
            return []