"""Native sources extend the existing M2 intake and M5 gate, never replace them."""

import asyncio
import base64
import email
import hashlib
import imaplib
import mimetypes
import socket
import ssl
import time
from datetime import UTC
from email import policy
from email.utils import getaddresses, parsedate_to_datetime

from sqlalchemy import select

from app.company.boundaries import mounted, resolve
from app.company.secrets import decrypt
from app.core.config import settings
from app.models.company import DocumentSource, Secret, SourceItem
from app.models.operations import now
from app.schemas.inbound import InboundEmail
from app.services.inbound import EmailIngestionService


def connect_imap(config, credentials):
    if not config["tls"] and (
        settings.app_env == "production" or not settings.connector_allow_plaintext_test
    ):
        raise ValueError("IMAP TLS required")
    host, port = config["host"], config["port"]
    ip = resolve(host, port)

    class PinnedIMAP(imaplib.IMAP4):
        def _create_socket(self, timeout):
            sock = socket.create_connection((ip, port), timeout=timeout)
            return (
                ssl.create_default_context().wrap_socket(sock, server_hostname=host)
                if config["tls"]
                else sock
            )

    connection = PinnedIMAP(host, port, timeout=20)
    connection.login(config["username"], credentials.get("password", ""))
    result, _ = connection.select(config["folder"], readonly=True)
    if result != "OK":
        raise ValueError("IMAP folder unavailable")
    return connection


def fetch_imap(config, credentials):
    conn = connect_imap(config, credentials)
    try:
        validity = conn.response("UIDVALIDITY")[1][0].decode()
        status, ids = conn.uid("search", None, "ALL")
        if status != "OK":
            raise ValueError("IMAP search failed")
        output: list[tuple[str, bytes]] = []
        # Source deduplication permits replay; bounded batches are filtered before body fetch.
        known = set(credentials.get("_known", []))
        for uid in ids[0].split():
            identity = f"{validity}:{uid.decode()}"
            if identity in known:
                continue
            if len(output) >= 20:
                break
            status, metadata = conn.uid("fetch", uid, "(RFC822.SIZE)")
            import re

            size = re.search(rb"RFC822.SIZE (\d+)", metadata[0] or b"")
            if status != "OK" or not size or int(size[1]) > 32 * 1024 * 1024:
                raise ValueError("IMAP message size rejected")
            status, parts = conn.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                raise ValueError("IMAP message fetch failed")
            raw = next(part[1] for part in parts if isinstance(part, tuple))
            if len(raw) > 32 * 1024 * 1024:
                raise ValueError("IMAP message size rejected")
            output.append((identity, raw))
        return output
    finally:
        conn.logout()


def payload_from_email(raw: bytes):
    message = email.message_from_bytes(raw, policy=policy.default)

    def addresses(header):
        return [
            {"name": name[:255] or None, "address": address}
            for name, address in getaddresses(message.get_all(header, []))
            if address
        ][:100]

    sender = addresses("From")
    if not sender:
        raise ValueError("Email sender missing")
    attachments = []
    for part in message.iter_attachments():
        content = part.get_payload(decode=True)
        if isinstance(content, bytes) and content:
            attachments.append(
                {
                    "filename": part.get_filename() or "attachment",
                    "mime_type": part.get_content_type(),
                    "content_base64": base64.b64encode(content).decode(),
                }
            )
    body = message.get_body(preferencelist=("plain",))
    sent = None
    if message.get("Date"):
        try:
            sent = parsedate_to_datetime(message["Date"])
            if sent.tzinfo is None:
                sent = sent.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            pass
    return InboundEmail.model_validate(
        {
            "external_message_id": message.get("Message-ID"),
            "sender": sender[0],
            "recipients": addresses("To"),
            "cc": addresses("Cc"),
            "reply_to": addresses("Reply-To"),
            "subject": str(message.get("Subject", ""))[:998],
            "received_at": now(),
            "sent_at": sent,
            "text_body": str(body.get_content())[:200000] if body else "",
            "attachments": attachments,
        }
    )


async def poll_source(service, source: DocumentSource):
    import json

    if source.kind in {"MANUAL", "API"}:
        return
    if source.kind == "IMAP":
        secret = await service.db.get(Secret, source.secret_id) if source.secret_id else None
        credentials = json.loads(decrypt(secret)) if secret else {}
        credentials["_known"] = list(
            await service.db.scalars(
                select(SourceItem.identity).where(SourceItem.source_id == source.id)
            )
        )
        messages = await asyncio.to_thread(fetch_imap, source.config, credentials)
        for identity, raw in messages:
            result = await EmailIngestionService(service).ingest(payload_from_email(raw))
            import uuid

            case = await service.get(uuid.UUID(str(result["case_id"])))
            service.db.add(SourceItem(source_id=source.id, identity=identity, case_id=case.id))
            service.audit(
                case,
                "SOURCE_DOCUMENT_RECEIVED",
                {"source_id": str(source.id), "source_kind": "IMAP", "message_identity": identity},
            )
            source.last_message = now()
            await service.db.flush()  # Commit complete batch before marking source success.
    elif source.kind == "WATCHED_FOLDER":
        folder = mounted(source.config["root"], source.config["path"])
        state = dict(source.runtime_state or {})
        observed: dict[str, dict] = {}
        for path in sorted(folder.iterdir())[:1000]:
            if (
                path.name.startswith("~")
                or path.suffix.lower() in {".tmp", ".part", ".crdownload"}
                or not path.is_file()
                or path.is_symlink()
            ):
                continue
            stat = path.stat()
            if stat.st_size > 5 * 1024 * 1024 or stat.st_size == 0:
                continue
            signature = f"{stat.st_size}:{stat.st_mtime_ns}"
            previous = state.get(path.name)
            observed[path.name] = (
                previous
                if previous and previous["signature"] == signature
                else {"signature": signature, "since": time.time()}
            )
            if time.time() - observed[path.name]["since"] < source.config["stable_seconds"]:
                continue
            with path.open("rb") as stream:
                data = stream.read(5 * 1024 * 1024 + 1)
            if len(data) > 5 * 1024 * 1024:
                continue
            after = path.stat()
            if after.st_size != stat.st_size or after.st_mtime_ns != stat.st_mtime_ns:
                continue
            identity = hashlib.sha256(data).hexdigest()
            exists = await service.db.scalar(
                select(SourceItem.id).where(
                    SourceItem.source_id == source.id, SourceItem.identity == identity
                )
            )
            if exists:
                continue
            case = await service.create(
                {"source": "api", "request_title": path.name, "customer_name": source.name}
            )
            await service.upload(
                case,
                [
                    (
                        path.name,
                        mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                        data,
                    )
                ],
            )
            service.db.add(SourceItem(source_id=source.id, identity=identity, case_id=case.id))
            service.audit(
                case,
                "SOURCE_DOCUMENT_RECEIVED",
                {
                    "source_id": str(source.id),
                    "source_kind": "WATCHED_FOLDER",
                    "filename": path.name,
                    "sha256": identity,
                },
            )
            source.last_message = now()
            await service.db.flush()
        source.runtime_state = observed
    source.last_success = now()
    source.last_error = None
    source.status = "HEALTHY"


def test_source(source, credentials):
    if source.kind == "IMAP":
        conn = connect_imap(source.config, credentials)
        conn.logout()
    elif source.kind == "WATCHED_FOLDER":
        if not mounted(source.config["root"], source.config["path"]).is_dir():
            raise ValueError("Directory unavailable")
