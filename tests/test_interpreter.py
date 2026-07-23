import sqlite3
import os
from modules.interpreter import process_interpretation
from database.db import DB_PATH

def test_ai_interpreter():
    print("========================================")
    print(" TESTING AI INTERPRETER MODULE          ")
    print("========================================")
    
    class_id = 1 
    
    new_ai_id = process_interpretation(class_id)
    
    if new_ai_id:
        print("\n========================================")
        print(" DATABASE VERIFICATION (ai_alerts)      ")
        print("========================================")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT explanation, recommendations FROM ai_alerts WHERE id = ?", (new_ai_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            print("[+] EXPLANATION SAVED:")
            print(row[0])
            print("\n[+] RECOMMENDATIONS SAVED:")
            print(row[1])
        else:
            print("[-] Error: Could not find the record in the database.")
        print("========================================\n")
    else:
        print("\n[-] Test failed.")
        print("Make sure you have your .env file configured with GEMINI_API_KEY")
        print("and that a classification with ID 1 exists in the database.")

if __name__ == "__main__":
    test_ai_interpreter()
