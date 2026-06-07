from app.models import PassType, UserRole

# ── Approval Matrix ──
# All pass-related permission rules live here.
# To add a new pass type or change who approves what, edit only this file.

APPROVAL_MATRIX = {
    PassType.single_day_visitor: {
        "can_create":  [UserRole.student, UserRole.hostel_superintendent],
        "must_approve": UserRole.hostel_superintendent,
        "auto_approve": False,
    },
    PassType.conference_temp: {
        "can_create":  [UserRole.faculty, UserRole.conference_supervisor],
        "must_approve": UserRole.conference_supervisor,
        "auto_approve": False,
    },
    PassType.permanent: {
        "can_create":  [UserRole.hostel_superintendent, UserRole.conference_supervisor],
        "must_approve": None,
        "auto_approve": True,  # superintendents create these directly, no separate approval
    },
}


def can_create_pass(role: UserRole, pass_type: PassType) -> bool:
    return role in APPROVAL_MATRIX[pass_type]["can_create"]


def get_approver_role(pass_type: PassType) -> UserRole | None:
    return APPROVAL_MATRIX[pass_type]["must_approve"]


def is_auto_approved(pass_type: PassType) -> bool:
    return APPROVAL_MATRIX[pass_type]["auto_approve"]

# Gate security can view all approved passes across all types
GATE_VIEWABLE_STATUSES = ["approved"]
