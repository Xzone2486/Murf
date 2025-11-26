import sqlite3
import os

DB_FILE = "fraud_cases.db"

def setup_db():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"Removed existing {DB_FILE}")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fraud_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            userName TEXT NOT NULL,
            securityIdentifier TEXT,
            cardEnding TEXT,
            case_status TEXT,
            transactionName TEXT,
            transactionTime TEXT,
            transactionCategory TEXT,
            transactionSource TEXT,
            transactionAmount TEXT,
            securityQuestion TEXT,
            securityAnswer TEXT,
            outcome_note TEXT
        )
    ''')

    # Insert sample data
    sample_case = (
        "John",
        "12345",
        "4242",
        "pending_review",
        "ABC Industry",
        "2023-10-27 14:30:00",
        "e-commerce",
        "alibaba.com",
        "$1,250.00",
        "What is your mother's maiden name?",
        "Smith",
        ""
    )

    cursor.execute('''
        INSERT INTO fraud_cases (
            userName, securityIdentifier, cardEnding, case_status, 
            transactionName, transactionTime, transactionCategory, 
            transactionSource, transactionAmount, securityQuestion, 
            securityAnswer, outcome_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', sample_case)

    conn.commit()
    print(f"Database {DB_FILE} created and populated with sample data.")
    
    # Verify data
    cursor.execute("SELECT * FROM fraud_cases")
    rows = cursor.fetchall()
    for row in rows:
        print(row)

    conn.close()

if __name__ == "__main__":
    setup_db()
