from app.domain.enums import CaseStatus

ALLOWED_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.RECEIVED: {CaseStatus.PROCESSING, CaseStatus.FAILED},
    CaseStatus.PROCESSING: {
        CaseStatus.READY,
        CaseStatus.REVIEW_REQUIRED,
        CaseStatus.DUPLICATE,
        CaseStatus.FAILED,
    },
    CaseStatus.REVIEW_REQUIRED: {CaseStatus.READY, CaseStatus.FAILED, CaseStatus.PROCESSING},
    CaseStatus.READY: {
        CaseStatus.APPROVED,
        CaseStatus.REVIEW_REQUIRED,
        CaseStatus.PROCESSING,
        CaseStatus.FAILED,
    },
    CaseStatus.APPROVED: {CaseStatus.EXPORTED},
    CaseStatus.EXPORTED: set(),
    CaseStatus.DUPLICATE: set(),
    CaseStatus.FAILED: set(),
}


def ensure_transition(current: str, target: str) -> None:
    if CaseStatus(target) not in ALLOWED_TRANSITIONS[CaseStatus(current)]:
        raise ValueError(f"Invalid transition: {current} -> {target}")
