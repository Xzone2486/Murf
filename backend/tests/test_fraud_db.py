import unittest
import sqlite3
import os
import sys

# Add src to path so we can import the agent module if needed, 
# but here we'll just test the DB logic directly or mock it.
# Actually, let's just copy the DB class logic here for a standalone test 
# or import it if we structure it as a module. 
# For simplicity, I will test the database file directly using the same logic.

DB_FILE = "fraud_cases.db"

class TestFraudDB(unittest.TestCase):
    def setUp(self):
        # Reset DB for test
        if os.path.exists(DB_FILE):
            # We assume setup_fraud_db.py has run, but let's just use the existing one
            pass
        
    def test_get_case(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fraud_cases WHERE userName = 'John'")
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "John")

    def test_update_case(self):
        # Update
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE fraud_cases SET case_status = 'test_status' WHERE userName = 'John'")
        conn.commit()
        
        # Verify
        cursor.execute("SELECT case_status FROM fraud_cases WHERE userName = 'John'")
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row[0], "test_status")

        # Revert
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE fraud_cases SET case_status = 'pending_review' WHERE userName = 'John'")
        conn.commit()
        conn.close()

if __name__ == '__main__':
    unittest.main()
