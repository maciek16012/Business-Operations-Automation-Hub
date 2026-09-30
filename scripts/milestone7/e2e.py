"""Real local M7 E2E: SMTP -> IMAP -> M5/M6 -> approved delivery over 3 protocols.
Uses fresh synthetic PDFs, never M4/M6 HOLDOUT. Credentials stay in ignored runtime.
"""

import json
import smtplib
import time
import uuid
from email.message import EmailMessage
from pathlib import Path

import httpx
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime-m7"
ENV = dict(
    line.split("=", 1)
    for line in (RUNTIME / "integration.env").read_text().splitlines()
    if "=" in line
)
REPORT = ROOT / "docs/milestone7/e2e.json"
STATE = RUNTIME / "e2e-state.json"
state = (
    json.loads(STATE.read_text())
    if STATE.exists()
    else {"run": uuid.uuid4().hex[:10], "checks": {}}
)


def save():
    STATE.write_text(json.dumps(state, indent=2))


def check(name, details=True):
    state["checks"][name] = details
    save()
    print(name + ": PASS", flush=True)


client = httpx.Client(base_url="http://localhost:8000/api/v1", timeout=180)


def api(method, path, **kwargs):
    r = client.request(method, path, **kwargs)
    if not r.is_success:
        raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:400]}")
    return r.json()


def wait_for(fn, timeout=180):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = fn()
        if result:
            return result
        time.sleep(2)
    raise TimeoutError("Timed out waiting for persisted E2E evidence")


def connector(collection, name, kind, config, secret=None):
    full = "M7 " + state["run"] + " " + name
    existing = next((v for v in api("GET", "/settings/" + collection) if v["name"] == full), None)
    payload = {
        "name": full,
        "kind": kind,
        "enabled": True,
        "config": config,
        "interval_seconds": 10,
    }
    if secret:
        payload["secret"] = secret
    result = api(
        "PUT" if existing else "POST",
        "/settings/" + collection + ("/" + existing["id"] if existing else ""),
        json=payload,
    )
    return result["id"]


def pdf(number):
    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        "FAKTURA VAT / INVOICE",
        f"Numer faktury: {number}",
        "Sprzedawca: Synthetic M7 Company",
        "NIP: 5260250274",
        "Data wystawienia: 2026-09-29",
        "Netto: 100.00 PLN",
        "VAT: 23.00 PLN",
        "Brutto: 123.00 PLN",
        "Waluta: PLN",
        "Synthetic integration verification. No personal data.",
    ]
    for n, line in enumerate(lines):
        page.insert_text((60, 70 + n * 30), line, fontsize=13)
    return doc.tobytes()


def email_send(subject, attachment, filename, message_id):
    msg = EmailMessage()
    msg["From"] = "Synthetic Operator <sender@example.com>"
    msg["To"] = "synthetic@example.com"
    msg["Message-ID"] = message_id
    msg["Subject"] = subject
    msg.set_content("Synthetic M7 operational intake test. Please review the attached evidence.")
    msg.add_attachment(
        attachment,
        maintype="application" if filename.endswith(".pdf") else "text",
        subtype="pdf" if filename.endswith(".pdf") else "plain",
        filename=filename,
    )
    with smtplib.SMTP("localhost", 3025, timeout=10) as smtp:
        smtp.send_message(msg)


def find_case(title):
    return next(
        (
            c
            for c in api("GET", "/cases", params={"q": title})["items"]
            if c["request_title"] == title
        ),
        None,
    )


