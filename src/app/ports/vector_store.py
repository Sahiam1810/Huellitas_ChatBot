import math
from dataclasses import dataclass
from enum import StrEnum
from numbers import Real
from typing import Protocol, runtime_checkable


class VectorDistance(StrEnum):
    COSINE = "cosine"
    DOT = "dot"
    EUCLID = "euclid"


def validate_vector(vector: tuple[float, ...]) -> None:
    if not vector or any(
        isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value))
        for value in vector
    ):
        raise ValueError("vector must contain finite numeric values")


@dataclass(frozen=True, slots=True)
class VectorCollectionDefinition:
    name: str
    dimensions: int
    distance: VectorDistance

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if not normalized_name:
            raise ValueError("collection name cannot be blank")
        if self.dimensions < 1:
            raise ValueError("dimensions must be greater than zero")
        object.__setattr__(self, "name", normalized_name)


@runtime_checkable
class VectorStore(Protocol):
    async def check_health(self) -> None: ...

    async def ensure_collection(self, definition: VectorCollectionDefinition) -> None: ...

    async def close(self) -> None: ...
