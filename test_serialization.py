from datetime import datetime, date, time, timedelta
from decimal import Decimal
import json

def test_serialization():
    # Mock result row
    row = {
        'id': 1,
        'user_id': 'EMP001',
        'name': 'John Doe',
        'date': date(2026, 4, 15),
        'time_in': timedelta(hours=9, minutes=30),  # MySQL TIME often maps to timedelta
        'department': 'Engineering',
        'daily_wage': Decimal('1500.00')
    }
    
    # Logic from database_handler.py
    for key, val in row.items():
        if isinstance(val, (datetime, date, time, timedelta)):
            row[key] = str(val)
        elif isinstance(val, Decimal):
            row[key] = float(val)
            
    try:
        json_output = json.dumps(row)
        print("Serialization Successful!")
        print(json_output)
    except Exception as e:
        print(f"Serialization Failed: {e}")

if __name__ == "__main__":
    test_serialization()
