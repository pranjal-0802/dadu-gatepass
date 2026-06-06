from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import pyotp
import random

from app.core.database import get_db
from app.core.auth import get_current_user, require_role
from app.core.rules import can_create_pass, get_approver_role, is_auto_approved
from app.models import User, Pass, TOTPSecret, OTPRequest, PassType, PassStatus, UserRole
from app.schemas import PassCreate, PassOut, PassStatusUpdate

router = APIRouter(prefix="/passes", tags=["Passes"])


def validate_phone(phone: str):
    if not phone or not phone.isdigit() or len(phone) != 10:
        raise HTTPException(status_code=400, detail="Phone number must be exactly 10 digits")


def validate_dates(valid_from: datetime, valid_until: datetime, pass_type: PassType):
    now = datetime.now(timezone.utc)

    # make naive datetimes timezone aware
    if valid_from.tzinfo is None:
        valid_from = valid_from.replace(tzinfo=timezone.utc)
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)

    if valid_from < now:
        raise HTTPException(status_code=400, detail="valid_from cannot be in the past")

    if valid_until <= valid_from:
        raise HTTPException(status_code=400, detail="valid_until must be after valid_from")

    if pass_type == PassType.single_day_visitor:
        if valid_from.date() != valid_until.date():
            raise HTTPException(status_code=400, detail="Single day visitor pass must start and end on the same day")


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

    # Phone required and validated for temporary passes
    if payload.pass_type in [PassType.single_day_visitor, PassType.conference_temp]:
        validate_phone(payload.holder_phone)

    validate_dates(payload.valid_from, payload.valid_until, payload.pass_type)

    auto = is_auto_approved(payload.pass_type)

    # Temporary passes start as pending_otp until visitor verifies phone
    needs_otp = payload.pass_type in [PassType.single_day_visitor, PassType.conference_temp]

    new_pass = Pass(
        pass_type=payload.pass_type,
        holder_name=payload.holder_name,
        holder_phone=payload.holder_phone,
        holder_email=payload.holder_email,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        created_by_id=current_user.id,
        status=PassStatus.approved if auto else (PassStatus.pending_otp if needs_otp else PassStatus.pending),
        approved_by_id=current_user.id if auto else None
    )
    db.add(new_pass)
    db.commit()
    db.refresh(new_pass)

    # Generate TOTP secret for QR
    if needs_otp:
        totp_entry = TOTPSecret(pass_id=new_pass.id, secret_key=pyotp.random_base32())
        db.add(totp_entry)

        # Generate phone OTP
        otp_code = str(random.randint(100000, 999999))
        otp_entry = OTPRequest(
            pass_id=new_pass.id,
            phone=payload.holder_phone,
            otp_code=otp_code,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        db.add(otp_entry)
        db.commit()

        # In production: send SMS via Twilio/MSG91
        # For simulation: return OTP in response
        print(f"[SIMULATED SMS] Sending OTP {otp_code} to {payload.holder_phone}")

    return new_pass


@router.post("/{pass_id}/verify-otp")
def verify_visitor_otp(
    pass_id: int,
    otp_code: str,
    db: Session = Depends(get_db)
):
    """
    Public endpoint - no auth required.
    Visitor enters OTP received on their phone.
    On success, pass moves from pending_otp to pending (awaiting superintendent approval).
    """
    pass_ = db.query(Pass).filter(Pass.id == pass_id).first()
    if not pass_:
        raise HTTPException(status_code=404, detail="Pass not found")

    if pass_.status != PassStatus.pending_otp:
        raise HTTPException(status_code=400, detail="Pass is not awaiting OTP verification")

    otp = db.query(OTPRequest).filter(OTPRequest.pass_id == pass_id).first()
    if not otp:
        raise HTTPException(status_code=404, detail="OTP record not found")

    now = datetime.now(timezone.utc)
    expires = otp.expires_at.replace(tzinfo=timezone.utc) if otp.expires_at.tzinfo is None else otp.expires_at

    if now > expires:
        raise HTTPException(status_code=400, detail="OTP has expired")

    if otp.otp_code != otp_code:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    otp.verified = True
    pass_.status = PassStatus.pending
    pass_.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Phone verified. Pass is now pending superintendent approval."}


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
    pass_ = db.query(Pass).filter(Pass.id == pass_id).first()
    if not pass_:
        raise HTTPException(status_code=404, detail="Pass not found")

    events = []

    creator = db.query(User).filter(User.id == pass_.created_by_id).first()
    events.append({"time": pass_.created_at, "event": f"Pass created by {creator.name} ({creator.role.value})", "type": "created"})

    otp = db.query(OTPRequest).filter(OTPRequest.pass_id == pass_id).first()
    if otp:
        if otp.verified:
            events.append({"time": pass_.updated_at, "event": f"Phone {otp.phone} verified by visitor", "type": "approved"})
        else:
            events.append({"time": otp.created_at, "event": f"OTP sent to {otp.phone} - awaiting verification", "type": "created"})

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


@router.get("/{pass_id}/otp-status")
def get_otp_status(
    pass_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Simulation only - returns the OTP so testers can verify without SMS.
    In production this endpoint would not exist.
    """
    otp = db.query(OTPRequest).filter(OTPRequest.pass_id == pass_id).first()
    if not otp:
        raise HTTPException(status_code=404, detail="No OTP found for this pass")
    return {
        "pass_id": pass_id,
        "phone": otp.phone,
        "otp_code": otp.otp_code,
        "verified": otp.verified,
        "expires_at": otp.expires_at,
        "note": "This endpoint is for simulation only. In production, OTP is sent via SMS."
    }
