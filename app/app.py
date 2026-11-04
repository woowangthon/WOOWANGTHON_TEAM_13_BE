from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.openapi import configure_openapi

app = FastAPI(
    title="WOOWANGTHON API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
configure_openapi(app)


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    return {"message": "WOOWANGTHON API"}
