from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import pyotp

from app.core.database import get_db
from app.core.auth import get_current_user, require_role
from app.models import User, Pass, TOTPSecret, PassType, PassStatus, UserRole
from app.schemas import PassCreate, PassOut, PassStatusUpdate

router = APIRouter(prefix="/passes", tags=["Passes"])

def validate_pass_creation_permission(user: User, pass_type: PassType):
    allowed = {
        UserRole.student:               [PassType.single_day_visitor],
        UserRole.faculty:               [PassType.conference_temp],
        UserRole.hostel_superintendent: [PassType.permanent, PassType.single_day_visitor],
        UserRole.conference_supervisor: [PassType.permanent, PassType.conference_temp],
    }
    if pass_type not in allowed.get(user.role, []):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{user.role.value}' cannot create a '{pass_type.value}' pass"
        )

def get_required_approver_role(pass_type: PassType):
    if pass_type == PassType.single_day_visitor:
        return UserRole.hostel_superintendent
    if pass_type == PassType.conference_temp:
        return UserRole.conference_supervisor
    return None

@router.post("/", response_model=PassOut, status_code=201)
def apply_for_pass(
    payload: PassCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    validate_pass_creation_permission(current_user, payload.pass_type)
    if payload.valid_until <= payload.valid_from:
        raise HTTPException(status_code=400, detail="valid_until must be after valid_from")
    new_pass = Pass(
        pass_type=payload.pass_type,
        holder_name=payload.holder_name,
        holder_phone=payload.holder_phone,
        holder_email=payload.holder_email,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        created_by_id=current_user.id,
        status=PassStatus.approved if payload.pass_type == PassType.permanent else PassStatus.pending,
        approved_by_id=current_user.id if payload.pass_type == PassType.permanent else None
    )
    db.add(new_pass)
    db.commit()
    db.refresh(new_pass)
    if payload.pass_type in [PassType.conference_temp, PassType.single_day_visitor]:
        totp_entry = TOTPSecret(pass_id=new_pass.id, secret_key=pyotp.random_base32())
        db.add(totp_entry)
        db.commit()
    return new_pass

@router.get("/", response_model=list[PassOut])
def list_passes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role in [UserRole.student, UserRole.faculty]:
        return db.query(Pass).filter(Pass.created_by_id == current_user.id).all()
    if current_user.role == UserRole.hostel_superintendent:
        return db.query(Pass).filter(Pass.pass_type == PassType.single_day_visitor).all()
    if current_user.role == UserRole.conference_supervisor:
        return db.query(Pass).filter(Pass.pass_type == PassType.conference_temp).all()
    if current_user.role == UserRole.gate_security:
        return db.query(Pass).filter(Pass.status == PassStatus.approved).all()
    return []

@router.patch("/{pass_id}/status", response_model=PassOut)
def update_pass_status(
    pass_id: int,
    payload: PassStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    pass_ = db.query(Pass).filter(Pass.id == pass_id).first()
    if not pass_:
        raise HTTPException(status_code=404, detail="Pass not found")
    if pass_.status != PassStatus.pending:
        raise HTTPException(status_code=400, detail="Only pending passes can be updated")
    required_role = get_required_approver_role(pass_.pass_type)
    if current_user.role != required_role:
        raise HTTPException(
            status_code=403,
            detail=f"Only a '{required_role.value}' can approve this pass type"
        )
    pass_.status = payload.status
    pass_.approved_by_id = current_user.id
    pass_.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pass_)
    return pass_

@router.get("/{pass_id}/qr-payload")
def get_qr_payload(
    pass_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    pass_ = db.query(Pass).filter(Pass.id == pass_id).first()
    if not pass_:
        raise HTTPException(status_code=404, detail="Pass not found")
    if pass_.status != PassStatus.approved:
        raise HTTPException(status_code=400, detail="Pass is not approved yet")
    if not pass_.totp_secret:
        raise HTTPException(status_code=400, detail="No TOTP secret for this pass")
    totp = pyotp.TOTP(pass_.totp_secret.secret_key)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    return {
        "pass_id": pass_id,
        "holder_name": pass_.holder_name,
        "totp_code": totp.now(),
        "seconds_remaining": 30 - (now_ts % 30),
        "valid_until": pass_.valid_until
    }
