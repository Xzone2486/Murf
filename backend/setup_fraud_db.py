import sqlite3
import os

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fraud_cases.db")

def setup_db():
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print(f"Removed existing {DB_FILE}")
        except PermissionError:
            print(f"Error: Could not remove {DB_FILE}. It might be in use.")
            return

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
        "Ansh",
        "98765",
        "1234",
        "pending_review",
        "Flipkart",
        "2023-10-27 14:30:00",
        "e-commerce",
        "flipkart.com",
        "Rs.1,250.00",
        "What is your favorite food?",
        "Biryani",
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
        try:
            print(row)
        except UnicodeEncodeError:
            safe_row = str(row).replace('\u20b9', 'Rs.')
            print(safe_row)

    conn.close()

if __name__ == "__main__":
    setup_db()
