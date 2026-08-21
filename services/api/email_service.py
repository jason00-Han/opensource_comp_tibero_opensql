import os
import smtplib
from email.message import EmailMessage


def send_invitation(email: str, join_url: str) -> bool:
    host = os.getenv("SMTP_HOST")
    if not host:
        return False
    message = EmailMessage()
    message["Subject"] = "Tibero Doc 워크스페이스 초대"
    message["From"] = os.getenv("SMTP_FROM", "noreply@tibero-doc.local")
    message["To"] = email
    message.set_content(f"Tibero Doc에 초대되었습니다.\n\n{join_url}\n\n이 링크는 7일 동안 한 번만 사용할 수 있습니다.")
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as smtp:
        if os.getenv("SMTP_TLS", "true").lower() == "true":
            smtp.starttls()
        if os.getenv("SMTP_USERNAME"):
            smtp.login(os.environ["SMTP_USERNAME"], os.environ.get("SMTP_PASSWORD", ""))
        smtp.send_message(message)
    return True
