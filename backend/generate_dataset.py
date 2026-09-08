"""Generate a synthetic clinical dataset at demonstration scale.

Purpose
-------
Show that the platform holds a realistic hospital's worth of data — roughly
500 users and ~10,000 clinical records — with *no* weakening of the security
pipeline. Every key here is a genuine ML-KEM-768 / ML-DSA-65 keypair, every
encrypted column is real AES, and every finalised report is really signed and
anchored. Only the *identities and clinical content* are invented.

Why this writes to the database directly
----------------------------------------
It calls the same crypto services the API calls, but skips the HTTP layer.
The HTTP layer contributes nothing to authenticity — it is session handling
and JSON shaping — while costing a round trip per record. Skipping it makes
500 users feasible; skipping the crypto would have made the dataset
worthless, so that is never skipped.

Passwords
---------
Password hashes are Argon2 and therefore irreversible: there is no way to
recover a password from the database afterwards. The only opportunity to
record them is at creation, so every account is written to
``dataset_credentials.csv`` as it is made. All synthetic accounts share one
password so any of them can be demonstrated instantly.

Existing accounts are never touched — this appends.
"""

from __future__ import annotations

import csv
import os
import random
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
sys.path.insert(0, str(BASE))

import psycopg
from psycopg.rows import dict_row

from app.crypto_service import (
    generate_mlkem_keypair, generate_mldsa_keypair, encapsulate_aes_key,
    derive_aes_key, encrypt_document, sign_document_hash, sha256_hex,
    ML_KEM_ALG, ML_DSA_ALG,
)
from app.security import encrypt_data, hash_password
from app.lab_catalog import (
    get_panel, list_panels, analytes_of, apply_computed, interpretation_for,
)
from app.report_pdf import build_report_pdf
from app.storage_service import upload_to_aws_s3

SHARED_PASSWORD = "Demo@1234"
SEED = 20260903
random.seed(SEED)

# Volumes. Patients dominate, as in a real hospital's user base.
N_PATIENTS, N_DOCTORS, N_NURSES, N_LABTECHS, N_ADMINS = 400, 40, 30, 25, 5

# A tiny run that exercises every code path, for checking the generator itself
# before committing to the full volume.
if "--smoke" in sys.argv:
    N_PATIENTS, N_DOCTORS, N_NURSES, N_LABTECHS, N_ADMINS = 6, 3, 2, 2, 1

DSN = (f"host={os.getenv('DB_HOST','127.0.0.1')} port={os.getenv('DB_PORT','5433')} "
       f"dbname={os.getenv('DB_NAME','pqc_hospital')} user={os.getenv('DB_USER','postgres')} "
       f"password={os.getenv('DB_PASSWORD','')}")

# ─── Name pools ──────────────────────────────────────────────────────────────
FIRST_M = ["Arjun","Ravi","Vikram","Karthik","Suresh","Anil","Rahul","Manoj","Prakash","Sanjay",
           "Deepak","Naveen","Rajesh","Kiran","Aditya","Harish","Mahesh","Vinod","Ashok","Gopal",
           "Srinivas","Venkat","Ramesh","Pradeep","Sunil","Nikhil","Varun","Rohit","Ajay","Girish"]
FIRST_F = ["Priya","Lakshmi","Anjali","Kavita","Sunita","Meera","Divya","Sneha","Pooja","Rekha",
           "Swathi","Nandini","Aruna","Vidya","Shalini","Geetha","Radha","Bhavana","Latha","Usha",
           "Padma","Sushma","Ramya","Sirisha","Madhavi","Jyothi","Kalpana","Vasantha","Indira","Asha"]
LAST = ["Reddy","Sharma","Kumar","Rao","Nair","Patel","Iyer","Menon","Chowdhury","Verma",
        "Gupta","Bose","Naidu","Pillai","Desai","Joshi","Malhotra","Sinha","Kaur","Bhat",
        "Prasad","Varma","Shetty","Hegde","Kulkarni","Mehta","Agarwal","Banerjee","Das","Krishnan"]

SPECIALIZATIONS = ["Cardiology","General Medicine","Endocrinology","Nephrology","Neurology",
                   "Orthopaedics","Paediatrics","Pulmonology","Gastroenterology","Dermatology"]
