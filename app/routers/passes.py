from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import pyotp

from app.core.database import get_db
from app.core.auth import get_current_user, require_role
from app.core.rules import can_create_pass, get_approver_role, is_auto_approved
from app.models import User, Pass, TOTPSecret, PassType, PassStatus, UserRole
from app.schemas import PassCreate, PassOut, PassStatusUpdate

router = APIRouter(prefix="/passes", tags=["Passes"])


@router.post("/", response_model=PassOut, status_code=201)
def apply_for_pass(
    payload: PassCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not can_create_pass(current_user.role, payload.pass_type):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{current_user.role.value}' cannot create a '{payload.pass_type.value}' pass"
        )

    if payload.valid_until <= payload.valid_from:
        raise HTTPException(status_code=400, detail="valid_until must be after valid_from")

    auto = is_auto_approved(payload.pass_type)

    new_pass = Pass(
        pass_type=payload.pass_type,
        holder_name=payload.holder_name,
        holder_phone=payload.holder_phone,
        holder_email=payload.holder_email,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        created_by_id=current_user.id,
        status=PassStatus.approved if auto else PassStatus.pending,
        approved_by_id=current_user.id if auto else None
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

    required_role = get_approver_role(pass_.pass_type)
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


@router.patch("/{pass_id}/revoke", response_model=PassOut)
def revoke_pass(
    pass_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("hostel_superintendent", "conference_supervisor"))
):
    """
    Revoke an approved pass - e.g. visitor blacklisted or pass issued by mistake.
    Only the relevant supervisor can revoke.
    """
    pass_ = db.query(Pass).filter(Pass.id == pass_id).first()
    if not pass_:
        raise HTTPException(status_code=404, detail="Pass not found")

    required_role = get_approver_role(pass_.pass_type)
    if current_user.role != required_role:
        raise HTTPException(
            status_code=403,
            detail=f"Only a '{required_role.value}' can revoke this pass type"
        )

    if pass_.status == PassStatus.revoked:
        raise HTTPException(status_code=400, detail="Pass is already revoked")

    pass_.status = PassStatus.revoked
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


@router.get("/{pass_id}/timeline")
def get_pass_timeline(
    pass_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns a chronological audit trail for a pass.
    Stitches together data from passes and gate_logs tables.
    No new tables needed - all data already exists.
    """
    pass_ = db.query(Pass).filter(Pass.id == pass_id).first()
    if not pass_:
        raise HTTPException(status_code=404, detail="Pass not found")

    events = []

    # Event 1: creation
    creator = db.query(User).filter(User.id == pass_.created_by_id).first()
    events.append({
        "time": pass_.created_at,
        "event": f"Pass created by {creator.name} ({creator.role.value})",
        "type": "created"
    })

    # Event 2: approval or rejection
    if pass_.approved_by_id and pass_.status in [PassStatus.approved, PassStatus.rejected]:
        approver = db.query(User).filter(User.id == pass_.approved_by_id).first()
        events.append({
            "time": pass_.updated_at,
            "event": f"Pass {pass_.status.value} by {approver.name} ({approver.role.value})",
            "type": pass_.status.value
        })

    # Event 3: revocation
    if pass_.status == PassStatus.revoked:
        events.append({
            "time": pass_.updated_at,
            "event": "Pass revoked",
            "type": "revoked"
        })

    # Events 4+: every gate scan attempt
    for log in pass_.gate_logs:
        scanner = db.query(User).filter(User.id == log.scanned_by_id).first()
        suffix = f" - {log.failure_reason}" if log.failure_reason else ""
        events.append({
            "time": log.timestamp,
            "event": f"Gate scan by {scanner.name} - {log.result.value.upper()}{suffix}",
            "type": log.result.value
        })

    # Sort by time
    events.sort(key=lambda e: e["time"])

    return events


@router.get("/{pass_id}/timeline")
def get_pass_timeline(
    pass_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    pass_ = db.query(Pass).filter(Pass.id == pass_id).first()
    if not pass_:
        raise HTTPException(status_code=404, detail="Pass not found")

    events = []

    creator = db.query(User).filter(User.id == pass_.created_by_id).first()
    events.append({"time": pass_.created_at, "event": f"Pass created by {creator.name} ({creator.role.value})", "type": "created"})

    if pass_.approved_by_id and pass_.status in [PassStatus.approved, PassStatus.rejected]:
        approver = db.query(User).filter(User.id == pass_.approved_by_id).first()
        events.append({"time": pass_.updated_at, "event": f"Pass {pass_.status.value} by {approver.name} ({approver.role.value})", "type": pass_.status.value})

    if pass_.status == PassStatus.revoked:
        events.append({"time": pass_.updated_at, "event": "Pass revoked", "type": "revoked"})

    for log in pass_.gate_logs:
        scanner = db.query(User).filter(User.id == log.scanned_by_id).first()
        suffix = f" - {log.failure_reason}" if log.failure_reason else ""
        events.append({"time": log.timestamp, "event": f"Gate scan by {scanner.name} - {log.result.value.upper()}{suffix}", "type": log.result.value})

    events.sort(key=lambda e: e["time"])
    return events
