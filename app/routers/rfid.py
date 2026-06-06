from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import uuid

from app.core.database import get_db
from app.core.auth import require_role
from app.models import User, RFIDTag, RFIDStatus
from app.schemas import RFIDRequest, RFIDOut

router = APIRouter(prefix="/rfid", tags=["RFID"])

@router.post("/request", response_model=RFIDOut, status_code=201)
def request_rfid_tag(
    payload: RFIDRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("faculty"))
):
    existing = db.query(RFIDTag).filter(
        RFIDTag.faculty_id == current_user.id,
        RFIDTag.vehicle_number == payload.vehicle_number,
        RFIDTag.status.in_([RFIDStatus.pending, RFIDStatus.active])
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Active or pending request already exists for this vehicle")
    tag = RFIDTag(faculty_id=current_user.id, vehicle_number=payload.vehicle_number)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag

@router.get("/my-tags", response_model=list[RFIDOut])
def get_my_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("faculty"))
):
    return db.query(RFIDTag).filter(RFIDTag.faculty_id == current_user.id).all()

@router.get("/pending", response_model=list[RFIDOut])
def get_pending_rfid_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("hostel_superintendent"))
):
    return db.query(RFIDTag).filter(RFIDTag.status == RFIDStatus.pending).all()

@router.patch("/{tag_id}/approve", response_model=RFIDOut)
def approve_rfid_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("hostel_superintendent"))
):
    tag = db.query(RFIDTag).filter(RFIDTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="RFID request not found")
    if tag.status != RFIDStatus.pending:
        raise HTTPException(status_code=400, detail="Only pending requests can be approved")
    tag.tag_uid        = f"RFID-{uuid.uuid4().hex[:12].upper()}"
    tag.status         = RFIDStatus.active
    tag.approved_at    = datetime.now(timezone.utc)
    tag.approved_by_id = current_user.id
    db.commit()
    db.refresh(tag)
    return tag

@router.patch("/{tag_id}/revoke", response_model=RFIDOut)
def revoke_rfid_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("hostel_superintendent"))
):
    tag = db.query(RFIDTag).filter(RFIDTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="RFID tag not found")
    tag.status = RFIDStatus.revoked
    db.commit()
    db.refresh(tag)
    return tag
