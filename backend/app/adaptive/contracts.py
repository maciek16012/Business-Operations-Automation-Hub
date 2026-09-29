"""Replaceable classification/layout/recognition contracts; never invoice-specific."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Cell:
    row: int
    column: int
    value: str | None
    bbox: list[float] | None
    confidence: float = 0.0
    source: str = "unresolved"
    uncertain: bool = True


@dataclass
class Table:
    page: int
    rows: int
    columns: int
    bbox: list[float]
    cells: list[Cell]
    source: str
    irregular: bool = False


@dataclass
class Evidence:
    text: str = ""
    tables: list[Table] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class Classification:
    document_type: str
    confidence: float
    reasons: list[str]
    review_required: bool
    classifier: str = "local-signals-v1"


class DocumentClassifier(Protocol):
    def classify(self, evidence: Evidence) -> Classification: ...


class HandwritingProvider(Protocol):
    async def recognize(self, image: bytes) -> tuple[str | None, float, str]: ...
