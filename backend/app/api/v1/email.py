from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.services.email_service import send_email, test_email_configuration

router = APIRouter(prefix="/email", tags=["Email"])


@router.get("/test-configuration")
def test_email_config(
    current_user: User = Depends(require_roles(["admin", "platformadmin"]))
):
    """Test email configuration status without sending an email"""
    return test_email_configuration()


@router.post("/send-test")
def send_test_email(
    current_user: User = Depends(require_roles(["admin", "platformadmin"])),
    db: Session = Depends(get_db)
):
    """Send a test email to verify configuration"""
    result = send_email(
        subject="HIOP Email Configuration Test",
        body="This is a test email from HIOP to verify that your email configuration is working correctly. If you received this, your email settings are properly configured.",
        recipient=current_user.email
    )
    
    if result["status"] == "sent":
        return {
            "success": True,
            "message": "Test email sent successfully",
            "attempts": result.get("attempts", 1)
        }
    else:
        return {
            "success": False,
            "message": result.get("safe_message", "Test email failed"),
            "attempts": result.get("attempts", 1)
        }