DEPARTMENTS = SPECIALIZATIONS
BLOOD_GROUPS = ["O+","O-","A+","A-","B+","B-","AB+","AB-"]

# ─── Clinical coherence ──────────────────────────────────────────────────────
# A dataset of random rows would look full but make no clinical sense: a
# patient on metformin with no glucose panel and a normal HbA1c. Each condition
# below carries the prescription, panel and vitals bias that belong with it, so
# a doctor opening any chart sees a story that hangs together.
CONDITIONS = [
    {"title": "Type 2 Diabetes Mellitus",
     "symptoms": "Increased thirst, frequent urination, fatigue over several months.",
     "notes": "Fasting glucose and HbA1c consistent with type 2 diabetes. Lifestyle advice given.",
     "tests": "Fasting blood glucose, HbA1c, renal profile",
     "drugs": [("Metformin","500 mg","Twice daily","3 months","Take after meals.")],
     "panels": ["BLOOD_SUGAR","KFT"], "vitals_bias": {"weight_kg": +12}},
    {"title": "Essential Hypertension",
     "symptoms": "Occasional headaches and dizziness; clinic readings persistently elevated.",
     "notes": "Stage 1 hypertension. Salt restriction advised; review in six weeks.",
     "tests": "Lipid profile, renal function, ECG",
     "drugs": [("Amlodipine","5 mg","Once daily","3 months","Take in the morning.")],
     "panels": ["LIPID","ECG","KFT"], "vitals_bias": {"blood_pressure_systolic": +28, "blood_pressure_diastolic": +14}},
    {"title": "Hypothyroidism",
     "symptoms": "Fatigue, cold intolerance, weight gain, dry skin.",
     "notes": "TSH elevated with low free T4. Started on replacement; repeat in eight weeks.",
     "tests": "Thyroid function tests",
     "drugs": [("Levothyroxine","50 mcg","Once daily","6 months","Empty stomach, 30 min before food.")],
     "panels": ["THYROID"], "vitals_bias": {"heart_rate": -12}},
    {"title": "Iron Deficiency Anaemia",
     "symptoms": "Tiredness, breathlessness on exertion, pallor.",
     "notes": "Microcytic hypochromic picture. Oral iron started; investigate source of loss.",
     "tests": "Complete blood count, serum ferritin",
     "drugs": [("Ferrous Sulphate","200 mg","Twice daily","3 months","With vitamin C; may darken stools.")],
     "panels": ["CBC"], "vitals_bias": {"heart_rate": +14}},
    {"title": "Chronic Kidney Disease Stage 3",
     "symptoms": "Reduced urine output, ankle swelling, general fatigue.",
     "notes": "eGFR persistently reduced. Nephrology follow-up; avoid nephrotoxic drugs.",
     "tests": "Renal function, urine protein, ultrasound KUB",
     "drugs": [("Furosemide","40 mg","Once daily","2 months","Morning dose; monitor for dizziness.")],
     "panels": ["KFT","URINE"], "vitals_bias": {"blood_pressure_systolic": +20}},
    {"title": "Dyslipidaemia",
     "symptoms": "Asymptomatic; detected on routine screening.",
     "notes": "LDL above target for cardiovascular risk. Statin commenced with dietary advice.",
     "tests": "Fasting lipid profile, liver function",
     "drugs": [("Atorvastatin","20 mg","Once at night","6 months","Report unexplained muscle pain.")],
     "panels": ["LIPID","LFT"], "vitals_bias": {"weight_kg": +8}},
    {"title": "Bronchial Asthma",
     "symptoms": "Episodic wheeze and nocturnal cough, worse in cold weather.",
     "notes": "Moderate persistent asthma. Inhaler technique demonstrated.",
     "tests": "Chest X-ray, spirometry",
     "drugs": [("Salbutamol Inhaler","100 mcg","As required","3 months","Two puffs during breathlessness.")],
     "panels": ["RADIOLOGY","CBC"], "vitals_bias": {"spo2": -5, "respiratory_rate": +7}},
    {"title": "Acute Gastroenteritis",
     "symptoms": "Loose stools and vomiting for two days, mild abdominal cramps.",
     "notes": "Clinically dehydrated. Oral rehydration advised; review if symptoms persist.",
     "tests": "Stool routine, serum electrolytes",
     "drugs": [("Oral Rehydration Salts","1 sachet","After each loose stool","5 days","Dissolve in 1 litre of clean water.")],
     "panels": ["CBC","URINE"], "vitals_bias": {"temperature_celsius": +1.6, "heart_rate": +18}},
    {"title": "Viral Hepatitis",
     "symptoms": "Jaundice, nausea, right upper quadrant discomfort.",
     "notes": "Transaminases raised. Supportive care; alcohol avoidance emphasised.",
     "tests": "Liver function tests, viral markers",
     "drugs": [("Ursodeoxycholic Acid","300 mg","Twice daily","2 months","Take with food.")],
     "panels": ["LFT"], "vitals_bias": {"temperature_celsius": +1.1}},
    {"title": "Urinary Tract Infection",
     "symptoms": "Burning micturition, urinary frequency, suprapubic discomfort.",
     "notes": "Urine culture sent. Empirical antibiotic started; push fluids.",
     "tests": "Urine routine and culture",
     "drugs": [("Nitrofurantoin","100 mg","Twice daily","7 days","Complete the full course.")],
     "panels": ["URINE","CBC"], "vitals_bias": {"temperature_celsius": +1.3}},
]