login = api(
    "POST",
    "/auth/login",
    json={
        "email": ENV["BOAH_INITIAL_ADMIN_EMAIL"],
        "password": ENV["BOAH_INITIAL_ADMIN_PASSWORD"],
    },
)
client.headers["X-CSRF-Token"] = login["csrf_token"]
api(
    "PUT",
    "/settings/company",
    json={
        "company_name": "BOAH Synthetic M7 Company",
        "identifier": "TEST-M7",
        "timezone": "Europe/Warsaw",
        "locale": "pl-PL",
        "currency": "PLN",
        "notifications": {
            "review": "review@example.com",
            "security": "security@example.com",
            "integration": "integration@example.com",
            "operations": "operations@example.com",
        },
    },
)
check("A_admin_login_company")
imap = connector(
    "sources",
    "Inbox",
    "IMAP",
    {
        "host": "greenmail",
        "port": 3143,
        "tls": False,
        "username": "synthetic",
        "folder": "INBOX",
    },
    {"password": ENV["M7_MAIL_PASSWORD"]},
)
folder = connector(
    "sources",
    "Watched folder",
    "WATCHED_FOLDER",
    {"root": "incoming", "path": "", "stable_seconds": 2},
)
archive = connector(
    "destinations",
    "Archive",
    "FILESYSTEM",
    {"root": "archive", "artifacts": ["original", "json", "xlsx"]},
)
webhook = connector(
    "destinations",
    "Signed webhook",
    "WEBHOOK",
    {"url": "http://m7-webhook:8080/retry"},
    {"hmac": ENV["M7_WEBHOOK_HMAC"]},
)
sftp = connector(
    "destinations",
    "SFTP",
    "SFTP",
    {
        "host": "m7-sftp",
        "port": 2222,
        "username": "synthetic",
        "target_folder": "uploads",
        "host_key": (RUNTIME / "test-services/ssh_host_rsa_key.pub").read_text().strip(),
        "artifacts": ["json", "xlsx"],
    },
    {"password": ENV["M7_SFTP_PASSWORD"]},
)
failed = connector(
    "destinations",
    "Failing webhook",
    "WEBHOOK",
    {"url": "http://m7-webhook:8080/fail"},
    {"hmac": ENV["M7_WEBHOOK_HMAC"]},
)
# Explicit new rule, reusing persisted identity on resume.
rule = {
    "name": "M7 " + state["run"],
    "document_type": "INVOICE",
    "case_state": "APPROVED",
    "destinations": [archive, webhook, sftp, failed],
    "priority": 10,
    "require_reviewed": False,
}
existing = next((r for r in api("GET", "/settings/routing") if r["name"] == rule["name"]), None)
api(
    "PUT" if existing else "POST",
    "/settings/routing" + ("/" + existing["id"] if existing else ""),
    json=rule,
)
state["destinations"] = {
    "archive": archive,
    "webhook": webhook,
    "sftp": sftp,
    "failed": failed,
}
save()
subject = "M7 email " + state["run"]
mid = "<m7-" + state["run"] + "@example.com>"
if not find_case(subject):
    email_send(subject, pdf("M7/" + state["run"]), "invoice.pdf", mid)
case = wait_for(lambda: find_case(subject))
cid = case["id"]
state["case_id"] = cid
save()
detail = api("GET", "/cases/" + cid)
assert detail["inbound_message"]["external_message_id"] == mid
assert detail["security_scans"][-1]["verdict"] == "SAFE"
assert detail["documents"][0]["document_type"] == "INVOICE"
check(
    "B_imap_real_pdf_m5_m6",
    {"case_id": cid, "document_type": "INVOICE", "security": "SAFE"},
)
if "C_duplicate_email" not in state["checks"]:
    email_send(subject, pdf("M7/" + state["run"]), "invoice.pdf", mid)
    wait_for(
        lambda: any(
            e["event_type"] == "EMAIL_DUPLICATE_IGNORED" or "DUPLICATE" in e["event_type"]
            for e in api("GET", "/cases/" + cid)["audit_events"]
        )
    )
assert api("GET", "/cases", params={"q": subject})["total"] == 1
check("C_duplicate_email")
watch_name = "M7-watched-" + state["run"] + ".pdf"
if not (RUNTIME / "incoming" / watch_name).exists():
    (RUNTIME / "incoming" / watch_name).write_bytes(pdf("WATCH/" + state["run"]))
watched = wait_for(lambda: find_case(watch_name))
check("D_watched_folder", {"case_id": watched["id"]})
if detail["status"] not in ["APPROVED", "EXPORTED"]:
    for doc in detail["ocr_documents"]:
        if not doc["reviewed"]:
            api(
                "POST",
                f"/ocr/{cid}/{doc['id']}/review",
                json={
                    "reason": "M7 E2E human verification against generated synthetic PDF",
                    "values": {
                        "document_number": "M7/" + state["run"],
                        "tax_id": "5260250274",
                        "issue_date": "2026-09-29",
                        "net_total": "100.00",
                        "vat_total": "23.00",
                        "gross_total": "123.00",
                        "currency": "PLN",
                    },
                },
            )
    detail = api(
        "PATCH",
        "/review/" + cid,
        json={
            "customer_name": "Synthetic Operator",
            "customer_email": "sender@example.com",
            "request_title": subject,
            "request_description": "Synthetic integration acceptance",
            "tax_id": "5260250274",
            "estimated_value": "123.00",
            "currency": "PLN",
        },
    )
    for doc in detail["documents"]:
        if doc["review_required"] and not doc["reviewed"]:
            api(
                "POST",
                f"/documents/{doc['id']}/review",
                json={
                    "revision": doc["revision"],
                    "reason": "Synthetic PDF visually verified for M7",
                    "cells": [],
                },
            )
    api("POST", f"/review/{cid}/approve")


