from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.models.device import Device
from app.models.user import User
from app.schemas.ticket import TicketCreate
from app.services.audit_service import create_audit_log
from app.schemas.ticket import TicketCreate, TicketUpdate

def create_ticket(
    db: Session,
    ticket: TicketCreate,
    current_user: User
):
    if ticket.device_id is not None and not db.query(Device).filter(Device.id == ticket.device_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    new_ticket = Ticket(
        title=ticket.title,
        description=ticket.description,
        priority=ticket.priority,
        status="Open",
        reported_by=current_user.id,
        assigned_to=None,
        device_id=ticket.device_id,
    )

    db.add(new_ticket)
    db.flush()

    create_audit_log(
        db=db,
        actor=current_user.username,
        action="CREATE_TICKET",
        entity_type="Ticket",
        entity_id=str(new_ticket.id),
        description=f"Created ticket '{new_ticket.title}'"
    )

    try:
        db.commit()
        db.refresh(new_ticket)
    except Exception:
        db.rollback()
        raise

    return new_ticket

def update_ticket(
    db: Session,
    ticket_id: str,
    ticket_data: TicketUpdate,
    current_user: User
):
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )

    update_data = ticket_data.model_dump(exclude_unset=True)

    if update_data.get("device_id") is not None and not db.query(Device).filter(Device.id == update_data["device_id"]).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    for key, value in update_data.items():
        setattr(ticket, key, value)

    create_audit_log(
        db=db,
        actor=current_user.username,
        action="UPDATE_TICKET",
        entity_type="Ticket",
        entity_id=str(ticket.id),
        description=f"Updated ticket '{ticket.title}'"
    )

    try:
        db.commit()
        db.refresh(ticket)
    except Exception:
        db.rollback()
        raise

    return ticket

def delete_ticket(
    db: Session,
    ticket_id: str,
    current_user: User
):
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )

    title = ticket.title
    ticket_id_value = str(ticket.id)

    db.delete(ticket)

    create_audit_log(
        db=db,
        actor=current_user.username,
        action="DELETE_TICKET",
        entity_type="Ticket",
        entity_id=ticket_id_value,
        description=f"Deleted ticket '{title}'"
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Ticket deleted successfully"
    }

def assign_ticket(
    db: Session,
    ticket_id: str,
    assigned_to: str,
    current_user: User
):
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )

    assignee = db.query(User).filter(
        User.id == assigned_to
    ).first()

    if not assignee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assigned user not found"
        )

    if not assignee.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive users cannot be assigned tickets")

    if assignee.role not in ["admin", "technician"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tickets can only be assigned to an admin or technician"
        )

    ticket.assigned_to = assignee.id
    ticket.status = "In Progress"

    create_audit_log(
        db=db,
        actor=current_user.username,
        action="ASSIGN_TICKET",
        entity_type="Ticket",
        entity_id=str(ticket.id),
        description=(
            f"Assigned ticket '{ticket.title}' "
            f"to {assignee.username}"
        )
    )

    try:
        db.commit()
        db.refresh(ticket)
    except Exception:
        db.rollback()
        raise

    return ticket

def close_ticket(
    db: Session,
    ticket_id: str,
    current_user: User
):
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )

    ticket.status = "Closed"

    create_audit_log(
        db=db,
        actor=current_user.username,
        action="CLOSE_TICKET",
        entity_type="Ticket",
        entity_id=str(ticket.id),
        description=f"Closed ticket '{ticket.title}'"
    )

    try:
        db.commit()
        db.refresh(ticket)
    except Exception:
        db.rollback()
        raise

    return ticket
