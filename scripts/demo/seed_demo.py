"""API-only seed/verification for the explicitly marked isolated synthetic demo."""

import argparse
import json
import os
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

import httpx

RUNTIME = Path("/demo-runtime")
FIXTURES = Path("/demo-fixtures")
BASE = "http://backend:8000/api/v1"
PREFIX = "[DEMO] "


def guard():
    if (
        os.environ.get("BOAH_DEMO_INSTANCE") != "portfolio-v1"
        or os.environ.get("APP_ENV") != "development"
    ):
        raise RuntimeError("Seed is restricted to the explicit local portfolio demo instance")
    identity = json.loads((RUNTIME / "identity.json").read_text(encoding="utf-8-sig"))
    if identity != {"project": "boah-portfolio-demo", "kind": "BOAH_M8_SYNTHETIC_DEMO"}:
        raise RuntimeError("Unexpected demo runtime identity")


def session():
    client = httpx.Client(base_url=BASE, timeout=180)
    result = client.post(
        "/auth/login",
        json={
            "email": os.environ["BOAH_INITIAL_ADMIN_EMAIL"],
            "password": os.environ["BOAH_INITIAL_ADMIN_PASSWORD"],
        },
    )
    result.raise_for_status()
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    company = call(client, "GET", "/settings/company")
    if company.get("configured") and company.get("identifier") != "DEMO-ONLY":
        raise RuntimeError("Existing company is not the synthetic demo; no seed changes made")
    return client


def call(client, method, path, **kwargs):
    result = client.request(method, path, **kwargs)
    if not result.is_success:
        raise RuntimeError(f"Demo API {method} {path}: HTTP {result.status_code}")
    return result.json() if result.content else None


def wait(fn, timeout=180):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = fn()
        if result:
            return result
        time.sleep(2)
    raise TimeoutError("Demo timed out; inspect the isolated project logs")


def existing_case(client, title):
    return next(
        (
            c
            for c in call(client, "GET", "/cases", params={"q": PREFIX + title})["items"]
            if c["request_title"] == PREFIX + title
        ),
        None,
    )


def create_case(client, title, fixture):
    existing = existing_case(client, title)
    case = (
        call(client, "GET", "/cases/" + existing["id"])
        if existing
        else call(
            client,
            "POST",
            "/cases",
            json={
                "source": "manual_upload",
                "customer_name": "Fictional Demo Operator",
                "company_name": "Northstar Demo Workshops",
                "customer_email": "operator@example.com",
                "request_title": PREFIX + title,
                "request_description": "Synthetic portfolio demonstration; not evaluation data.",
                "currency": "PLN",
            },
        )
    )
    if not case["attachments"]:
        path = FIXTURES / fixture
        case = call(
            client,
            "POST",
            "/uploads/" + case["id"],
            files={
                "files": (
                    path.name,
                    path.read_bytes(),
                    "application/pdf" if path.suffix == ".pdf" else "text/plain",
                )
            },
        )
    return case


def review_invoice(client, case, fields):
    if case["status"] in ["APPROVED", "EXPORTED"]:
        return case
    for document in case["ocr_documents"]:
        case = call(
            client,
            "POST",
            f"/ocr/{case['id']}/{document['id']}/review",
            json={
                "reason": (
                    "Demo seed: explicit confirmation against the synthetic original, "
                    "not independent extraction accuracy."
                ),
                "values": fields,
            },
        )
    case = call(
        client,
        "PATCH",
        "/review/" + case["id"],
        json={
            "customer_name": "Fictional Demo Operator",
            "request_title": case["request_title"],
            "tax_id": fields["tax_id"],
            "estimated_value": fields["gross_total"],
            "currency": fields["currency"],
        },
    )
    event_types = [event["event_type"] for event in case["audit_events"]]
    assert event_types.index("ATTACHMENT_SECURITY_SAFE") < event_types.index(
        "DOCUMENT_CLASSIFICATION_STARTED"
    )
    for document in case["documents"]:
        if document["review_required"] and not document["reviewed"]:
            case = call(
                client,
                "POST",
                f"/documents/{document['id']}/review",
                json={
                    "revision": document["revision"],
                    "reason": "Synthetic invoice reviewed against original for demonstration.",
                    "cells": [],
                },
            )
    assert case["status"] == "READY", [
        (i["code"], i["resolved"]) for i in case["validation_issues"]
    ]
    return case


