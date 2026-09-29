"""M6 live API evaluation. HOLDOUT is single-use and requires a verified freeze."""

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "datasets/milestone6"
OUT = ROOT / "docs/milestone6"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime():
    code = (
        "from app.core.config import settings; import json; "
        "print(json.dumps({k:v for k,v in settings.model_dump().items() "
        "if k.startswith(('ocr_', 'stp_', 'adaptive_', 'security_'))}))"
    )
    settings = json.loads(
        subprocess.check_output(
            ["docker", "compose", "exec", "-T", "backend", "python", "-c", code],
            cwd=ROOT,
            text=True,
        )
    )
    images = json.loads(
        subprocess.check_output(
            [
                "docker",
                "compose",
                "-f",
                "docker-compose.yml",
                "-f",
                "docker-compose.ocr.yml",
                "-f",
                "docker-compose.security.yml",
                "images",
                "--format",
                "json",
            ],
            cwd=ROOT,
            text=True,
        )
    )
    return {"settings": settings, "images": sorted({item["ID"] for item in images})}


def freeze():
    paths = []
    for pattern in (
        "backend/app/**/*.py",
        "backend/alembic/versions/ad14*.py",
        "scripts/milestone6/*.py",
        "datasets/milestone6/**/*.pdf",
        "datasets/milestone6/**/*.json",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "ocr-services/**/*.py",
        "ocr-services/**/requirements*.txt",
        "docker-compose*.yml",
    ):
        paths.extend(ROOT.glob(pattern))
    manifest = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(paths))}
    environment = runtime()
    identifier = hashlib.sha256(
        json.dumps({"files": manifest, "runtime": environment}, sort_keys=True).encode()
    ).hexdigest()
    value = {
        "id": identifier,
        "created_at": datetime.now(UTC).isoformat(),
        "profile": (
            "M6 local-signals-v1; native/grid; baseline layout OCR; "
            "handwriting unavailable; all non-invoices reviewed"
        ),
        "files": manifest,
        "runtime": environment,
    }
    target = ROOT / "configs/milestone6/freeze.json"
    with target.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2)
    print(identifier)


