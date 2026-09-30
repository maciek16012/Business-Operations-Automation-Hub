from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.company.boundaries import mounted
from app.core.config import settings


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Retention(Strict):
    safe_days: int = Field(default=365, ge=1, le=36500)
    export_days: int = Field(default=365, ge=1, le=36500)
    quarantine_days: int | None = Field(default=None, ge=1, le=36500)


class Notifications(Strict):
    review: EmailStr | None = None
    security: EmailStr | None = None
    integration: EmailStr | None = None
    operations: EmailStr | None = None


class CompanyData(Strict):
    company_name: str = Field(min_length=1, max_length=255)
    identifier: str | None = Field(default=None, max_length=80)
    timezone: str = "Europe/Warsaw"
    locale: str = Field(default="pl-PL", pattern=r"^[a-z]{2}-[A-Z]{2}$")
    currency: str = Field(default="PLN", pattern=r"^[A-Z]{3}$")
    notification_email: EmailStr | None = None
    notifications: Notifications = Field(default_factory=Notifications)
    retention: Retention = Field(default_factory=Retention)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError("Unknown timezone") from exc
        return value


class ImapConfig(Strict):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=993, ge=1, le=65535)
    tls: bool = True
    username: str = Field(min_length=1, max_length=320)
    folder: str = Field(default="INBOX", pattern=r"^[\w /.-]{1,120}$")


class FolderConfig(Strict):
    root: str
    path: str = ""
    stable_seconds: int = Field(default=10, ge=2, le=3600)


class FileConfig(Strict):
    root: str
    path_template: str = "{year}/{month}/{document_type}/{case_id}"
    filename: str = "{document_number_or_case_id}.{extension}"
    artifacts: list[Literal["original", "json", "xlsx"]] = Field(
        default=["original", "json"], min_length=1, max_length=3
    )


class WebhookConfig(Strict):
    url: str = Field(max_length=2000)


class SftpConfig(Strict):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=200)
    target_folder: str = Field(default="uploads", pattern=r"^[a-zA-Z0-9_./-]{1,200}$")
    host_key: str = Field(min_length=20, max_length=2000)
    artifacts: list[Literal["original", "json", "xlsx"]] = Field(
        default=["json"], min_length=1, max_length=3
    )


class ConnectorData(Strict):
    name: str = Field(min_length=1, max_length=200)
    kind: str
    enabled: bool = False
    config: dict = Field(default_factory=dict)
    secret: dict[str, str] | None = Field(default=None, repr=False)
    interval_seconds: int = Field(default=60, ge=10, le=86400)

    def checked(self, source: bool):
        models: dict[str, type[BaseModel]] = (
            {"IMAP": ImapConfig, "WATCHED_FOLDER": FolderConfig, "MANUAL": Strict, "API": Strict}
            if source
            else {"FILESYSTEM": FileConfig, "WEBHOOK": WebhookConfig, "SFTP": SftpConfig}
        )
        if self.kind not in models:
            raise ValueError("Unsupported connector type")
        config = models[self.kind].model_validate(self.config).model_dump()
        if self.secret is not None:
            if not set(self.secret) <= {"password", "private_key", "token", "hmac"} or any(
                len(v) > 20000 for v in self.secret.values()
            ):
                raise ValueError("Invalid secret fields")
        if (
            self.kind == "IMAP"
            and not config["tls"]
            and not (settings.app_env != "production" and settings.connector_allow_plaintext_test)
        ):
            raise ValueError("IMAP TLS required")
        if self.kind == "WATCHED_FOLDER":
            mounted(config["root"], config["path"])
        if self.kind == "FILESYSTEM":
            import string

            for template in [config["path_template"], config["filename"]]:
                for _, field, format_spec, conversion in string.Formatter().parse(template):
                    if field and field not in {
                        "year",
                        "month",
                        "document_type",
                        "case_id",
                        "document_number_or_case_id",
                        "extension",
                    }:
                        raise ValueError("Unsupported template field")
                    if format_spec or conversion:
                        raise ValueError("Template formatting prohibited")
                if (
                    ".." in template
                    or "\\" in template
                    or ":" in template
                    or template.startswith("/")
                ):
                    raise ValueError("Unsafe template path")
            if "/" in config["filename"]:
                raise ValueError("Filename cannot contain directories")
            mounted(config["root"])
        if self.kind == "WEBHOOK":
            parsed = urlsplit(config["url"])
            if parsed.username or parsed.password or parsed.fragment or parsed.query:
                raise ValueError("URL cannot contain credentials, query or fragment")
            if parsed.scheme != "https" and not (
                settings.app_env != "production"
                and settings.connector_allow_plaintext_test
                and parsed.scheme == "http"
            ):
                raise ValueError("HTTPS required")
            if self.secret is not None and len(self.secret.get("hmac", "")) < 32:
                raise ValueError("HMAC signing key requires at least 32 characters")
            if not parsed.hostname:
                raise ValueError("Hostname required")
        if self.kind == "SFTP" and (
            ".." in config["target_folder"] or config["target_folder"].startswith("/")
        ):
            raise ValueError("SFTP folder must be relative without traversal")
        return config


class RuleData(Strict):
    name: str = Field(min_length=1, max_length=200)
    document_type: Literal[
        "*", "INVOICE", "HANDWRITTEN_TABLE", "PRINTED_TABLE", "GENERIC_DOCUMENT", "UNKNOWN"
    ] = "*"
    case_state: Literal["APPROVED", "EXPORTED"] = "APPROVED"
    require_reviewed: bool = False
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=10000)
    destinations: list[str] = Field(min_length=1, max_length=30)
