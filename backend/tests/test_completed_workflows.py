"""Regression checks for completion work; live cases run in PostgreSQL/liboqs CI."""
import base64
import os
import time
import uuid
from datetime import date, timedelta
from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from app import account_security as accounts
from app.security import encrypt_data, decrypt_data, decrypt_data_strict, ColumnIntegrityError


@pytest.mark.parametrize('timestamp,expected', [(59, '94287082'), (1111111109, '07081804'),
    (1111111111, '14050471'), (1234567890, '89005924'), (2000000000, '69279037'), (20000000000, '65353130')])
def test_totp_rfc6238_vectors(timestamp, expected):
    secret = base64.b32encode(b'12345678901234567890').decode()
    assert accounts.totp(secret, timestamp // 30, digits=8) == expected


def test_totp_replay_and_expiry():
    secret = base64.b32encode(b'12345678901234567890').decode()
    counter = 1000
    code = accounts.totp(secret, counter)
    assert accounts.match_totp(secret, code, now=counter * 30) == counter
    assert accounts.match_totp(secret, code, last_counter=counter, now=counter * 30) is None
    assert accounts.match_totp(secret, code, now=(counter + 3) * 30) is None


def test_columns_authenticate_ciphertext_and_reject_wrong_key():
    value = encrypt_data('private clinical note', 'a' * 32)
    assert value.startswith('gcm2:')
    with pytest.raises(ColumnIntegrityError):
        decrypt_data_strict(value, 'b' * 32)
    parts = value.split(':')
    damaged = bytearray(base64.b64decode(parts[2])); damaged[0] ^= 1
    parts[2] = base64.b64encode(damaged).decode()
    with pytest.raises(ColumnIntegrityError):
        decrypt_data_strict(':'.join(parts), 'a' * 32)
    with pytest.raises(ColumnIntegrityError):
        decrypt_data('gcm2:corrupt')


def test_legacy_cbc_migrates_to_authenticated_format():
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    key, iv = b'a' * 32, b'b' * 16
    ciphertext = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(b'legacy clinical note', 16))
    old = base64.b64encode(iv).decode() + ':' + base64.b64encode(ciphertext).decode()
    plain = decrypt_data_strict(old, key.decode())
    assert plain == 'legacy clinical note'
    assert decrypt_data_strict(encrypt_data(plain, key.decode()), key.decode()) == plain


def test_s3_recovery_is_reachable_and_authenticates(monkeypatch):
    from app import main
    from app.crypto_service import encrypt_document, derive_aes_key, sha256_hex
    secret = b'x' * 32
    plain = b'Cloud recovered document'
    encrypted = encrypt_document(plain, derive_aes_key(secret))
    row = {'id': 'doc', 'encrypted_content': None, 's3_key': 'object',
           'mlkem_private_key_encrypted': 'key', 'encrypted_aes_key': 'kem',
           'encryption_nonce': encrypted['nonce'], 'encryption_tag': encrypted['tag'],
           'document_hash': sha256_hex(plain)}
    monkeypatch.setattr(main, 'decapsulate_aes_key', lambda *args: secret)
    monkeypatch.setattr(main, 'download_file_from_s3', lambda key: encrypted['ciphertext'].encode())
    assert main._decrypt_medical_document(row)['content'] == plain.decode()
    row['document_hash'] = '0' * 64
    with pytest.raises(HTTPException) as exc:
        main._decrypt_medical_document(row)
    assert exc.value.status_code == 409


def test_s3_failure_never_releases_legacy_plaintext(monkeypatch):
    from app import main
    def unavailable(key): raise main.StorageError('offline')
    monkeypatch.setattr(main, 'download_file_from_s3', unavailable)
    with pytest.raises(HTTPException) as exc:
        main._decrypt_medical_document({'encrypted_content': None, 'content': 'stale', 's3_key': 'object', 'mlkem_private_key_encrypted': 'key'})
    assert exc.value.status_code == 503


LIVE = pytest.mark.skipif(os.getenv('RUN_E2E') != '1', reason='requires real PostgreSQL and liboqs')
PASSWORD = 'Completion-Password-123!'


