# DADU Gatepass System

A campus gate pass management system built for BITS Pilani Hyderabad Campus. Handles permanent residents, conference participants, and single-day visitors with role-based access control, rotating TOTP verification, and simulated RFID vehicle passes.

## Live Demo

UI: https://dadu-gatepass-production.up.railway.app/ui
API docs: https://dadu-gatepass-production.up.railway.app/docs

## Test Credentials

| Role | Email | Password |
|------|-------|----------|
| Student | student@bits.ac.in | test123 |
| Faculty | faculty@bits.ac.in | test123 |
| Hostel Superintendent | sup@bits.ac.in | test123 |
| Conference Supervisor | confsup@bits.ac.in | test123 |
| Gate Security | gate@bits.ac.in | test123 |

## Setup (Local)

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python seed.py
uvicorn main:app --reload

UI: http://localhost:8000/ui
API docs: http://localhost:8000/docs

## Architecture

### Stack
- Backend: FastAPI (Python)
- Database: SQLite via SQLAlchemy ORM
- Auth: JWT tokens + bcrypt password hashing
- QR Verification: TOTP via pyotp (RFC 6238)
- Frontend: Single-page vanilla HTML/JS, no framework
- Deployment: Railway

### Project Structure

dadu-gatepass/
├── main.py               # app entry point
├── seed.py               # creates test users
├── app/
│   ├── models.py         # SQLAlchemy DB models
│   ├── schemas.py        # Pydantic request/response schemas
│   ├── core/
│   │   ├── auth.py       # JWT, bcrypt, role enforcement
│   │   ├── database.py   # DB connection and session
│   │   ├── rules.py      # approval matrix (single source of truth)
│   │   └── expiry.py     # auto-expiry logic
│   └── routers/
│       ├── auth.py       # register, login
│       ├── passes.py     # pass lifecycle
│       ├── gate.py       # TOTP verification, RFID scan, audit logs
│       └── rfid.py       # RFID tag requests and approvals
└── static/
    └── index.html        # single-page frontend

### Database Schema
- users - all system users with roles
- passes - pass applications with full lifecycle tracking
- totp_secrets - per-pass TOTP secret keys for rotating codes
- otp_requests - phone OTP verification for visitor tracking
- rfid_tags - faculty vehicle pass requests and approvals
- gate_logs - full audit trail of every scan attempt

## Role-Based Access Control

Each role has strictly enforced permissions at the API layer.

| Role | Permissions |
|------|-------------|
| Student | Apply for single-day visitor passes |
| Faculty | Apply for conference participant passes, request RFID tags |
| Hostel Superintendent | Approve visitor passes, approve RFID requests, create permanent passes |
| Conference Supervisor | Approve conference participant passes |
| Gate Security | Verify TOTP codes, scan RFID tags, view audit logs |

## Innovations and Design Decisions

### 1. Centralized Approval Matrix (app/core/rules.py)
All approval routing logic lives in a single config dictionary instead of scattered if/else checks. Adding a new pass type or changing who approves what requires editing exactly one file. This makes the system auditable and maintainable.

### 2. Rotating TOTP Codes for Temporary Passes
Temporary passes use TOTP (Time-based One-Time Password, RFC 6238) - the same algorithm behind Google Authenticator. Every 30 seconds a new 6-digit code is derived from a secret key and the current timestamp.

Why this beats static QR codes:
- A screenshot is useless after 30 seconds
- No database lookup needed to verify - server recomputes the expected code
- Each pass has its own unique secret key - compromising one pass does not affect others
- Clock drift of up to 30 seconds is tolerated

In production, this code would be wrapped in a QR image library in a single line. The security guarantee is identical - the QR is just a presentation layer on top of TOTP.

### 3. Phone OTP Verification for Visitor Tracking
Temporary passes require the visitor to verify their phone number before the pass enters the approval queue. This:
- Confirms the visitor's identity before they arrive on campus
- Gives campus security a verified phone number for every visitor
- Prevents students from applying passes for random people
- Pass stays in pending_otp status until verified, then moves to pending for superintendent approval

Currently simulated (OTP printed to server logs). In production: swap one line for a Twilio/MSG91 SMS call.

### 4. Per-Pass Audit Timeline
Every pass has a complete chronological timeline reconstructed from existing data:
- Pass created by (name + role)
- Phone OTP verified
- Approved/rejected by (name + role)
- Every gate scan attempt with result and reason

Accessible via GET /passes/{id}/timeline. No extra tables needed - stitched from passes and gate_logs.

### 5. Pass Revocation
Supervisors can revoke any approved pass - for blacklisted visitors or passes issued by mistake. Revoked passes are rejected at gate verification and logged in the audit trail.

### 6. Auto-Expiry
Passes are automatically marked expired when valid_until passes. Called on every relevant API request instead of a background job - keeps deployment simple with no scheduler infrastructure needed.

### 7. Simulated RFID Vehicle Passes
Full request-approve-scan flow:
- Faculty submits vehicle number
- Superintendent approves and a unique tag UID is generated (simulating chip programming)
- Gate security endpoint accepts a UID and returns faculty details (simulating embedded firmware)

### 8. Timing-Safe Login
Login checks both user existence and password correctness before raising an error, preventing timing attacks that could reveal whether an email is registered.

### 9. Input Validation
- Phone numbers must be exactly 10 digits for temporary passes
- valid_from cannot be in the past
- valid_until must be after valid_from
- Single-day visitor passes must start and end on the same calendar day

## SWD API Integration

The existing SWD app can integrate via the REST API:
- POST /auth/login - authenticate students using their BITS credentials
- POST /passes/ - students apply for visitor passes
- GET /passes/ - students view their pass applications and status
- GET /passes/{id}/qr-payload - get rotating TOTP code for display in SWD app

Assumed SWD implementation: SWD app maps student roll numbers to registered emails. Pass applications from SWD set created_by_id to the corresponding user, maintaining the same approval workflow.
