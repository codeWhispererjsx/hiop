import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings


def send_email(
    subject: str,
    body: str,
    recipient: str | None = None
):
    destination = recipient or settings.email_recipient
    if not settings.email_address or not settings.email_password:
        raise RuntimeError("Email delivery is not configured")
    if not destination:
        raise RuntimeError("An email recipient is not configured")

    message = EmailMessage()

    message["Subject"] = subject
    message["From"] = formataddr(("HIOP Notifications", settings.email_address))
    message["To"] = destination

    message.set_content(body)

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        timeout=15,
    ) as smtp:
        smtp.login(
            settings.email_address,
            settings.email_password
        )

        smtp.send_message(message)
