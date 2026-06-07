from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.models import Pass, PassStatus


def expire_stale_passes(db: Session):
    """
    Marks approved passes as expired if valid_until has passed.
    Called on relevant API requests instead of a background job.
    This keeps deployment simple - no scheduler needed.
    """
    now = datetime.now(timezone.utc)

    stale = db.query(Pass).filter(
        Pass.status == PassStatus.approved,
        Pass.valid_until < now
    ).all()

    for pass_ in stale:
        pass_.status = PassStatus.expired
        pass_.updated_at = now

    if stale:
        db.commit()

    return len(stale)
