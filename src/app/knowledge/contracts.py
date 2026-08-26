from dataclasses import dataclass


def _normalize_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be blank")
    return normalized


def _normalize_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        value = _normalize_text(tag, "tag")
        if value not in seen:
            normalized.append(value)
            seen.add(value)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class CreateKnowledgeDocument:
    external_id: str
    title: str
    content: str
    source: str
    tags: tuple[str, ...]
    active: bool

    def __post_init__(self) -> None:
        for field in ("external_id", "title", "content", "source"):
            object.__setattr__(self, field, _normalize_text(getattr(self, field), field))
        object.__setattr__(self, "tags", _normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class ReplaceKnowledgeDocument:
    title: str
    content: str
    source: str
    tags: tuple[str, ...]
    active: bool

    def __post_init__(self) -> None:
        for field in ("title", "content", "source"):
            object.__setattr__(self, field, _normalize_text(getattr(self, field), field))
        object.__setattr__(self, "tags", _normalize_tags(self.tags))


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentFilters:
    limit: int = 20
    cursor: str | None = None
    active: bool | None = None
    include_deleted: bool = False
    source: str | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if self.source is not None:
            object.__setattr__(self, "source", _normalize_text(self.source, "source"))
        object.__setattr__(self, "tags", _normalize_tags(self.tags))
