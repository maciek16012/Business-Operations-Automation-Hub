from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from pydantic import ConfigDict, Field, field_validator

from app.core.config import settings
from app.schemas.cases import SafeTextModel


class EmailAddress(SafeTextModel):
    model_config = ConfigDict(extra="forbid")
    address: str = Field(max_length=320)
    name: str | None = Field(default=None, max_length=255)

    @field_validator("address")
    @classmethod
    def syntax(cls, value: str) -> str:
        try:
            return validate_email(
                value, check_deliverability=False, test_environment=True
            ).normalized
        except EmailNotValidError as exc:
            raise ValueError("Invalid email address syntax") from exc


class EmailAttachment(SafeTextModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(default="application/octet-stream", min_length=1, max_length=255)
    content_base64: str = Field(max_length=6990508, repr=False)

    @field_validator("filename", "mime_type")
    @classmethod
    def single_line(cls, value: str) -> str:
        if any(ord(c) < 32 for c in value):
            raise ValueError("Filename and MIME type must be single-line")
        return value

    def decode(self) -> bytes:
        try:
            content = base64.b64decode(self.content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Attachment must contain valid base64") from exc
        if not content or len(content) > settings.max_upload_bytes:
            raise ValueError("Attachment must be nonempty and within MAX_UPLOAD_BYTES")
        return content


class InboundEmail(SafeTextModel):
    model_config = ConfigDict(extra="forbid")
    source_type: Literal["imap"] = "imap"
    external_message_id: str | None = Field(default=None, max_length=998)
    sender: EmailAddress
    recipients: list[EmailAddress] = Field(default_factory=list, max_length=100)
    cc: list[EmailAddress] = Field(default_factory=list, max_length=100)
    reply_to: list[EmailAddress] = Field(default_factory=list, max_length=100)
    subject: str = Field(default="", max_length=998)
    received_at: datetime
    sent_at: datetime | None = None
    text_body: str = Field(default="", max_length=200000)
    html_body: str | None = Field(default=None, max_length=200000)
    attachments: list[EmailAttachment] = Field(default_factory=list, max_length=10)

    @field_validator("received_at", "sent_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Timestamp must include a timezone")
            return value.astimezone(UTC)
        return value


class InboundResult(SafeTextModel):
    result: Literal["created", "duplicate"]
    case_id: UUID
    public_case_id: str
    message_id: UUID
    status: str
    processing_status: str
    identity_method: str
    attachment_results: list[dict]
