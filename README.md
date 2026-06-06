# DADU Gatepass System

Campus gate pass management system with role-based access control, rotating TOTP-based QR verification, and simulated RFID vehicle passes.

## Setup

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python seed.py
uvicorn main:app --reload

UI: http://localhost:8000/ui
API docs: http://localhost:8000/docs

## Test Credentials

| Role | Email | Password |
|------|-------|----------|
| Student | student@bits.ac.in | test123 |
| Faculty | faculty@bits.ac.in | test123 |
| Hostel Superintendent | sup@bits.ac.in | test123 |
| Conference Supervisor | confsup@bits.ac.in | test123 |
| Gate Security | gate@bits.ac.in | test123 |

## Architecture

### Stack
- Backend: FastAPI (Python)
- Database: SQLite via SQLAlchemy ORM
- Auth: JWT tokens (python-jose) + bcrypt password hashing
- QR Verification: TOTP via pyotp (RFC 6238)
- Frontend: Single-page vanilla HTML/JS, no framework

### Database Schema
- users - all system users with roles
- passes - pass applications with approval workflow
- totp_secrets - per-pass TOTP secret keys for rotating codes
- rfid_tags - faculty vehicle pass requests and approvals
- gate_logs - full audit trail of every scan attempt

### Role-Based Access Control
Each role has strictly enforced permissions at the API layer, not just the frontend.
- Student - applies for single-day visitor passes only
- Faculty - requests RFID vehicle tags, applies for conference passes
- Hostel Superintendent - approves visitor passes and RFID requests, creates permanent passes
- Conference Supervisor - approves conference participant passes
- Gate Security - verifies TOTP codes, scans RFID tags, views audit logs

## Security Design Decisions

### Rotating TOTP Codes (Dynamic QR Equivalent)
Temporary passes use TOTP (Time-based One-Time Password, RFC 6238) - the same algorithm behind Google Authenticator. Every 30 seconds, a new 6-digit code is derived mathematically from a secret key and the current timestamp.

Why this beats static QR codes:
- A screenshot of the code is useless after 30 seconds
- No database lookup needed to verify - the server recomputes the expected code
- Clock drift of up to 30 seconds is tolerated via valid_window=1
- Each pass has its own unique secret key

In production, this code would be wrapped in a QR image library (e.g. qrcode.js) in a single line. The security guarantee is identical - the QR is just a presentation layer on top of TOTP.

### JWT Authentication
After login, users receive a signed JWT token containing their user ID and role. Tokens expire after 8 hours. No database session lookup required per request.

### Password Security
Passwords are hashed with bcrypt before storage. bcrypt is deliberately slow to resist brute-force attacks. Raw passwords are never stored or logged.

### Timing-Safe Login
The login endpoint checks both user existence and password correctness before raising an error, preventing timing attacks that could reveal whether a given email is registered.

### Audit Trail
Every gate scan attempt (success or failure) is logged with timestamp, pass ID, and scanning officer ID.

### RFID Simulation
RFID tag UIDs are generated on approval, simulating a physical chip being programmed. The gate scan endpoint simulates embedded firmware calling the API with a tag UID.

## SWD API Integration
The existing SWD app can integrate via the REST API:
- POST /auth/login - authenticate students
- POST /passes/ - students apply for visitor passes
- GET /passes/ - students view their pass status
- GET /passes/{id}/qr-payload - get rotating TOTP code for display

Assumed SWD implementation: the SWD app maps student roll numbers to user emails. Pass applications from the SWD app set created_by_id to the corresponding user, maintaining the same approval workflow.