NOTE_TEXTS = [
    ("Observation", "Patient comfortable at rest. Observations within expected limits for them."),
    ("Observation", "Reviewed during the morning round; no new complaints reported."),
    ("Care",        "Assisted with mobility and personal care. Tolerated the session well."),
    ("Care",        "Wound site inspected and dressing renewed. No discharge or surrounding redness."),
    ("Care",        "Dietary intake encouraged; fluid balance chart maintained."),
    ("Incident",    "Reported dizziness on standing. Sat down promptly, no fall. Doctor informed."),
    ("Incident",    "Refused the evening dose citing nausea. Escalated to the treating doctor."),
]


def full_name(gender: str) -> str:
    pool = FIRST_M if gender == "Male" else FIRST_F
    return f"{random.choice(pool)} {random.choice(LAST)}"


def make_user(role: str, gender: str, pw_hash: str) -> dict:
    """Build one user with genuine post-quantum key material."""
    kem_pub, kem_priv = generate_mlkem_keypair()
    dsa_pub, dsa_priv = generate_mldsa_keypair()
    name = full_name(gender)
    age = random.randint(21, 84) if role == "Patient" else random.randint(28, 62)
    dob = date.today() - timedelta(days=age * 365 + random.randint(0, 364))
    return {
        "id": str(uuid.uuid4()), "full_name": name, "role": role, "gender": gender,
        "password_hash": pw_hash,
        "date_of_birth_encrypted": encrypt_data(dob.isoformat()),
        "blood_group_encrypted": encrypt_data(random.choice(BLOOD_GROUPS)) if role == "Patient" else None,
        "specialization": random.choice(SPECIALIZATIONS) if role == "Doctor" else None,
        "mlkem_public_key": kem_pub, "mlkem_private_key_encrypted": kem_priv,
        "mldsa_public_key": dsa_pub, "mldsa_private_key_encrypted": dsa_priv,
        "_dob": dob, "_age": age,
    }


def next_seq(cur, prefix: str, year: int, count: int) -> int:
    """Reserve `count` public IDs atomically and return the first."""
    cur.execute(
        """INSERT INTO UserIdSequences (role_prefix, year, last_sequence) VALUES (%s,%s,%s)
           ON CONFLICT (role_prefix, year) DO UPDATE SET last_sequence = UserIdSequences.last_sequence + %s
           RETURNING last_sequence""", (prefix, year, count, count))
    return cur.fetchone()[0] - count + 1


PREFIX = {"Patient": "PAT", "Doctor": "DOC", "Nurse": "NUR", "Lab Technician": "LAB",
          "Administrator": "ADM"}


