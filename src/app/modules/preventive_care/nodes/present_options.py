from collections.abc import Sequence

from app.orchestration.rule_based_intent_router import normalize_for_routing


def numbered_options(items: Sequence[tuple[str, str]]) -> str:
    return "\n".join(f"{index}. {label}" for index, (_, label) in enumerate(items, start=1))


def choose_option(message: str, items: Sequence[tuple[str, str]]) -> tuple[str, str] | None:
    normalized = normalize_for_routing(message)
    if normalized.isdigit():
        index = int(normalized) - 1
        return items[index] if 0 <= index < len(items) else None
    matches = [item for item in items if normalize_for_routing(item[1]) in normalized]
    return matches[0] if len(matches) == 1 else None
