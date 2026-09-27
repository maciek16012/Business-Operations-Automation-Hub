from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import SourceType


class SafeTextModel(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def no_control_characters(cls, value):
        if isinstance(value, str) and any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise ValueError("Unsupported control characters")
        return value


class ReviewData(SafeTextModel):
    model_config = ConfigDict(extra="forbid")
    customer_name: str | None = Field(default=None, max_length=255)
    customer_email: str | None = Field(default=None, max_length=320)
    company_name: str | None = Field(default=None, max_length=255)
    tax_id: str | None = Field(default=None, max_length=32)
    request_title: str | None = Field(default=None, max_length=255)
    request_description: str | None = Field(default=None, max_length=20000)
    requested_deadline: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, max_length=20)
    estimated_value: str | None = Field(default=None, max_length=100)


class CaseCreate(ReviewData):
    source: Literal[SourceType.MANUAL_UPLOAD, SourceType.API] = SourceType.MANUAL_UPLOAD


class Decision(SafeTextModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=2000)
