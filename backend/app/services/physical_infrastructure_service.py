from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.hierarchy import Building, Floor, Zone, Property

class PhysicalInfrastructureService:
    def __init__(self, db: Session): self.db = db
    def get(self, model, ident: UUID):
        row = self.db.get(model, ident)
        if not row: raise HTTPException(404, f"{model.__name__} not found")
        return row
    def ensure_unique(self, model, name: str, parent_field: str, parent_id: UUID, ident=None):
        q = self.db.query(model).filter(model.name.ilike(name.strip()), getattr(model, parent_field) == parent_id)
        if ident: q = q.filter(model.id != ident)
        if q.first(): raise HTTPException(409, "An item with this name already exists in the parent")
    def validate_parent(self, model, ident): return self.get(model, ident)
