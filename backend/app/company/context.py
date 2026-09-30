"""Request-scoped audit identity without storing credential/document material."""

from contextvars import ContextVar

correlation: ContextVar[str | None] = ContextVar("correlation", default=None)
actor: ContextVar[str | None] = ContextVar("actor", default=None)
