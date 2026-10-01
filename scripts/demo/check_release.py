"""Read-only M8 release-file, local-link, secret and frozen-scope sanity checks."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def check(base: str) -> dict:
    candidates = sorted(
        set(git("diff", "--name-only", "HEAD").splitlines())
        | set(git("ls-files", "--others", "--exclude-standard").splitlines())
    )
    files = [ROOT / name for name in candidates if (ROOT / name).is_file()]
    forbidden = []
    for name in candidates:
        parts = Path(name).parts
        if (
            any(p.startswith(".runtime") for p in parts)
            or any(p in {"storage", "node_modules", ".next", ".n8n", "__pycache__"} for p in parts)
            or Path(name).name in {".env", ".env.production", "demo.env", "login.txt"}
            or Path(name).suffix in {".secret", ".pem", ".key", ".db", ".sqlite", ".zip", ".tar"}
        ):
            forbidden.append(name)
    assert not forbidden, f"Runtime/private material in release candidates: {forbidden}"
    runtime = ROOT / ".runtime-demo/demo.env"
    secrets = []
    if runtime.exists():
        for line in runtime.read_text(encoding="utf-8-sig").splitlines():
            key, _, value = line.partition("=")
            if any(part in key for part in ["PASSWORD", "TOKEN", "MASTER_KEY", "HMAC"]):
                assert len(value) >= 24, "Unexpectedly short generated demo secret"
                secrets.append(value.encode())
    secret_hits = [
        str(path.relative_to(ROOT))
        for path in files
        if any(secret in path.read_bytes() for secret in secrets)
        or re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", path.read_bytes())
    ]
    assert not secret_hits, f"Secret material in release candidates: {secret_hits}"
    broken = []
    checked_links = 0
    markdown = [path for path in files if path.suffix == ".md"]
    for path in markdown:
        text = path.read_text(encoding="utf-8-sig")
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for target in re.findall(r"\[[^\]]*\]\(([^)\n]+)\)", text):
            target = target.strip().strip("<>")
            if re.match(r"^[a-zA-Z]+:", target) or target.startswith("#"):
                continue
            relative = unquote(target.split("#", 1)[0])
            checked_links += 1
            if not (path.parent / relative).exists():
                broken.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not broken, f"Broken local links: {broken}"
    frozen = [
        "datasets",
        "configs",
        "ocr-services",
        "backend/app/adaptive",
        "backend/app/stp",
        "backend/app/ocr",
        "docs/milestone4",
        "docs/milestone6",
        "docs/milestone7",
    ]
    changes = git("diff", "--name-only", base, "--", *frozen).splitlines()
    assert not changes, f"Frozen implementation/evidence changed: {changes}"
    git("diff", "--check")
    return {
        "status": "PASS",
        "base": git("rev-parse", base).strip(),
        "release_candidate_files": len(files),
        "markdown_files_checked": len(markdown),
        "local_links_checked": checked_links,
        "broken_local_links": 0,
        "generated_secret_values_checked": len(secrets),
        "secret_hits": 0,
        "runtime_private_candidates": 0,
        "frozen_scopes": frozen,
        "frozen_scopes_unchanged": True,
        "git_diff_check": "PASS",
        "scope": "Changed/untracked release files; unchanged historical links excluded; "
        "exact generated-secret/private-key scan, not an independent DLP audit.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="a80f963")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check(args.base)
    data = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(data, encoding="utf-8")
    print(data)


if __name__ == "__main__":
    main()
