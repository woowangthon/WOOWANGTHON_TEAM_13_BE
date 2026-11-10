import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

logger = logging.getLogger("app.errors")

DB_BUSY_MARKERS = ("EMAXCONNSESSION", "too many clients", "max clients reached")


def _is_db_busy(error: Exception) -> bool:
    """DB 연결 한도나 연결 대기 시간 초과로 실패했는지 확인합니다."""
    if isinstance(error, PoolTimeoutError):
        return True
    if isinstance(error, DBAPIError):
        text = str(error.orig)
        return any(marker in text for marker in DB_BUSY_MARKERS)
    return False


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """FE와 맞춘 code, message 형식의 오류 응답을 만듭니다."""
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "detail": None},
    )


async def catch_unhandled_errors(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """처리되지 않은 오류도 CORS 미들웨어 안쪽에서 JSON 응답으로 바꿉니다."""
    try:
        return await call_next(request)
    except Exception as error:
        if _is_db_busy(error):
            logger.warning(
                "DB 연결이 부족해 요청을 처리하지 못했습니다: %s %s",
                request.method,
                request.url.path,
            )
            return _error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "DATABASE_BUSY",
                "요청이 많아 잠시 처리하지 못했어요. 다시 시도해 주세요",
            )
        logger.exception("처리되지 않은 오류: %s %s", request.method, request.url.path)
        return _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_SERVER_ERROR",
            "서버에서 문제가 생겼어요. 잠시 후 다시 시도해 주세요",
        )
