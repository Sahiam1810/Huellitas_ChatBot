from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentChunker:
    max_characters: int
    overlap_characters: int

    def __post_init__(self) -> None:
        if self.max_characters < 1:
            raise ValueError("max_characters must be greater than zero")
        if self.overlap_characters < 0:
            raise ValueError("overlap_characters cannot be negative")
        if self.overlap_characters >= self.max_characters:
            raise ValueError("overlap_characters must be smaller than max_characters")

    def split(self, text: str) -> tuple[str, ...]:
        content = text.strip()
        if not content:
            raise ValueError("content cannot be blank")
        if len(content) <= self.max_characters:
            return (content,)

        chunks: list[str] = []
        start = 0
        while start < len(content):
            hard_end = min(start + self.max_characters, len(content))
            end = hard_end
            if hard_end < len(content):
                boundary = content.rfind(" ", start + 1, hard_end + 1)
                if boundary > start:
                    end = boundary

            chunk = content[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(content):
                break
            start = max(start + 1, end - self.overlap_characters)

        return tuple(chunks)
