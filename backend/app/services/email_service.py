import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_email(
    subject: str,
    body: str,
    recipient: str | None = None
):
    message = EmailMessage()

    message["Subject"] = subject
    message["From"] = settings.email_address
    message["To"] = recipient or settings.email_recipient

    message.set_content(body)

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465
    ) as smtp:
        smtp.login(
            settings.email_address,
            settings.email_password
        )

        smtp.send_message(message)