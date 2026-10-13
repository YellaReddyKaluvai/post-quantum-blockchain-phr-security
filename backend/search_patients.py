import sys
import argparse
from app.database import get_db
from app.security import decrypt_data
from psycopg.rows import dict_row

def search_patients(blood_group=None, dob=None):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, user_id, full_name, date_of_birth_encrypted, blood_group_encrypted FROM Users WHERE role = 'Patient'")
            patients = cur.fetchall()

    results = []
    for p in patients:
        dec_dob = decrypt_data(p["date_of_birth_encrypted"]) if p["date_of_birth_encrypted"] else None
        dec_bg = decrypt_data(p["blood_group_encrypted"]) if p["blood_group_encrypted"] else None
        
        match = True
        if blood_group and dec_bg != blood_group:
            match = False
        if dob and dec_dob != dob:
            match = False
            
        if match:
            p["date_of_birth"] = dec_dob
            p["blood_group"] = dec_bg
            results.append(p)

    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search Patients by encrypted Blood Group or DOB")
    parser.add_argument("--blood-group", help="Blood Group to search for (e.g. 'O+')")
    parser.add_argument("--dob", help="Date of birth to search for (e.g. '1990-01-01')")
    args = parser.parse_args()

    print(f"Searching for Patients - Blood Group: {args.blood_group}, DOB: {args.dob}")
    matches = search_patients(args.blood_group, args.dob)
    
    if not matches:
        print("No matching patients found.")
    else:
        print(f"Found {len(matches)} match(es):")
        for m in matches:
            print(f"- {m['full_name']} (ID: {m['user_id']}) | DOB: {m['date_of_birth']} | Blood Group: {m['blood_group']}")
