"""No application document parser is imported or called by this gate."""

import asyncio
import re
import struct
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.core.config import settings

TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".txt": "text/plain",
}
DANGEROUS = {
    ".exe",
    ".dll",
    ".com",
    ".scr",
    ".bat",
    ".cmd",
    ".ps1",
    ".js",
    ".vbs",
    ".msi",
    ".jar",
    ".hta",
    ".sh",
    ".docm",
    ".xlsm",
    ".lnk",
}


@dataclass
class Verdict:
    verdict: str
    reason: str
    detected_mime: str | None = None
    scanner_version: str | None = None
    threat_name: str | None = None
    checks: dict = field(default_factory=dict)


def detect(data: bytes) -> str | None:
    for signature, mime in [
        (b"%PDF-", "application/pdf"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"II*\x00", "image/tiff"),
        (b"MM\x00*", "image/tiff"),
    ]:
        if data.startswith(signature):
            return mime
    try:
        text = data.decode("utf-8-sig")
        if text and all(c.isprintable() or c in "\r\n\t" for c in text):
            return "text/plain"
    except UnicodeDecodeError:
        pass
    return None


class ClamAV:
    async def command(self, command: bytes, data: bytes | None = None) -> str:
        async with asyncio.timeout(settings.clamav_timeout_seconds):
            reader, writer = await asyncio.open_connection(
                settings.clamav_host, settings.clamav_port
            )
            try:
                writer.write(command)
                if data is not None:
                    for offset in range(0, len(data), 65536):
                        chunk = data[offset : offset + 65536]
                        writer.write(struct.pack("!I", len(chunk)) + chunk)
                        await writer.drain()
                    writer.write(struct.pack("!I", 0))
                await writer.drain()
                return (await reader.readuntil(b"\0")).rstrip(b"\0").decode("utf-8")
            finally:
                writer.close()
                await writer.wait_closed()

    async def scan(self, data: bytes) -> tuple[str, str | None]:
        version = await self.command(b"zVERSION\0")
        if not version.startswith("ClamAV "):
            raise ValueError("Unexpected scanner version response")
        result = await self.command(b"zINSTREAM\0", data)
        if result == "stream: OK":
            return version, None
        if result.startswith("stream: ") and result.endswith(" FOUND"):
            return version, result[8:-6]
        raise ValueError("Scanner did not return a conclusive verdict")


async def preflight(filename: str, claimed: str, data: bytes) -> Verdict:
    mime = detect(data)
    ext = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    result = Verdict(
        "QUARANTINED",
        "UNSUPPORTED_TYPE",
        mime,
        checks={"policy": "m5-v1", "size": len(data), "extension": ext},
    )
    if not data or len(data) > settings.security_max_attachment_bytes:
        result.reason = "SIZE_LIMIT"
        return result
    if any(s.lower() in DANGEROUS for s in PurePosixPath(filename).suffixes) or data.startswith(
        (b"MZ", b"\x7fELF", b"#!", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")
    ):
        result.verdict, result.reason = "BLOCKED", "EXECUTABLE_CONTENT"
        return result
    # Antivirus also scans unrecognised formats. Unknown/mismatched files never reach a parser.
    try:
        result.scanner_version, result.threat_name = await ClamAV().scan(data)
        result.checks["antivirus"] = "infected" if result.threat_name else "clean"
    except (
        OSError,
        ValueError,
        TimeoutError,
        asyncio.IncompleteReadError,
        asyncio.LimitOverrunError,
    ):
        result.verdict, result.reason = "SCAN_FAILED", "SCANNER_UNAVAILABLE"
        result.checks["antivirus"] = "inconclusive"
        return result
    if result.threat_name:
        result.verdict, result.reason = "BLOCKED", "MALWARE_DETECTED"
        return result
    allowed = settings.security_allowed_mime_types.split(",")
    if mime not in allowed or ext not in TYPES:
        return result
    if TYPES[ext] != mime or claimed.split(";")[0].strip().lower() not in {
        mime,
        "application/octet-stream",
    }:
        result.reason = "TYPE_MISMATCH"
        return result
    if mime == "application/pdf":
        # Lexical rejection only, never a PDF parser. Unescape PDF name bytes first.
        names = re.sub(rb"#([0-9a-fA-F]{2})", lambda m: bytes([int(m[1], 16)]), data)
        if re.search(
            rb"/(JavaScript|JS|Launch|EmbeddedFile|OpenAction|AA|RichMedia|Encrypt)\b", names
        ):
            result.reason = "ACTIVE_OR_ENCRYPTED_PDF"
            return result
    result.verdict, result.reason = "SAFE", "ALL_CHECKS_PASSED"
    return result