def evaluate(split):
    httpx.get("http://localhost:8000/health").raise_for_status()
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = None
    if split == "holdout":
        frozen = json.loads((ROOT / "configs/milestone6/freeze.json").read_text())
        assert all(sha(ROOT / p) == digest for p, digest in frozen["files"].items()), (
            "Freeze changed"
        )
        assert runtime() == frozen["runtime"], "Runtime changed"
        # Exclusive marker BEFORE any HOLDOUT document is opened or submitted.
        with (OUT / "holdout-started.json").open("x", encoding="utf-8") as f:
            json.dump(
                {
                    "freeze_id": frozen["id"],
                    "started_at": datetime.now(UTC).isoformat(),
                },
                f,
            )
    manifest = json.loads((DATA / f"{split}-manifest.json").read_text())
    rows = []
    with httpx.Client(base_url="http://localhost:8000/api/v1", timeout=180) as client:
        for item in manifest:
            truth = json.loads((DATA / item["truth"]).read_text())
            result = client.post(
                "/cases",
                json={
                    "request_title": f"M6 {split} {item['document']}",
                    "customer_name": "Synthetic operator",
                    "customer_email": "m6@example.com",
                },
            )
            result.raise_for_status()
            cid = result.json()["id"]
            path = DATA / item["document"]
            response = client.post(
                f"/uploads/{cid}",
                files={"files": (path.name, path.read_bytes(), "application/pdf")},
            )
            response.raise_for_status()
            case = response.json()
            doc = case["documents"][0]
            scans = case["security_scans"]
            assert scans and all(s["verdict"] == "SAFE" for s in scans)
            expected = truth["tables"]
            actual = doc["tables"]
            total = correct = numeric = numeric_correct = unresolved = fabricated = 0
            structure = len(actual) == len(expected)
            for ti, table in enumerate(expected):
                found = actual[ti] if ti < len(actual) else None
                structure &= bool(
                    found
                    and found["row_count"] == table["row_count"]
                    and found["column_count"] == table["column_count"]
                )
                values = {(c["row"], c["column"]): c for c in found["cells"]} if found else {}
                for r, line in enumerate(table["rows"]):
                    for c, target in enumerate(line):
                        cell = values.get((r, c), {})
                        value = cell.get("raw_value")
                        match = value is not None and str(value).strip() == str(target).strip()
                        uncertain = not cell or cell.get("uncertain") or value is None
                        total += 1
                        correct += match
                        unresolved += bool(uncertain)
                        if r > 0 and c > 0:
                            numeric += 1
                            numeric_correct += match
                            # Unsupported confident numeric output is an error, even when reviewed.
                            fabricated += bool(value is not None and not match and not uncertain)
            events = [e["event_type"] for e in case["audit_events"]]
            bypass = events.index("DOCUMENT_CLASSIFICATION_STARTED") < events.index(
                "ATTACHMENT_SECURITY_SAFE"
            )
            auto = case["status"] in ["READY", "APPROVED", "EXPORTED"]
            row = {
                "document": item["document"],
                "case_id": cid,
                "expected": truth["type"],
                "predicted": doc["document_type"],
                "confidence": doc["confidence"],
                "correct": doc["document_type"] == truth["type"],
                "review": not auto,
                "unknown": doc["document_type"] == "UNKNOWN",
                "table_document": bool(expected),
                "structure_correct": bool(structure),
                "cells": total,
                "correct_cells": correct,
                "numeric_cells": numeric,
                "correct_numeric_cells": numeric_correct,
                "unresolved": unresolved,
                "fabricated_critical_values": fabricated,
                "unknown_autoaccept": int(doc["document_type"] == "UNKNOWN" and auto),
                "low_confidence_bypass": int((unresolved > 0 or doc["confidence"] < 0.9) and auto),
                "security_bypass": int(bypass),
                "unsafe_high_confidence": int(
                    doc["document_type"] != truth["type"] and doc["confidence"] >= 0.9 and auto
                ),
            }
            rows.append(row)
            print(split, item["document"], row["predicted"], case["status"], flush=True)

    def ratio(a, b):
        return a / b if b else None

    metrics = {
        "documents": len(rows),
        "classification_accuracy": sum(r["correct"] for r in rows) / len(rows),
        "per_class_accuracy": {
            kind: sum(r["correct"] for r in rows if r["expected"] == kind)
            / sum(r["expected"] == kind for r in rows)
            for kind in sorted({r["expected"] for r in rows})
        },
        "unknown_rate": sum(r["unknown"] for r in rows) / len(rows),
        "review_rate": sum(r["review"] for r in rows) / len(rows),
        "structure_accuracy": ratio(
            sum(r["structure_correct"] for r in rows if r["table_document"]),
            sum(r["table_document"] for r in rows),
        ),
        "cell_accuracy": ratio(
            sum(r["correct_cells"] for r in rows), sum(r["cells"] for r in rows)
        ),
        "numeric_cell_accuracy": ratio(
            sum(r["correct_numeric_cells"] for r in rows),
            sum(r["numeric_cells"] for r in rows),
        ),
        "unresolved_rate": ratio(sum(r["unresolved"] for r in rows), sum(r["cells"] for r in rows)),
    }
    for key in [
        "fabricated_critical_values",
        "unknown_autoaccept",
        "low_confidence_bypass",
        "security_bypass",
        "unsafe_high_confidence",
    ]:
        metrics[key] = sum(r[key] for r in rows)
    result = {
        "split": split,
        "completed_at": datetime.now(UTC).isoformat(),
        "freeze_id": frozen["id"] if frozen else None,
        "metrics": metrics,
        "documents": rows,
    }
    (OUT / f"{split}-results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    with (OUT / f"{split}-results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT / f"{split}-results.md").write_text(
        f"# M6 {split.upper()}\n\nFreeze: {result['freeze_id']}\n\n| Metric | Value |\n|---|---|\n"
        + "".join(f"| {k} | {v} |\n" for k, v in metrics.items())
        + (
            "\nSynthetic data only; rasterized italic text is a handwriting-like proxy, "
            "not human handwriting. Missing cells count as incorrect. "
            "No ground truth enters the API.\n"
        ),
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["dev", "freeze", "holdout"])
    args = parser.parse_args()
    freeze() if args.action == "freeze" else evaluate(args.action)
