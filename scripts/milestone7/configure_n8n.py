"""Attach scoped runtime credentials without changing credential-free workflow templates."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def configure(token, base=None):
    base = base or ["docker", "compose"]

    def put(path, data):
        subprocess.run(
            [*base, "exec", "-T", "n8n", "sh", "-c", f"umask 077; cat > {path}"],
            input=json.dumps(data).encode(),
            check=True,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
        )

    credential = [
        {
            "id": "boahM7Service",
            "name": "BOAH scoped service",
            "type": "httpHeaderAuth",
            "data": {"name": "Authorization", "value": "Bearer " + token},
        }
    ]
    put("/tmp/boah-m7-credentials.json", credential)
    try:
        subprocess.run(
            [
                *base,
                "exec",
                "-T",
                "n8n",
                "n8n",
                "import:credentials",
                "--input=/tmp/boah-m7-credentials.json",
            ],
            check=True,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
        )
    finally:
        subprocess.run(
            [*base, "exec", "-T", "n8n", "rm", "-f", "/tmp/boah-m7-credentials.json"],
            check=True,
            cwd=ROOT,
        )
    for name in [
        "review-notifications.json",
        "inbound-email-fixture.json",
        "inbound-email.json",
    ]:
        workflow = json.loads((ROOT / "n8n/workflows" / name).read_text())
        for node in workflow["nodes"]:
            if node["type"] == "n8n-nodes-base.httpRequest" and "backend:8000/api/v1/" in node.get(
                "parameters", {}
            ).get("url", ""):
                node["parameters"].update(
                    authentication="genericCredentialType",
                    genericAuthType="httpHeaderAuth",
                )
                node["credentials"] = {
                    "httpHeaderAuth": {
                        "id": "boahM7Service",
                        "name": "BOAH scoped service",
                    }
                }
        put("/tmp/boah-m7-workflow.json", workflow)
        subprocess.run(
            [
                *base,
                "exec",
                "-T",
                "n8n",
                "n8n",
                "import:workflow",
                "--input=/tmp/boah-m7-workflow.json",
            ],
            check=True,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
        )
        if name == "review-notifications.json":
            subprocess.run(
                [
                    *base,
                    "exec",
                    "-T",
                    "n8n",
                    "n8n",
                    "publish:workflow",
                    "--id=" + workflow["id"],
                ],
                check=True,
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
            )
    subprocess.run(
        [*base, "exec", "-T", "n8n", "rm", "-f", "/tmp/boah-m7-workflow.json"],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([*base, "restart", "n8n"], check=True, cwd=ROOT, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    import os

    token = os.environ.get("BOAH_SERVICE_TOKEN")
    if not token:
        import getpass

        token = getpass.getpass("Scoped BOAH service token: ")
    configure(token)
    print("Runtime n8n credential configured; repository templates remain credential-free.")