@pytest.fixture(scope='module')
def live():
    if os.getenv('RUN_E2E') != '1':
        pytest.skip('requires RUN_E2E')
    import psycopg
    from psycopg.rows import dict_row
    from fastapi.testclient import TestClient
    from app.main import app
    from app.crypto_service import generate_mlkem_keypair, generate_mldsa_keypair, pqc_available
    from app.security import hash_password
    if not pqc_available(): pytest.skip('real liboqs required')
    with TestClient(app) as client:
        db = psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, autocommit=True)
        people = {}
        for role in ('Patient', 'Doctor', 'Nurse'):
            tag = uuid.uuid4().hex[:10]
            kp, ks = generate_mlkem_keypair(); sp, ss = generate_mldsa_keypair()
            row = db.execute("""INSERT INTO Users (user_id, full_name, email, password_hash, role, gender,
                date_of_birth_encrypted, status, mlkem_public_key, mlkem_private_key_encrypted, mldsa_public_key, mldsa_private_key_encrypted)
                VALUES (%s,%s,%s,%s,%s,'Other',%s,'Approved',%s,%s,%s,%s) RETURNING id, user_id, email""",
                (tag, role, tag+'@example.com', hash_password(PASSWORD), role, encrypt_data('1990-01-01'),kp,ks,sp,ss)).fetchone()
            result = client.post('/api/login',json={'user_id':tag,'password':PASSWORD})
            assert result.status_code == 200, result.text
            people[role] = {**row, 'headers': {'Authorization': 'Bearer '+result.json()['access_token']}}
        yield client, db, people
        db.close()


@LIVE
def test_document_creation_rotation_history_and_revocation(live):
    client, db, people = live
    p, d = people['Patient'], people['Doctor']
    db.execute("INSERT INTO Consent (patient_id, subject_user_id, subject_role) VALUES (%s,%s,'Doctor')", (p['id'],d['id']))
    result = client.post('/api/doctor/documents', headers=d['headers'], json={
        'patient_id': str(p['id']), 'document_name':'Referral', 'document_type':'Referral Letter', 'content':'Please review.'})
    assert result.status_code == 200, result.text
    ident = result.json()['document_id']
    read = '/api/patient/documents/'+ident+'/content'
    assert client.get(read, headers=p['headers']).json()['content'] == 'Please review.'
    assert client.get('/api/doctor/documents/'+ident+'/content', headers=d['headers']).status_code == 200
    for actor in (p,d):
        result = client.post('/api/auth/keys/rotate', headers=actor['headers'],json={'password':PASSWORD})
        assert result.status_code == 200, result.text
        assert result.json()['version'] == 2
    assert client.get(read, headers=p['headers']).json()['content'] == 'Please review.'
    new = client.post('/api/doctor/documents', headers=d['headers'], json={
        'patient_id':str(p['id']), 'document_name':'New', 'document_type':'Other', 'content':'Fresh keys.'})
    assert new.status_code == 200, new.text
    stored = db.execute('SELECT recipient_key_version, signer_key_version FROM MedicalDocuments WHERE id=%s', (new.json()['document_id'],)).fetchone()
    assert stored == {'recipient_key_version':2, 'signer_key_version':2}
    revoked = client.post('/api/auth/keys/revoke', headers=d['headers'], json={'password':PASSWORD,'version':1})
    assert revoked.status_code == 200, revoked.text
    assert client.get(read, headers=p['headers']).status_code == 409
    assert client.get('/api/patient/documents/'+new.json()['document_id']+'/content',headers=p['headers']).status_code == 200
    assert client.get(read,headers=people['Nurse']['headers']).status_code == 403


@LIVE
def test_appointment_conflicts_and_transitions(live):
    client, db, people = live
    p,d=people['Patient'],people['Doctor']
    tomorrow=(date.today()+timedelta(days=2)).isoformat()
    payload={'doctor_id':str(d['id']),'department':'General','appointment_date':tomorrow,'appointment_time':'11:00'}
    booked=client.post('/api/patient/appointments',headers=p['headers'],json=payload)
    assert booked.status_code==200,booked.text
    ident=booked.json()['appointment_id']
    assert client.post('/api/patient/appointments',headers=p['headers'],json={**payload,'appointment_time':'11:15'}).status_code==409
    available=client.get(f"/api/patient/doctors/{d['id']}/slots?day={tomorrow}",headers=p['headers']).json()
    assert '11:00' not in available['slots']
    assert client.post(f'/api/doctor/appointments/{ident}/complete',headers=d['headers']).status_code==409
    changed=client.post(f'/api/patient/appointments/{ident}/reschedule',headers=p['headers'],json={'appointment_date':tomorrow,'appointment_time':'12:00'})
    assert changed.status_code==200,changed.text
    assert client.post(f'/api/doctor/appointments/{ident}/accept',headers=d['headers']).status_code==200
    assert client.post(f'/api/patient/appointments/{ident}/cancel',headers=p['headers']).status_code==200
    assert client.post(f'/api/doctor/appointments/{ident}/complete',headers=d['headers']).status_code==409


