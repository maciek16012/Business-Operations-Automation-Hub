# Troubleshooting

| Symptom | Check and resolution |
|---|---|
| Docker is unavailable or Windows-container mode is active | Start Docker Desktop in Linux-container mode; run `docker info`. No application reset is necessary. |
| First demo start is slow | Wait for image builds, Paddle model downloads and ClamAV signatures. Inspect the isolated service logs. Internet access is needed for a cold cache. Keep security fail-closed. |
| Port 3080 is occupied | Identify the listener and stop only that known conflicting application, or select another deployment deliberately. The shipped reproducible demo uses loopback 3080 consistently. |
| Startup says unowned/linked runtime | Check `.runtime-demo/identity.json` and directory ownership. Do not overwrite credentials or use a broad delete; restore the expected owned directory or move an unrelated directory manually after inspection. |
| Login fails | Read generated `.runtime-demo/login.txt` locally. Restart preserves passwords; reset regenerates them. Bootstrap variables do not overwrite an existing admin. Never paste credentials into issue reports. |
| Case is blocked while ClamAV is down | Inspect health and signature updates; wait for a conclusive SAFE scan. Do not disable preflight or enable fail-open. |
| OCR/table fields are unresolved | Compare the original and record a reasoned human correction. Unknown values and handwritten-like content legitimately require review; do not manufacture readings. |
| Approval returns 409 | Resolve all blocking business/OCR/document issues and confirm safety first. Review tasks are not bypassed by changing a status label. |
| Test connection remains PENDING or retries | Check delivery-worker health, jobs and sanitized errors. Verify the configured target, mounted root, secret and exact deployment allowlist. PENDING is not proof of connectivity. |
| Production IMAP rejects a restored source | Enable verified TLS with the proper IMAP endpoint. Restored plaintext configurations remain forbidden in production. |
| Webhook/SFTP is rejected | Check trusted destination and DNS/IP policy; use narrow deployment allowlists. Verify HMAC at the receiver and obtain the SFTP fingerprint through a trusted channel. Do not disable host-key checks or redirects policy. |
| Encrypted connector secrets cannot be read after restore | Supply the original independently backed-up master key. A new random key does not decrypt old records. Avoid logging key values. |
| Filesystem archive fails | Verify the named mount/root, permissions and safe relative template. Production processes use UID 10001; host directories must be accessible without granting unrelated access. |
| Alembic reports drift | Check the database URL/profile and run the existing upgrade/check workflow. Do not drop a populated database to conceal drift. |
| n8n review notification fails | Check review-worker, scoped backend credential and published workflow. Demo startup reimports the template and removes temporary credential copies. Keep credentials in protected runtime, not tracked JSON. |
| HTTPS does not work publicly | M7 validated local HTTPS with its own test CA. Public ACME additionally needs your domain, DNS, reachable 80/443 and deployment configuration. Local test certificates do not establish public readiness. |

Inspect only the named demo project:

```powershell
docker compose --project-name boah-portfolio-demo --env-file .runtime-demo/demo.env -f docker-compose.demo.yml ps
docker compose --project-name boah-portfolio-demo --env-file .runtime-demo/demo.env -f docker-compose.demo.yml logs --tail 100 backend delivery-worker review-worker
```

Do not publish raw `.env`, login files, database dumps, object storage or unreviewed logs. For a disposable demo reset use the [guarded reset](demo/DEMO-GUIDE.md); never use global Docker prune as an application repair. The demo uses standalone production frontend images, avoiding shared development `.next` output. See [configuration](CONFIGURATION.md) and [production operations](milestone7/deployment.md).
