from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class ExtractedValue:
    field_name: str
    raw_value: str | None
    confidence: Decimal | None = None


class ExtractionProvider(ABC):
    name: str

    @abstractmethod
    async def extract(self, content: bytes) -> list[ExtractedValue]:
        raise NotImplementedError
