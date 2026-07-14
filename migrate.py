import sqlite3
import os

db_path = r'd:\Fraud_Detection_System\transactions.db'
if os.path.exists(db_path):
    print("Database found. Running migrations...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check current columns in transactions table
    cursor.execute("PRAGMA table_info(transactions)")
    columns = [col[1] for col in cursor.fetchall()]
    print("Existing columns:", columns)
    
    # Add top_factor_1 if not exists
    if 'top_factor_1' not in columns:
        cursor.execute('ALTER TABLE transactions ADD COLUMN top_factor_1 TEXT')
        print("Added top_factor_1 column successfully.")
    else:
        print("top_factor_1 column already exists.")
        
    # Add top_factor_2 if not exists
    if 'top_factor_2' not in columns:
        cursor.execute('ALTER TABLE transactions ADD COLUMN top_factor_2 TEXT')
        print("Added top_factor_2 column successfully.")
    else:
        print("top_factor_2 column already exists.")
        
    conn.commit()
    conn.close()
    print("Migration completed.")
else:
    print("Database file does not exist yet. SQLAlchemy will create tables with columns automatically.")
