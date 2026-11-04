from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Annotated, Any
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.auth import (
    AuthenticatedUser,
    JWTValidationError,
    SupabaseJWTVerifier,
    get_current_user,
    get_jwt_verifier,
)

ISSUER = "https://example.supabase.co/auth/v1"
AUDIENCE = "authenticated"


class StaticJWKClient:
    def __init__(self, public_key: Any) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        return SimpleNamespace(key=self._public_key)


class StaticVerifier:
    def __init__(self, claims: Mapping[str, Any]) -> None:
        self._claims = claims

    async def verify(self, token: str) -> Mapping[str, Any]:
        return self._claims


@pytest.fixture
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def build_claims(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(uuid4()),
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "email": "user@example.com",
        "role": "authenticated",
    }
    claims.update(overrides)
    return claims


def build_verifier(private_key: Any) -> SupabaseJWTVerifier:
    return SupabaseJWTVerifier(
        jwks_url="https://example.invalid/.well-known/jwks.json",
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_client=StaticJWKClient(private_key.public_key()),
    )


def encode_token(
    private_key: Any,
    claims: Mapping[str, Any],
    algorithm: str = "RS256",
) -> str:
    return jwt.encode(
        dict(claims),
        private_key,
        algorithm=algorithm,
        headers={"kid": "test-key"},
    )


@pytest.mark.asyncio
async def test_verify_valid_supabase_token(
    private_key: rsa.RSAPrivateKey,
) -> None:
    claims = build_claims()
    token = encode_token(private_key, claims)

    decoded = await build_verifier(private_key).verify(token)

    assert decoded["sub"] == claims["sub"]
    assert decoded["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_verify_es256_token_used_by_supabase() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    claims = build_claims()
    token = encode_token(private_key, claims, algorithm="ES256")

    decoded = await build_verifier(private_key).verify(token)

    assert decoded["sub"] == claims["sub"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"iss": "https://attacker.example/auth/v1"},
        {"aud": "wrong-audience"},
    ],
)
async def test_reject_invalid_token_claims(
    private_key: rsa.RSAPrivateKey,
    claim_overrides: dict[str, Any],
) -> None:
    token = encode_token(private_key, build_claims(**claim_overrides))

    with pytest.raises(JWTValidationError):
        await build_verifier(private_key).verify(token)


def create_protected_client(claims: Mapping[str, Any]) -> TestClient:
    test_app = FastAPI()

    @test_app.get("/protected")
    async def protected(
        user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> dict[str, str | None]:
        return {"user_id": str(user.id), "email": user.email}

    test_app.dependency_overrides[get_jwt_verifier] = lambda: StaticVerifier(
        claims
    )
    return TestClient(test_app)


def test_current_user_requires_bearer_token() -> None:
    client = create_protected_client(build_claims())

    response = client.get("/protected")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_current_user_returns_verified_identity() -> None:
    user_id = uuid4()
    client = create_protected_client(build_claims(sub=str(user_id)))

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user_id),
        "email": "user@example.com",
    }


def test_current_user_rejects_non_uuid_subject() -> None:
    client = create_protected_client(build_claims(sub="not-a-uuid"))

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 401


def test_authenticated_user_id_is_uuid() -> None:
    user_id = uuid4()
    client = create_protected_client(build_claims(sub=str(user_id)))

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert UUID(response.json()["user_id"]) == user_id
