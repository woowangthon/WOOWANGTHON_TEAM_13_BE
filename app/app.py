from fastapi import FastAPI

from app.api.router import api_router

app = FastAPI(
    title="WOOWANGTHON API",
    version="0.1.0",
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    return {"message": "WOOWANGTHON API"}
