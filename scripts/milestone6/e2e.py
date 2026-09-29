"""Live M6 scenarios A-F, correction/export, and durable M5 notifications."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fixtures import TYPES, fixture

ROOT = Path(__file__).resolve().parents[2]


def main():
    results = {"started_at": datetime.now(UTC).isoformat(), "checks": []}
    pending = set()
    with httpx.Client(base_url="http://localhost:8000/api/v1", timeout=180) as client:
        for kind in TYPES:
            data, truth = fixture(kind, 0, 161)
            response = client.post(
                "/cases",
                json={
                    "request_title": "M6 E2E " + kind,
                    "customer_name": "Synthetic operator",
                    "customer_email": "m6@example.com",
                },
            )
            response.raise_for_status()
            cid = response.json()["id"]
            response = client.post(
                f"/uploads/{cid}", files={"files": ("m6.pdf", data, "application/pdf")}
            )
            response.raise_for_status()
            case = response.json()
            doc = case["documents"][0]
            assert doc["document_type"] == kind
            assert case["security_scans"][0]["verdict"] == "SAFE"
            events = [e["event_type"] for e in case["audit_events"]]
            assert events.index("ATTACHMENT_SECURITY_SAFE") < events.index(
                "DOCUMENT_CLASSIFICATION_STARTED"
            )
            assert (
                client.get(f"/documents/{doc['id']}/preview").headers["content-type"] == "image/png"
            )
            if case["review_tasks"]:
                pending.add(cid)
            check = {
                "scenario": kind,
                "case_id": cid,
                "document_id": doc["id"],
                "status_before_review": case["status"],
                "passed": True,
            }
            if kind == "INVOICE":
                assert doc["strategy"] == "existing-m4-invoice" and case["ocr_documents"]
                check["invoice_route"] = case["ocr_documents"][0]["report"].get("route")
            else:
                assert case["status"] == "REVIEW_REQUIRED"
                assert client.post(f"/review/{cid}/approve").status_code == 409
            if kind == "HANDWRITTEN_TABLE":
                cells = doc["tables"][0]["cells"]
                assert any(c["uncertain"] and c["raw_value"] is None for c in cells)
                edits = [
                    {
                        "cell_id": c["id"],
                        "value": truth["tables"][0]["rows"][c["row"]][c["column"]],
                    }
                    for c in cells
                ]
                reviewed = client.post(
                    f"/documents/{doc['id']}/review",
                    json={
                        "revision": 0,
                        "reason": "M6 synthetic E2E original verified",
                        "cells": edits,
                    },
                )
                reviewed.raise_for_status()
                assert reviewed.json()["status"] == "READY"
                assert client.post(f"/review/{cid}/approve").status_code == 200
                exported = client.post(f"/exports/{cid}/json")
                exported.raise_for_status()
                assert exported.json()["documents"][0]["reviewed"]
                assert client.post(f"/exports/{cid}/xlsx").status_code == 201
                check["corrected_approved_exported"] = True
            results["checks"].append(check)
            print(kind, "PASS", flush=True)
        # Standard harmless antivirus test string, assembled only in memory.
        eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        cid = client.post("/cases", json={"request_title": "M6 E2E antivirus sentinel"}).json()[
            "id"
        ]
        response = client.post(
            f"/uploads/{cid}", files={"files": ("eicar.txt", eicar, "text/plain")}
        )
        response.raise_for_status()
        case = response.json()
        assert case["security_scans"][0]["verdict"] == "BLOCKED"
        assert not case["documents"] and not case["ocr_documents"]
        assert not any(
            e["event_type"] == "DOCUMENT_CLASSIFICATION_STARTED" for e in case["audit_events"]
        )
        assert client.post(f"/review/{cid}/approve").status_code == 409
        pending.add(cid)
        results["checks"].append(
            {
                "scenario": "MALICIOUS",
                "case_id": cid,
                "passed": True,
                "classification_invocations": 0,
            }
        )
        deadline = time.monotonic() + 50
        while pending and time.monotonic() < deadline:
            for cid in list(pending):
                case = client.get(f"/cases/{cid}").json()
                if any(e["event_type"] == "REVIEW_NOTIFICATION_SENT" for e in case["audit_events"]):
                    pending.remove(cid)
            if pending:
                time.sleep(1)
        assert not pending, "Missing durable n8n notification receipts"
    results["notifications_delivered"] = True
    results["completed_at"] = datetime.now(UTC).isoformat()
    (ROOT / "docs/milestone6/e2e-results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    print("Six live scenarios, correction/approval/export and notifications PASS")


if __name__ == "__main__":
    main()
