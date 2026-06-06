from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime, timezone
import enum

Base = declarative_base()

class UserRole(str, enum.Enum):
    student               = "student"
    faculty               = "faculty"
    hostel_superintendent = "hostel_superintendent"
    conference_supervisor = "conference_supervisor"
    gate_security         = "gate_security"

class PassType(str, enum.Enum):
    permanent          = "permanent"
    conference_temp    = "conference_temp"
    single_day_visitor = "single_day_visitor"

class PassStatus(str, enum.Enum):
    pending  = "pending"
    approved = "approved"
    rejected = "rejected"
    expired  = "expired"
    revoked  = "revoked"
    pending_otp = "pending_otp"

class RFIDStatus(str, enum.Enum):
    pending = "pending"
    active  = "active"
    revoked = "revoked"

class GateScanResult(str, enum.Enum):
    success = "success"
    failure = "failure"


class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String, nullable=False)
    email         = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role          = Column(Enum(UserRole), nullable=False)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    passes_created  = relationship("Pass", foreign_keys="Pass.created_by_id", back_populates="creator")
    passes_approved = relationship("Pass", foreign_keys="Pass.approved_by_id", back_populates="approver")
    rfid_tags       = relationship("RFIDTag", foreign_keys="RFIDTag.faculty_id", back_populates="faculty")
    gate_logs       = relationship("GateLog", back_populates="scanned_by_user")


class Pass(Base):
    __tablename__ = "passes"
    id             = Column(Integer, primary_key=True, index=True)
    pass_type      = Column(Enum(PassType), nullable=False)
    holder_name    = Column(String, nullable=False)
    holder_phone   = Column(String, nullable=True)
    holder_email   = Column(String, nullable=True)
    valid_from     = Column(DateTime, nullable=False)
    valid_until    = Column(DateTime, nullable=False)
    status         = Column(Enum(PassStatus), default=PassStatus.pending, nullable=False)
    created_by_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))

    creator     = relationship("User", foreign_keys=[created_by_id], back_populates="passes_created")
    approver    = relationship("User", foreign_keys=[approved_by_id], back_populates="passes_approved")
    totp_secret = relationship("TOTPSecret", back_populates="pass_", uselist=False)
    gate_logs   = relationship("GateLog", back_populates="pass_")


class TOTPSecret(Base):
    __tablename__ = "totp_secrets"
    id         = Column(Integer, primary_key=True, index=True)
    pass_id    = Column(Integer, ForeignKey("passes.id"), unique=True, nullable=False)
    secret_key = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    pass_ = relationship("Pass", back_populates="totp_secret")


class RFIDTag(Base):
    __tablename__ = "rfid_tags"
    id             = Column(Integer, primary_key=True, index=True)
    faculty_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    vehicle_number = Column(String, nullable=False)
    tag_uid        = Column(String, unique=True, nullable=True)
    status         = Column(Enum(RFIDStatus), default=RFIDStatus.pending, nullable=False)
    requested_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    approved_at    = Column(DateTime, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    faculty  = relationship("User", foreign_keys=[faculty_id], back_populates="rfid_tags")
    approver = relationship("User", foreign_keys=[approved_by_id])


class GateLog(Base):
    __tablename__ = "gate_logs"
    id             = Column(Integer, primary_key=True, index=True)
    pass_id        = Column(Integer, ForeignKey("passes.id"), nullable=False)
    scanned_by_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    result         = Column(Enum(GateScanResult), nullable=False)
    failure_reason = Column(String, nullable=True)

    pass_           = relationship("Pass", back_populates="gate_logs")
    scanned_by_user = relationship("User", back_populates="gate_logs")

class OTPRequest(Base):
    """
    Stores OTP for visitor phone verification.
    Temporary passes start as pending_otp until visitor verifies their phone.
    OTP expires after 10 minutes.
    """
    __tablename__ = "otp_requests"

    id         = Column(Integer, primary_key=True, index=True)
    pass_id    = Column(Integer, ForeignKey("passes.id"), unique=True, nullable=False)
    phone      = Column(String, nullable=False)
    otp_code   = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified   = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
