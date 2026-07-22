import sys
import os
from datetime import date, datetime
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.database import get_db

def seed_data():
    with get_db() as conn:
        with conn.cursor() as cur:
            # Note: ALTER TYPE cannot be run inside a transaction block in PostgreSQL.
            # We must use autocommit mode for it.
            pass

    # Since we can't easily do ALTER TYPE in a transaction, let's connect with autocommit just for the ALTER TYPE
    with get_db() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            try:
                cur.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'Pending'")
            except Exception as e:
                print(f"Pending already exists or failed: {e}")
            try:
                cur.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'Confirmed'")
            except Exception as e:
                print(f"Confirmed already exists or failed: {e}")

    with get_db() as conn:
        with conn.cursor() as cur:
            # 2. Get first approved doctor
            cur.execute("SELECT id FROM Users WHERE role = 'Doctor' AND status = 'Approved' LIMIT 1")
            doc = cur.fetchone()
            if not doc:
                print("No approved doctor found. Please create one.")
                return
            doc_id = doc[0]

            # 3. Get first approved patient
            cur.execute("SELECT id FROM Users WHERE role = 'Patient' AND status = 'Approved' LIMIT 1")
            pat = cur.fetchone()
            if not pat:
                print("No approved patient found. Please create one.")
                return
            pat_id = pat[0]

            print(f"Seeding data for Doctor {doc_id} and Patient {pat_id}")

            # 4. Insert an appointment
            cur.execute("""
                INSERT INTO Appointments (patient_id, doctor_id, department, appointment_date, appointment_time, status, notes)
                VALUES (%s, %s, %s, CURRENT_DATE, '10:00:00', 'Scheduled', 'Routine checkup')
            """, (pat_id, doc_id, 'General'))

            # 5. Insert a diagnosis
            cur.execute("""
                INSERT INTO Diagnoses (patient_id, doctor_id, title, description, symptoms, doctor_notes, recommended_tests, visit_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_DATE)
            """, (pat_id, doc_id, 'Hypertension', 'High blood pressure observed', 'Headache', 'Monitor BP daily', 'CBC'))

            # 6. Insert a medical document
            cur.execute("""
                INSERT INTO MedicalDocuments (patient_id, doctor_id, document_name, document_type, content, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (pat_id, doc_id, 'Initial Assessment', 'Consultation Report', 'Patient complains of headaches.', 'Final'))

            conn.commit()
            print("Data seeded successfully.")

if __name__ == "__main__":
    seed_data()
