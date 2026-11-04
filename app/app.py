from fastapi import FastAPI

from app.api.router import api_router
from app.core.openapi import configure_openapi

app = FastAPI(
    title="WOOWANGTHON API",
    version="0.1.0",
)

app.include_router(api_router, prefix="/api/v1")
configure_openapi(app)


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    return {"message": "WOOWANGTHON API"}
