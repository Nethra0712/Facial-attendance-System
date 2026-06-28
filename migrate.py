import mysql.connector
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

config = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'user': os.environ.get('DB_USER', 'root'), 
    'password': os.environ.get('DB_PASSWORD', ''),  
    'database': os.environ.get('DB_NAME', 'attendance_system')
}

def migrate():
    try:
        conn = mysql.connector.connect(host=config['host'], user=config['user'], password=config['password'])
        cursor = conn.cursor()
        
        # Create DB if not exists
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {config['database']}")
        cursor.execute(f"USE {config['database']}")
        
        # Alter users table to add new columns if they don't exist
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''")
            cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'employee'")
            cursor.execute("ALTER TABLE users ADD COLUMN daily_wage DECIMAL(10, 2) DEFAULT 0.00")
            print("Successfully added new columns to users table.")
        except mysql.connector.Error as err:
            if err.errno == 1060: # Duplicate column name
                print("Columns already exist.")
            else:
                print(f"Error altering table: {err}")
        
        conn.commit()
        
        # Create New Tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaves (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(50),
                leave_date DATE,
                type VARCHAR(50),
                status VARCHAR(20) DEFAULT 'Pending',
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS holidays (
                id INT AUTO_INCREMENT PRIMARY KEY,
                holiday_date DATE UNIQUE,
                description VARCHAR(255)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS off_days (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(50),
                off_date DATE,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                UNIQUE KEY unique_off_day (user_id, off_date)
            )
        """)
        
        print("Successfully created/updated all tables.")
        
        # Create default admin
        admin_hash = generate_password_hash('admin123')
        try:
            cursor.execute("""
                INSERT INTO users (user_id, name, email, department, password_hash, role)
                VALUES ('admin', 'System Administrator', 'admin@system.local', 'Admin', %s, 'admin')
            """, (admin_hash,))
            conn.commit()
            print("Admin account created! (Username: admin, Password: admin123)")
        except mysql.connector.Error as err:
            if err.errno == 1062: # Duplicate entry
                print("Admin account already exists.")
            else:
                print(f"Error creating admin: {err}")
                
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Migration error: {e}")

if __name__ == "__main__":
    migrate()
