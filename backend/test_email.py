"""Verify SMTP configuration by sending a real test email.

Usage:
    python3 test_email.py                  # send to SMTP_USER (yourself)
    python3 test_email.py someone@x.com    # send to a specific address

Reads credentials from .env. Prints a clear diagnosis if Gmail rejects the login.
"""

import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from app.config import get_settings
from app.email_service import SENDER_NAME


def main() -> int:
    settings = get_settings()

    if not settings.SMTP_HOST or not settings.SMTP_USER:
        print("SMTP_HOST / SMTP_USER are not set in .env")
        return 1

    if not settings.SMTP_PASSWORD:
        print("SMTP_PASSWORD is empty in .env — email is running in MOCKED mode.")
        print("Generate a Gmail App Password at https://myaccount.google.com/apppasswords")
        print("then set SMTP_PASSWORD in backend/.env and re-run this script.")
        return 1

    recipient = sys.argv[1] if len(sys.argv) > 1 else settings.SMTP_USER

    print(f"Host      : {settings.SMTP_HOST}:{settings.SMTP_PORT}")
    print(f"From      : {settings.SMTP_USER}")
    print(f"To        : {recipient}")
    print("Connecting...")

    msg = MIMEMultipart()
    msg["From"] = formataddr((SENDER_NAME, settings.SMTP_USER))
    msg["To"] = recipient
    msg["Subject"] = "QuantumCare SMTP Test"
    msg.attach(
        MIMEText(
            "This is a test message from the QuantumCare backend.\n\n"
            "If you are reading this, approval and rejection emails will be "
            "delivered correctly.\n\nRegards,\nThe QuantumCare Team",
            "plain",
        )
    )

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        print(f"\nAUTHENTICATION FAILED: {exc.smtp_code} {exc.smtp_error!r}")
        print("\nMost likely causes:")
        print("  * SMTP_PASSWORD is the account password, not a 16-char App Password")
        print("  * 2-Step Verification is not enabled on the Google account")
        print("  * The App Password was revoked")
        return 1
    except Exception as exc:
        print(f"\nSEND FAILED: {type(exc).__name__}: {exc}")
        return 1

    print(f"\nSUCCESS — test email delivered to {recipient}. Check the inbox.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
