import pytest

from app.orchestration.intent_router import IntentRouter, RoutingDecision, RoutingKind


class Router:
    async def route(self, command: object, manifests: tuple[object, ...]) -> RoutingDecision:
        return RoutingDecision.unknown("not matched")


def test_module_decision_requires_normalized_intent_and_module() -> None:
    decision = RoutingDecision.module(
        intent=" appointments.list ",
        module_id=" appointments ",
    )

    assert decision.kind is RoutingKind.MODULE
    assert decision.intent == "appointments.list"
    assert decision.module_id == "appointments"
    assert decision.reason is None


@pytest.mark.parametrize("field", ["intent", "module_id"])
def test_module_decision_rejects_blank_routing_data(field: str) -> None:
    values = {"intent": "appointments.list", "module_id": "appointments"}
    values[field] = " "

    with pytest.raises(ValueError, match=field):
        RoutingDecision.module(**values)


@pytest.mark.parametrize(
    ("decision", "kind"),
    [
        (RoutingDecision.unknown(" no route "), RoutingKind.UNKNOWN),
        (RoutingDecision.ambiguous(" several routes "), RoutingKind.AMBIGUOUS),
    ],
)
def test_non_module_decisions_contain_only_a_normalized_reason(
    decision: RoutingDecision,
    kind: RoutingKind,
) -> None:
    assert decision.kind is kind
    assert decision.intent is None
    assert decision.module_id is None
    assert decision.reason in {"no route", "several routes"}


def test_router_protocol_accepts_an_async_neutral_implementation() -> None:
    assert isinstance(Router(), IntentRouter)
