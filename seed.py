from app.core.database import init_db, SessionLocal
from app.core.auth import hash_password
from app.models import User, UserRole

SEED_USERS = [
    {"name": "Student One",           "email": "student@bits.ac.in",  "password": "test123", "role": UserRole.student},
    {"name": "Faculty One",           "email": "faculty@bits.ac.in",  "password": "test123", "role": UserRole.faculty},
    {"name": "Hostel Superintendent", "email": "sup@bits.ac.in",      "password": "test123", "role": UserRole.hostel_superintendent},
    {"name": "Conference Supervisor", "email": "confsup@bits.ac.in",  "password": "test123", "role": UserRole.conference_supervisor},
    {"name": "Gate Security",         "email": "gate@bits.ac.in",     "password": "test123", "role": UserRole.gate_security},
]

def seed():
    init_db()
    db = SessionLocal()
    try:
        for u in SEED_USERS:
            existing = db.query(User).filter(User.email == u["email"]).first()
            if existing:
                print(f"  Skipping {u['email']} - already exists")
                continue
            user = User(
                name=u["name"],
                email=u["email"],
                password_hash=hash_password(u["password"]),
                role=u["role"]
            )
            db.add(user)
            print(f"  Created: {u['email']} | role: {u['role'].value}")
        db.commit()
        print("\nSeed complete. All users have password: test123")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
