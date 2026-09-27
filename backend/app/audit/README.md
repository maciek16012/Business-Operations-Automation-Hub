# Audit

CaseService.audit appends AuditEvent rows in the business transaction. Manual corrections include old/new/input values and actor=operator; state changes include old/new status. Review decisions are separately persisted. Actor identity is a placeholder until authentication is introduced.