@LIVE
def test_mfa_recovery_reset_and_session_revocation(live, monkeypatch):
    client, db, people = live
    n=people['Nurse']
    setup=client.post('/api/auth/mfa/setup',headers=n['headers'],json={'password':PASSWORD})
    assert setup.status_code==200,setup.text
    secret=setup.json()['secret']
    confirmed=client.post('/api/auth/mfa/confirm',headers=n['headers'],json={'code':accounts.totp(secret,int(time.time())//30)})
    assert confirmed.status_code==200,confirmed.text
    codes=confirmed.json()['recovery_codes']
    login={'user_id':n['user_id'],'password':PASSWORD}
    assert client.post('/api/login',json=login).status_code==401
    signed=client.post('/api/login',json={**login,'otp':codes[0]})
    assert signed.status_code==200,signed.text
    assert client.post('/api/login',json={**login,'otp':codes[0]}).status_code==401
    delivered=[]
    monkeypatch.setattr(accounts,'send_reset_email',lambda address,token:delivered.append((address,token)))
    asked=client.post('/api/auth/password/forgot',json={'email':n['email']})
    assert asked.status_code==200 and len(delivered)==1
    raw=delivered[0][1]
    assert db.execute('SELECT token_hash FROM PasswordResetTokens WHERE user_id=%s',(n['id'],)).fetchone()['token_hash'] != raw
    reset={'token':raw,'new_password':'Changed-Password-456!'}
    assert client.post('/api/auth/password/reset',json=reset).status_code==403  # MFA survives recovery
    done=client.post('/api/auth/password/reset',json={**reset,'otp':codes[1]})
    assert done.status_code==200,done.text
    assert client.post('/api/auth/password/reset',json={**reset,'otp':codes[2]}).status_code==400
    assert client.get('/api/auth/me',headers=n['headers']).status_code==401
    assert client.post('/api/login',json={'user_id':n['user_id'],'password':reset['new_password'],'otp':codes[2]}).status_code==200


@LIVE
def test_throttle_persists_and_rejects_over_limit(live):
    client,db,_=live
    ident=uuid.uuid4().hex
    for _ in range(3): accounts.throttle('test-completion',ident,3)
    with pytest.raises(HTTPException) as exc: accounts.throttle('test-completion',ident,3)
    assert exc.value.status_code==429 and int(exc.value.headers['Retry-After'])>0
    db.execute('UPDATE AuthRateLimits SET expires_at=NOW()-INTERVAL \'1 second\' WHERE bucket=%s',(accounts.token_digest('test-completion:'+ident),))
    accounts.throttle('test-completion',ident,3)


def test_strict_column_mode_rejects_plaintext_downgrades(monkeypatch):
    monkeypatch.setenv('REQUIRE_AUTHENTICATED_COLUMNS', 'true')
    assert decrypt_data(encrypt_data('clinical note')) == 'clinical note'
    with pytest.raises(ColumnIntegrityError):
        decrypt_data('injected plaintext')
    assert decrypt_data(None) is None


@pytest.mark.parametrize('proven', [False, True])
def test_optional_consent_proof_is_enforced(monkeypatch, proven):
    from app import main
    monkeypatch.setenv('REQUIRE_CONSENT_PROOF', 'true')
    monkeypatch.setattr(main.consent_ledger, 'chain_state', lambda *args: None)
    class Cursor:
        def __init__(self): self.rows = iter([{'blocked': False, 'emergency': False}, {'treating': False, 'consented': True}, {'proven': proven}])
        def execute(self, *args): pass
        def fetchone(self): return next(self.rows)
    allowed, detail = main._doctor_patient_authorization(Cursor(), 'doctor', 'patient')
    assert allowed is proven
    if not proven: assert 'proof' in detail


def test_imaging_cloud_recovery_and_missing_key(monkeypatch):
    from app import main
    from app.crypto_service import encrypt_document, derive_aes_key, sha256_hex
    plain, secret = b'{"image_data":"data:image/png;base64,AAAA"}', b'z' * 32
    encrypted = encrypt_document(plain, derive_aes_key(secret))
    row = {'encrypted_image': None, 's3_key': 'image', 'mlkem_private_key_encrypted': 'key',
           'encrypted_aes_key':'kem', 'encryption_nonce':encrypted['nonce'], 'encryption_tag':encrypted['tag'],
           'document_hash':sha256_hex(plain)}
    monkeypatch.setattr(main, 'download_file_from_s3', lambda key: encrypted['ciphertext'].encode())
    monkeypatch.setattr(main, 'decapsulate_aes_key', lambda *args: secret)
    result = main._release_imaging_payload(row, 'image')
    assert result['encrypted'] is True
    row['mlkem_private_key_encrypted'] = None
    with pytest.raises(HTTPException) as exc:
        main._release_imaging_payload(row,'image')
    assert exc.value.status_code == 409
