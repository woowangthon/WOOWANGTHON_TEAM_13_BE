from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import catch_unhandled_errors
from app.core.openapi import configure_openapi


def configure_middlewares(app: FastAPI, cors_origins: list[str]) -> None:
    """오류 처리를 CORS 안쪽에 두어 500 응답에도 CORS 헤더가 붙게 합니다."""
    # 나중에 추가한 미들웨어가 바깥쪽이므로 오류 처리를 먼저, CORS를 나중에 추가합니다.
    app.add_middleware(BaseHTTPMiddleware, dispatch=catch_unhandled_errors)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


app = FastAPI(
    title="WOOWANGTHON API",
    version="0.1.0",
)

configure_middlewares(app, settings.cors_origin_list)

app.include_router(api_router, prefix="/api/v1")
configure_openapi(app)


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    return {"message": "WOOWANGTHON API"}
