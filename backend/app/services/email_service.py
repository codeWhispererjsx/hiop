import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr
from enum import Enum

from app.core.config import settings


class EmailDeliveryStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"


class EmailServiceError(Exception):
    def __init__(self, message: str, safe_message: str = None):
        super().__init__(message)
        self.safe_message = safe_message or message


def _send_email_raw(
    subject: str,
    body: str,
    recipient: str | None = None,
    max_retries: int = None
) -> dict:
    """
    Send email with configurable SMTP settings and bounded retries.
    
    Returns:
        dict with status, message, and delivery info
    """
    destination = recipient or settings.email_recipient
    
    # Check for new production email configuration
    use_new_config = bool(settings.smtp_host and settings.smtp_sender_address)
    
    # Fall back to legacy configuration for compatibility
    if not use_new_config:
        if not settings.email_address or not settings.email_password:
            return {
                "status": EmailDeliveryStatus.FAILED,
                "message": "Email delivery is not configured",
                "safe_message": "Email delivery is not configured"
            }
        smtp_host = "smtp.gmail.com"
        smtp_port = 465
        smtp_security = "SSL"
        smtp_username = settings.email_address
        smtp_password = settings.email_password
        sender_address = settings.email_address
        sender_name = "HIOP Notifications"
        connection_timeout = 15
        send_timeout = 30
        max_retries = max_retries or 3
        retry_backoff = 5
    else:
        # Use new production configuration
        smtp_host = settings.smtp_host
        smtp_port = settings.smtp_port
        smtp_security = settings.smtp_security
        smtp_username = settings.smtp_username
        smtp_password = settings.smtp_password
        sender_address = settings.smtp_sender_address
        sender_name = settings.smtp_sender_name
        connection_timeout = settings.smtp_connection_timeout
        send_timeout = settings.smtp_send_timeout
        max_retries = max_retries or settings.smtp_max_retries
        retry_backoff = settings.smtp_retry_backoff
    
    if not destination:
        return {
            "status": EmailDeliveryStatus.FAILED,
            "message": "An email recipient is not configured",
            "safe_message": "An email recipient is not configured"
        }

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((sender_name, sender_address))
    message["To"] = destination
    message.set_content(body)

    last_error = None
    
    for attempt in range(max_retries):
        try:
            if smtp_security.upper() == "SSL":
                with smtplib.SMTP_SSL(
                    smtp_host,
                    smtp_port,
                    timeout=connection_timeout,
                ) as smtp:
                    smtp.sendmail(sender_address, destination, message.as_string())
            elif smtp_security.upper() == "STARTTLS":
                with smtplib.SMTP(
                    smtp_host,
                    smtp_port,
                    timeout=connection_timeout,
                ) as smtp:
                    smtp.starttls()
                    if smtp_username and smtp_password:
                        smtp.login(smtp_username, smtp_password)
                    smtp.sendmail(sender_address, destination, message.as_string())
            else:  # NONE
                with smtplib.SMTP(
                    smtp_host,
                    smtp_port,
                    timeout=connection_timeout,
                ) as smtp:
                    if smtp_username and smtp_password:
                        smtp.login(smtp_username, smtp_password)
                    smtp.sendmail(sender_address, destination, message.as_string())
            
            return {
                "status": EmailDeliveryStatus.SENT,
                "message": "Email sent successfully",
                "attempts": attempt + 1
            }
            
        except smtplib.SMTPAuthenticationError as e:
            # Authentication failures are not retryable
            return {
                "status": EmailDeliveryStatus.FAILED,
                "message": f"SMTP authentication failed: {str(e)}",
                "safe_message": "SMTP authentication failed - check credentials",
                "attempts": attempt + 1
            }
        except smtplib.SMTPConnectError as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(retry_backoff * (attempt + 1))
                continue
            return {
                "status": EmailDeliveryStatus.FAILED,
                "message": f"SMTP connection failed: {str(e)}",
                "safe_message": "SMTP connection failed - check host and port",
                "attempts": attempt + 1
            }
        except smtplib.SMTPException as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(retry_backoff * (attempt + 1))
                continue
            return {
                "status": EmailDeliveryStatus.FAILED,
                "message": f"SMTP error: {str(e)}",
                "safe_message": "SMTP error occurred",
                "attempts": attempt + 1
            }
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(retry_backoff * (attempt + 1))
                continue
            return {
                "status": EmailDeliveryStatus.FAILED,
                "message": f"Email delivery failed: {str(e)}",
                "safe_message": "Email delivery failed",
                "attempts": attempt + 1
            }
    
    return {
        "status": EmailDeliveryStatus.FAILED,
        "message": f"Email delivery failed after {max_retries} attempts",
        "safe_message": "Email delivery failed after maximum retries",
        "attempts": max_retries
    }


def send_email(subject: str, body: str, recipient: str | None = None, max_retries: int = None) -> dict:
    """Deliver email and persist provider-neutral delivery health metadata."""
    result = _send_email_raw(subject, body, recipient, max_retries)
    try:
        from datetime import datetime, timezone
        from app.db.database import SessionLocal
        from app.models.system_health import NotificationDelivery
        destination = recipient or settings.email_recipient
        status_value = getattr(result.get("status"), "value", result.get("status", "failed"))
        db = SessionLocal()
        try:
            db.add(NotificationDelivery(notification_type="email", recipient=destination or "unconfigured", status=status_value, attempted_at=datetime.now(timezone.utc), delivered_at=datetime.now(timezone.utc) if status_value == "sent" else None, retry_count=max(0, int(result.get("attempts", 1))-1), error=None if status_value == "sent" else str(result.get("safe_message", "Delivery failed"))[:500]))
            db.commit()
        finally: db.close()
    except Exception:
        pass
    return result


def test_email_configuration() -> dict:
    """
    Test email configuration without sending a real email.
    
    Returns:
        dict with test results and configuration status
    """
    use_new_config = bool(settings.smtp_host and settings.smtp_sender_address)
    
    if use_new_config:
        return {
            "configured": True,
            "host": settings.smtp_host,
            "port": settings.smtp_port,
            "security": settings.smtp_security,
            "sender_address": settings.smtp_sender_address,
            "sender_name": settings.smtp_sender_name,
            "has_credentials": bool(settings.smtp_username and settings.smtp_password),
            "connection_timeout": settings.smtp_connection_timeout,
            "max_retries": settings.smtp_max_retries,
            "status": "CONFIGURED"
        }
    elif settings.email_address and settings.email_password:
        return {
            "configured": True,
            "host": "smtp.gmail.com",
            "port": 465,
            "security": "SSL",
            "sender_address": settings.email_address,
            "sender_name": "HIOP Notifications",
            "has_credentials": True,
            "connection_timeout": 15,
            "max_retries": 3,
            "status": "LEGACY_GMAIL",
            "warning": "Using legacy Gmail configuration - migrate to production SMTP settings"
        }
    else:
        return {
            "configured": False,
            "status": "NOT_CONFIGURED",
            "message": "Email delivery is not configured"
        }
