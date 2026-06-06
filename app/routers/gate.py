from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import pyotp

from app.core.database import get_db
from app.core.auth import get_current_user, require_role
from app.models import User, Pass, RFIDTag, GateLog, PassStatus, RFIDStatus, GateScanResult
from app.schemas import TOTPVerifyRequest, RFIDScanRequest, GateLogOut

router = APIRouter(prefix="/gate", tags=["Gate Security"])

def log_scan(db, pass_id, scanned_by_id, result, reason=None):
    db.add(GateLog(pass_id=pass_id, scanned_by_id=scanned_by_id, result=result, failure_reason=reason))
    db.commit()

@router.post("/verify-totp", response_model=GateLogOut)
def verify_totp(
    payload: TOTPVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("gate_security"))
):
    pass_ = db.query(Pass).filter(Pass.id == payload.pass_id).first()
    if not pass_:
        raise HTTPException(status_code=404, detail="Pass not found")
    now = datetime.now(timezone.utc)
    if pass_.status != PassStatus.approved:
        log_scan(db, pass_.id, current_user.id, GateScanResult.failure, "Pass not approved")
        raise HTTPException(status_code=400, detail="Pass is not approved")
    valid_from  = pass_.valid_from.replace(tzinfo=timezone.utc)  if pass_.valid_from.tzinfo  is None else pass_.valid_from
    valid_until = pass_.valid_until.replace(tzinfo=timezone.utc) if pass_.valid_until.tzinfo is None else pass_.valid_until
    if not (valid_from <= now <= valid_until):
        log_scan(db, pass_.id, current_user.id, GateScanResult.failure, "Outside validity window")
        raise HTTPException(status_code=400, detail="Pass is not currently valid")
    if not pass_.totp_secret:
        raise HTTPException(status_code=400, detail="No TOTP secret found")
    if not pyotp.TOTP(pass_.totp_secret.secret_key).verify(payload.totp_code, valid_window=1):
        log_scan(db, pass_.id, current_user.id, GateScanResult.failure, "Invalid TOTP code")
        raise HTTPException(status_code=400, detail="Invalid or expired QR code")
    entry = GateLog(pass_id=pass_.id, scanned_by_id=current_user.id, result=GateScanResult.success)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry

@router.post("/scan-rfid")
def scan_rfid(
    payload: RFIDScanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("gate_security"))
):
    tag = db.query(RFIDTag).filter(RFIDTag.tag_uid == payload.tag_uid).first()
    if not tag:
        return {"result": "denied", "reason": "Unknown RFID tag"}
    if tag.status != RFIDStatus.active:
        return {"result": "denied", "reason": f"Tag is {tag.status.value}"}
    return {
        "result": "granted",
        "faculty_name": tag.faculty.name,
        "faculty_email": tag.faculty.email,
        "vehicle_number": tag.vehicle_number
    }

@router.get("/logs", response_model=list[GateLogOut])
def get_gate_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("gate_security", "hostel_superintendent", "conference_supervisor"))
):
    return db.query(GateLog).order_by(GateLog.timestamp.desc()).limit(200).all()
