from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.auth import bearer_scheme


def configure_openapi(app: FastAPI) -> None:
    """Expose Supabase Bearer JWT authentication in Swagger UI."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes[bearer_scheme.scheme_name] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": bearer_scheme.model.description,
        }
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
