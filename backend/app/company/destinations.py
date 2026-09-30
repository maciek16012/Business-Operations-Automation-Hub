"""Bounded, idempotent outbound artifact delivery. Called only by the worker."""

import hashlib
import hmac
import io
import json
import os
import socket
import uuid
from pathlib import PurePosixPath

import paramiko
from sqlalchemy import select

from app.company.auth import aware
from app.company.boundaries import mounted, resolve, safe_name, webhook
from app.company.secrets import decrypt
from app.exports.render import json_export, xlsx_export
from app.models.company import Secret
from app.models.entities import Attachment, ValidationIssue
from app.models.operations import AttachmentSecurityScan


async def safe_case(service, case):
    if case.status not in {"APPROVED", "EXPORTED"}:
        raise ValueError("Only approved cases may be delivered")
    if any(
        not i.resolved and i.severity in {"ERROR", "CRITICAL"}
        for i in await service.rows(ValidationIssue, case.id)
    ):
        raise ValueError("Unresolved validation blocks delivery")
    attachments = await service.rows(Attachment, case.id)
    if not attachments:
        raise ValueError("No SAFE original")
    for attachment in attachments:
        scan = await service.db.scalar(
            select(AttachmentSecurityScan)
            .where(AttachmentSecurityScan.attachment_id == attachment.id)
            .order_by(AttachmentSecurityScan.created_at.desc())
            .limit(1)
        )
        if not scan or scan.verdict != "SAFE":
            raise ValueError("Delivery requires persisted SAFE for every attachment")
    return attachments


async def credentials(service, connector):
    record = await service.db.get(Secret, connector.secret_id) if connector.secret_id else None
    return json.loads(decrypt(record)) if record else {}


async def artifacts(service, case, config):
    attachments = await safe_case(service, case)
    detail = await service.detail(case)
    values = []
    if "original" in config.get("artifacts", []):
        for a in attachments:
            values.append(
                (
                    f"{a.sha256[:12]}-{safe_name(a.original_filename)}",
                    service.storage.get(a.storage_key),
                )
            )
    if "json" in config.get("artifacts", []):
        values.append((f"{case.public_id}.json", json_export(detail)))
    if "xlsx" in config.get("artifacts", []):
        values.append((f"{case.public_id}.xlsx", xlsx_export(detail)))
    return values, detail


def sftp_connect(config, secret):
    ip = resolve(config["host"], config["port"])
    entry = paramiko.hostkeys.HostKeyEntry.from_line(config["host"] + " " + config["host_key"])
    if not entry or not entry.key:
        raise ValueError("Valid pinned SSH host key required")
    client = paramiko.SSHClient()
    label = config["host"] if config["port"] == 22 else f"[{config['host']}]:{config['port']}"
    client.get_host_keys().add(label, entry.key.get_name(), entry.key)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    key = None
    if secret.get("private_key"):
        for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
            try:
                key = cls.from_private_key(io.StringIO(secret["private_key"]))
                break
            except (paramiko.SSHException, ValueError):
                continue
        if key is None:
            raise ValueError("Unsupported private key")
    sock = socket.create_connection((ip, config["port"]), timeout=15)
    try:
        client.connect(
            config["host"],
            port=config["port"],
            username=config["username"],
            password=secret.get("password"),
            pkey=key,
            sock=sock,
            allow_agent=False,
            look_for_keys=False,
            timeout=15,
            banner_timeout=15,
            auth_timeout=15,
        )
    except Exception:
        sock.close()
        client.close()
        raise
    return client


