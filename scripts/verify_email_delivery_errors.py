"""Exercise bounded n8n failures and recovery. Briefly stops/pauses the local backend."""

import argparse
import json
import subprocess
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
WEBHOOK = "http://localhost:5678/webhook/boah-email-fixture-m2"
API = "http://localhost:8000/api/v1"


def docker(*arguments):
    return subprocess.run(
        ["docker", "compose", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def ready(client):
    for _ in range(30):
        try:
            if client.get("http://localhost:8000/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise AssertionError("Backend did not recover")


def message(suffix, sender="test@example.com"):
    return {
        "mail": {
            "messageId": f"<boah-failure-{suffix}@example.test>",
            "from": {"value": [{"address": sender, "name": "Test Operator"}]},
            "subject": "Synthetic failure recovery",
            "date": "2026-09-27T10:00:00Z",
            "text": "Synthetic recovery test",
        },
        "attachments": [],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run_id = uuid.uuid4().hex[:8]
    report = {"run_id": run_id}
    with httpx.Client(timeout=65) as client:
        invalid = client.post(WEBHOOK, json=message(run_id + "-invalid", "bad-address"))
        assert invalid.status_code == 500
        report["invalid_payload_webhook_status"] = invalid.status_code
        start_total = client.get(API + "/cases").json()["total"]
        for label, suspend, resume in [
            ("unavailable", "stop", "start"),
            ("timeout", "pause", "unpause"),
        ]:
            payload = message(run_id + "-" + label)
            docker(suspend, "backend")
            started = time.monotonic()
            try:
                failed = client.post(WEBHOOK, json=payload)
                assert failed.status_code == 500, failed.text
                duration = round(time.monotonic() - started, 2)
                assert duration < 60
                print(
                    label, "failed as expected after", duration, "seconds", flush=True
                )
            finally:
                docker(resume, "backend")
            ready(client)
            recovered = client.post(WEBHOOK, json=payload)
            recovered.raise_for_status()
            again = client.post(WEBHOOK, json=payload)
            again.raise_for_status()
            assert again.json()["result"] == "duplicate"
            assert again.json()["case_id"] == recovered.json()["case_id"]
            report[label] = {
                "failure_http_status": failed.status_code,
                "failure_seconds": duration,
                "recovery_result": recovered.json()["result"],
                "replay_result": again.json()["result"],
                "case_id": recovered.json()["case_id"],
            }
        assert client.get(API + "/cases").json()["total"] - start_total == 2
        report["new_cases_for_two_recovered_messages"] = 2
        docker(
            "cp", "n8n/execution-evidence.cjs", "n8n:/tmp/boah-execution-evidence.cjs"
        )
        # Error Trigger executions are asynchronous; wait only for the three expected summaries.
        for _ in range(10):
            executions = json.loads(
                docker("exec", "-T", "n8n", "node", "/tmp/boah-execution-evidence.cjs")
            )
            categories = {e.get("recovery", {}).get("category") for e in executions}
            if {
                "INVALID_PAYLOAD",
                "BACKEND_UNAVAILABLE",
                "BACKEND_TIMEOUT",
            } <= categories:
                break
            time.sleep(1)
        else:
            raise AssertionError(f"Missing error categories: {categories}")
        report["error_workflow_executions"] = [
            e for e in executions if e.get("recovery")
        ]
        report["result"] = "PASS"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