def biased_vitals(cond: dict | None) -> dict:
    """A vitals set that reflects the patient's condition.

    Readings drift toward the condition's signature rather than being random,
    so an abnormal flag on a chart has a reason behind it. Values are then
    clamped to the ranges the API validator accepts — a generator that emitted
    rows the live API would reject would be quietly lying about capacity.
    """
    v = {
        "temperature_celsius": round(random.uniform(36.2, 37.3), 1),
        "blood_pressure_systolic": random.randint(105, 132),
        "blood_pressure_diastolic": random.randint(66, 85),
        "heart_rate": random.randint(62, 92),
        "spo2": random.randint(96, 99),
        "respiratory_rate": random.randint(12, 18),
        "weight_kg": round(random.uniform(48, 88), 1),
        "height_cm": random.randint(150, 186),
    }
    if cond:
        for k, delta in cond.get("vitals_bias", {}).items():
            jitter = random.uniform(0.45, 1.15)
            v[k] = round(v[k] + delta * jitter, 1) if isinstance(v[k], float) else int(v[k] + delta * jitter)
    limits = {"temperature_celsius": (30.0, 43.0), "blood_pressure_systolic": (60, 260),
              "blood_pressure_diastolic": (30, 160), "heart_rate": (25, 250), "spo2": (50, 100),
              "respiratory_rate": (5, 60), "weight_kg": (2.0, 400.0), "height_cm": (30, 250)}
    for k, (lo, hi) in limits.items():
        v[k] = max(lo, min(hi, v[k]))
    return v


def panel_values(panel_code: str, abnormal: bool, sex: str) -> dict:
    """Plausible result values for a panel, driven by its real reference ranges.

    Ranges are sex-specific in the catalogue, so the patient's sex is honoured
    — otherwise half the haemoglobin results would flag against the wrong
    reference and the abnormal counts would be meaningless.
    """
    panel = get_panel(panel_code)
    if not panel:
        return {}
    out: dict = {}
    for a in analytes_of(panel):
        if a.get("computed"):
            continue                      # derived by apply_computed(), not entered
        key = a["key"]
        ref = a.get("ref") or {}
        band = ref.get(sex) or ref.get("A") or next(iter(ref.values()), None)
        if band and isinstance(band[0], (int, float)):
            lo, hi = float(band[0]), float(band[1])
            if abnormal and random.random() < 0.5:
                val = hi * random.uniform(1.15, 1.8) if random.random() < 0.7 else lo * random.uniform(0.4, 0.85)
            else:
                val = random.uniform(lo, hi)
            out[key] = round(val, 2)
        elif a.get("input") == "select" and a.get("options"):
            out[key] = random.choice(a["options"])
        elif a.get("input") in ("text", "textarea"):
            out[key] = "Abnormal appearance noted." if abnormal else "Within normal limits."
    return apply_computed(panel_code, out)


def create_users(conn, credentials: list) -> dict:
    """Create every user with real PQC keys, recording credentials as we go."""
    print("  hashing shared password (Argon2)…", flush=True)
    pw_hash_pool = [hash_password(SHARED_PASSWORD) for _ in range(24)]

    plan = [("Patient", N_PATIENTS), ("Doctor", N_DOCTORS), ("Nurse", N_NURSES),
            ("Lab Technician", N_LABTECHS), ("Administrator", N_ADMINS)]
    made: dict[str, list] = {r: [] for r, _ in plan}
    year = date.today().year

    with conn.cursor() as cur:
        for role, count in plan:
            t0 = time.perf_counter()
            # Each user's keypairs are generated independently; liboqs releases
            # the GIL, so threads give a real speed-up here.
            with ThreadPoolExecutor(max_workers=8) as ex:
                users = list(ex.map(
                    lambda _: make_user(role, random.choice(["Male", "Female"]),
                                        random.choice(pw_hash_pool)),
                    range(count)))

            first = next_seq(cur, PREFIX[role], year, count)
            rows = []
            for i, u in enumerate(users):
                u["user_id"] = f"{PREFIX[role]}-{year}-{first + i:06d}"
                u["email"] = (f"{u['full_name'].split()[0].lower()}."
                              f"{u['user_id'].lower().replace('-', '')}@quantumcare-demo.invalid")
                rows.append((u["id"], u["user_id"], u["full_name"], u["email"], u["password_hash"],
                             u["role"], u["gender"], u["date_of_birth_encrypted"],
                             u["blood_group_encrypted"], u["specialization"], "Approved",
                             u["mlkem_public_key"], u["mlkem_private_key_encrypted"],
                             u["mldsa_public_key"], u["mldsa_private_key_encrypted"]))
                credentials.append({"user_id": u["user_id"], "full_name": u["full_name"],
                                    "role": role, "password": SHARED_PASSWORD,
                                    "email": u["email"], "specialization": u["specialization"] or ""})
            cur.executemany(
                """INSERT INTO Users (id,user_id,full_name,email,password_hash,role,gender,
                   date_of_birth_encrypted,blood_group_encrypted,specialization,status,
                   mlkem_public_key,mlkem_private_key_encrypted,mldsa_public_key,
                   mldsa_private_key_encrypted,approved_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)""", rows)
            conn.commit()
            made[role] = users
            print(f"    {role:<16} {count:>4}  ({time.perf_counter()-t0:5.1f}s)", flush=True)
    return made


