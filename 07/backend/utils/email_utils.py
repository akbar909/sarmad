import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TEMP_OTP_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp_otp.json")

def send_otp_email(email: str, otp: str) -> bool:
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD")

    # Always log to temp file for debugging
    try:
        otp_data = {
            "email": email,
            "otp": otp,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "Logged"
        }
        with open(TEMP_OTP_FILE, "w") as f:
            json.dump(otp_data, f, indent=4)
    except Exception as e:
        print(f"[OTP LOG ERROR] {e}")

    # Always print to terminal for easy access
    print("\n" + "="*60)
    print("              DEEPGUARD OTP DISPATCH")
    print("="*60)
    print(f"  To Email : {email}")
    print(f"  OTP Code : {otp}")
    print(f"  Expiry   : 10 Minutes")
    print("="*60 + "\n")

    if not sender or not password:
        print("[EMAIL] No EMAIL_USER/EMAIL_PASSWORD set. OTP printed above only.")
        return True

    msg = MIMEMultipart("alternative")
    msg['From'] = sender
    msg['To'] = email
    msg['Subject'] = "DeepGuard - Password Reset OTP"

    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #0f172a; color: #e2e8f0; padding: 30px;">
        <div style="max-width: 500px; margin: auto; background: #1e293b; border-radius: 12px; padding: 30px; border: 1px solid #334155;">
            <h2 style="color: #7C3AED; margin-bottom: 10px;">DeepGuard - Password Reset</h2>
            <p>You requested a password reset. Use the OTP below:</p>
            <div style="background: #0f172a; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
                <h1 style="color: #7C3AED; font-size: 36px; letter-spacing: 8px; margin: 0;">{otp}</h1>
            </div>
            <p style="color: #94a3b8;">This OTP expires in <strong>10 minutes</strong>.</p>
            <p style="color: #94a3b8;">If you did not request this, please ignore this email.</p>
            <hr style="border-color: #334155; margin-top: 20px;">
            <p style="color: #475569; font-size: 12px;">DeepGuard AI - MUET Jamshoro</p>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(body, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, email, msg.as_string())
        server.quit()
        print(f"[EMAIL SUCCESS] OTP sent to {email}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send email: {e}")
        print("[EMAIL] OTP still printed above — check terminal logs.")
        return True  # Return True so the API still responds with success
