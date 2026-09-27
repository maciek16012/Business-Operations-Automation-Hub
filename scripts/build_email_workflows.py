"""Build sanitized importable n8n workflows from reviewable Code-node sources."""

import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1] / "n8n"


def code(name, filename, x):
    return {
        "id": name,
        "name": name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x, 300],
        "parameters": {
            "jsCode": (ROOT / "code" / filename).read_text(encoding="utf-8")
        },
    }


def workflow(identifier, name, nodes):
    return {
        "id": identifier,
        "name": name,
        "active": False,
        "versionId": str(uuid5(NAMESPACE_URL, identifier)),
        "nodes": nodes,
        "connections": {
            a["name"]: {"main": [[{"node": b["name"], "type": "main", "index": 0}]]}
            for a, b in zip(nodes, nodes[1:])
        },
        "settings": {
            "executionOrder": "v1",
            "timezone": "Europe/Warsaw",
            "saveDataErrorExecution": "all",
            "saveDataSuccessExecution": "all",
            "errorWorkflow": "boahEmailErrors2",
        },
        "pinData": {},
    }


def build():
    transport = {
        "id": "Send to BOAH",
        "name": "Send to BOAH",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [700, 300],
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 1000,
        "onError": "continueRegularOutput",
        "parameters": {
            "method": "POST",
            "url": "http://backend:8000/api/v1/inbound/email",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json }}",
            "options": {
                "timeout": 15000,
                "response": {
                    "response": {"fullResponse": True, "responseFormat": "json"}
                },
            },
        },
    }
    normal = code("Normalize email", "normalize-email.js", 460)
    classify = code("Classify delivery", "classify-response.js", 940)
    imap = {
        "id": "IMAP mailbox",
        "name": "IMAP mailbox",
        "type": "n8n-nodes-base.emailReadImap",
        "typeVersion": 2.2,
        "position": [200, 300],
        "parameters": {
            "mailbox": "INBOX",
            "postProcessAction": "nothing",
            "format": "resolved",
            "dataPropertyAttachmentsPrefixName": "attachment_",
            "options": {
                "customEmailConfig": '["UNSEEN"]',
                "trackLastMessageId": False,
                "forceReconnect": 5,
            },
        },
        "notes": "Bind your IMAP credential, then publish. No mailbox credential is shipped. Leave unread until BOAH delivery is confirmed. See n8n/README.md for recovery.",
    }
    real = workflow(
        "boahEmailImapM2",
        "BOAH - Inbound email (IMAP)",
        [imap, normal, transport, classify],
    )
    webhook = {
        "id": "Local fixture",
        "name": "Local fixture",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [0, 300],
        "webhookId": "boah-email-fixture-m2",
        "parameters": {
            "httpMethod": "POST",
            "path": "boah-email-fixture-m2",
            "responseMode": "lastNode",
            "options": {},
        },
    }
    fixture = workflow(
        "boahEmailFixture2",
        "BOAH - Local email fixture",
        [
            webhook,
            code("Fixture binary", "fixture-to-binary.js", 230),
            normal,
            transport,
            classify,
        ],
    )
    errors = workflow(
        "boahEmailErrors2",
        "BOAH - Email delivery errors",
        [
            {
                "id": "Delivery error",
                "name": "Delivery error",
                "type": "n8n-nodes-base.errorTrigger",
                "typeVersion": 1,
                "position": [200, 300],
                "parameters": {},
            },
            code("Recovery context", "error-summary.js", 460),
        ],
    )
    errors["settings"].pop("errorWorkflow")
    for name, value in [
        ("inbound-email.json", real),
        ("inbound-email-fixture.json", fixture),
        ("inbound-email-error.json", errors),
    ]:
        (ROOT / "workflows" / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    build()
