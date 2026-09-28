"""Reproducible DEV experiments, immutable freeze, one final HOLDOUT run."""

import argparse, asyncio, csv, hashlib, json, math, statistics, sys
from datetime import datetime, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ocr.pipeline import FIELDS, compare, extract_fields, infer, normalize_field


def distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        curr = [i]
        for j, y in enumerate(b, 1):
            curr.append(min(curr[-1] + 1, prev[j] + 1, prev[j - 1] + (x != y)))
        prev = curr
    return prev[-1]


def metrics(records):
    summary = {}
    for engine in ("tesseract", "paddle"):
        rows = [x for x in records if x["provider"] == engine]
        lat = [x["latency_ms"] for x in rows]
        count = len(rows) * len(FIELDS)
        summary[engine] = {
            "documents": len(rows),
            "cer": sum(x["char_errors"] for x in rows)
            / sum(x["characters"] for x in rows),
            "wer": sum(x["word_errors"] for x in rows) / sum(x["words"] for x in rows),
            "exact_field_accuracy": sum(x["exact_correct"] for x in rows) / count,
            "normalized_field_accuracy": sum(x["normalized_correct"] for x in rows)
            / count,
            "critical_field_accuracy": sum(x["normalized_correct"] for x in rows)
            / count,
            "provider_failure_rate": sum(bool(x["error"]) for x in rows) / len(rows),
            "latency_mean_ms": statistics.mean(lat),
            "latency_p95_ms": sorted(lat)[max(0, math.ceil(len(lat) * 0.95) - 1)],
            "per_critical_field": {
                f: sum(x["fields"][f]["correct"] for x in rows) / len(rows)
                for f in FIELDS
            },
        }
    return summary


def freeze():
    config = ROOT / "configs/ocr-benchmark.json"
    files = [
        config,
        *sorted((ROOT / "backend/app/ocr").rglob("*.py")),
        *sorted((ROOT / "ocr-services").rglob("server.py")),
        *sorted((ROOT / "ocr-services").rglob("Dockerfile")),
        ROOT / "scripts/benchmark_ocr.py",
        ROOT / "datasets/ocr/manifest.json",
    ]
    for d in ("input", "ground_truth"):
        files += sorted((ROOT / "datasets/ocr" / d).rglob("*.*"))
    files += [ROOT / "configs/ocr-model-hashes.json", ROOT / "docker-compose.ocr.yml"]
    files += sorted((ROOT / "ocr-services").rglob("installed-versions.txt"))
    hashes = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
    }
    path = ROOT / "configs/ocr-freeze.json"
    if path.exists():
        raise SystemExit("Freeze already exists; do not overwrite after HOLDOUT")
    path.write_text(
        json.dumps(
            {"created_at": datetime.now(UTC).isoformat(), "files": hashes}, indent=2
        ),
        encoding="utf-8",
    )
    print("Configuration and dataset frozen; HOLDOUT not evaluated.")


