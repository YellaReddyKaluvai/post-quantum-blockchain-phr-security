import uuid
from datetime import date, timedelta
from app.database import get_db
from app.security import hash_password, encrypt_data

def seed_data():
    with get_db() as conn:
        with conn.cursor() as cur:
            # 2. Find first approved Patient
            cur.execute("SELECT id FROM Users WHERE role = 'Patient' AND status = 'Approved' LIMIT 1")
            patient = cur.fetchone()
            if not patient:
                print("No approved Patient found. Cannot seed data.")
                return
            patient_id = patient[0]
            print(f"Using Patient ID: {patient_id}")

            # 3. Create or find Doctor
            cur.execute("SELECT id FROM Users WHERE role = 'Doctor' AND status = 'Approved' LIMIT 1")
            doctor = cur.fetchone()
            if not doctor:
                print("Creating sample Doctor...")
                pwd_hash = hash_password("Password123!")
                cur.execute("""
                    INSERT INTO Users (full_name, email, password_hash, role, gender, date_of_birth_encrypted, specialization, status)
                    VALUES (%s, %s, %s, 'Doctor', 'Male', %s, 'General Medicine', 'Approved')
                    RETURNING id
                """, ("Dr. Gregory House", "house@hospital.com", pwd_hash, encrypt_data("1959-06-11")))
                doctor_id = cur.fetchone()[0]
                conn.commit()
            else:
                doctor_id = doctor[0]

            # 4. Create or find Lab Technician
            cur.execute("SELECT id FROM Users WHERE role = 'Lab Technician' AND status = 'Approved' LIMIT 1")
            lab_tech = cur.fetchone()
            if not lab_tech:
                print("Creating sample Lab Technician...")
                pwd_hash = hash_password("Password123!")
                cur.execute("""
                    INSERT INTO Users (full_name, email, password_hash, role, gender, date_of_birth_encrypted, status)
                    VALUES (%s, %s, %s, 'Lab Technician', 'Female', %s, 'Approved')
                    RETURNING id
                """, ("Alice Smith", "alice@hospital.com", pwd_hash, encrypt_data("1985-02-20")))
                lab_tech_id = cur.fetchone()[0]
                conn.commit()
            else:
                lab_tech_id = lab_tech[0]

            today = date.today()

            # 5a. 5 Diagnoses
            print("Inserting 5 Diagnoses...")
            diagnoses = [
                ("Seasonal Allergic Rhinitis", "Allergy to pollen", "Sneezing, runny nose", "Take antihistamines", "No specific tests", today - timedelta(days=60)),
                ("Upper Respiratory Infection", "Viral infection", "Cough, sore throat, mild fever", "Rest, fluids", "None", today - timedelta(days=45)),
                ("Type 2 Diabetes Management", "Routine checkup", "None (asymptomatic)", "Continue current meds", "HbA1c, Fasting Sugar", today - timedelta(days=30)),
                ("Vitamin D Deficiency", "Low levels found in recent test", "Fatigue", "Start supplements", "Vitamin D3 levels again in 3 months", today - timedelta(days=15)),
                ("Hypertension Stage 1", "Elevated BP", "Occasional headaches", "Monitor BP, reduce salt", "ECG, Lipid Profile", today - timedelta(days=2))
            ]
            for d in diagnoses:
                cur.execute("""
                    INSERT INTO Diagnoses (patient_id, doctor_id, title, description, symptoms, doctor_notes, recommended_tests, visit_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (patient_id, doctor_id, d[0], d[1], d[2], d[3], d[4], d[5]))

            # 5b. 6 Lab Reports
            print("Inserting 6 Lab Reports...")
            lab_reports = [
                ("Complete Blood Count", "CBC", "Normal", "WBC 7000/mcL", "4500-11000/mcL", 'Completed', today - timedelta(days=60)),
                ("Fasting Blood Sugar", "Blood Sugar", "Slightly elevated", "110 mg/dL", "70-100 mg/dL", 'Completed', today - timedelta(days=30)),
                ("Lipid Profile", "Lipid Profile", "High LDL", "LDL 140 mg/dL", "< 100 mg/dL", 'Reviewed', today - timedelta(days=10)),
                ("Liver Function Test", "Liver Function", "Normal", "ALT 25 U/L", "7-56 U/L", 'Completed', today - timedelta(days=5)),
                ("Kidney Function Test", "Kidney Function", "Normal", "Creatinine 0.9 mg/dL", "0.6-1.2 mg/dL", 'Completed', today - timedelta(days=2)),
                ("Chest X-Ray", "X-Ray", "Pending review", "Clear lungs", "N/A", 'Pending', today)
            ]
            for r in lab_reports:
                cur.execute("""
                    INSERT INTO LabReports (patient_id, uploaded_by, report_name, report_type, findings, normal_range, status, upload_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (patient_id, lab_tech_id, r[0], r[1], r[3], r[4], r[5], r[6]))

            # 5c. 5 Prescriptions
            print("Inserting 5 Prescriptions...")
            prescriptions = [
                ("Cetirizine 10mg", "1 tablet", "Once daily", "14 days", "Take at night", today - timedelta(days=60)),
                ("Metformin 500mg", "1 tablet", "Twice daily", "90 days", "Take after meals", today - timedelta(days=30)),
                ("Amlodipine 5mg", "1 tablet", "Once daily", "30 days", "Take in morning", today - timedelta(days=15)),
                ("Vitamin D3 60K IU", "1 capsule", "Once weekly", "8 weeks", "Take with milk", today - timedelta(days=10)),
                ("Amoxicillin 500mg", "1 capsule", "Three times a day", "5 days", "Complete full course", today - timedelta(days=2))
            ]
            for p in prescriptions:
                cur.execute("""
                    INSERT INTO Prescriptions (patient_id, doctor_id, medicine_name, dosage, frequency, duration, instructions, prescribed_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (patient_id, doctor_id, p[0], p[1], p[2], p[3], p[4], p[5]))

            # 5d. 4 Doctor Consultations
            print("Inserting 4 Doctor Consultations...")
            consultations = [
                (today - timedelta(days=60), "Sneezing and runny nose", "Allergic rhinitis", "Prescribed antihistamine"),
                (today - timedelta(days=30), "Routine diabetes check", "Stable type 2 diabetes", "Continue Metformin"),
                (today - timedelta(days=15), "Fatigue", "Vitamin D deficiency", "Prescribed supplements"),
                (today - timedelta(days=2), "Headaches", "Mild hypertension", "Prescribed Amlodipine, ordered tests")
            ]
            for c in consultations:
                cur.execute("""
                    INSERT INTO DoctorConsultations (patient_id, doctor_id, consultation_date, symptoms, diagnosis_summary, doctor_notes)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (patient_id, doctor_id, c[0], c[1], c[2], c[3]))

            # 5e. 5 Appointments (2 upcoming/scheduled, 3 completed)
            print("Inserting 5 Appointments...")
            appointments = [
                ("General Medicine", today - timedelta(days=30), "09:00:00", "Completed", "Routine checkup"),
                ("Cardiology", today - timedelta(days=15), "10:30:00", "Completed", "BP follow-up"),
                ("General Medicine", today - timedelta(days=2), "11:00:00", "Completed", "Headache evaluation"),
                ("Cardiology", today + timedelta(days=7), "09:00:00", "Scheduled", "ECG review"),
                ("Endocrinology", today + timedelta(days=14), "14:00:00", "Scheduled", "Diabetes follow-up")
            ]
            for a in appointments:
                cur.execute("""
                    INSERT INTO Appointments (patient_id, doctor_id, department, appointment_date, appointment_time, status, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (patient_id, doctor_id, a[0], a[1], a[2], a[3], a[4]))

            # 5f. 6 Notifications
            print("Inserting 6 Notifications...")
            notifications = [
                ("InApp", "APPOINTMENT_REMINDER", "Upcoming Appointment", "You have an appointment tomorrow at 09:00 AM.", None),
                ("InApp", "LAB_RESULT", "New Lab Result", "Your CBC report is now available.", None),
                ("InApp", "PRESCRIPTION_ADDED", "New Prescription", "A new prescription for Metformin has been added.", None),
                ("InApp", "SYSTEM_ALERT", "Welcome", "Welcome to the PQC Hospital Patient Portal.", today - timedelta(days=90)),
                ("InApp", "LAB_RESULT", "Lab Result Pending", "Your Chest X-Ray is pending review.", None),
                ("InApp", "APPOINTMENT_SCHEDULED", "Appointment Confirmed", "Your Endocrinology appointment is confirmed.", None)
            ]
            for n in notifications:
                cur.execute("""
                    INSERT INTO Notifications (User_ID, Channel, Notification_Type, Title, Body, Read_At)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (patient_id, n[0], n[1], n[2], n[3], n[4]))

            conn.commit()
            print("Sample data seeded successfully!")

if __name__ == "__main__":
    seed_data()