def finish_invoice(client, case, fields):
    case = review_invoice(client, case, fields)
    if case["status"] not in ["APPROVED", "EXPORTED"]:
        case = call(client, "POST", "/review/" + case["id"] + "/approve")
    for kind in ["json", "xlsx"]:
        if not any(e["export_type"] == kind for e in case["exports"]):
            response = client.post(f"/exports/{case['id']}/{kind}")
            response.raise_for_status()
            assert response.status_code == 201
    return call(client, "GET", "/cases/" + case["id"])


def prepare_n8n():
    destination = RUNTIME / "n8n"
    destination.mkdir(exist_ok=True)
    credential = [
        {
            "id": "boahDemoService",
            "name": "BOAH demo scoped service",
            "type": "httpHeaderAuth",
            "data": {
                "name": "Authorization",
                "value": "Bearer " + os.environ["BOAH_SERVICE_TOKEN"],
            },
        }
    ]
    workflow = json.loads(
        Path("/demo-workflows/review-notifications.json").read_text(encoding="utf-8-sig")
    )
    for node in workflow["nodes"]:
        if node["type"] == "n8n-nodes-base.httpRequest" and "backend:8000/api/v1/" in node.get(
            "parameters", {}
        ).get("url", ""):
            node["parameters"].update(
                authentication="genericCredentialType", genericAuthType="httpHeaderAuth"
            )
            node["credentials"] = {
                "httpHeaderAuth": {"id": "boahDemoService", "name": "BOAH demo scoped service"}
            }
    for name, data in [("credential.json", credential), ("workflow.json", workflow)]:
        path = destination / name
        path.write_text(json.dumps(data), encoding="utf-8")
        path.chmod(0o600)
    print("Prepared ignored local n8n runtime configuration; no credential values printed.")


