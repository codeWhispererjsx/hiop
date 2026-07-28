import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base
class ConfigurationKnownHost(Base):
    __tablename__="configuration_known_hosts"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); property_id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id",ondelete="CASCADE"),nullable=False,index=True); hostname:Mapped[str]=mapped_column(String(255),nullable=False); ip_address:Mapped[str|None]=mapped_column(String(64)); port:Mapped[int]=mapped_column(default=22); key_type:Mapped[str|None]=mapped_column(String(30)); fingerprint:Mapped[str]=mapped_column(String(255),nullable=False); trust_status:Mapped[str]=mapped_column(String(20),default="pending",server_default="pending"); approved_by:Mapped[str|None]=mapped_column(String); approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default="now()",nullable=False); __table_args__=(Index("uq_known_host_endpoint","property_id","hostname","port","fingerprint",unique=True),)
class ConfigurationConnectionTestRun(Base):
    __tablename__="configuration_connection_test_runs"
    id:Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); property_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("properties.id"),index=True); assignment_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True)); device_id:Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("devices.id"),index=True); collector_type:Mapped[str]=mapped_column(String(30),default="mock"); status:Mapped[str]=mapped_column(String(20),default="passed"); safe_message:Mapped[str]=mapped_column(String(255),default="Collector foundation validated"); error_category:Mapped[str|None]=mapped_column(String(40)); triggered_by:Mapped[str|None]=mapped_column(String); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default="now()",nullable=False)
