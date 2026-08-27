from base64 import b64encode
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ACCOUNT_ID = UUID("11111111-1111-1111-1111-111111111111")
PERSON_ID = UUID("22222222-2222-2222-2222-222222222222")
ROLE_ID = UUID("33333333-3333-3333-3333-333333333333")
KEY_ID = "chatbot-test-key"
ISSUER = "https://issuer.huellitas.test"
AUDIENCE = "huellitas-chatbot-tests"


@dataclass(frozen=True, slots=True)
class JwtTestKeyMaterial:
    private_key: rsa.RSAPrivateKey
    private_key_pem_base64: str
    public_key_pem_base64: str


def create_key_material(key_size: int = 2048) -> JwtTestKeyMaterial:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return JwtTestKeyMaterial(
        private_key=private_key,
        private_key_pem_base64=b64encode(private_pem).decode("ascii"),
        public_key_pem_base64=b64encode(public_pem).decode("ascii"),
    )


def issue_token(
    keys: JwtTestKeyMaterial,
    *,
    claims: Mapping[str, Any] | None = None,
    role: str = "Cliente",
    person_id: UUID = PERSON_ID,
    key_id: str = KEY_ID,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": str(ACCOUNT_ID),
        "person_id": str(person_id),
        "role_id": str(ROLE_ID),
        "role": role,
        "preferred_username": "cliente.demo",
        "email": "cliente@example.test",
        "jti": str(uuid4()),
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + timedelta(minutes=5),
    }
    if claims:
        payload.update(claims)
    return jwt.encode(
        payload,
        keys.private_key,
        algorithm="RS256",
        headers={"kid": key_id},
    )


TEST_JWT_KEYS = create_key_material()
