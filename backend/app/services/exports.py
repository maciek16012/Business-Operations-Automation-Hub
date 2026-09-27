import uuid

from app.exports.render import json_export, xlsx_export
from app.models.entities import Export
from app.services.cases import CaseService
from app.services.errors import WorkflowError

MIME = {
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class ExportService:
    def __init__(self, cases: CaseService):
        self.cases = cases

    async def generate(self, case, kind: str) -> tuple[Export, bytes]:
        case_id = case.id
        try:
            return await self._generate(case, kind)
        except OSError as exc:
            await self.cases.db.rollback()
            case = await self.cases.get(case_id, lock=True)
            self.cases.audit(case, "processing_failure", {"operation": "export", "type": kind})
            self.cases.db.add(
                Export(case_id=case_id, export_type=kind, metadata_json={"success": False})
            )
            await self.cases.db.commit()
            raise WorkflowError("EXPORT_FAILED", "Unable to store export", 503) from exc

    async def _generate(self, case, kind: str) -> tuple[Export, bytes]:
        if kind not in MIME:
            raise WorkflowError("EXPORT_TYPE_INVALID", "Use json or xlsx", 422)
        if case.status not in {"APPROVED", "EXPORTED"}:
            raise WorkflowError("EXPORT_BLOCKED", "Only approved cases can be exported")
        export = Export(
            id=uuid.uuid4(), case_id=case.id, export_type=kind, metadata_json={"success": True}
        )
        self.cases.db.add(export)
        self.cases.transition(case, "EXPORTED")
        self.cases.audit(
            case, "export_generated", {"export_id": str(export.id), "type": kind}, "operator"
        )
        await self.cases.db.flush()
        detail = await self.cases.detail(case)
        content = json_export(detail) if kind == "json" else xlsx_export(detail)
        export.storage_key = self.cases.storage.put(content)
        await self.cases.db.flush()
        return export, content
