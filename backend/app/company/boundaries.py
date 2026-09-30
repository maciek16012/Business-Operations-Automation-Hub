"""Restricted mounted paths and DNS-pinned outbound networking."""

import http.client
import ipaddress
import re
import socket
import ssl
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from app.core.config import settings


def mounted(root: str, relative: str = "") -> Path:
    if root not in settings.mounted_roots:
        raise ValueError("Unknown mounted storage root")
    if "\\" in relative or ":" in relative or relative.startswith("/"):
        raise ValueError("Invalid relative path")
    parts = PurePosixPath(relative).parts
    if any(p in {".", ".."} for p in parts):
        raise ValueError("Path traversal rejected")
    base = Path(settings.mounted_roots[root]).resolve(strict=True)
    target = base.joinpath(*parts)
    if not target.resolve().is_relative_to(base):
        raise ValueError("Path outside mounted root")
    for ancestor in [target, *target.parents]:
        if ancestor == base:
            break
        if ancestor.is_symlink():
            raise ValueError("Symlinks not allowed in connector paths")
    return target


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:120].strip(" .")
    if not value or value in {".", ".."}:
        return "document"
    if value.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)],
    }:
        return "_" + value
    return value


def resolve(host: str, port: int) -> str:
    if not host or any(c in host for c in "/\\@\r\n") or not 1 <= port <= 65535:
        raise ValueError("Invalid network destination")
    addresses = sorted(
        {info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
    )
    if not addresses:
        raise ValueError("DNS returned no addresses")
    for value in addresses:
        ip = ipaddress.ip_address(value)
        allowed = host in settings.connector_network_allowlist
        for entry in settings.connector_network_allowlist:
            try:
                allowed |= ip in ipaddress.ip_network(entry, strict=False)
            except ValueError:
                pass
        if (
            ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or (not ip.is_global and not allowed)
        ):
            raise ValueError("Network destination prohibited by policy")
    return str(addresses[0])


def webhook(url: str, payload: bytes, headers: dict) -> int:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment or not parsed.hostname:
        raise ValueError("Invalid webhook URL")
    if parsed.scheme != "https" and not (
        settings.app_env != "production"
        and settings.connector_allow_plaintext_test
        and parsed.scheme == "http"
    ):
        raise ValueError("HTTPS required")
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ip = resolve(host, port)
    # Connect directly to the vetted address. Keep TLS hostname verification/SNI.
    sock = socket.create_connection((ip, port), timeout=15)
    try:
        if parsed.scheme == "https":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        conn = http.client.HTTPConnection(host, port, timeout=15)
        conn.sock = sock
        conn.request(
            "POST",
            (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""),
            body=payload,
            headers=headers,
        )
        response = conn.getresponse()
        status = response.status
        response.read(4096)
        conn.close()
        # Redirects never followed: no second unchecked target and no credential forwarding.
        if not 200 <= status < 300:
            raise ValueError(f"HTTP status {status}")
        return status
    finally:
        sock.close()
