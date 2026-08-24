import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
import logging
from datetime import datetime
from app.config import get_settings

logger = logging.getLogger(__name__)

# Display name shown to recipients in their inbox.
SENDER_NAME = "QuantumCare"

def send_and_log_email(
    conn, 
    user_id: str, 
    to_email: str, 
    full_name: str, 
    notification_type: str, 
    user_id_gen: str = None, 
    reason: str = None
) -> dict:
    """
    Sends an email and logs the delivery status in EmailNotifications.
    Guarantees exceptions are caught so SMTP failure doesn't rollback account actions.
    """
    if notification_type == "APPROVAL":
        subject = "Your QuantumCare Account Has Been Approved"
        body = f"""Dear {full_name},

Congratulations! Your registration request has been reviewed and approved by the QuantumCare Hospital Administrator.

Your account is now active.

Your Login Details:

User ID: {user_id_gen}

You can now sign in to QuantumCare using your User ID and the password you created during registration. Your account is protected end-to-end with post-quantum cryptography (ML-KEM / ML-DSA) alongside AES-256 encryption.

For your security:

* Do not share your User ID.
* Do not share your password.
* Never share your account credentials with anyone, including QuantumCare staff.

Regards,
The QuantumCare Team"""
    elif notification_type == "REJECTION":
        subject = "Update on Your QuantumCare Registration Request"
        body = f"""Dear {full_name},

Thank you for your interest in QuantumCare. After review, your registration request has not been approved at this time."""
        if reason:
            body += f"\n\nReason: {reason}"
        body += """\n\nIf you believe this was in error or would like more information, please contact the QuantumCare Hospital Administration.

Regards,
The QuantumCare Team"""
    else:
        raise ValueError(f"Invalid notification type: {notification_type}")

    # Insert initial PENDING log
    notification_id = None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO EmailNotifications (
                    user_id, email_address, notification_type, email_subject, email_content, sent_status
                ) VALUES (%s, %s, %s, %s, %s, 'PENDING')
                RETURNING id
            """, (user_id, to_email, notification_type, subject, body))
            notification_id = cur.fetchone()[0]
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to log pending email in DB: {e}")
        # If DB log fails, we still proceed to try sending

    # Attempt transmission
    settings = get_settings()
    sent_status = "SENT"
    error_message = None
    sent_timestamp = None

    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        # SMTP is not configured (typical in local dev). Record this honestly as
        # MOCKED rather than SENT -- the audit trail must not claim delivery that
        # never happened. The approval/rejection action itself still succeeds.
        logger.info(f"SMTP not configured. Mock sending email to {to_email}")
        logger.info(f"Subject: {subject}\nBody: {body}")
        sent_status = "MOCKED"
        sent_timestamp = datetime.now()
    else:
        try:
            msg = MIMEMultipart()
            msg['From'] = formataddr((SENDER_NAME, settings.SMTP_USER))
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
            
            sent_status = "SENT"
            sent_timestamp = datetime.now()
            logger.info(f"Email sent successfully to {to_email}")
        except Exception as e:
            sent_status = "FAILED"
            error_message = str(e)
            logger.error(f"Failed to send email to {to_email}: {e}")

    # Update log in database
    if notification_id:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE EmailNotifications
                    SET sent_status = %s, sent_timestamp = %s, error_message = %s
                    WHERE id = %s
                """, (sent_status, sent_timestamp, error_message, notification_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update email log in DB: {e}")

    return {
        "notification_id": str(notification_id) if notification_id else None,
        "sent_status": sent_status,
        "error_message": error_message
    }

def retry_failed_email(conn, notification_id: str) -> dict:
    """
    Retries sending an email that previously failed.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT email_address, email_subject, email_content, sent_status
                FROM EmailNotifications
                WHERE id = %s
            """, (notification_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("Notification not found")
            
            email_address, subject, body, status = row
            
            if status == "SENT":
                return {"sent_status": "SENT", "error_message": "Email was already sent successfully"}
    except Exception as e:
        logger.error(f"Failed to query notification for retry: {e}")
        return {"sent_status": "FAILED", "error_message": f"Database error: {str(e)}"}

    settings = get_settings()
    sent_status = "SENT"
    error_message = None
    sent_timestamp = None

    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.info(f"SMTP not configured. Mock resending email to {email_address}")
        sent_status = "MOCKED"
        sent_timestamp = datetime.now()
    else:
        try:
            msg = MIMEMultipart()
            msg['From'] = formataddr((SENDER_NAME, settings.SMTP_USER))
            msg['To'] = email_address
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
            
            sent_status = "SENT"
            sent_timestamp = datetime.now()
            logger.info(f"Email resent successfully to {email_address}")
        except Exception as e:
            sent_status = "FAILED"
            error_message = str(e)
            logger.error(f"Failed to resend email to {email_address}: {e}")

    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE EmailNotifications
                SET sent_status = %s, sent_timestamp = %s, error_message = %s
                WHERE id = %s
            """, (sent_status, sent_timestamp, error_message, notification_id))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to update retry log in DB: {e}")

    return {
        "sent_status": sent_status,
        "error_message": error_message
    }

def send_admin_notification(registration_data: dict):
    settings = get_settings()
    
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.info(f"SMTP not configured. Mock admin notification.")
        return

    subject = "QuantumCare - New Registration Pending Approval"
    full_name = registration_data.get('full_name')
    email = registration_data.get('email')
    role = registration_data.get('role')
    
    body = f"A new user has registered and is pending approval.\n\nName: {full_name}\nEmail: {email}\nRole: {role}\n\nPlease log in to the administrator dashboard to review."
    
    try:
        msg = MIMEMultipart()
        msg['From'] = formataddr((SENDER_NAME, settings.SMTP_USER))
        msg['To'] = settings.ADMIN_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Admin notification sent successfully")
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")
