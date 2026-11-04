import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any, Protocol
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError


class JWTValidationError(Exception):
    """Raised when a Supabase access token cannot be trusted."""


class SigningKeyClient(Protocol):
    """Subset of PyJWKClient used by the verifier and its tests."""

    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Authenticated identity extracted from a verified Supabase JWT."""

    id: UUID
    email: str | None
    role: str | None
    claims: Mapping[str, Any]


class SupabaseJWTVerifier:
    """Verify Supabase JWTs with the project's published JWKS keys."""

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        algorithms: Sequence[str] = ("RS256", "ES256"),
        jwks_client: SigningKeyClient | None = None,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._algorithms = tuple(algorithms)
        self._jwks_client = jwks_client or PyJWKClient(
            jwks_url,
            cache_keys=True,
        )

    async def verify(self, token: str) -> Mapping[str, Any]:
        """Validate a token without blocking FastAPI's event loop."""

        return await asyncio.to_thread(self._verify_sync, token)

    def _verify_sync(self, token: str) -> Mapping[str, Any]:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["sub", "iss", "aud", "exp"]},
            )
        except (PyJWTError, ValueError, TypeError) as exc:
            raise JWTValidationError from exc


bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    description="Supabase access token",
    bearerFormat="JWT",
    auto_error=False,
)


@lru_cache
def get_jwt_verifier() -> SupabaseJWTVerifier:
    """Build one cached verifier and JWKS client for the application."""

    # Import lazily so unit tests can inject a verifier without loading .env.
    from app.core.config import settings

    return SupabaseJWTVerifier(
        jwks_url=settings.supabase_jwks_url,
        issuer=settings.supabase_jwt_issuer,
        audience=settings.supabase_jwt_audience,
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
    verifier: Annotated[TokenVerifier, Depends(get_jwt_verifier)],
) -> AuthenticatedUser:
    """Return the current identity after validating its Supabase JWT."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        claims = await verifier.verify(credentials.credentials)
        user_id = UUID(str(claims["sub"]))
    except (JWTValidationError, KeyError, TypeError, ValueError):
        raise _unauthorized() from None

    email = claims.get("email")
    role = claims.get("role")

    return AuthenticatedUser(
        id=user_id,
        email=email if isinstance(email, str) else None,
        role=role if isinstance(role, str) else None,
        claims=claims,
    )
