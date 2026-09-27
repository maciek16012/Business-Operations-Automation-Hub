# Local infrastructure

`docker compose up -d --build` starts PostgreSQL 17, FastAPI, Next.js and pinned n8n 2.40.7. Backend startup applies Alembic migrations. Postgres and backend healthchecks gate dependent services. No MinIO service is needed.

`postgres_data` preserves database data. `boah_files` preserves original documents and generated exports at `/data/documents`. Back up both together. Normal restarts and `docker compose down` retain named volumes; `down -v` destroys them.

Development bind mounts are intentionally retained. Restart backend after Python changes. Next.js runs its development server; use `npm run build` as the frontend production compilation check. Future n8n configuration can live here without restructuring this stack.

M2 adds n8n_data for workflow/credential/execution/binary persistence and localhost:5678. Workflow import and IMAP binding are documented in n8n/README.md. No mailbox secret is required for the deterministic fixture path.
