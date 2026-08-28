from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from app.orchestration.execution_context import ExecutionContext
from app.ports.token_validator import AuthenticatedPrincipal


def principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        account_id=UUID("11111111-1111-1111-1111-111111111111"),
        person_id=UUID("22222222-2222-2222-2222-222222222222"),
        role_id=UUID("33333333-3333-3333-3333-333333333333"),
        role="Cliente",
        username="cliente.demo",
        email="cliente@example.test",
        token_id=UUID("44444444-4444-4444-4444-444444444444"),
    )


def test_execution_context_is_an_immutable_run_scoped_value() -> None:
    context = ExecutionContext(
        bearer_token="header.payload.signature",
        principal=principal(),
        execution_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        correlation_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    )

    assert context.bearer_token == "header.payload.signature"
    assert context.principal.person_id == UUID("22222222-2222-2222-2222-222222222222")
    assert context.execution_id == UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert context.correlation_id == UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    with pytest.raises(FrozenInstanceError):
        context.bearer_token = "changed"  # type: ignore[misc]