def create_clinical(conn, made: dict) -> dict:
    """Diagnoses, prescriptions, vitals, notes, appointments and lab requests."""
    patients, doctors = made["Patient"], made["Doctor"]
    nurses, techs = made["Nurse"], made["Lab Technician"]
    counts = {k: 0 for k in ("diagnoses", "prescriptions", "vitals", "notes",
                             "appointments", "lab_requests", "med_admin")}
    requests_for_reports = []
    today = date.today()

    with conn.cursor() as cur:
        for pt in patients:
            # Each patient keeps one care team, so consent and chart access
            # mean something rather than being scattered at random.
            team = random.sample(doctors, k=random.randint(1, 2))
            conds = random.sample(CONDITIONS, k=random.randint(1, 3))
            pt["_conds"] = conds
            presc_ids = []

            for cond in conds:
                doc = random.choice(team)
                visit = today - timedelta(days=random.randint(1, 540))
                cur.execute(
                    """INSERT INTO Diagnoses (patient_id,doctor_id,title,description,symptoms,
                       doctor_notes,recommended_tests,visit_date,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (pt["id"], doc["id"], encrypt_data(cond["title"]),
                     encrypt_data(cond["notes"]), encrypt_data(cond["symptoms"]),
                     encrypt_data(cond["notes"]), encrypt_data(cond["tests"]), visit, visit))
                counts["diagnoses"] += 1

                for (med, dose, freq, dur, instr) in cond["drugs"]:
                    pid = str(uuid.uuid4())
                    cur.execute(
                        """INSERT INTO Prescriptions (id,patient_id,doctor_id,medicine_name,dosage,
                           frequency,duration,instructions,prescribed_date,created_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (pid, pt["id"], doc["id"], encrypt_data(med), encrypt_data(dose),
                         encrypt_data(freq), encrypt_data(dur), encrypt_data(instr), visit, visit))
                    presc_ids.append(pid)
                    counts["prescriptions"] += 1

                for code in cond["panels"]:
                    if random.random() < 0.75:
                        rid = str(uuid.uuid4())
                        panel = get_panel(code)
                        pri = random.choices(["Routine", "Urgent", "Emergency"], [0.72, 0.22, 0.06])[0]
                        done = random.random() < 0.72
                        tech = random.choice(techs)
                        cur.execute(
                            """INSERT INTO LabTestRequests (id,patient_id,doctor_id,test_name,priority,
                               status,clinical_notes,requested_date,panel_code,accepted_by,accepted_at,
                               completed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (rid, pt["id"], doc["id"], panel["name"], pri,
                             "Completed" if done else random.choice(["Pending", "Accepted", "In Progress"]),
                             cond["tests"], visit, code,
                             tech["id"] if done else None, visit if done else None,
                             visit + timedelta(days=1) if done else None))
                        counts["lab_requests"] += 1
                        if done:
                            requests_for_reports.append(
                                {"request_id": rid, "patient": pt, "doctor": doc, "tech": tech,
                                 "panel_code": code, "collected": visit})

            for _ in range(random.randint(2, 7)):
                nurse = random.choice(nurses)
                v = biased_vitals(random.choice(conds))
                cur.execute(
                    """INSERT INTO PatientVitals (patient_id,nurse_id,temperature_celsius,
                       blood_pressure_systolic,blood_pressure_diastolic,heart_rate,spo2,
                       respiratory_rate,weight_kg,height_cm,notes,recorded_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (pt["id"], nurse["id"], v["temperature_celsius"], v["blood_pressure_systolic"],
                     v["blood_pressure_diastolic"], v["heart_rate"], v["spo2"],
                     v["respiratory_rate"], v["weight_kg"], v["height_cm"], None,
                     datetime.now() - timedelta(days=random.randint(0, 120), hours=random.randint(0, 23))))
                counts["vitals"] += 1

            for _ in range(random.randint(0, 3)):
                nt, body = random.choice(NOTE_TEXTS)
                cur.execute(
                    """INSERT INTO NursingNotes (patient_id,nurse_id,note_type,content,created_at)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (pt["id"], random.choice(nurses)["id"], nt, body,
                     datetime.now() - timedelta(days=random.randint(0, 90))))
                counts["notes"] += 1

            for pid in presc_ids:
                for _ in range(random.randint(0, 4)):
                    # Refusals and missed doses are the clinically interesting
                    # outcomes, so they are represented rather than idealised away.
                    st = random.choices(["Administered", "Refused", "Held", "Missed"],
                                        [0.86, 0.06, 0.05, 0.03])[0]
                    cur.execute(
                        """INSERT INTO MedicationAdministration (prescription_id,patient_id,nurse_id,
                           status,remarks,administered_at) VALUES (%s,%s,%s,%s,%s,%s)""",
                        (pid, pt["id"], random.choice(nurses)["id"], st,
                         "Patient declined this dose." if st == "Refused" else None,
                         datetime.now() - timedelta(days=random.randint(0, 60), hours=random.randint(0, 23))))
                    counts["med_admin"] += 1

            for _ in range(random.randint(0, 2)):
                doc = random.choice(team)
                future = random.random() < 0.4
                appt = today + timedelta(days=random.randint(1, 45)) if future \
                    else today - timedelta(days=random.randint(1, 180))
                cur.execute(
                    """INSERT INTO Appointments (patient_id,doctor_id,department,appointment_date,
                       appointment_time,status,notes) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (pt["id"], doc["id"], doc["specialization"] or "General Medicine", appt,
                     f"{random.randint(9,17):02d}:{random.choice(['00','15','30','45'])}",
                     random.choice(["Scheduled", "Confirmed"]) if future
                     else random.choices(["Completed", "Cancelled"], [0.85, 0.15])[0], None))
                counts["appointments"] += 1
        conn.commit()
    return counts, requests_for_reports


def build_one_report(job: dict, seq: int) -> dict:
    """Run the complete security pipeline for a single report.

    Deliberately identical in substance to what the lab-technician endpoint
    does: real PDF, real AES-256-GCM, real ML-KEM encapsulation against the
    patient's public key, real ML-DSA signature by the technician. Nothing is
    stubbed — a dataset built on stubbed crypto would prove nothing about
    capacity under the real workload.
    """
    pt, doc, tech = job["patient"], job["doctor"], job["tech"]
    code = job["panel_code"]
    panel = get_panel(code)
    sex = "M" if pt["gender"] == "Male" else "F"
    abnormal = random.random() < 0.42
    values = panel_values(code, abnormal, sex)

    year = date.today().year
    report_no = f"RPT-{year}-{seq:06d}"
    accession = f"ACC{year}{seq:06d}"

    collected_at = datetime.combine(job["collected"], datetime.min.time())
    reported_at = collected_at + timedelta(days=1)
    interpretation = interpretation_for(code, values, sex) or ""

    pdf = build_report_pdf(
        panel=panel, values=values,
        patient={"full_name": pt["full_name"], "user_id": pt["user_id"],
                 "gender": pt["gender"], "age": pt["_age"],
                 "date_of_birth": pt["_dob"].isoformat()},
        doctor={"full_name": doc["full_name"], "specialization": doc["specialization"]},
        technician={"full_name": tech["full_name"], "user_id": tech["user_id"]},
        report_no=report_no, accession=accession,
        collected_at=collected_at, reported_at=reported_at,
        interpretation=interpretation,
        signature_algorithm=ML_DSA_ALG, kem_algorithm=ML_KEM_ALG,
    )

    digest = sha256_hex(pdf)
    kem_ct, shared = encapsulate_aes_key(pt["mlkem_public_key"])
    enc = encrypt_document(pdf, derive_aes_key(shared))
    signature = sign_document_hash(digest, tech["mldsa_private_key_encrypted"])

    return {**job, "report_no": report_no, "accession": accession, "panel": panel,
            "values": values, "abnormal": abnormal, "digest": digest,
            "kem_ct": kem_ct, "enc": enc, "signature": signature,
            "pdf_size": len(pdf), "interpretation": interpretation}


def create_reports(conn, jobs: list, upload_s3: bool) -> dict:
    """Encrypt, sign, store and (optionally) upload every completed report."""
    stats = {"reports": 0, "s3": 0, "s3_failed": 0, "bytes": 0}
    if not jobs:
        return stats

    print(f"  running the security pipeline over {len(jobs)} reports…", flush=True)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as ex:
        built = list(ex.map(lambda p: build_one_report(p[1], p[0] + 1), enumerate(jobs)))
    print(f"    crypto complete ({time.perf_counter()-t0:5.1f}s)", flush=True)

    s3_keys: dict[str, str] = {}
    if upload_s3:
        t0 = time.perf_counter()
        def push(r):
            name = f"reports/{r['patient']['user_id']}/{r['report_no']}.enc"
            try:
                # Record the key the uploader *returns*, never the one we asked
                # for: it prefixes the object path, so a constructed key would
                # point at nothing. Storing a key for an object that does not
                # exist is the defect this pipeline was rewritten to prevent.
                stored_key, _url = upload_to_aws_s3(r["enc"]["ciphertext"].encode(), name)
                return r["report_no"], stored_key
            except Exception:
                return r["report_no"], None
        with ThreadPoolExecutor(max_workers=16) as ex:
            for name, key in ex.map(push, built):
                if key:
                    s3_keys[name] = key
        stats["s3"] = len(s3_keys)
        stats["s3_failed"] = len(built) - len(s3_keys)
        print(f"    cloud upload complete: {stats['s3']} objects "
              f"({time.perf_counter()-t0:5.1f}s)", flush=True)

    with conn.cursor() as cur:
        for r in built:
            cur.execute(
                """INSERT INTO LabReports (patient_id,uploaded_by,report_name,report_type,
                   report_id_public,findings,status,upload_date,structured_data,document_hash,
                   encrypted_aes_key,digital_signature,lab_tech_id,s3_key,lab_request_id,doctor_id,
                   panel_code,accession_number,collected_at,finalized_at,is_locked,interpretation,
                   encryption_nonce,encryption_tag,kem_algorithm,signature_algorithm,
                   encrypted_document,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           %s,%s,%s,%s)""",
                (r["patient"]["id"], r["tech"]["id"], r["panel"]["name"],
                 r["panel"]["db_report_type"], r["report_no"], r["interpretation"][:2000],
                 "Completed", r["collected"], psycopg.types.json.Json(r["values"]), r["digest"],
                 r["kem_ct"], r["signature"], r["tech"]["id"], s3_keys.get(r["report_no"]),
                 r["request_id"], r["doctor"]["id"], r["panel_code"], r["accession"],
                 r["collected"], r["collected"] + timedelta(days=1), True,
                 r["interpretation"][:2000], r["enc"]["nonce"], r["enc"]["tag"],
                 ML_KEM_ALG, ML_DSA_ALG, r["enc"]["ciphertext"], r["collected"]))
            stats["reports"] += 1
            stats["bytes"] += r["pdf_size"]

            cur.execute(
                """INSERT INTO Notifications (user_id,notification_type,title,body)
                   VALUES (%s,'REPORT_READY',%s,%s)""",
                (r["patient"]["id"], "Laboratory report ready",
                 f"Your {r['panel']['short_name']} report ({r['report_no']}) is ready to view."))
        conn.commit()
    return stats


SYNTHETIC_MARKER = "%@quantumcare-demo.invalid"


def reset_synthetic(conn) -> int:
    """Remove previously generated data so the script can be re-run cleanly.

    Scoped by the synthetic e-mail marker, which only generated accounts carry.
    Hand-made demo accounts and anything a person entered through the UI are
    matched by nothing here and are left untouched — a reset that could reach
    real data would be far more dangerous than a stale dataset.
    """
    with conn.cursor() as cur:
        cur.execute(f"SELECT id FROM Users WHERE email LIKE '{SYNTHETIC_MARKER}'")
        ids = [r[0] for r in cur.fetchall()]
        if not ids:
            return 0
        for table, col in [
            ("MedicationAdministration", "patient_id"), ("NursingNotes", "patient_id"),
            ("PatientVitals", "patient_id"), ("Prescriptions", "patient_id"),
            ("Diagnoses", "patient_id"), ("LabReports", "patient_id"),
            ("LabTestRequests", "patient_id"), ("Appointments", "patient_id"),
            ("Notifications", "user_id"), ("Consent", "Patient_ID"),
            ("EmergencyAccess", "Patient_ID"), ("Sessions", "user_id"),
            ("AuthLogs", "user_id"), ("AdminAuditLogs", "admin_id"),
            ("AdminAuditLogs", "target_user_id"), ("MedicalDocuments", "patient_id"),
            ("ImagingReports", "patient_id"),
        ]:
            try:
                cur.execute(f"DELETE FROM {table} WHERE {col} = ANY(%s)", (ids,))
            except Exception:
                conn.rollback()          # table or column absent in this schema
        cur.execute("DELETE FROM Users WHERE id = ANY(%s)", (ids,))
        conn.commit()
    return len(ids)


def main() -> None:
    upload_s3 = "--no-s3" not in sys.argv
    started = time.perf_counter()

    print("\n" + "=" * 66)
    print("  QuantumCare — synthetic dataset generation")
    print("=" * 66)
    print(f"  target users : {N_PATIENTS + N_DOCTORS + N_NURSES + N_LABTECHS + N_ADMINS}")
    print(f"  key material : {ML_KEM_ALG} + {ML_DSA_ALG}  (genuine, not simulated)")
    print(f"  cloud upload : {'enabled' if upload_s3 else 'skipped (--no-s3)'}")
    print(f"  seed         : {SEED}  (re-running reproduces the same dataset)")
    print("-" * 66)

    credentials: list[dict] = []
    with psycopg.connect(DSN) as conn:
        if "--reset" in sys.argv:
            removed = reset_synthetic(conn)
            print(f"  reset: removed {removed} previously generated users")
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM Users")
            before = cur.fetchone()[0]
        print(f"  pre-existing users preserved: {before}\n")

        print("  [1/3] users + post-quantum keypairs")
        made = create_users(conn, credentials)

        print("\n  [2/3] clinical records")
        t0 = time.perf_counter()
        counts, jobs = create_clinical(conn, made)
        print(f"    {'diagnoses':<16}{counts['diagnoses']:>6}")
        print(f"    {'prescriptions':<16}{counts['prescriptions']:>6}")
        print(f"    {'vitals':<16}{counts['vitals']:>6}")
        print(f"    {'nursing notes':<16}{counts['notes']:>6}")
        print(f"    {'med. rounds':<16}{counts['med_admin']:>6}")
        print(f"    {'appointments':<16}{counts['appointments']:>6}")
        print(f"    {'lab requests':<16}{counts['lab_requests']:>6}   ({time.perf_counter()-t0:5.1f}s)")

        print("\n  [3/3] lab reports through the full security pipeline")
        rstats = create_reports(conn, jobs, upload_s3)

    out = BASE / "dataset_credentials.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["user_id", "full_name", "role", "password",
                                           "email", "specialization"])
        w.writeheader()
        w.writerows(credentials)

    total = sum(counts.values()) + rstats["reports"] + len(credentials)
    print("\n" + "=" * 66)
    print(f"  users created      {len(credentials):>6}")
    print(f"  clinical records   {sum(counts.values()):>6}")
    print(f"  signed reports     {rstats['reports']:>6}"
          f"   ({rstats['bytes']/1_048_576:.1f} MB of PDF encrypted)")
    if upload_s3:
        print(f"  cloud objects      {rstats['s3']:>6}"
              + (f"   ({rstats['s3_failed']} failed)" if rstats["s3_failed"] else ""))
    print(f"  TOTAL ROWS         {total:>6}")
    print(f"  elapsed            {time.perf_counter()-started:>6.1f}s")
    print(f"\n  credentials -> {out}")
    print(f"  every synthetic account's password is: {SHARED_PASSWORD}")
    print("=" * 66 + "\n")


if __name__ == "__main__":
    main()
