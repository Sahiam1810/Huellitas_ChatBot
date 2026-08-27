from base64 import b64decode
from binascii import Error as Base64DecodeError
from typing import Any
from uuid import UUID

import jwt
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from app.bootstrap.settings import ActiveJwtConfiguration
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.exceptions import InvalidAccessTokenError, TokenValidatorConfigurationError

REQUIRED_CLAIMS = (
    "iss",
    "aud",
    "sub",
    "person_id",
    "role_id",
    "role",
    "preferred_username",
    "email",
    "jti",
    "iat",
    "nbf",
    "exp",
)


class JwtRs256TokenValidator:
    def __init__(self, configuration: ActiveJwtConfiguration) -> None:
        try:
            encoded_key = configuration.public_key_pem_base64.get_secret_value().strip()
            public_key_bytes = b64decode(encoded_key, validate=True)
            public_key = serialization.load_pem_public_key(public_key_bytes)
            if not isinstance(public_key, RSAPublicKey) or public_key.key_size < 2048:
                raise ValueError("Unsupported JWT public key")
        except (Base64DecodeError, TypeError, UnsupportedAlgorithm, ValueError):
            raise TokenValidatorConfigurationError(
                "JWT public key configuration is invalid"
            ) from None

        self._public_key = public_key
        self._issuer = configuration.issuer
        self._audience = configuration.audience
        self._key_id = configuration.key_id
        self._clock_skew_seconds = configuration.clock_skew_seconds

    def validate(self, token: str) -> AuthenticatedPrincipal:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or header.get("kid") != self._key_id:
                raise ValueError("Unsupported JWT header")
            claims = jwt.decode(
                token,
                self._public_key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._clock_skew_seconds,
                options={"require": list(REQUIRED_CLAIMS)},
            )
            self._validate_numeric_dates(claims)
            return AuthenticatedPrincipal(
                account_id=UUID(self._required_text(claims, "sub")),
                person_id=UUID(self._required_text(claims, "person_id")),
                role_id=UUID(self._required_text(claims, "role_id")),
                role=self._required_text(claims, "role"),
                username=self._required_text(claims, "preferred_username"),
                email=self._required_text(claims, "email"),
                token_id=UUID(self._required_text(claims, "jti")),
            )
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
            raise InvalidAccessTokenError("Access token is invalid") from None

    @staticmethod
    def _required_text(claims: dict[str, Any], name: str) -> str:
        value = claims[name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Invalid {name} claim")
        return value.strip()

    @staticmethod
    def _validate_numeric_dates(claims: dict[str, Any]) -> None:
        for name in ("iat", "nbf", "exp"):
            value = claims[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Invalid {name} claim")
