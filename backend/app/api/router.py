from fastapi import APIRouter

from app.api.routes import cases, exports, inbound, review, uploads

api_router = APIRouter()
api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(review.router, prefix="/review", tags=["review"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])

api_router.include_router(inbound.router, prefix="/inbound", tags=["inbound email"])
