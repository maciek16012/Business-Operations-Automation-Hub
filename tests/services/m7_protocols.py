"""Local protocol fixtures. Synthetic credentials only; not a production server."""

import hashlib
import hmac
import json
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path("/test-data")
ROOT.mkdir(exist_ok=True)


class Receiver(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            payload = b'{"status":"ok"}'
        else:
            records = [json.loads(p.read_text()) for p in ROOT.glob("webhook-*.json")]
            payload = json.dumps(records).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        data = self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 1024 * 1024))
        expected = (
            "sha256="
            + hmac.new(os.environ["M7_WEBHOOK_HMAC"].encode(), data, hashlib.sha256).hexdigest()
        )
        if not hmac.compare_digest(expected, self.headers.get("X-BOAH-Signature", "")):
            self.send_response(401)
            self.end_headers()
            return
        key = self.headers.get("Idempotency-Key", "")
        name = hashlib.sha256(key.encode()).hexdigest()
        path = ROOT / ("webhook-" + name + ".json")
        prior = json.loads(path.read_text()) if path.exists() else {"attempts": 0}
        record = {
            "idempotency_key": key,
            "signature_valid": True,
            "attempts": prior["attempts"] + 1,
            "body_sha256": hashlib.sha256(data).hexdigest(),
            "same_body": not prior.get("body_sha256")
            or prior["body_sha256"] == hashlib.sha256(data).hexdigest(),
            "event": json.loads(data),
        }
        path.write_text(json.dumps(record))
        status = (
            503
            if self.path == "/fail" or self.path == "/retry" and record["attempts"] == 1
            else 200
        )
        self.send_response(status)
        self.end_headers()
        self.wfile.write(b"{}")


if sys.argv[1] == "webhook":
    ThreadingHTTPServer(("0.0.0.0", 8080), Receiver).serve_forever()
else:
    import paramiko

    key_path = ROOT / "ssh_host_rsa_key"
    if not key_path.exists():
        paramiko.RSAKey.generate(2048).write_private_key_file(str(key_path))
    key = paramiko.RSAKey.from_private_key_file(str(key_path))
    (ROOT / "ssh_host_rsa_key.pub").write_text(key.get_name() + " " + key.get_base64())
    upload = ROOT / "sftp"
    upload.mkdir(exist_ok=True)

    class Auth(paramiko.ServerInterface):
        def check_auth_password(self, username, password):
            return (
                paramiko.AUTH_SUCCESSFUL
                if username == "synthetic"
                and hmac.compare_digest(password, os.environ["M7_SFTP_PASSWORD"])
                else paramiko.AUTH_FAILED
            )

        def get_allowed_auths(self, username):
            return "password"

        def check_channel_request(self, kind, chanid):
            return (
                paramiko.OPEN_SUCCEEDED
                if kind == "session"
                else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
            )

    class SFTP(paramiko.SFTPServerInterface):
        def path(self, path):
            value = (upload / path.lstrip("/")).resolve()
            if not value.is_relative_to(upload):
                raise OSError(13, "outside fixture root")
            return value

        def list_folder(self, path):
            try:
                result = []
                for p in self.path(path).iterdir():
                    a = paramiko.SFTPAttributes.from_stat(p.stat())
                    a.filename = p.name
                    result.append(a)
                return result
            except OSError as e:
                return paramiko.SFTPServer.convert_errno(e.errno)

        def stat(self, path):
            try:
                return paramiko.SFTPAttributes.from_stat(self.path(path).stat())
            except OSError as e:
                return paramiko.SFTPServer.convert_errno(e.errno)

        lstat = stat

        def mkdir(self, path, attr):
            try:
                self.path(path).mkdir()
                return paramiko.SFTP_OK
            except OSError as e:
                return paramiko.SFTPServer.convert_errno(e.errno)

        def open(self, path, flags, attr):
            try:
                fd = os.open(self.path(path), flags, 0o600)
                mode = "r+b" if flags & os.O_RDWR else "wb" if flags & os.O_WRONLY else "rb"
                stream = os.fdopen(fd, mode)
                handle = paramiko.SFTPHandle(flags)
                handle.readfile = stream
                handle.writefile = stream
                return handle
            except OSError as e:
                return paramiko.SFTPServer.convert_errno(e.errno)

        def rename(self, old, new):
            try:
                target = self.path(new)
                if target.exists():
                    return paramiko.SFTP_FAILURE
                self.path(old).rename(target)
                return paramiko.SFTP_OK
            except OSError as e:
                return paramiko.SFTPServer.convert_errno(e.errno)

    def serve(sock):
        transport = paramiko.Transport(sock)
        transport.add_server_key(key)
        transport.set_subsystem_handler("sftp", paramiko.SFTPServer, SFTP)
        try:
            transport.start_server(server=Auth())
            while transport.is_active():
                threading.Event().wait(0.2)
        finally:
            transport.close()

    listener = socket.create_server(("0.0.0.0", 2222))
    while True:
        client, _ = listener.accept()
        threading.Thread(target=serve, args=(client,), daemon=True).start()
