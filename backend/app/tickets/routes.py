from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketResponse, TicketUpdate

router = APIRouter(
    prefix="/tickets",
    tags=["Tickets"]
)


@router.post("/", response_model=TicketResponse)

def create_ticket(
    ticket_data: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    new_ticket = Ticket(
        title=ticket_data.title,
        description=ticket_data.description,
        priority=ticket_data.priority,
        status="Open",
        reported_by=current_user.id,
        assigned_to=None
    )

    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    return new_ticket

@router.get("/", response_model=List[TicketResponse])
def get_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tickets = db.query(Ticket).all()

    return tickets


@router.get("/", response_model=List[TicketResponse])
def get_tickets(
    status_filter: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Ticket)

    if status_filter:
        query = query.filter(
            Ticket.status.ilike(status_filter)
        )

    if priority:
        query = query.filter(
            Ticket.priority.ilike(priority)
        )

    if search:
        query = query.filter(
            or_(
                Ticket.title.ilike(f"%{search}%"),
                Ticket.description.ilike(f"%{search}%")
            )
        )

    return query.all()


@router.put("/{ticket_id}", response_model=TicketResponse)
def update_ticket(
    ticket_id: str,
    ticket_data: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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

    for key, value in update_data.items():
        setattr(ticket, key, value)

    db.commit()
    db.refresh(ticket)

    return ticket

@router.patch("/{ticket_id}/assign", response_model=TicketResponse)
def assign_ticket(
    ticket_id: str,
    assigned_to: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin", "technician"])
    )
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

    if assignee.role not in ["admin", "technician"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tickets can only be assigned to an admin or technician"
        )

    ticket.assigned_to = assignee.id
    ticket.status = "In Progress"

    db.commit()
    db.refresh(ticket)

    return ticket

   
@router.patch("/{ticket_id}/close", response_model=TicketResponse)
def close_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin", "technician"])
    )
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

    db.commit()
    db.refresh(ticket)

    return ticket

@router.delete("/{ticket_id}")
def delete_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin"])
    )
):
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )

    db.delete(ticket)
    db.commit()

    return {
        "message": "Ticket deleted successfully"
    }