def jobs_done():
    jobs = [j for j in api("GET", "/settings/jobs") if j["case_id"] == cid]
    return (
        jobs
        if len(jobs) == 4 and all(j["status"] in ["SUCCEEDED", "DEAD_LETTER"] for j in jobs)
        else None
    )


jobs = wait_for(jobs_done)
by_dest = {j["destination_id"]: j for j in jobs}
assert all(by_dest[d]["status"] == "SUCCEEDED" for d in [archive, webhook, sftp]), str(
    [(j["status"], j["last_error"]) for j in jobs]
)
assert by_dest[failed]["status"] == "DEAD_LETTER"
files = list((RUNTIME / "archive").rglob("*" + detail["public_id"] + "*"))
assert {p.suffix for p in files if p.is_file()} >= {".pdf", ".json", ".xlsx"}
check("E_filesystem_original_json_xlsx", {"files": len(files)})
receipts = httpx.get("http://localhost:8021/receipts").json()
receipt = next(r for r in receipts if r["idempotency_key"] == by_dest[webhook]["idempotency_key"])
assert receipt["signature_valid"] and receipt["same_body"] and receipt["attempts"] >= 2
check(
    "F_signed_webhook_retry",
    {"attempts": receipt["attempts"], "signature_valid": True, "byte_stable": True},
)
assert list((RUNTIME / "test-services/sftp/uploads" / detail["public_id"]).glob("*.json"))
check("G_sftp_pinned_host_key")
detail = api("GET", "/cases/" + cid)
assert any(t["task_type"] == "INTEGRATION_FAILURE" for t in detail["review_tasks"])
check("H_dead_letter_review_outbox", {"attempts": by_dest[failed]["attempts"]})
for role in ["VIEWER", "REVIEWER"]:
    email = role.lower() + "-m7@example.com"
    users = api("GET", "/settings/users")
    if not any(u["email"] == email for u in users):
        api(
            "POST",
            "/settings/users",
            json={
                "email": email,
                "password": ENV["BOAH_INITIAL_ADMIN_PASSWORD"],
                "role": role,
            },
        )
    with httpx.Client(base_url="http://localhost:8000/api/v1") as other:
        auth = other.post(
            "/auth/login",
            json={"email": email, "password": ENV["BOAH_INITIAL_ADMIN_PASSWORD"]},
        )
        assert auth.status_code == 200
        other.headers["X-CSRF-Token"] = auth.json()["csrf_token"]
        assert other.get("/settings/sources").status_code == 403
        assert other.post("/settings/destinations", json={}).status_code == 403
        assert other.get("/cases").status_code == 200
        other.post("/auth/logout")
check("I_J_viewer_reviewer_backend_403")
for path in [
    "/settings/export",
    "/settings/sources",
    "/settings/destinations",
    "/settings/audit",
]:
    value = json.dumps(api("GET", path))
    assert all(
        ENV[k] not in value
        for k in [
            "BOAH_MASTER_KEY",
            "BOAH_INITIAL_ADMIN_PASSWORD",
            "M7_MAIL_PASSWORD",
            "M7_SFTP_PASSWORD",
            "M7_WEBHOOK_HMAC",
            "BOAH_SERVICE_TOKEN",
        ]
    )
check("K_secrets_never_returned")
mal_subject = "M7 blocked " + state["run"]
if not find_case(mal_subject):
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    email_send(mal_subject, eicar, "test.txt", "<m7-eicar-" + state["run"] + "@example.com>")
mal = wait_for(lambda: find_case(mal_subject))
blocked = api("GET", "/cases/" + mal["id"])
assert blocked["security_scans"][-1]["verdict"] in ["BLOCKED", "QUARANTINED"]
assert not blocked["documents"] and not blocked["ocr_documents"]
assert client.post("/review/" + mal["id"] + "/approve").status_code == 409
check(
    "L_malicious_email_blocked_before_extraction",
    {"case_id": mal["id"], "verdict": blocked["security_scans"][-1]["verdict"]},
)
health = api("GET", "/system/health")
assert all(v == "HEALTHY" for v in health["checks"].values()), health["checks"]
check("live_system_health", health["checks"])
metrics = client.get("/system/metrics")
assert (
    metrics.status_code == 200
    and "boah_queue_depth" in metrics.text
    and "sender@example.com" not in metrics.text
)
check("metrics_without_pii")
REPORT.write_text(
    json.dumps(
        {
            "run": state["run"],
            "checks": state["checks"],
            "jobs": [{"status": j["status"], "attempts": j["attempts"]} for j in jobs],
        },
        indent=2,
    )
    + "\n"
)
print("Protocol E2E complete. Backup/restore is verified separately.", flush=True)
