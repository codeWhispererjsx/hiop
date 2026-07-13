import smtplib
from email.message import EmailMessage


def send_email(
    subject: str,
    body: str,
    recipient: str,
    sender: str,
    password: str
):
    message = EmailMessage()

    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient

    message.set_content(body)

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465
    ) as smtp:

        smtp.login(
            sender,
            password
        )

        smtp.send_message(message)