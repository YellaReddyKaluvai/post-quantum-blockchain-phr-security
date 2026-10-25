#!/usr/bin/env python3
"""Run a synthetic five-role demo through the public frontend; export evidence."""
import argparse
import datetime as dt
import getpass
import hashlib
import http.cookiejar
import json
import math
import os
from pathlib import Path
import platform
import secrets
import statistics
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--admin-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--backend-revision', default='unreported')
    parser.add_argument('--frontend-revision', default='unreported')
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--create-demo-data', action='store_true', help='Approve creating four fictional accounts and a report; no existing data is deleted')
    args = parser.parse_args()
    if not args.create_demo_data:
        parser.error('--create-demo-data is required; this run creates fictional records')
    if not 1 <= args.samples <= 20:
        parser.error('--samples must be 1..20')
    origin = args.url.rstrip('/')
    if not origin.startswith('https://') and not origin.startswith(('http://localhost:', 'http://127.0.0.1:')):
        parser.error('Use HTTPS except for local development')
    args.output.mkdir(parents=True, exist_ok=True)
    args.private_output.mkdir(parents=True, exist_ok=True, mode=0o700)
    tag = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(2)
    password = getpass.getpass('Administrator password (hidden): ')
    result = {'run_id': tag, 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'origin': origin, 'synthetic_data': True, 'checks': [], 'requests': [],
              'versions': {'runner_python': platform.python_version(),
                           'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           'backend_git_revision': args.backend_revision,
                           'frontend_git_revision': args.frontend_revision,
                           'revision_source': 'operator-supplied hosting metadata',
                           'dataset': 'synthetic-cbc-v1', 'schema': 'repository backend/db/init.sql'},
              'configuration': {'concurrency': 1, 'latency_samples_per_route': args.samples,
                                'mutations': 'four fictional accounts, consent, care team, vitals, diagnosis, lab request and report',
                                'external_integrations': 'reported from report verification; never inferred from a CID'},
              'limitations': ['Not a load test: client-observed latency includes network and hosting delays.',
                              'No database tampering or real patient data is used.',
                              'A successful PDF download verifies decryption/release, not independent database-at-rest inspection.',
                              'No independent federated institutions or trained classifier evaluation is claimed.']}
    credentials = {}
    clients = []

    class Client:
        def __init__(self, role):
            self.role = role
            self.jar = http.cookiejar.CookieJar()
            self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
            self.logged = False
            clients.append(self)

        def call(self, path, body=None, expected=200, label=None, raw=False):
            data = None if body is None else json.dumps(body).encode()
            request = urllib.request.Request(origin + path, data=data, headers={
                'Content-Type': 'application/json', 'X-Requested-With': 'QuantumCare'})
            start = time.perf_counter()
            try:
                with self.opener.open(request, timeout=120) as response:
                    code, headers, content = response.status, response.headers, response.read()
            except urllib.error.HTTPError as error:
                code, headers, content = error.code, error.headers, error.read()
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            result['requests'].append({'operation': label or path, 'role': self.role,
                                       'method': 'GET' if body is None else 'POST',
                                       'status': code, 'elapsed_ms': elapsed})
            if code != expected:
                raise RuntimeError(f'{label or path}: expected HTTP {expected}, got {code}')
            value = content if raw else json.loads(content)
            return value, headers

        def login(self, uid, pwd):
            data, headers = self.call('/api/login', {'user_id': uid, 'password': pwd}, label='login')
            self.logged = True
            check(self.role + ' login role', data['role'] == self.role)
            cookie = (headers.get('Set-Cookie') or '').lower()
            check(self.role + ' secure session cookie', 'httponly' in cookie and ('secure' in cookie or origin.startswith('http://')))
            return data

        def get(self, path, **kwargs):
            return self.call(path, **kwargs)[0]

        def post(self, path, body=None, **kwargs):
            return self.call(path, {} if body is None else body, **kwargs)[0]

    def check(name, passed):
        result['checks'].append({'name': name, 'passed': bool(passed)})
        if not passed:
            raise RuntimeError('Check failed: ' + name)

    def save_private():
        p = args.private_output / ('accounts-' + tag + '.json')
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump({'run_id': tag, 'origin': origin, 'accounts': credentials}, f, indent=2)

    try:
        anon = Client('Anonymous')
        check('frontend proxy health', anon.get('/api/health')['status'] == 'ok')
        anon.get('/api/admin/dashboard/stats', expected=401, label='anonymous admin refusal')
        check('anonymous admin request refused', True)
        admin = Client('Administrator')
        admin.login(args.admin_id, password)
        password = None
        people = {}
        for role in ['Patient', 'Doctor', 'Lab Technician', 'Nurse']:
            pwd = secrets.token_urlsafe(20)
            email = role.lower().replace(' ', '') + '-' + tag.lower() + '@example.com'
            body = {'full_name': 'Demo ' + role + ' (Fictional)', 'email': email,
                    'password': pwd, 'confirm_password': pwd, 'role': role,
                    'gender': 'Other', 'date_of_birth': '2000-01-01'}
            if role == 'Patient': body['blood_group'] = 'O+'
            if role == 'Doctor': body['specialization'] = 'General Medicine'
            anon.post('/api/register', body, label='register ' + role)
            pending = admin.get('/api/admin/registrations/pending')
            row = next(x for x in pending if x['email'] == email)
            approval = admin.post('/api/admin/registrations/' + row['id'] + '/approve', label='approve ' + role)
            uid = approval['user_id']
            credentials[role] = {'user_id': uid, 'password': pwd, 'uuid': row['id'], 'email': email}
            save_private()
            client = Client(role)
            client.login(uid, pwd)
            people[role] = client
        patient, doctor, lab, nurse = [people[x] for x in ['Patient','Doctor','Lab Technician','Nurse']]
        pid, did = credentials['Patient']['uuid'], credentials['Doctor']['uuid']
        doctor.get('/api/doctor/patients/' + pid, expected=403, label='doctor refused before consent')
        check('doctor cannot read without permission', True)
        access = doctor.post('/api/doctor/access-requests', {'patient_id':pid, 'purpose':'Fictional demonstration: review the sample laboratory report.'})
        patient.post('/api/patient/access-requests/' + access['request_id'] + '/approve')
        doctor.get('/api/doctor/patients/' + pid, label='doctor allowed after consent')
        check('patient approval enables authorized access', True)
        nurse.get('/api/nurse/patients/' + pid, expected=403, label='nurse refused before care assignment')
        doctor.post('/api/doctor/patients/' + pid + '/care-team', {'nurse_id':credentials['Nurse']['user_id'], 'reason':'Fictional demo observation round', 'duration_hours':24})
        nurse.post('/api/nurse/patients/' + pid + '/vitals', {'heart_rate':72, 'spo2':98, 'temperature_celsius':36.8, 'blood_pressure_systolic':118, 'blood_pressure_diastolic':76, 'notes':'Fictional demonstration readings; not clinical advice.'})
        nurse.post('/api/nurse/patients/' + pid + '/notes', {'note_type':'Observation','content':'Fictional demo: routine observation recorded.'})
        check('patient can read recorded vitals', len(patient.get('/api/patient/vitals')) >= 1)
        doctor.post('/api/doctor/patients/' + pid + '/diagnosis', {'title':'Fictional demonstration review','description':'Synthetic sample only. No real diagnosis or treatment.', 'visit_date':dt.date.today().isoformat()})
        check('patient receives clinical record', len(patient.get('/api/patient/medical-records')) >= 1)
        order = doctor.post('/api/doctor/requests', {'patient_id':pid,'panel_code':'CBC','clinical_notes':'Fictional CBC example for project demonstration.'})
        rid = order['request_id']
        check('laboratory receives doctor order', any(x['id']==rid for x in lab.get('/api/lab-tech/requests')))
        lab.post('/api/lab-tech/requests/' + rid + '/status', {'status':'Accepted'})
        report = lab.post('/api/lab-tech/reports/create', {'request_id':rid,'panel_code':'CBC','values':{'hemoglobin':13.2,'rbc_count':4.6,'hematocrit':40.1,'wbc_count':7.1,'platelet_count':245}})
        check('post-quantum algorithms reported', report['kem_algorithm']=='ML-KEM-768' and report['signature_algorithm']=='ML-DSA-65')
        report_id = report['report_id']
        result['report'] = {k: report.get(k) for k in ['report_id','report_no','panel_code','document_hash','signature_algorithm','kem_algorithm','anchored_on']}
        verification = patient.get('/api/patient/lab-reports/' + report_id + '/verify')
        check('report digest matches', verification['hash_matches'])
        check('ML-DSA signature verifies', verification['signature_valid'])
        result['verification'] = {k:verification.get(k) for k in ['hash_matches','signature_valid','blockchain_verified','anchored_on','signature_algorithm','kem_algorithm']}
        pdf = patient.get('/api/patient/lab-reports/' + report_id + '/download', raw=True)
        check('patient receives a decrypted PDF', pdf.startswith(b'%PDF'))
        (args.output/'sample-report.pdf').write_bytes(pdf)
        result['sample_pdf'] = {'bytes':len(pdf),'sha256':hashlib.sha256(pdf).hexdigest()}
        check('patient notified of report', any(n['notification_type']=='REPORT_READY' for n in patient.get('/api/patient/notifications')))
        patient.get('/api/admin/dashboard/stats', expected=403, label='patient admin-role refusal')
        check('patient cannot access admin API', True)
        patient.post('/api/patient/consent/' + did + '/revoke')
        doctor.get('/api/doctor/patients/' + pid, expected=403, label='doctor refused after withdrawal')
        nurse.get('/api/nurse/patients/' + pid, expected=403, label='delegated nurse refused after withdrawal')
        check('revocation blocks doctor and delegated nurse', True)
        patient.post('/api/patient/consent/' + did + '/grant')
        doctor.get('/api/doctor/patients/' + pid, label='access restored by patient for walkthrough')
        admin.get('/api/admin/audit-logs', label='administrator audit trail')
        admin.get('/api/admin/security/stats', label='administrator security overview')
        check('administrator audit and security APIs respond', True)
        latencies = {}
        for name, client, route in [('health',anon,'/api/health'),('patient_dashboard',patient,'/api/patient/dashboard/summary'),('report_verification',patient,'/api/patient/lab-reports/'+report_id+'/verify')]:
            timings=[]
            for _ in range(args.samples):
                client.get(route,label='metric: '+name)
                timings.append(result['requests'][-1]['elapsed_ms'])
            latencies[name]={'samples_ms':timings,'median_ms':round(statistics.median(timings),2),'p95_ms':sorted(timings)[math.ceil(.95*len(timings))-1]}
        result['latency']=latencies
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        password = None
        for client in clients:
            if client.logged:
                try:
                    client.post('/api/logout', label='logout '+client.role)
                    client.get('/api/auth/me', expected=401, label='session refused after logout '+client.role)
                    check(client.role+' logout invalidates session', True)
                except Exception as exc:
                    result.setdefault('cleanup_errors',[]).append(str(exc))
        result['finished_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
        result['all_passed']=not result.get('error') and not result.get('cleanup_errors') and all(x['passed'] for x in result['checks'])
        (args.output/'results.json').write_text(json.dumps(result,indent=2))
        summary=['# Hosted demonstration results','', 'Run: '+tag, '','Outcome: '+('PASS' if result['all_passed'] else 'FAIL'),'',
                 'All identities and observations in this run are fictional.','', '| Check | Result |','|---|---|']
        summary += ['| '+c['name']+' | '+('PASS' if c['passed'] else 'FAIL')+' |' for c in result['checks']]
        summary += ['', '## Client-observed latency', '', '| Route | Samples | Median ms | P95 ms |','|---|---:|---:|---:|']
        for name,data in result.get('latency',{}).items():
            summary.append(f"| {name} | {len(data['samples_ms'])} | {data['median_ms']} | {data['p95_ms']} |")
        summary += ['', 'Single client, sequential requests; includes network and hosting latency. This is not a throughput or clinical safety benchmark.', '',
                    'See results.json for source/configuration versions, request timings and limitations. Credentials are saved separately in the private output directory.']
        if result.get('error'): summary += ['', 'Failure: '+result['error']]
        (args.output/'summary.md').write_text('\n'.join(summary)+'\n')
        print(json.dumps({'run_id':tag,'all_passed':result['all_passed'],'checks':len(result['checks']),'error':result.get('error'),'output':str(args.output)},indent=2))
    return 0 if result['all_passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
