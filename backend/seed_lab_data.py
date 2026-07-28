import sys
import os
import hashlib
import json
import uuid
from datetime import datetime

# Add the backend directory to sys.path so we can import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import get_db
from app.security import hash_password, encrypt_data
from app.crypto_service import generate_mlkem_keypair, generate_mldsa_keypair

def seed_lab_data():
    with get_db() as conn:
        with conn.cursor() as cur:
            # 1. Ensure a default Lab Technician exists
            cur.execute("SELECT id FROM Users WHERE role = 'Lab Technician' LIMIT 1")
            lab_tech = cur.fetchone()
            
            if not lab_tech:
                print("Creating default Lab Technician...")
                pwd_hash = hash_password("Password123!")
                kem_pub, kem_priv = generate_mlkem_keypair()
                dsa_pub, dsa_priv = generate_mldsa_keypair()
                
                cur.execute("""
                    INSERT INTO Users (user_id, full_name, email, password_hash, role, gender, date_of_birth_encrypted, status,
                                     mlkem_public_key, mlkem_private_key_encrypted, mldsa_public_key, mldsa_private_key_encrypted, approved_at)
                    VALUES ('LAB-2026-001', 'Alice Johnson (Lab)', 'lab@pqc.com', %s, 'Lab Technician', 'Female', %s, 'Approved',
                            %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                """, (pwd_hash, encrypt_data("1985-05-15"), kem_pub, kem_priv, dsa_pub, dsa_priv))
                lab_tech_id = cur.fetchone()[0]
            else:
                lab_tech_id = lab_tech[0]
                
            # Get a patient to assign requests and reports to
            cur.execute("SELECT id, mlkem_public_key FROM Users WHERE role = 'Patient' LIMIT 1")
            patient = cur.fetchone()
            if not patient:
                # Create dummy patient
                pwd_hash = hash_password("Password123!")
                kem_pub, kem_priv = generate_mlkem_keypair()
                cur.execute("""
                    INSERT INTO Users (user_id, full_name, email, password_hash, role, gender, date_of_birth_encrypted, status, mlkem_public_key)
                    VALUES ('PAT-2026-001', 'Test Patient', 'patient@pqc.com', %s, 'Patient', 'Male', %s, 'Approved', %s)
                    RETURNING id, mlkem_public_key
                """, (pwd_hash, encrypt_data("1990-01-01"), kem_pub))
                patient_id, patient_kem_pub = cur.fetchone()
            else:
                patient_id, patient_kem_pub = patient

            # Get a doctor
            cur.execute("SELECT id FROM Users WHERE role = 'Doctor' LIMIT 1")
            doctor = cur.fetchone()
            doctor_id = doctor[0] if doctor else None

            # 2. Create sample LabTestRequests
            print("Creating sample LabTestRequests...")
            requests_data = [
                ('CBC Test', 'Routine', 'Pending'),
                ('Lipid Profile', 'Urgent', 'Pending'),
                ('Liver Function', 'Routine', 'In Progress'),
                ('Kidney Function', 'Urgent', 'In Progress'),
                ('Blood Sugar Fasting', 'Routine', 'Completed'),
                ('Thyroid Panel', 'Routine', 'Completed')
            ]
            for r_name, r_pri, r_stat in requests_data:
                cur.execute("""
                    INSERT INTO LabTestRequests (patient_id, doctor_id, test_name, priority, status, clinical_notes)
                    VALUES (%s, %s, %s, %s, %s, 'Sample clinical note')
                """, (patient_id, doctor_id, r_name, r_pri, r_stat))
                
            # 3. Create sample structured LabReports
            print("Creating sample LabReports...")
            reports_data = [
                ('CBC', {'wbc': '6.5', 'rbc': '4.8', 'hemoglobin': '14.2'}),
                ('Blood Sugar', {'fasting': '95', 'pp': '120'}),
                ('Urine Test', {'color': 'yellow', 'ph': '6.0'}),
                ('Liver Function', {'sgot': '25', 'sgpt': '30'}),
                ('ECG', {'heart_rate': '72', 'rhythm': 'sinus'})
            ]
            for r_type, s_data in reports_data:
                struct_json = json.dumps(s_data)
                doc_hash = hashlib.sha256(struct_json.encode('utf-8')).hexdigest()
                aes_key = os.urandom(32).hex()
                enc_aes = f"WRAPPED_BY_{patient_kem_pub[:10]}_{aes_key[:10]}" if patient_kem_pub else f"UNWRAPPED_{aes_key[:10]}"
                dig_sig = f"SIGNED_BY_{str(lab_tech_id)[:8]}_{doc_hash[:10]}"
                tx_hash = f"0x{hashlib.sha256(os.urandom(32)).hexdigest()}"
                
                cur.execute("""
                    INSERT INTO LabReports (patient_id, uploaded_by, lab_tech_id, report_name, report_type, findings, normal_range, structured_data, document_hash, encrypted_aes_key, digital_signature, blockchain_tx_hash, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Completed')
                """, (patient_id, lab_tech_id, lab_tech_id, f"Sample {r_type} Report", r_type, 'Normal findings', 'Standard', struct_json, doc_hash, enc_aes, dig_sig, tx_hash))

            # 4. Create sample ImagingReports
            print("Creating sample ImagingReports...")
            imaging_data = [
                ('Brain', 'MRI', 'Headaches', 'Normal brain parenchyma', 'No acute intracranial abnormality'),
                ('Chest', 'X-Ray', 'Cough', 'Clear lungs', 'Normal chest radiograph'),
                ('Abdomen', 'CT Scan', 'Pain', 'Normal solid organs', 'Unremarkable CT abdomen')
            ]
            for reg, ex, hist, find, imp in imaging_data:
                cur.execute("""
                    INSERT INTO ImagingReports (patient_id, lab_tech_id, scan_region, exam_type, clinical_history, findings, impression, recommendations, image_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (patient_id, lab_tech_id, reg, ex, hist, find, imp, 'None', 'base64_encoded_dummy_image_data'))

            # 5. Create notifications for the Lab Technician
            print("Creating notifications...")
            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'SYSTEM_ALERT', 'Welcome to Lab Dashboard', 'Your dashboard is fully set up with PQC and Blockchain auditing.')
            """, (lab_tech_id,))
            
            conn.commit()
            print("Seed script completed successfully!")

if __name__ == "__main__":
    seed_lab_data()
