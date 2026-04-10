"""
SQLAlchemy ORM models for the Monitoring database.

The Monitoring Agent is the only component allowed to write here.
The Orchestration Agent has read-only access via dedicated MCP tools.
"""

from sqlalchemy import Column, String, Float, Integer, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Device(Base):
    __tablename__ = "devices"

    device_id              = Column(String, primary_key=True)
    ip                     = Column(String, nullable=False)
    status                 = Column(String, nullable=False, default="unknown")
    device_type            = Column(String, nullable=False, default="fixed")
    zone                   = Column(String, nullable=False, default="unknown")
    x                      = Column(Float,  nullable=False, default=0.0)
    y                      = Column(Float,  nullable=False, default=0.0)
    z                      = Column(Float,  nullable=False, default=0.0)
    last_seen              = Column(String)
    last_capabilities_pull = Column(String)

    services = relationship(
        "Service",
        back_populates="device",
        cascade="all, delete-orphan",
    )
    neighbors = relationship(
        "Neighbor",
        back_populates="device",
        cascade="all, delete-orphan",
    )


class Service(Base):
    __tablename__ = "services"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    device_id    = Column(String, ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False)
    name         = Column(String, nullable=False)
    protocol     = Column(String, nullable=False)
    details_json = Column(Text,   nullable=False, default="{}")

    device = relationship("Device", back_populates="services")


class Neighbor(Base):
    __tablename__ = "neighbors"
    __table_args__ = (
        UniqueConstraint("device_id", "neighbor_id", name="uq_device_neighbor"),
    )

    id          = Column(Integer, primary_key=True, autoincrement=True)
    device_id   = Column(String, ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False)
    neighbor_id = Column(String, nullable=False)

    device = relationship("Device", back_populates="neighbors")
