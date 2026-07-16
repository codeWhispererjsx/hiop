from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List
from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketResponse, TicketUpdate
from app.services.ticket_service import (
    create_ticket as create_ticket_service,
    update_ticket as update_ticket_service,
    delete_ticket as delete_ticket_service,
    assign_ticket as assign_ticket_service,
    close_ticket as close_ticket_service,
)

router = APIRouter(
    prefix="/tickets",
    tags=["Tickets"]
)


@router.post("/", response_model=TicketResponse)
def create_ticket(
    ticket: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return create_ticket_service(
        db=db,
        ticket=ticket,
        current_user=current_user
    )

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

    return query.order_by(Ticket.created_at.desc()).all()


@router.get("/{ticket_id}", response_model=TicketResponse)
def get_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.put("/{ticket_id}", response_model=TicketResponse)
def update_ticket(
    ticket_id: str,
    ticket_data: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return update_ticket_service(
        db=db,
        ticket_id=ticket_id,
        ticket_data=ticket_data,
        current_user=current_user
    )


@router.patch("/{ticket_id}/assign", response_model=TicketResponse)
def assign_ticket(
    ticket_id: str,
    assigned_to: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin", "technician"])
    )
):
    return assign_ticket_service(
        db=db,
        ticket_id=ticket_id,
        assigned_to=assigned_to,
        current_user=current_user
    )

   
@router.patch("/{ticket_id}/close", response_model=TicketResponse)
def close_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin", "technician"])
    )
):
    return close_ticket_service(
        db=db,
        ticket_id=ticket_id,
        current_user=current_user
    )


@router.delete("/{ticket_id}")
def delete_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin"])
    )
):
    return delete_ticket_service(
        db=db,
        ticket_id=ticket_id,
        current_user=current_user
    )
