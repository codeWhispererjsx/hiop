from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.hierarchy import Organization, Property


class HospitalityService:
    def __init__(self, db: Session):
        self.db = db

    def organization(self, organization_id: UUID) -> Organization:
        row = self.db.get(Organization, organization_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
        return row

    def property(self, property_id: UUID) -> Property:
        row = self.db.get(Property, property_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
        return row

    def ensure_unique(self, model, name: str, code: str | None, current_id=None):
        query = self.db.query(model).filter(func.lower(model.name) == name.lower())
        if current_id:
            query = query.filter(model.id != current_id)
        if query.first():
            raise HTTPException(status.HTTP_409_CONFLICT, "A record with this name already exists")
        if code:
            query = self.db.query(model).filter(func.lower(model.code) == code.lower())
            if current_id:
                query = query.filter(model.id != current_id)
            if query.first():
                raise HTTPException(status.HTTP_409_CONFLICT, "A record with this code already exists")