def seed(client):
    if not call(client, "GET", "/settings/company").get("configured"):
        call(
            client,
            "PUT",
            "/settings/company",
            json={
                "company_name": "Northstar Demo Workshops",
                "identifier": "DEMO-ONLY",
                "timezone": "Europe/Warsaw",
                "locale": "pl-PL",
                "currency": "PLN",
                "notifications": {
                    "review": "review@example.com",
                    "security": "security@example.com",
                    "integration": "integrations@example.com",
                    "operations": "operations@example.com",
                },
            },
        )
    users = call(client, "GET", "/settings/users")
    login = [
        "LOCAL SYNTHETIC DEMO ONLY - http://localhost:3080",
        f"ADMIN: {os.environ['BOAH_INITIAL_ADMIN_EMAIL']} / "
        f"{os.environ['BOAH_INITIAL_ADMIN_PASSWORD']}",
    ]
    for role in ["OPERATOR", "REVIEWER", "VIEWER"]:
        email = role.lower() + "@example.com"
        password = os.environ["M8_" + role + "_PASSWORD"]
        if not any(u["email"] == email for u in users):
            call(
                client,
                "POST",
                "/settings/users",
                json={"email": email, "password": password, "role": role},
            )
        login.append(f"{role}: {email} / {password}")
    (RUNTIME / "login.txt").write_text("\n".join(login) + "\n", encoding="utf-8")
    (RUNTIME / "login.txt").chmod(0o600)

    def connector(collection, name, kind, config, secret=None):
        current = next(
            (r for r in call(client, "GET", "/settings/" + collection) if r["name"] == name), None
        )
        if current:
            return current
        body = {
            "name": name,
            "kind": kind,
            "enabled": True,
            "config": config,
            "interval_seconds": 10,
        }
        if secret:
            body["secret"] = secret
        return call(client, "POST", "/settings/" + collection, json=body)

    archive = connector(
        "destinations",
        "Demo archive",
        "FILESYSTEM",
        {"root": "archive", "artifacts": ["original", "json", "xlsx"]},
    )
    webhook = connector(
        "destinations",
        "Demo signed webhook",
        "WEBHOOK",
        {"url": "http://webhook:8080/retry"},
        {"hmac": os.environ["M7_WEBHOOK_HMAC"]},
    )
    sources = [
        connector(
            "sources",
            "Demo watched folder",
            "WATCHED_FOLDER",
            {"root": "incoming", "stable_seconds": 2},
        ),
        connector(
            "sources",
            "Demo local IMAP",
            "IMAP",
            {
                "host": "greenmail",
                "port": 3143,
                "tls": False,
                "username": "synthetic",
                "folder": "INBOX",
            },
            {"password": os.environ["M7_MAIL_PASSWORD"]},
        ),
    ]
    if not any(
        r["name"] == "Demo approved invoices" for r in call(client, "GET", "/settings/routing")
    ):
        call(
            client,
            "POST",
            "/settings/routing",
            json={
                "name": "Demo approved invoices",
                "priority": 10,
                "document_type": "INVOICE",
                "case_state": "APPROVED",
                "require_reviewed": False,
                "destinations": [archive["id"], webhook["id"]],
            },
        )
    manifest = json.loads((FIXTURES / "manifest.json").read_text())["fixtures"]
    titles = {
        "invoice-ready.pdf": "Completed invoice",
        "invoice-review.pdf": "Invoice needs review",
        "printed-table.pdf": "Printed score table",
        "handwritten-table-like.pdf": "Handwritten-like table - review required",
        "generic-document.pdf": "Operations memo",
        "unknown.pdf": "Unknown document",
        "blocked-sample.exe.txt": "Blocked filename policy - harmless text",
    }
    cases = []
    for fixture in manifest:
        case = create_case(client, titles[fixture["file"]], fixture["file"])
        if fixture["type"] == "BLOCKED":
            assert case["security_scans"][0]["verdict"] == "BLOCKED"
            assert not case["documents"] and not case["ocr_documents"]
            assert client.post("/review/" + case["id"] + "/approve").status_code == 409
        else:
            assert case["security_scans"][0]["verdict"] == "SAFE"
            assert case["documents"][0]["document_type"] == fixture["type"], (
                fixture["file"],
                case["documents"][0]["document_type"],
            )
            if fixture["file"] == "invoice-ready.pdf":
                case = finish_invoice(client, case, fixture["review_values"])
            elif fixture["type"] != "INVOICE" or fixture.get("review_exercise"):
                assert case["status"] == "REVIEW_REQUIRED", fixture["file"]
                assert client.post("/review/" + case["id"] + "/approve").status_code == 409
        cases.append(
            {
                "title": case["request_title"],
                "case_id": case["id"],
                "status": case["status"],
                "fixture": fixture["file"],
                "document_type": case["documents"][0]["document_type"]
                if case["documents"]
                else None,
            }
        )
        print(case["request_title"] + ": " + case["status"], flush=True)
    for source in sources:
        job = call(client, "POST", f"/settings/sources/{source['id']}/test")
        wait(
            lambda job_id=job["id"]: next(
                (
                    j
                    for j in call(client, "GET", "/settings/jobs")
                    if j["id"] == job_id and j["status"] == "SUCCEEDED"
                ),
                None,
            )
        )
    wait(lambda: call(client, "GET", "/system/health")["status"] == "HEALTHY")
    (RUNTIME / "seed-state.json").write_text(
        json.dumps({"cases": cases, "destinations": [archive["id"], webhook["id"]]}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return cases


def verify(client):
    fixture = json.loads((FIXTURES / "manifest.json").read_text())["fixtures"][1]
    case = create_case(client, "Live flow verification", fixture["file"])
    if case["status"] not in ["APPROVED", "EXPORTED"]:
        assert case["status"] == "REVIEW_REQUIRED"
        assert client.post("/review/" + case["id"] + "/approve").status_code == 409
    case = finish_invoice(client, case, fixture["review_values"])

    def completed_jobs():
        jobs = [
            j
            for j in call(client, "GET", "/settings/jobs")
            if j["case_id"] == case["id"] and j["kind"] == "DELIVERY"
        ]
        return jobs if len(jobs) == 2 and all(j["status"] == "SUCCEEDED" for j in jobs) else None

    jobs = wait(completed_jobs)
    receipts = httpx.get("http://webhook:8080/receipts", timeout=10).json()
    assert any(
        r["signature_valid"]
        and r["same_body"]
        and r["attempts"] >= 2
        and r["idempotency_key"] in {j["idempotency_key"] for j in jobs}
        for r in receipts
    )
    original = list((RUNTIME / "archive").rglob("*" + case["public_id"] + "*"))
    assert {p.suffix for p in original if p.is_file()} >= {".pdf", ".json", ".xlsx"}
    assert {"OCR_HUMAN_REVIEW", "case_approved", "export_generated"} <= {
        e["event_type"] for e in case["audit_events"]
    }
    event_types = [event["event_type"] for event in case["audit_events"]]
    assert event_types.index("ATTACHMENT_SECURITY_SAFE") < event_types.index(
        "DOCUMENT_CLASSIFICATION_STARTED"
    )
    for document in case["documents"]:
        assert client.get("/documents/" + document["id"] + "/preview").status_code == 200
    health = call(client, "GET", "/system/health")
    assert health["status"] == "HEALTHY"
    assert client.get("/documents/summary").status_code == 200
    metrics = client.get("/system/metrics")
    assert metrics.status_code == 200 and "admin@example.com" not in metrics.text
    report = {
        "status": "PASS",
        "login_dashboard_case_document_review_approve_export_delivery_audit": True,
        "case_id": case["id"],
        "status_after": case["status"],
        "delivery_jobs": [{"status": j["status"], "attempts": j["attempts"]} for j in jobs],
        "signed_webhook": True,
        "original_json_xlsx_archive": True,
        "security_before_classification": True,
        "service_checks": health["checks"],
        "synthetic_only": True,
        "holdout_used": False,
    }
    (RUNTIME / "verification.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report), flush=True)


def email_demo(client):
    subject = PREFIX + "Optional local email"
    if not existing_case(client, "Optional local email"):
        msg = EmailMessage()
        msg["From"] = "sender@example.com"
        msg["To"] = "synthetic@example.com"
        msg["Subject"] = subject
        msg["Message-ID"] = "<boah-portfolio-email@example.com>"
        msg.set_content("Synthetic local email demo. No real mailbox is used.")
        msg.add_attachment(
            (FIXTURES / "invoice-ready.pdf").read_bytes(),
            maintype="application",
            subtype="pdf",
            filename="demo-email-invoice.pdf",
        )
        with smtplib.SMTP("greenmail", 3025, timeout=20) as smtp:
            smtp.send_message(msg)
    case = wait(lambda: existing_case(client, "Optional local email"))
    detail = call(client, "GET", "/cases/" + case["id"])
    assert (
        detail["security_scans"][0]["verdict"] == "SAFE"
        and detail["documents"][0]["document_type"] == "INVOICE"
    )
    (RUNTIME / "email-result.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "case_id": case["id"],
                "smtp_imap_real_local": True,
                "security": "SAFE",
                "classification": "INVOICE",
                "synthetic_only": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Real local SMTP -> IMAP -> SAFE -> INVOICE: PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["seed", "verify", "email", "prepare-n8n"])
    args = parser.parse_args()
    guard()
    if args.action == "prepare-n8n":
        prepare_n8n()
        return
    client = session()
    try:
        {"seed": seed, "verify": verify, "email": email_demo}[args.action](client)
    finally:
        try:
            client.post("/auth/logout")
        finally:
            client.close()


if __name__ == "__main__":
    main()
