from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.extraction.development import DevelopmentExtractionProvider
from app.services.cases import CaseService
from app.storage.base import LocalFilesystemStorage


def get_service(db: Annotated[AsyncSession, Depends(get_db)]) -> CaseService:
    return CaseService(
        db, LocalFilesystemStorage(settings.storage_path), DevelopmentExtractionProvider()
    )


Service = Annotated[CaseService, Depends(get_service)]
