from enum import StrEnum


class CaseStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    READY = "READY"
    APPROVED = "APPROVED"
    EXPORTED = "EXPORTED"
    DUPLICATE = "DUPLICATE"
    FAILED = "FAILED"


class SourceType(StrEnum):
    MANUAL_UPLOAD = "manual_upload"
    API = "api"
    EMAIL = "email"


class IssueSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    CORRECT = "correct"


class EmailAuditEvent(StrEnum):
    RECEIVED = "EMAIL_RECEIVED"
    DUPLICATE_IGNORED = "EMAIL_DUPLICATE_IGNORED"
    CASE_CREATED = "EMAIL_CASE_CREATED"
    ATTACHMENT_STORED = "EMAIL_ATTACHMENT_STORED"
    INGESTION_FAILED = "EMAIL_INGESTION_FAILED"
    ATTACHMENT_REVIEWED = "EMAIL_ATTACHMENT_REVIEWED"
