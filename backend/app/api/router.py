from fastapi import APIRouter

from app.api.routes import cases, documents, exports, inbound, ocr, review, tasks, uploads

api_router = APIRouter()
api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(review.router, prefix="/review", tags=["review"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])

api_router.include_router(inbound.router, prefix="/inbound", tags=["inbound email"])

api_router.include_router(ocr.router, prefix="/ocr", tags=["OCR review"])


api_router.include_router(tasks.router, prefix="/review-tasks", tags=["Review operations"])

api_router.include_router(documents.router, prefix="/documents", tags=["Adaptive documents"])
