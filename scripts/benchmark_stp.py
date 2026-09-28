"""Milestone 4 STP benchmark.

DEV may be executed repeatedly.
HOLDOUT requires a prior SHA-256 freeze and may be executed once.
Ground truth is used only after routing/processing to evaluate decisions.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import math
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from app.document_routing.processor import process_document
from app.ocr.pipeline import FIELDS, normalize_field


CONFIG_PATH = ROOT / "configs" / "stp" / "benchmark.json"
DATASET_ROOT = ROOT / "datasets" / "stp"
FREEZE_PATH = ROOT / "configs" / "stp" / "freeze.json"
HOLDOUT_MARKER = DATASET_ROOT / "holdout-executed.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mime_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(suffix, "application/octet-stream")


def nearest_rank_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def configure_runtime(config: dict) -> None:
    settings.stp_enabled = True

    profiles = config["profiles"]
    settings.ocr_tesseract_profile = profiles["tesseract"]
    settings.ocr_paddle_profile = profiles["paddle"]

    routing = config["routing"]
    settings.stp_target_rate = routing["target_stp_rate"]
    settings.stp_primary_ocr_provider = routing["primary_ocr_provider"]

    native = routing["native_text"]
    settings.stp_native_min_chars_per_page = native["min_chars_per_page"]
    settings.stp_native_min_alnum_ratio = native["min_alnum_ratio"]
    settings.stp_native_min_printable_ratio = native["min_printable_ratio"]
    settings.stp_native_min_text_page_ratio = native["min_text_page_ratio"]
    settings.stp_native_max_image_area_ratio = native["max_image_area_ratio"]


def normalized_truth(gt: dict) -> dict[str, str | None]:
    return {
        field: normalize_field(field, gt["fields"].get(field))
        for field in FIELDS
    }


def normalized_selected(report: dict) -> dict[str, str | None]:
    selected = report.get("selected") or {}
    return {
        field: normalize_field(field, selected.get(field))
        if selected.get(field) is not None
        else None
        for field in FIELDS
    }


def decision_for(report: dict) -> str:
    if report.get("outcome") == "BOTH_FAILED":
        return "PROCESSING_FAILED"

    if (
        report.get("route") == "NATIVE_TEXT"
        and report.get("stp", {}).get("candidate") is True
    ):
        # Benchmark the candidate as hypothetical AUTO_ACCEPT.
        # Ground truth is checked only afterwards.
        return "AUTO_ACCEPT"

    if report.get("review_required") is False:
        return "AUTO_ACCEPT"

    return "REVIEW_REQUIRED"


def ocr_invocations(report: dict) -> int:
    route = report.get("route")

    if route == "NATIVE_TEXT":
        return 0
    if route == "PRIMARY_OCR":
        return 1
    if route == "DUAL_OCR":
        return 2

    providers = report.get("providers") or []
    return len([p for p in providers if p.get("provider") in {"tesseract", "paddle"}])


def freeze() -> None:
    if FREEZE_PATH.exists():
        raise SystemExit("STP freeze already exists; refusing to overwrite it")

    files: list[Path] = [
        CONFIG_PATH,
        ROOT / "configs" / "stp" / "policy.json",
        ROOT / "scripts" / "benchmark_stp.py",
        ROOT / "scripts" / "generate_stp_dataset.py",
        DATASET_ROOT / "manifests" / "dataset.json",
        ROOT / "backend" / "pyproject.toml",
        ROOT / "backend" / "uv.lock",
    ]

    files += sorted((ROOT / "backend" / "app" / "document_routing").rglob("*.py"))
    files += sorted((ROOT / "backend" / "app" / "ocr").rglob("*.py"))

    for directory in ("input", "ground_truth"):
        files += sorted((DATASET_ROOT / directory).rglob("*.*"))

    for optional in (
        ROOT / "docker-compose.ocr.yml",
        ROOT / "configs" / "ocr-model-hashes.json",
    ):
        if optional.exists():
            files.append(optional)

    files += sorted((ROOT / "ocr-services").rglob("server.py"))
    files += sorted((ROOT / "ocr-services").rglob("Dockerfile"))
    files += sorted((ROOT / "ocr-services").rglob("installed-versions.txt"))

    unique_files = sorted(set(path.resolve() for path in files if path.is_file()))

    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "files": {
            path.relative_to(ROOT).as_posix(): sha256(path)
            for path in unique_files
        },
    }

    FREEZE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        "M4 STP code/config/dataset frozen. "
        "HOLDOUT has not been evaluated."
    )


def verify_freeze() -> dict:
    if not FREEZE_PATH.exists():
        raise SystemExit("HOLDOUT requires configs/stp/freeze.json")

    frozen = json.loads(FREEZE_PATH.read_text(encoding="utf-8-sig"))

    for relative, digest in frozen["files"].items():
        path = ROOT / relative
        if not path.exists():
            raise SystemExit(f"Frozen file missing: {relative}")
        current = sha256(path)
        if current != digest:
            raise SystemExit(f"Frozen file changed: {relative}")

    return frozen


async def benchmark(split: str, name: str) -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    configure_runtime(config)

    if split == "holdout":
        frozen = verify_freeze()

        if HOLDOUT_MARKER.exists():
            raise SystemExit(
                "M4 HOLDOUT was already started/executed; refusing a second run"
            )

        marker = {
            "started_at": datetime.now(UTC).isoformat(),
            "freeze_sha256": sha256(FREEZE_PATH),
            "freeze_created_at": frozen["created_at"],
        }

        with HOLDOUT_MARKER.open("x", encoding="utf-8") as handle:
            json.dump(marker, handle, ensure_ascii=False, indent=2)

    output = DATASET_ROOT / "results" / name
    output.mkdir(parents=True, exist_ok=False)

    truth_dir = DATASET_ROOT / "ground_truth" / split
    truth_paths = sorted(truth_dir.glob("*.json"))

    if not truth_paths:
        raise SystemExit(f"No ground-truth documents found for split: {split}")

    records: list[dict] = []

    for truth_path in truth_paths:
        gt = json.loads(truth_path.read_text(encoding="utf-8-sig"))
        source = ROOT / gt["source_file"]
        content = source.read_bytes()

        started = time.perf_counter()

        try:
            report = await process_document(
                document_id=gt["document_id"],
                filename=source.name,
                mime_type=mime_for(source),
                content=content,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            processing_exception = None
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            report = {
                "route": "PROCESSING_FAILED",
                "outcome": "PROCESSING_FAILED",
                "review_required": True,
                "selected": {},
                "providers": [],
            }
            processing_exception = f"{type(exc).__name__}: {exc}"

        decision = decision_for(report)
        truth = normalized_truth(gt)
        selected = normalized_selected(report)

        fields = {
            field: {
                "ground_truth": truth[field],
                "selected": selected[field],
                "correct": selected[field] == truth[field],
            }
            for field in FIELDS
        }

        incorrect_fields = [
            field
            for field in FIELDS
            if selected[field] != truth[field]
        ]

        route = report.get("route") or "DUAL_OCR"

        record = {
            "document_id": gt["document_id"],
            "style": gt["conditions"][0],
            "document_class": gt.get("document_class"),
            "challenge_tags": gt.get("challenge_tags", []),
            "source_file": gt["source_file"],
            "route": route,
            "outcome": report.get("outcome"),
            "decision": decision,
            "review_required": report.get("review_required", True),
            "processing_time_ms": elapsed_ms,
            "ocr_invocations": ocr_invocations(report),
            "incorrect_critical_fields": incorrect_fields,
            "all_critical_fields_correct": not incorrect_fields,
            "fields": fields,
            "processing_exception": processing_exception,
        }

        records.append(record)

        (output / f"{gt['document_id']}-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(
            gt["document_id"],
            route,
            decision,
            "OK" if not incorrect_fields else f"WRONG:{','.join(incorrect_fields)}",
            flush=True,
        )

    total_documents = len(records)
    accepted = [row for row in records if row["decision"] == "AUTO_ACCEPT"]
    reviewed = [row for row in records if row["decision"] == "REVIEW_REQUIRED"]
    failed = [row for row in records if row["decision"] == "PROCESSING_FAILED"]

    accepted_field_count = len(accepted) * len(FIELDS)
    accepted_incorrect_fields = sum(
        len(row["incorrect_critical_fields"])
        for row in accepted
    )
    accepted_wrong_documents = sum(
        not row["all_critical_fields_correct"]
        for row in accepted
    )

    route_counts = {
        route: sum(row["route"] == route for row in records)
        for route in ("NATIVE_TEXT", "PRIMARY_OCR", "DUAL_OCR", "HUMAN_REVIEW")
    }

    latencies = [row["processing_time_ms"] for row in records]

    summary = {
        "documents": total_documents,
        "auto_accept_documents": len(accepted),
        "review_required_documents": len(reviewed),
        "processing_failed_documents": len(failed),
        "stp_rate": len(accepted) / total_documents,
        "manual_review_rate": len(reviewed) / total_documents,
        "processing_failure_rate": len(failed) / total_documents,
        "critical_field_false_accept_count": accepted_incorrect_fields,
        "critical_field_false_accept_rate": (
            accepted_incorrect_fields / accepted_field_count
            if accepted_field_count
            else 0.0
        ),
        "document_false_accept_count": accepted_wrong_documents,
        "document_false_accept_rate": (
            accepted_wrong_documents / len(accepted)
            if accepted
            else 0.0
        ),
        "native_text_route_rate": route_counts["NATIVE_TEXT"] / total_documents,
        "primary_ocr_route_rate": route_counts["PRIMARY_OCR"] / total_documents,
        "dual_ocr_route_rate": route_counts["DUAL_OCR"] / total_documents,
        "human_review_route_rate": route_counts["HUMAN_REVIEW"] / total_documents,
        "mean_processing_time_ms": statistics.mean(latencies),
        "p95_processing_time_ms": nearest_rank_p95(latencies),
        "mean_ocr_invocations_per_document": statistics.mean(
            row["ocr_invocations"] for row in records
        ),
        "hard_safety_constraint_passed": accepted_incorrect_fields == 0,
        "target_stp_rate": config["routing"]["target_stp_rate"],
        "target_stp_rate_met": (
            len(accepted) / total_documents
            >= config["routing"]["target_stp_rate"]
        ),
        "route_counts": route_counts,
    }

    report = {
        "benchmark_version": config["benchmark_version"],
        "split": split,
        "created_at": datetime.now(UTC).isoformat(),
        "profiles": config["profiles"],
        "routing_config": config["routing"],
        "summary": summary,
        "records": records,
    }

    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with (output / "report.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "document_id",
                "style",
                "document_class",
                "route",
                "decision",
                "processing_time_ms",
                "ocr_invocations",
                "all_critical_fields_correct",
                "incorrect_critical_fields",
            ]
        )

        for row in records:
            writer.writerow(
                [
                    row["document_id"],
                    row["style"],
                    row["document_class"],
                    row["route"],
                    row["decision"],
                    f"{row['processing_time_ms']:.3f}",
                    row["ocr_invocations"],
                    row["all_critical_fields_correct"],
                    ",".join(row["incorrect_critical_fields"]),
                ]
            )

    markdown = (
        f"# Milestone 4 STP benchmark — {split}\n\n"
        f"- Documents: {summary['documents']}\n"
        f"- STP rate: {summary['stp_rate']:.2%}\n"
        f"- Manual review rate: {summary['manual_review_rate']:.2%}\n"
        f"- Critical-field false accepts: "
        f"{summary['critical_field_false_accept_count']}\n"
        f"- Document false accepts: "
        f"{summary['document_false_accept_count']}\n"
        f"- Safety constraint passed: "
        f"{summary['hard_safety_constraint_passed']}\n"
        f"- Mean processing time: "
        f"{summary['mean_processing_time_ms']:.1f} ms\n"
        f"- p95 processing time: "
        f"{summary['p95_processing_time_ms']:.1f} ms\n"
        f"- Mean OCR invocations/document: "
        f"{summary['mean_ocr_invocations_per_document']:.2f}\n\n"
        "## Routes\n\n"
        f"```json\n{json.dumps(route_counts, indent=2)}\n```\n"
    )

    (output / "report.md").write_text(markdown, encoding="utf-8")

    if split == "holdout":
        marker = json.loads(HOLDOUT_MARKER.read_text(encoding="utf-8"))
        marker["completed_at"] = datetime.now(UTC).isoformat()
        marker["result_directory"] = output.relative_to(ROOT).as_posix()
        marker["summary"] = summary
        HOLDOUT_MARKER.write_text(
            json.dumps(marker, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("dev", "holdout"), default="dev")
    parser.add_argument("--name", default="stp-dev-baseline")
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()

    if args.freeze:
        freeze()
    else:
        asyncio.run(benchmark(args.split, args.name))

