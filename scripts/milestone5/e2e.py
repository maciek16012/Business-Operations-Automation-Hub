"""M5 only: synthetic live-stack checks. Never reads any M3/M4 dataset/HOLDOUT."""

import argparse
import json
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import httpx
import pymupdf
from PIL import Image


def fixtures():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (60, 60),
        "Faktura: M5/TEST/2026\nNIP: 5260250274\n"
        "Data wystawienia: 2026-01-10\nNetto: 1000,00\nVAT: 230,00\n"
        "Brutto: 1230,00\nWaluta: PLN\nSynthetic public test fixture",
        fontsize=14,
    )
    pdf = doc.tobytes(no_new_id=True)
    png = page.get_pixmap(dpi=150).tobytes("png")
    image = Image.open(BytesIO(png)).convert("RGB")
    jpeg = BytesIO()
    image.save(jpeg, format="JPEG", quality=90)
    doc.close()
    return {
        "native_pdf": ("m5.pdf", pdf, "application/pdf", "SAFE"),
        "scan_png": ("m5.png", png, "image/png", "SAFE"),
        "scan_jpeg": ("m5.jpg", jpeg.getvalue(), "image/jpeg", "SAFE"),
        "spoof_extension": ("m5.png", pdf, "image/png", "QUARANTINED"),
        "spoof_mime": ("m5.pdf", pdf, "image/png", "QUARANTINED"),
        "executable": ("m5.pdf", b"MZ harmless synthetic bytes", "application/pdf", "BLOCKED"),
        "eicar": (
            "eicar.txt",
            b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*",
            "text/plain",
            "BLOCKED",
        ),
        "unsupported": (
            "m5.bin",
            b"\x00\x01\x02 synthetic",
            "application/octet-stream",
            "QUARANTINED",
        ),
        "archive": ("m5.zip", b"PK\x03\x04 harmless metadata", "application/zip", "QUARANTINED"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = {"started_at": datetime.now(UTC).isoformat(), "checks": []}
    with httpx.Client(base_url="http://localhost:8000/api/v1", timeout=180) as client:
        data = fixtures()
        for name, (filename, content, mime, expected) in data.items():
            response = client.post(
                "/cases",
                json={
                    "customer_name": "Synthetic M5",
                    "customer_email": "m5@example.com",
                    "request_title": f"M5 E2E {name}",
                },
            )
            response.raise_for_status()
            cid = response.json()["id"]
            response = client.post(f"/uploads/{cid}", files={"files": (filename, content, mime)})
            response.raise_for_status()
            case = response.json()
            scan = case["security_scans"][0]
            assert scan["verdict"] == expected, (name, scan)
            if expected != "SAFE":
                assert not case["ocr_documents"] and not case["extracted_fields"]
                assert client.post(f"/review/{cid}/approve").status_code == 409
                task = case["review_tasks"][0]
                decision = client.post(
                    f"/review-tasks/{task['id']}/decision",
                    json={"action": "acknowledge", "reason": "M5 synthetic E2E investigation"},
                )
                decision.raise_for_status()
                assert (
                    client.post(
                        f"/review-tasks/{task['id']}/decision",
                        json={"action": "resolve", "reason": "No bypass permitted"},
                    ).status_code
                    == 409
                )
            else:
                assert case["ocr_documents"], name
            results["checks"].append(
                {
                    "scenario": name,
                    "case_id": cid,
                    "verdict": scan["verdict"],
                    "reason": scan["reason"],
                    "scanner_version": scan["scanner_version"],
                    "threat_name": scan["threat_name"],
                    "routes": [d["report"].get("route") for d in case["ocr_documents"]],
                    "task_count": len(case["review_tasks"]),
                    "passed": True,
                }
            )
            print(name, scan["verdict"], flush=True)
        cid = client.post("/cases", json={"request_title": "M5 mixed synthetic"}).json()["id"]
        response = client.post(
            f"/uploads/{cid}",
            files=[
                ("files", data["native_pdf"][:3]),
                ("files", data["executable"][:3]),
                ("files", ("clean.txt", b"Currency: PLN", "text/plain")),
            ],
        )
        response.raise_for_status()
        mixed = response.json()
        assert [s["verdict"] for s in mixed["security_scans"]] == ["SAFE", "BLOCKED", "SAFE"]
        assert client.post(f"/review/{cid}/approve").status_code == 409
        results["checks"].append({"scenario": "mixed", "case_id": cid, "passed": True})
        # The persisted SENT audit requires matching n8n/local sink receipt.
        deadline = time.monotonic() + 50
        pending = {r["case_id"] for r in results["checks"] if r.get("task_count", 1)}
        while pending and time.monotonic() < deadline:
            for cid in list(pending):
                case = client.get(f"/cases/{cid}").json()
                if any(a["event_type"] == "REVIEW_NOTIFICATION_SENT" for a in case["audit_events"]):
                    pending.remove(cid)
            if pending:
                time.sleep(1)
        assert not pending, f"Missing durable n8n receipts: {pending}"
        results["notifications_delivered"] = True
    results["completed_at"] = datetime.now(UTC).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("E2E passed; evidence:", args.output)


if __name__ == "__main__":
    main()