async def main(args):
    config = json.loads(
        (ROOT / "configs/ocr-benchmark.json").read_text(encoding="utf-8-sig")
    )
    if args.split == "holdout":
        if args.profile:
            raise SystemExit("HOLDOUT uses frozen profiles only")
        frozen = json.loads((ROOT / "configs/ocr-freeze.json").read_text())
        for p, digest in frozen["files"].items():
            assert hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest, (
                "Frozen file changed: " + p
            )
        marker = ROOT / "datasets/ocr/holdout-executed.json"
        with marker.open("x") as f:
            json.dump(
                {
                    "started_at": datetime.now(UTC).isoformat(),
                    "freeze_sha256": hashlib.sha256(
                        (ROOT / "configs/ocr-freeze.json").read_bytes()
                    ).hexdigest(),
                },
                f,
            )
    output = ROOT / "datasets/ocr/results" / args.name
    output.mkdir(parents=True, exist_ok=False)
    records = []
    comparisons = []
    counts = dict(
        agreement=0,
        disagreement=0,
        both_correct=0,
        one_correct_conflict=0,
        both_wrong_agreement=0,
        both_wrong_disagreement=0,
    )
    for truthpath in sorted(
        (ROOT / "datasets/ocr/ground_truth" / args.split).glob("*.json")
    ):
        gt = json.loads(truthpath.read_text(encoding="utf-8"))
        content = (ROOT / gt["source_file"]).read_bytes()
        profiles = config.get(
            "selected_profiles", {"tesseract": "baseline", "paddle": "baseline"}
        )
        if args.profile:
            profiles = dict.fromkeys(("tesseract", "paddle"), args.profile)
        # Inputs constructed only from original bytes, ID, fixed preprocessing; no ground truth.
        a, b = await asyncio.gather(
            infer(
                "http://localhost:8011/ocr",
                "tesseract",
                gt["document_id"],
                content,
                profiles["tesseract"],
                180,
            ),
            infer(
                "http://localhost:8012/ocr",
                "paddle",
                gt["document_id"],
                content,
                profiles["paddle"],
                180,
            ),
        )
        for result in (a, b):
            (output / f"{gt['document_id']}-{result.provider}-raw.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
            raw = (
                extract_fields(result.raw_text)
                if not result.error
                else dict.fromkeys(FIELDS)
            )
            fields = {
                f: {
                    "raw": raw[f],
                    "normalized": normalize_field(f, raw[f]),
                    "ground_truth": gt["fields"][f],
                    "correct": normalize_field(f, raw[f])
                    == normalize_field(f, gt["fields"][f]),
                }
                for f in FIELDS
            }
            actual = " ".join(result.raw_text.split())
            expected = " ".join(gt["full_text"].split())
            records.append(
                {
                    "document_id": gt["document_id"],
                    "provider": result.provider,
                    "provider_version": result.provider_version,
                    "latency_ms": result.processing_time_ms,
                    "error": result.error,
                    "char_errors": distance(actual, expected),
                    "characters": len(expected),
                    "word_errors": distance(actual.split(), expected.split()),
                    "words": len(expected.split()),
                    "exact_correct": sum(raw[f] == gt["fields"][f] for f in FIELDS),
                    "normalized_correct": sum(x["correct"] for x in fields.values()),
                    "fields": fields,
                }
            )
        comparison = compare(a, b)
        comparison.pop("providers")
        comparison["document_id"] = gt["document_id"]
        for row in comparison["fields"]:
            f = row["field"]
            truth = normalize_field(f, gt["fields"][f])
            x = row["normalized_a"]
            y = row["normalized_b"]
            agree = x is not None and x == y
            row["ground_truth"] = gt["fields"][f]
            row["a_correct"] = x == truth
            row["b_correct"] = y == truth
            counts["agreement" if agree else "disagreement"] += 1
            if x == truth and y == truth:
                counts["both_correct"] += 1
            elif (x == truth) != (y == truth):
                counts["one_correct_conflict"] += 1
            elif agree:
                counts["both_wrong_agreement"] += 1
            else:
                counts["both_wrong_disagreement"] += 1
        comparisons.append(comparison)
        print(gt["document_id"], a.error or "A OK", b.error or "B OK", flush=True)
    total = len(comparisons) * len(FIELDS)
    consensus = {
        **counts,
        "field_pairs": total,
        "pairwise_agreement": counts["agreement"] / total,
        "pairwise_disagreement": counts["disagreement"] / total,
        "false_consensus_rate_all_pairs": counts["both_wrong_agreement"] / total,
        "false_consensus_rate_agreements": counts["both_wrong_agreement"]
        / counts["agreement"]
        if counts["agreement"]
        else None,
    }
    decisions = {
        "AUTO_ACCEPT": 0,
        "REVIEW_REQUIRED": 0,
        "BOTH_FAILED": 0,
        "incorrect_critical_fields_auto_accepted": 0,
    }
    for item in comparisons:
        category = (
            "BOTH_FAILED"
            if item["outcome"] == "BOTH_FAILED"
            else "REVIEW_REQUIRED"
            if item["review_required"]
            else "AUTO_ACCEPT"
        )
        decisions[category] += 1
        if category == "AUTO_ACCEPT":
            decisions["incorrect_critical_fields_auto_accepted"] += sum(
                row["selected"] != normalize_field(row["field"], row["ground_truth"])
                for row in item["fields"]
            )
    report = {
        "document_decisions": decisions,
        "split": args.split,
        "profiles": profiles,
        "summary": metrics(records),
        "consensus": consensus,
        "records": records,
        "comparisons": comparisons,
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with (output / "report.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "document_id",
                "provider",
                "field",
                "raw",
                "normalized",
                "ground_truth",
                "correct",
                "latency_ms",
                "error",
            ]
        )
        for rec in records:
            for field, values in rec["fields"].items():
                writer.writerow(
                    [
                        rec["document_id"],
                        rec["provider"],
                        field,
                        values["raw"],
                        values["normalized"],
                        values["ground_truth"],
                        values["correct"],
                        rec["latency_ms"],
                        rec["error"],
                    ]
                )
    md = f"# OCR benchmark: {args.split}\n\nProfiles: {profiles}\n\n| Provider | CER | WER | Exact | Normalized/critical | Failures | Mean ms | p95 ms |\n|---|---:|---:|---:|---:|---:|---:|---:|\n"
    for p, m in report["summary"].items():
        md += f"| {p} | {m['cer']:.4f} | {m['wer']:.4f} | {m['exact_field_accuracy']:.4f} | {m['critical_field_accuracy']:.4f} | {m['provider_failure_rate']:.4f} | {m['latency_mean_ms']:.1f} | {m['latency_p95_ms']:.1f} |\n"
    md += (
        "\n## Consensus\n\n```json\n"
        + json.dumps(consensus, indent=2)
        + "\n```\n\n## Per critical field\n\n"
        + json.dumps(
            {p: m["per_critical_field"] for p, m in report["summary"].items()}, indent=2
        )
        + "\n"
    )
    md += (
        "\n## Document decisions\n\n```json\n"
        + json.dumps(decisions, indent=2)
        + "\n```\n"
    )
    (output / "report.md").write_text(md, encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "consensus": consensus}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument("--name", default="dev-baseline")
    parser.add_argument("--profile")
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        asyncio.run(main(args))
