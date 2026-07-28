import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base
class OperationalIncident(Base):
    __tablename__="operational_incidents"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); property_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id"),nullable=False,index=True); incident_number:Mapped[str]=mapped_column(String(40),unique=True); title:Mapped[str]=mapped_column(String(180)); description:Mapped[str|None]=mapped_column(Text); incident_type:Mapped[str]=mapped_column(String(50),default="unknown"); status:Mapped[str]=mapped_column(String(20),default="detected",index=True); severity:Mapped[str]=mapped_column(String(20),default="unknown",index=True); priority:Mapped[str]=mapped_column(String(4),default="P3"); guest_impact_level:Mapped[str]=mapped_column(String(20),default="unknown"); revenue_impact_level:Mapped[str]=mapped_column(String(20),default="unknown"); incident_commander_id:Mapped[str|None]=mapped_column(String); created_by:Mapped[str]=mapped_column(String); detected_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default="now()",nullable=False); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default="now()",nullable=False)
class OperationalIncidentSource(Base):
    __tablename__="operational_incident_sources"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); incident_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("operational_incidents.id",ondelete="CASCADE"),index=True); source_type:Mapped[str]=mapped_column(String(40)); source_entity_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True)); relationship_type:Mapped[str]=mapped_column(String(30),default="related")
class IncidentParticipant(Base):
    __tablename__="incident_participants"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); incident_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("operational_incidents.id",ondelete="CASCADE"),index=True); user_id:Mapped[str]=mapped_column(String); participant_role:Mapped[str]=mapped_column(String(30)); active:Mapped[bool]=mapped_column(default=True,server_default="true")
class IncidentTask(Base):
    __tablename__="incident_tasks"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); incident_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("operational_incidents.id",ondelete="CASCADE"),index=True); title:Mapped[str]=mapped_column(String(180)); status:Mapped[str]=mapped_column(String(20),default="open",index=True); assigned_user_id:Mapped[str|None]=mapped_column(String); due_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); output_summary:Mapped[str|None]=mapped_column(Text)
class IncidentTimelineEntry(Base):
    __tablename__="incident_timeline_entries"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); incident_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("operational_incidents.id",ondelete="CASCADE"),index=True); entry_type:Mapped[str]=mapped_column(String(30)); title:Mapped[str]=mapped_column(String(180)); summary:Mapped[str|None]=mapped_column(Text); actor_user_id:Mapped[str|None]=mapped_column(String); occurred_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default="now()",nullable=False)
