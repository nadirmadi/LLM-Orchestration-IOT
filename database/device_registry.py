"""
device_registry.py — Clean CRUD layer over the Monitoring database.

This module is the SINGLE entry point used by the MCP tools to read or
write the deployment state. The Monitoring Agent is the only consumer
that has write access; the Orchestration Agent's MCP tools must call
read-only functions only.

Convention for `device_dict` (the format the Monitoring Agent will return
to the Orchestration Agent in natural-language conversations):

    {
      "device_id" : "esp32-001",
      "ip"        : "192.168.1.42",
      "status"    : "light_sleep",
      "device_type": "fixed",
      "location"  : { "zone": "corridor", "x": 3.5, "y": 1.2, "z": 0.0 },
      "services"  : [
          { "name": "pir", "protocol": "MQTT",
            "details": { "detection_range_m": 5 } },
          { "name": "imu", "protocol": "MQTT",
            "details": { "fall_detection": true } }
      ],
      "neighbors" : ["esp32-002", "esp32-003"],
      "last_seen" : "2026-04-08T10:23:00+00:00"
    }
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, select, or_
from sqlalchemy.orm import sessionmaker, Session

from .models import Base, Device, Service, Neighbor


# ─────────────────────────────────────────────────────────────────
# Engine & session setup
# ─────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "/data/monitoring.db")

# Make sure the parent directory exists (useful in Docker)
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create tables if they do not exist."""
    Base.metadata.create_all(bind=engine)
    print(f"[DB] Schema ready at {DB_PATH}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────
# Serialization helpers
# ─────────────────────────────────────────────────────────────────
def device_to_dict(d: Device) -> dict:
    """Convert a Device ORM row into the canonical JSON shape that
    the Monitoring Agent returns to the Orchestration Agent."""
    return {
        "device_id":    d.device_id,
        "ip":           d.ip,
        "status":       d.status,
        "device_type":  d.device_type,
        "location":     {"zone": d.zone, "x": d.x, "y": d.y, "z": d.z},
        "services": [
            {
                "name":     s.name,
                "protocol": s.protocol,
                "details":  json.loads(s.details_json or "{}"),
            }
            for s in d.services
        ],
        "neighbors":             [n.neighbor_id for n in d.neighbors],
        "last_seen":             d.last_seen,
        "last_capabilities_pull": d.last_capabilities_pull,
    }


# ─────────────────────────────────────────────────────────────────
# Read operations  (used by both Monitoring and Orchestration agents)
# ─────────────────────────────────────────────────────────────────
def get_device(device_id: str) -> Optional[dict]:
    with SessionLocal() as db:
        d = db.get(Device, device_id)
        return device_to_dict(d) if d else None


def get_all_devices() -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(select(Device)).scalars().all()
        return [device_to_dict(d) for d in rows]


def query_devices(
    zone:        Optional[str] = None,
    service:     Optional[str] = None,
    status:      Optional[str] = None,
    device_type: Optional[str] = None,
) -> list[dict]:
    """Filter devices by combinations of zone / service / status / type.
    All filters are optional and combined with AND."""
    with SessionLocal() as db:
        stmt = select(Device)
        if zone is not None:
            stmt = stmt.where(Device.zone == zone)
        if status is not None:
            stmt = stmt.where(Device.status == status)
        if device_type is not None:
            stmt = stmt.where(Device.device_type == device_type)

        rows = db.execute(stmt).scalars().all()

        # Filter by service name in Python so we keep the relationship loaded
        if service is not None:
            rows = [d for d in rows if any(s.name == service for s in d.services)]

        return [device_to_dict(d) for d in rows]


# ─────────────────────────────────────────────────────────────────
# Write operations  (Monitoring Agent ONLY)
# ─────────────────────────────────────────────────────────────────
def upsert_device(payload: dict) -> dict:
    """Insert a new device or update an existing one from a payload
    matching the canonical JSON shape (see module docstring).

    This is what `discover_network` and `get_capabilities` will end up
    calling once they have pulled fresh data from an ESP32.
    """
    with SessionLocal() as db:
        device_id = payload["device_id"]
        d = db.get(Device, device_id)
        if d is None:
            d = Device(device_id=device_id)
            db.add(d)

        d.ip          = payload.get("ip", d.ip or "0.0.0.0")
        d.status      = payload.get("status", d.status or "unknown")
        d.device_type = payload.get("device_type", d.device_type or "fixed")

        loc = payload.get("location") or {}
        d.zone = loc.get("zone", d.zone or "unknown")
        d.x    = float(loc.get("x", d.x or 0.0))
        d.y    = float(loc.get("y", d.y or 0.0))
        d.z    = float(loc.get("z", d.z or 0.0))

        d.last_seen              = now_iso()
        d.last_capabilities_pull = now_iso()

        # Replace services
        d.services.clear()
        for s in payload.get("services", []):
            d.services.append(
                Service(
                    name=s["name"],
                    protocol=s.get("protocol", "HTTP"),
                    details_json=json.dumps(s.get("details", {})),
                )
            )

        # Replace neighbors. Accept both shapes:
        #   - bare ID strings:        ["esp32-002", "esp32-003"]
        #   - dicts from firmware:    [{"device_id": "esp32-002", "ip": "..."}]
        # We only persist the ID; the IP carried alongside is consumed by
        # discover_network at recursion time and is not stored here.
        d.neighbors.clear()
        for n in payload.get("neighbors", []):
            if isinstance(n, dict):
                nid = n.get("device_id")
            else:
                nid = n
            if nid:
                d.neighbors.append(Neighbor(neighbor_id=nid))

        db.commit()
        db.refresh(d)
        return device_to_dict(d)


def update_device_status(device_id: str, new_status: str) -> Optional[dict]:
    """Light update used after a wake_up / put_to_sleep / heartbeat."""
    with SessionLocal() as db:
        d = db.get(Device, device_id)
        if d is None:
            return None
        d.status    = new_status
        d.last_seen = now_iso()
        db.commit()
        db.refresh(d)
        return device_to_dict(d)


def delete_device(device_id: str) -> bool:
    with SessionLocal() as db:
        d = db.get(Device, device_id)
        if d is None:
            return False
        db.delete(d)
        db.commit()
        return True
