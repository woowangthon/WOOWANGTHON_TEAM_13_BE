from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}