def file_deliver(config, case, detail, values):
    kind = detail["documents"][0]["document_type"] if detail.get("documents") else "UNKNOWN"
    fields = {
        "year": case.created_at.strftime("%Y"),
        "month": case.created_at.strftime("%m"),
        "document_type": safe_name(kind),
        "case_id": safe_name(case.public_id),
        "document_number_or_case_id": safe_name(case.public_id),
        "extension": "json",
    }
    directory = mounted(config["root"], config["path_template"].format(**fields))
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in values:
        fields["extension"] = name.rsplit(".", 1)[-1]
        filename = safe_name(config["filename"].format(**fields))
        # Multiple originals of the same type must never overwrite one another.
        if not name.startswith(case.public_id):
            filename = safe_name(name.rsplit(".", 1)[0]) + "-" + filename
        relative = str(directory.relative_to(mounted(config["root"])) / filename).replace("\\", "/")
        target = mounted(config["root"], relative)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(data).digest():
                raise ValueError("Destination collision")
            continue
        temporary = target.with_name("." + target.name + "." + uuid.uuid4().hex + ".part")
        try:
            with temporary.open("xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            # Exclusive publication, no overwrite of an existing destination.
            os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def sftp_deliver(config, secret, case, values):
    client = sftp_connect(config, secret)
    try:
        sftp = client.open_sftp()
        sftp.get_channel().settimeout(15)
        directory = PurePosixPath(config["target_folder"]) / safe_name(case.public_id)
        current = PurePosixPath(".")
        for component in directory.parts:
            current = current / component
            try:
                sftp.mkdir(str(current))
            except OSError:
                sftp.stat(str(current))
        for name, data in values:
            target = str(directory / safe_name(name))
            try:
                with sftp.open(target, "rb") as f:
                    existing = f.read(len(data) + 1)
                if hashlib.sha256(existing).digest() != hashlib.sha256(data).digest():
                    raise ValueError("SFTP destination collision")
                continue
            except FileNotFoundError:
                pass
            temporary = target + "." + uuid.uuid4().hex + ".part"
            with sftp.open(temporary, "wx") as f:
                f.write(data)
            sftp.rename(temporary, target)
        sftp.close()
    finally:
        client.close()


async def deliver(service, job, destination):
    import asyncio

    case = await service.get(job.case_id)
    await safe_case(service, case)
    detail = await service.detail(case)
    if destination.kind != "WEBHOOK" and not job.artifacts:
        prepared, _ = await artifacts(service, case, destination.config)
        job.artifacts = [
            {"name": name, "storage_key": service.storage.put(data)} for name, data in prepared
        ]
        await service.db.commit()  # Durable retry snapshot before any external publication.
    values = [(item["name"], service.storage.get(item["storage_key"])) for item in job.artifacts]
    secret = await credentials(service, destination)
    if destination.kind == "FILESYSTEM":
        await asyncio.to_thread(file_deliver, destination.config, case, detail, values)
    elif destination.kind == "SFTP":
        await asyncio.to_thread(sftp_deliver, destination.config, secret, case, values)
    elif destination.kind == "WEBHOOK":
        if not secret.get("hmac"):
            raise ValueError("HMAC secret required")
        # Keep retries byte-stable: approved data and persisted job identity/time only.
        payload = json.dumps(
            {
                "schema_version": 1,
                "case_id": str(case.id),
                "public_case_id": case.public_id,
                "documents": [
                    {
                        "id": d["id"],
                        "type": d["document_type"],
                        "reviewed": d["reviewed"],
                        "tables": d["tables"],
                    }
                    for d in detail["documents"]
                ],
                "extraction": {k: detail[k] for k in ["tax_id", "estimated_value", "currency"]},
                "validation_status": "APPROVED",
                "created_at": aware(job.created_at).isoformat(),
                "correlation_id": str(job.id),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        signature = hmac.new(secret["hmac"].encode(), payload, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": job.idempotency_key,
            "X-BOAH-Signature": "sha256=" + signature,
        }
        if secret.get("token"):
            headers["Authorization"] = "Bearer " + secret["token"]
        await asyncio.to_thread(webhook, destination.config["url"], payload, headers)


def test_destination(destination, secret):
    if destination.kind == "FILESYSTEM":
        path = mounted(destination.config["root"])
        if not path.is_dir() or not os.access(path, os.W_OK):
            raise ValueError("Mounted root is not writable")
    elif destination.kind == "SFTP":
        client = sftp_connect(destination.config, secret)
        try:
            client.open_sftp().listdir(".")
        finally:
            client.close()
    elif destination.kind == "WEBHOOK":
        payload = b'{"event":"boah.connection_test"}'
        if not secret.get("hmac"):
            raise ValueError("HMAC secret required")
        headers = {
            "Content-Type": "application/json",
            "X-BOAH-Signature": "sha256="
            + hmac.new(secret["hmac"].encode(), payload, hashlib.sha256).hexdigest(),
            "Idempotency-Key": "test-" + uuid.uuid4().hex,
        }
        if secret.get("token"):
            headers["Authorization"] = "Bearer " + secret["token"]
        webhook(destination.config["url"], payload, headers)
