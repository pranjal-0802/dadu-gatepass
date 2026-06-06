from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from app.models import UserRole, PassType, PassStatus, RFIDStatus, GateScanResult

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole

class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: UserRole
    created_at: datetime
    model_config = {"from_attributes": True}

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PassCreate(BaseModel):
    pass_type: PassType
    holder_name: str
    holder_phone: Optional[str] = None
    holder_email: Optional[str] = None
    valid_from: datetime
    valid_until: datetime

class PassOut(BaseModel):
    id: int
    pass_type: PassType
    holder_name: str
    holder_phone: Optional[str]
    holder_email: Optional[str]
    valid_from: datetime
    valid_until: datetime
    status: PassStatus
    created_by_id: int
    approved_by_id: Optional[int]
    created_at: datetime
    model_config = {"from_attributes": True}

class PassStatusUpdate(BaseModel):
    status: PassStatus

class TOTPVerifyRequest(BaseModel):
    pass_id: int
    totp_code: str

class RFIDRequest(BaseModel):
    vehicle_number: str

class RFIDOut(BaseModel):
    id: int
    faculty_id: int
    vehicle_number: str
    tag_uid: Optional[str]
    status: RFIDStatus
    requested_at: datetime
    approved_at: Optional[datetime]
    model_config = {"from_attributes": True}

class RFIDScanRequest(BaseModel):
    tag_uid: str

class GateLogOut(BaseModel):
    id: int
    pass_id: int
    scanned_by_id: int
    timestamp: datetime
    result: GateScanResult
    failure_reason: Optional[str]
    model_config = {"from_attributes": True}
